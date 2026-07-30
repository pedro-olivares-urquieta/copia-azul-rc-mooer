from __future__ import annotations
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
import importlib.util, json, math, re, shutil, subprocess, hashlib
from pathlib import Path
import numpy as np, pandas as pd, soundfile as sf
from scipy import ndimage, signal

from repo_paths import (
    MODULE as OUT,
    CODE,
    DATA,
    CONFIG,
    PLOTS,
    LOGS,
    WAV_CACHE,
    AUDIO_FILES,
    audio_path,
    ensure_runtime_dirs,
)

ensure_runtime_dirs()


def main():

    # Load pipeline algorithms from this module.
    module_path = CODE / 'source_reconstruction_pipeline.py'
    spec = importlib.util.spec_from_file_location('pipe', module_path)
    pipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(pipe)

    files = list(AUDIO_FILES.keys())
    # Keep existing 192 PPO / QC artifacts in modules/rc_pedals/data; this script refreshes 384 audit outputs.

    # ---------------- Audio QC extension ----------------
    def parse_ebur128(path: Path):
        cmd=['ffmpeg','-hide_banner','-nostats','-i',str(path),'-filter_complex','ebur128=peak=true','-f','null','-']
        p=subprocess.run(cmd,capture_output=True,text=True)
        text=p.stderr
        # Last summary values.
        I=re.findall(r'\bI:\s*([-+\d.]+) LUFS',text)
        LRA=re.findall(r'\bLRA:\s*([-+\d.]+) LU',text)
        peak=re.findall(r'\bPeak:\s*([-+\d.]+) dBFS',text)
        return {
            'integrated_lufs_approx': float(I[-1]) if I else np.nan,
            'loudness_range_lu': float(LRA[-1]) if LRA else np.nan,
            'true_peak_dbfs_est': float(peak[-1]) if peak else np.nan,
        }

    def load_pcm(name):
        src=audio_path(name)
        wav=WAV_CACHE/f'{Path(name).stem}.wav'
        if not wav.exists() or wav.stat().st_mtime < src.stat().st_mtime:
            subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(src),'-acodec','pcm_f32le',str(wav)],check=True)
        x,sr=sf.read(wav,always_2d=True,dtype='float64')
        return x,sr

    base_qc=pd.read_csv(DATA/'audio_qc.csv')
    extra=[]
    for name in files:
        x2,sr=load_pcm(name); mono=x2.mean(axis=1)
        rms=np.sqrt(np.mean(mono**2)+1e-30); peak=np.max(np.abs(mono))+1e-30
        # Approximate 4x true peak with polyphase resampling as independent check.
        up=signal.resample_poly(mono,4,1,window=('kaiser',8.6))
        tp=20*np.log10(np.max(np.abs(up))+1e-30)
        dc=float(np.mean(mono)); crest=20*np.log10(peak/rms)
        lr_diff=float(20*np.log10(np.sqrt(np.mean((x2[:,0]-x2[:,-1])**2)+1e-30)+1e-30)) if x2.shape[1]>1 else -np.inf
        eb=parse_ebur128(audio_path(name))
        extra.append({'file':name,'dc_offset':dc,'crest_factor_db':crest,'true_peak_4x_dbfs':tp,
                      'lr_difference_rms_dbfs':lr_diff,**eb})
    extra_df=pd.DataFrame(extra)
    qc=base_qc.merge(extra_df,on='file',how='left')
    qc['digital_clipping']=qc['true_peak_4x_dbfs']>=-0.1
    qc['channels_effectively_duplicate']=qc['stereo_correlation']>=0.9999
    qc.to_csv(DATA/'audio_qc_extended.csv',index=False)

    # ---------------- 384 PPO audit ----------------
    ppo=384
    freq384=20*2**(np.arange(int(np.log2(18000/20)*ppo)+1)/ppo)
    freq384=freq384[freq384<=18000]
    rng=np.random.default_rng(20260730)

    # Load mono arrays.
    audio={}
    for name in files:
        x2,sr=load_pcm(name); audio[name]=x2.mean(axis=1)

    # Pink 384: same DPSS estimator, robust uncertainty from block MAD (audit, not replacement central CI).
    pink_blocks={}; pink_windows=[]
    for name in ['Pink.m4a','Pink rc bass on.m4a','Pink rc hybrid on.m4a','Pink rc guitar on.m4a']:
        st,en,thr=pipe.stable_active_interval(audio[name],sr)
        blocks,starts=pipe.multitaper_blocks(audio[name],sr,st,en,freq384,ppo)
        pink_blocks[name]=blocks
        pink_windows.append({'file':name,'start_s':st,'end_s':en,'blocks':len(blocks),'threshold_dbfs':thr})
    pd.DataFrame(pink_windows).to_csv(DATA/'pink_windows_384.csv',index=False)

    # Sweep mapping already measured fresh. Refit from audio for 384 audit.
    sweep_files=['1 22k.m4a','1 22k rc bass on.m4a','1 22k rc hybrid on.m4a','1 22k rc guitar on.m4a']
    runs={}
    run_rows=[]
    for name in sweep_files:
        c1,c2,rr=pipe.fit_sweep_runs(audio[name],sr); runs[name]=rr
        for r in rr: run_rows.append({'file':name,'gap1_s':c1,'gap2_s':c2,**r})
    pd.DataFrame(run_rows).to_csv(DATA/'sweep_mapping_384_audit.csv',index=False)

    # Cache reference amplitudes at 384.
    ref_amp=[]; ref_snr=[]
    for rr in runs['1 22k.m4a']:
        a,s=pipe.chirp_amplitude_curve(audio['1 22k.m4a'],sr,rr,freq384)
        ref_amp.append(a); ref_snr.append(s)
    ref_amp=np.asarray(ref_amp); ref_snr=np.asarray(ref_snr)

    setup_files={
     'bass':('Pink rc bass on.m4a','1 22k rc bass on.m4a'),
     'hybrid':('Pink rc hybrid on.m4a','1 22k rc hybrid on.m4a'),
     'guitar':('Pink rc guitar on.m4a','1 22k rc guitar on.m4a')}
    curves384=pd.DataFrame({'frequency_hz':freq384})
    validation384=[]
    run384=[]
    for setup,(pink_name,sweep_name) in setup_files.items():
        # Pink median and robust block dispersion.
        pb=pink_blocks[pink_name]; rb=pink_blocks['Pink.m4a']
        pink=np.median(pb,axis=0)-np.median(rb,axis=0)
        # Bootstrap 64 enough for grid-convergence audit.
        boots=[]
        for _ in range(64):
            oi=rng.integers(0,len(pb),len(pb)); ri=rng.integers(0,len(rb),len(rb))
            boots.append(np.median(pb[oi],axis=0)-np.median(rb[ri],axis=0))
        boots=np.asarray(boots); pink_unc=np.maximum(0.05,(np.percentile(boots,84,axis=0)-np.percentile(boots,16,axis=0))/2)

        out_amp=[]; out_snr=[]
        for rr in runs[sweep_name]:
            a,s=pipe.chirp_amplitude_curve(audio[sweep_name],sr,rr,freq384)
            out_amp.append(a); out_snr.append(s)
        out_amp=np.asarray(out_amp); out_snr=np.asarray(out_snr)
        raw=20*np.log10((out_amp+1e-30)/(ref_amp+1e-30))
        snr=np.minimum(out_snr,ref_snr)
        raw=pipe.smooth_octave(raw,ppo,1/24)
        prelim=np.nanmedian(np.where(snr>=8,raw,np.nan),axis=0)
        norm=[]; offsets=[]
        for row,srow in zip(raw,snr):
            v=(freq384>=30)&(freq384<=14000)&(srow>=15)&np.isfinite(prelim)
            off=float(np.nanmedian(row[v]-prelim[v])); offsets.append(off); norm.append(row-off)
        norm=np.asarray(norm); masked=np.where(snr>=8,norm,np.nan)
        sweep=np.nanmedian(masked,axis=0)
        sweep_unc=np.maximum(0.04,1.4826*np.nanmedian(np.abs(masked-sweep),axis=0))
        med_snr=np.nanmedian(snr,axis=0)
        fused=pipe.fuse_methods(freq384,pink,pink_unc,sweep,sweep_unc,med_snr,ppo)
        curves384[f'{setup}_pink_db']=pink
        curves384[f'{setup}_sweep_aligned_db']=fused['sweep_aligned_db']
        curves384[f'{setup}_recommended_analog_db']=fused['recommended_analog_db']
        curves384[f'{setup}_uncertainty_db']=fused['uncertainty_db']
        common=(freq384>=30)&(freq384<=14000)&np.isfinite(fused['sweep_aligned_db'])
        d=pink[common]-fused['sweep_aligned_db'][common]
        validation384.append({'setup':setup,'alignment_db':fused['alignment_offset_db'],
            'median_abs_method_difference_db':float(np.nanmedian(np.abs(d))),
            'p95_abs_method_difference_db':float(np.nanpercentile(np.abs(d),95)),
            'run_offsets_db':json.dumps([round(x,5) for x in offsets])})
        for i,row in enumerate(norm):
            for f,v,s in zip(freq384,row,snr[i]):
                run384.append({'setup':setup,'run':i+1,'frequency_hz':f,'normalized_transfer_db':v,'snr_db':s})
    curves384.to_csv(DATA/'refined_curves_384ppo_audit.csv',index=False)
    pd.DataFrame(validation384).to_csv(DATA/'method_validation_384.csv',index=False)
    pd.DataFrame(run384).to_csv(DATA/'sweep_runs_384_long.csv',index=False)

    # 192/384 convergence: downsample 384 to 192 grid and compare central curves.
    c192=pd.read_csv(DATA/'refined_curves_192ppo.csv'); f192=c192.frequency_hz.to_numpy()
    conv=[]
    for setup in setup_files:
        v384=np.interp(np.log(f192),np.log(freq384),curves384[f'{setup}_recommended_analog_db'])
        v192=c192[f'{setup}_recommended_analog_db'].to_numpy(); d=v384-v192
        for lo,hi,label in [(20,15500,'20-15500 high/medium confidence'),(15500,18000,'15500-18000 low confidence'),(20,18000,'20-18000 total')]:
            m=(f192>=lo)&(f192<=hi)
            conv.append({'setup':setup,'range':label,'rmse_difference_db':float(np.sqrt(np.mean(d[m]**2))),
                         'median_difference_db':float(np.median(d[m])),'p95_abs_difference_db':float(np.percentile(np.abs(d[m]),95)),
                         'max_abs_difference_db':float(np.max(np.abs(d[m])))})
    pd.DataFrame(conv).to_csv(DATA/'grid_convergence_192_vs_384.csv',index=False)

    # ---------------- Harmonic excess proxy / non-linearity audit ----------------
    # Demodulate fundamental and harmonics at selected frequencies for each sweep run.
    selected=np.array([100.,250.,500.,1000.,2000.,4000.,7000.])
    def local_tone_amp(x,sr,run,f0,harm=1):
        a,b=run['a'],run['b']; t0=(np.log(f0)-a)/b
        half=max(3.0/f0,0.04); half=min(half,0.18)
        i0=max(0,int((t0-half)*sr)); i1=min(len(x),int((t0+half)*sr))
        if i1-i0<64: return np.nan
        tt=np.arange(i0,i1)/sr; inst=np.exp(a+b*tt); phase=2*np.pi/b*(inst-f0)*harm
        y=x[i0:i1]; w=np.hanning(len(y)); c=np.cos(phase); s=np.sin(phase)
        X=np.column_stack([c,s,np.ones_like(c)])
        sw=np.sqrt(w)[:,None]; coef=np.linalg.lstsq(X*sw,y*np.sqrt(w),rcond=None)[0]
        return float(np.hypot(coef[0],coef[1]))

    harm_rows=[]
    for setup,(_,sweep_name) in setup_files.items():
        for run_i,(rr,oo) in enumerate(zip(runs['1 22k.m4a'],runs[sweep_name]),1):
            for f0 in selected:
                vals={}
                for h in [1,2,3]:
                    if f0*h>18000: vals[f'ref_h{h}']=np.nan; vals[f'on_h{h}']=np.nan; continue
                    vals[f'ref_h{h}']=local_tone_amp(audio['1 22k.m4a'],sr,rr,f0,h)
                    vals[f'on_h{h}']=local_tone_amp(audio[sweep_name],sr,oo,f0,h)
                ref_ratio=np.sqrt((vals['ref_h2'] or 0)**2+(vals['ref_h3'] or 0)**2)/(vals['ref_h1']+1e-30)
                on_ratio=np.sqrt((vals['on_h2'] or 0)**2+(vals['on_h3'] or 0)**2)/(vals['on_h1']+1e-30)
                harm_rows.append({'setup':setup,'run':run_i,'fundamental_hz':f0,
                    'reference_harmonic_ratio_db':20*np.log10(ref_ratio+1e-30),
                    'pedal_on_harmonic_ratio_db':20*np.log10(on_ratio+1e-30),
                    'harmonic_excess_on_minus_off_db':20*np.log10((on_ratio+1e-30)/(ref_ratio+1e-30))})
    harm=pd.DataFrame(harm_rows); harm.to_csv(DATA/'nonlinearity_harmonic_proxy.csv',index=False)

    # Summary nonlinearity by setup.
    ns=harm.groupby('setup').agg(
     median_harmonic_excess_db=('harmonic_excess_on_minus_off_db','median'),
     p95_harmonic_excess_db=('harmonic_excess_on_minus_off_db',lambda x: np.percentile(x,95)),
     max_harmonic_excess_db=('harmonic_excess_on_minus_off_db','max')).reset_index()
    ns.to_csv(DATA/'nonlinearity_summary.csv',index=False)

    # Central config.
    config={
     'analysis_seed':20260730,'sample_rate_hz':int(sr),'grid_192_ppo':192,'grid_384_ppo':384,
     'main_high_confidence_limit_hz':15500,'optimization_limit_hz':18000,
     'mooer':{'frequencies_hz':[30,148,735,3637,18000],'q_display':0.3,'global_gain_db':3.0,
              'gain_range_db':[-16,16],'gain_step_db':0.5,
              'gain_effective_coefficient':0.75,'q_base_coefficient':0.569,'q_gain_slope':-0.0026},
     'calibration_uncertainty_scenario_not_measured':{'gain_coefficient_sd':0.015,'q_base_sd':0.010,'q_gain_slope_sd':0.0003,'center_frequency_relative_sd':0.003}
    }
    (CONFIG/'config.json').write_text(json.dumps(config,indent=2,ensure_ascii=False),encoding='utf-8')
    print('DONE',OUT)
    print(pd.DataFrame(conv).to_string(index=False))


if __name__ == "__main__":
    main()
