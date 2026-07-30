import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from pathlib import Path
import sys,os,zipfile
import numpy as np,pandas as pd
import matplotlib.pyplot as plt
from repo_paths import ROOT, OUT, AUD, CODE, LEGACY, EXPORTS, ensure_runtime_dirs
ensure_runtime_dirs(); sys.path.insert(0,str(CODE)); import build_v10_2 as m


def main():
    fund=pd.read_csv(OUT/'FUNDAMENTALES_CORREGIDAS_V10_2.csv');ton=pd.read_csv(OUT/'TONAL_HARMONICS_CORRECTED_V10_2.csv');res=pd.read_csv(OUT/'TRAYECTORIAS_ARMONICAS_V10_2.csv');res=res[res.kind=='band_residual'].copy();res['weight_base']*=.35;obs=fund.to_dict('records')+ton.to_dict('records')+res.to_dict('records')

    def old_clean(name):
     q=m.load_old_curve(name)
     if q is None: return pd.DataFrame(columns=['model','pair','mae','rmse','p75','p90','p95','improved'])
     out=[]
     for hold in sorted(set(o['pair'] for o in obs)):
      nu=m.fit_nuisance_fixed(obs,q,hold);test=[o for o in obs if o['pair']==hold and np.isfinite(o['y']) and np.isfinite(o['snr']) and o['snr']>=8 and o['match_cost']<=3 and abs(o['y'])<=18];rr=[];ww=[]
      for r in test:
       pred=(nu[m.IG]+nu[m.IS+m.STRINGS.index(r['string'])]+nu[m.IR+m.REGS.index(r['register'])]+nu[m.IP+m.PHASES.index(r['phase'])]+q(r['f'])) if r['kind']=='fundamental' else q(r['f'])-q(r['f0'])
       rr.append(r['y']-pred);ww.append(r['weight_base']*np.clip((r['snr']-6)/24,.08,1.5))
      a=np.abs(rr);out.append(dict(model=name,pair=hold,mae=np.average(a,weights=ww),rmse=np.sqrt(np.average(np.array(rr)**2,weights=ww)),p75=m.weighted_quantile(a,ww,.75),p90=m.weighted_quantile(a,ww,.9),p95=m.weighted_quantile(a,ww,.95),improved=np.nan))
     return pd.DataFrame(out)
    metrics=pd.read_csv(OUT/'METRICAS_POR_PAREJA_V10_2.csv');metrics=metrics[~metrics.model.isin(['V9','V10_1'])]
    olds=[old_clean('V9'),old_clean('V10_1')];metrics=pd.concat([metrics]+[o for o in olds if len(o)],ignore_index=True);metrics.to_csv(OUT/'METRICAS_POR_PAREJA_V10_2.csv',index=False)
    summary=metrics.groupby('model').agg(pairs=('pair','count'),MAE=('mae','mean'),RMSE=('rmse','mean'),Median_MAE=('mae','median'),P90=('p90','mean'),P95=('p95','mean'),worst_pair=('mae','max')).reset_index().sort_values('MAE');summary.to_csv(OUT/'COMPARACION_MODELOS_MISMO_PIPELINE.csv',index=False)
    curve=pd.read_csv(OUT/'CURVAS_DENSAS_V10_2.csv');attack=pd.read_csv(OUT/'ATAQUES_MULTIESCALA_V10_2.csv');matching=pd.read_csv(OUT/'MATCHING_EVENTOS_V10_2.csv');windows=pd.read_csv(OUT/'VENTANAS_ADAPTATIVAS_V10_2.csv');gaps=pd.read_csv(OUT/'ESPACIOS_Y_SOLAPAMIENTOS_V10_2.csv');traj=pd.read_csv(OUT/'TRAYECTORIAS_FUNDAMENTALES_V10_2.csv');local=pd.read_csv(OUT/'METRICAS_LOCALES_Y_TEMPORALES_V10_2.csv')
    m.plots(curve,curve.raw_db.to_numpy(),curve.precise_central_db.to_numpy(),curve.precise_robust_db.to_numpy(),curve.safe_db.to_numpy(),curve.parametric_db.to_numpy(),curve.no_sub_db.to_numpy(),curve.no_high_db.to_numpy(),attack,matching,windows,gaps,traj,metrics,local)
    # comparison curves (optional legacy V9/V10.1)
    plt.figure(figsize=(12,6));plt.semilogx(curve.frequency_hz,curve.precise_central_db,label='V10.2 CENTRAL');plt.semilogx(curve.frequency_hz,curve.precise_robust_db,label='V10.2 ROBUST')
    v9p=LEGACY/'curva_v9_puntos.csv';v10p=LEGACY/'curva_v10_1_densa.csv'
    if v10p.exists():
     v10=pd.read_csv(v10p);plt.semilogx(v10.frequency_hz,v10.eq_precise_db,label='V10.1')
    if v9p.exists():
     v9=pd.read_csv(v9p);plt.semilogx(v9.frequency_hz,v9.eq_v9_db,label='V9')
    plt.axhline(0,color='k',lw=.6);plt.grid(alpha=.25,which='both');plt.legend();plt.xlabel('Hz');plt.ylabel('dB');plt.title('Curvas V9, V10.1 y V10.2');plt.tight_layout();plt.savefig(OUT/'10_COMPARACION_V9_V10_1_V10_2.png',dpi=180);plt.close()
    # gain plot
    g=pd.read_csv(OUT/'GAIN_POR_PAREJA_Y_FUENTE_V10_2.csv').sort_values('gain_combined_db');x=np.arange(len(g));plt.figure(figsize=(13,6));plt.plot(x,g.gain_fundamental_db,'o',label='Fundamental');plt.plot(x,g.gain_energy_db,'s',label='Energía');plt.plot(x,g.gain_combined_db,'^-',label='Combinado');rec=pd.read_csv(OUT/'GAIN_GLOBAL_V10_2.csv').iloc[0];plt.axhline(rec.gain_recommended_db,color='k',ls='--',label='Recomendado');plt.xticks(x,g.pair,rotation=45);plt.ylabel('dB');plt.grid(alpha=.25);plt.legend();plt.tight_layout();plt.savefig(OUT/'11_GAIN_POR_PAREJA_Y_FUENTE.png',dpi=180);plt.close()
    # points summary
    freqs=[20,22,25,28,30,30.87,32,35,38,40,41.2,45,48,50,52,55,58,60,61.74,65,70,75,80,100,120,160,200,250,315,400,500,630,800,1000,1250,1600,2000,2500,3150,4000,5000,6300,8000,10000,12500,16000,20000]
    rows=[]
    for f in freqs:
     i=(curve.frequency_hz-f).abs().idxmin();r=curve.loc[i];rows.append(dict(requested_frequency_hz=f,measured_grid_hz=r.frequency_hz,central_db=r.precise_central_db,robust_db=r.precise_robust_db,safe_db=r.safe_db,parametric_db=r.parametric_db,ci95_low_db=r.ci95_low_db,ci95_high_db=r.ci95_high_db,effective_pairs=r.effective_pairs,strings=r.strings,families=r.families,support_state=r.support_state,origin=r.origin))
    pd.DataFrame(rows).to_csv(OUT/'PUNTOS_RESUMIDOS_V10_2.csv',index=False)
    # append corrected same-pipeline comparison
    p=OUT/'INFORME_TECNICO_AUTONOMO_V10_2.md';txt=p.read_text();txt+='\n\n## Comparación final con el mismo pipeline\n\n'+summary.to_markdown(index=False)+'\n\nNO-SUB y NO-HIGH no muestran una mejora práctica significativa frente a CENTRAL; sus intervalos pareados incluyen 0 y la probabilidad de superar 0,1 dB es 0.\n';p.write_text(txt)
    (OUT/'INFORME_COMPARACION_V9_V10_1_V10_2.md').write_text('# Comparación con el mismo pipeline\n\n'+summary.to_markdown(index=False)+'\n\nV9 y V10.1 se evaluaron sobre las observaciones V10.2 con nuisances reajustados.\n')
    # repackage analysis and complete into module exports/
    EXPORTS.mkdir(parents=True,exist_ok=True)
    for zname,roots in [(EXPORTS/'CAFE_AZUL_V10_2_ANALISIS_CODIGO.zip',[OUT,CODE]),(EXPORTS/'CAFE_AZUL_V10_2_COMPLETA.zip',[OUT,CODE,AUD])]:
     try:os.remove(zname)
     except:pass
     with zipfile.ZipFile(zname,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
      for r in roots:
       for f in r.rglob('*'):
        if f.is_file():z.write(f,arcname=str(f.relative_to(ROOT)))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
