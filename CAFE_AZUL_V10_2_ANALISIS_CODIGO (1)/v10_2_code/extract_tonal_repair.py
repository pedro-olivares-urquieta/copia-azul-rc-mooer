from pathlib import Path
import sys, numpy as np, pandas as pd
from scipy import signal
ROOT=Path('/mnt/data/reanalysis_cafe_azul');OUT=ROOT/'v10_2_results';sys.path.insert(0,str(ROOT/'v10_2_code'))
import build_v10_2 as m

def noise_psd(y):
    chunks=[y[:int(min(1.25,len(y)/m.SR*.12)*m.SR)],y[int(max(0,len(y)-m.SR)):]]
    z=np.concatenate([x for x in chunks if len(x)>256]);f,P=signal.welch(z-np.mean(z),m.SR,window='hann',nperseg=min(8192,len(z)),noverlap=min(4096,len(z)//2),scaling='density');return f,P

def line_fft(seg,target):
    if len(seg)<128:return np.nan,np.nan,np.nan
    x=seg-np.mean(seg);w=signal.windows.hann(len(x),sym=False);nfft=min(65536,1<<int(np.ceil(np.log2(max(2048,len(x)*8)))))
    X=np.fft.rfft(x*w,nfft);ff=np.fft.rfftfreq(nfft,1/m.SR);tol=max(2.0,target*.005);mask=(ff>=target-tol)&(ff<=target+tol)
    if not mask.any():return np.nan,np.nan,np.nan
    ids=np.where(mask)[0];i=ids[np.argmax(np.abs(X[mask]))];amp=2*np.abs(X[i])/(w.sum()+1e-30);return float(ff[i]),float(amp),1.5/(len(x)/m.SR)

match=pd.read_csv(OUT/'MATCHING_EVENTOS_V10_2.csv')
phase_bounds={.6:m.phase_bounds(.6),.3:m.phase_bounds(.3)}
rows=[]
for key,z in match.groupby('pair'):
    p=m.PAIRS[key];yc,_=m.load(p['cafe']);ya,_=m.load(p['azul']);period=.3 if p['kind']=='chromatic' else .6
    fnc,pnc=noise_psd(yc);fna,pna=noise_psd(ya)
    for ei,r in z.reset_index(drop=True).iterrows():
        fc,fa=r.f0_cafe,r.f0_azul
        if not np.isfinite(fc) or not np.isfinite(fa):continue
        fg=float(np.sqrt(fc*fa));nextc=z.iloc[ei+1].time_cafe if ei+1<len(z) else None;nexta=z.iloc[ei+1].time_azul if ei+1<len(z) else None
        for ph,(a,b) in phase_bounds[period].items():
            sc=m.extract_seg(yc,r.time_cafe,a,b,nextc);sa=m.extract_seg(ya,r.time_azul,a,b,nexta)
            fpc,ac0,enbw_c=line_fft(sc,fc);fpa,aa0,enbw_a=line_fft(sa,fa)
            if not np.isfinite(ac0) or ac0<=0 or aa0<=0:continue
            maxk=min(64,int(16000/max(fg,1)))
            if m.fam(key)=='open':maxk=min(maxk,int(300/max(fg,1)))
            for k in range(2,maxk+1):
                tc,ta=k*fc,k*fa;fm_c,ac,en_c=line_fft(sc,tc);fm_a,aa,en_a=line_fft(sa,ta)
                if not np.isfinite(ac) or ac<=0 or aa<=0:continue
                nc=np.sqrt(2*np.interp(fm_c,fnc,pnc)*en_c+1e-30);na=np.sqrt(2*np.interp(fm_a,fna,pna)*en_a+1e-30)
                snc=m.db(ac)-m.db(nc);sna=m.db(aa)-m.db(na)
                if min(snc,sna)<10:continue
                yy=(m.db(aa)-m.db(aa0))-(m.db(ac)-m.db(ac0));rel_common=min(m.db(ac/ac0),m.db(aa/aa0));energy=np.clip(10**(rel_common/20),.025,1)
                rows.append(dict(pair=key,family=m.fam(key),string=m.string_of(key),register=m.register_of(fg),event=ei,phase=ph,f=float(np.sqrt(fm_c*fm_a)),f0=fg,y=float(yy),snr=float(min(snc,sna)),match_cost=float(r.match_cost),kind='tonal_harmonic',weight_base=m.PHASE_W[ph]*energy,harmonic=k,frequency_cafe=fm_c,frequency_azul=fm_a))
    print(key,len(rows),flush=True)
pd.DataFrame(rows).to_csv(OUT/'TONAL_HARMONICS_CORRECTED_V10_2.csv',index=False)
print('done',len(rows))
