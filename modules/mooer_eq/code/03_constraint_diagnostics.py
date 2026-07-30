import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from pathlib import Path
import json, math
import numpy as np, pandas as pd
from scipy.optimize import minimize
from repo_paths import MODULE as ROOT, DATA as D, curves_csv, ensure_runtime_dirs
ensure_runtime_dirs()


def main():
    curves=pd.read_csv(curves_csv());freq=curves.frequency_hz.to_numpy();sel=pd.read_csv(D/'final_preset_selection_metrics.csv');pres=pd.read_csv(D/'final_presets.csv')
    SETUPS={'Bajo':'bass','Híbrido':'hybrid','Guitarra':'guitar'};F=np.array([30.,148.,735.,3637.,18000.]);QFIX=.3;GLOBAL=3.
    REG=[('Subgraves',20,60),('Graves',60,250),('Medios',250,2000),('Presencia',2000,8000),('Brillo',8000,15500)]
    FREE={
    'Bajo':[(32,16,.4),(296,5,.5),(1151,-.5,5),(1166,2,1.7),(4258,12.5,.6)],
    'Híbrido':[(43,.5,4),(289,-1,.3),(733,10.5,.3),(3705,4.5,1.1),(9002,6,1)],
    'Guitarra':[(30,-6.5,.4),(437,.5,5),(823,10,.4),(1129,-.5,1.6),(5921,9,.7)]}
    VARQ={
    'Bajo':[(30,15,.3),(148,3,.3),(735,-.5,2.1),(3637,12.5,.4),(18000,-1.5,2.1)],
    'Híbrido':[(30,-2.5,.4),(148,4.5,.3),(735,5.5,.5),(3637,9.5,.8),(18000,4,.4)],
    'Guitarra':[(30,-10.5,.3),(148,6,.3),(735,5,.6),(3637,9.5,.7),(18000,3.5,.3)]}

    def bell(f,fc,g,qdisp,gc=.75,q0=.569,qs=-.0026):
     A=10**(gc*g/40);q=qdisp*(q0+qs*g);r=f/fc
     return 10*np.log10(((1-r*r)**2+(A*r/q)**2)/((1-r*r)**2+(r/(A*q))**2))
    def response(bands,global_gain=3):
     y=np.full_like(freq,global_gain)
     for fc,g,q in bands:y+=bell(freq,fc,g,q)
     return y
    def metrics(y,t,u):
     e=y-t;rs=[]
     for name,lo,hi in REG:
      m=(freq>=lo)&(freq<(hi if hi<15500 else hi+1));w=1/(u[m]**2+.12**2);w/=w.sum();rs.append(np.sqrt(np.sum(w*e[m]**2)))
     w=1/(u**2+.12**2);w*=np.where(freq<=15500,1,np.clip((18000-freq)/2500,.05,1));w/=w.sum()
     return {'worst':max(rs),'avg':np.mean(rs),'global':np.sqrt(np.sum(w*e**2)),'p95':np.percentile(abs(e),95),'regions':rs}
    def obj(y,t,u):
     m=metrics(y,t,u);return m['worst']+.35*m['avg']+.1*m['global']+.025*m['p95']
    rows=[];global_rows=[];unc_rows=[]
    for name,key in SETUPS.items():
     t=curves[f'{key}_recommended_analog_db'].to_numpy();u=curves[f'{key}_uncertainty_db'].to_numpy()
     p=pres[(pres.setup==name)&(pres.variant=='balanced')].sort_values('band');g=p.gain_display_db.to_numpy();bands=[(fc,x,.3) for fc,x in zip(F,g)];base=response(bands);bm=metrics(base,t,u)
     # Continuous gains fixed Q/frequencies.
     def fg(x):return obj(response([(fc,v,.3) for fc,v in zip(F,x)]),t,u)
     r=minimize(fg,g,method='Powell',bounds=[(-16,16)]*5,options={'maxiter':500,'xtol':1e-5,'ftol':1e-8});cm=metrics(response([(fc,v,.3) for fc,v in zip(F,r.x)]),t,u)
     # Variable Q continuous at fixed freqs.
     start=[]
     for fc,gg,qq in VARQ[name]:start += [gg,qq]
     def fq(x):return obj(response([(F[i],x[2*i],x[2*i+1]) for i in range(5)]),t,u)
     bounds=[]
     for i in range(5):bounds += [(-16,16),(.3,5)]
     rv=minimize(fq,start,method='Powell',bounds=bounds,options={'maxiter':800,'xtol':1e-4,'ftol':1e-7});vm=metrics(response([(F[i],rv.x[2*i],rv.x[2*i+1]) for i in range(5)]),t,u)
     # Historical free frequency/Q diagnostic, re-evaluated on new target.
     fm=metrics(response(FREE[name]),t,u)
     for label,m in [('principal_fixed_quantized',bm),('fixed_continuous_gain',cm),('fixed_frequency_variable_q_continuous',vm),('free_frequency_q_historical',fm)]:
      rows.append({'setup':name,'architecture':label,'worst_region_rmse':m['worst'],'mean_region_rmse':m['avg'],'global_rmse':m['global'],'p95':m['p95'],'region_rmse_json':json.dumps([round(x,6) for x in m['regions']])})
     # global free step diagnostic with reoptimized continuous gains for each likely global neighborhood (-3 to +3 sufficient after band redistribution, full range scanned offset-only)
     best=None
     for glob in np.arange(-60,3.001,.5):
      m=metrics(response(bands,glob),t,u)
      score=m['worst']+.35*m['avg']+.1*m['global']
      if best is None or score<best[0]:best=(score,glob,m)
     global_rows.append({'setup':name,'principal_global_db':3,'best_offset_only_global_db':best[1],'principal_worst':bm['worst'],'diagnostic_worst':best[2]['worst'],'principal_global_rmse':bm['global'],'diagnostic_global_rmse':best[2]['global']})
     # uncertainty region medians
     for regname,lo,hi in REG:
      m=(freq>=lo)&(freq<(hi if hi<15500 else hi+1));unc_rows.append({'setup':name,'region':regname,'median_target_uncertainty_db':np.median(u[m]),'p95_target_uncertainty_db':np.percentile(u[m],95)})
    pd.DataFrame(rows).to_csv(D/'constraint_decomposition.csv',index=False)
    pd.DataFrame(global_rows).to_csv(D/'global_gain_free_diagnostic.csv',index=False)
    pd.DataFrame(unc_rows).to_csv(D/'target_uncertainty_by_region.csv',index=False)
    # Fix nonlinear summary robustly.
    h=pd.read_csv(D/'nonlinearity_harmonic_proxy.csv');nr=[]
    for setup,x in h.groupby('setup'):
     v=x.harmonic_excess_on_minus_off_db.to_numpy();v=v[np.isfinite(v)];nr.append({'setup':setup,'finite_observations':len(v),'median_harmonic_excess_db':np.median(v),'p95_harmonic_excess_db':np.percentile(v,95),'max_harmonic_excess_db':np.max(v),'interpretation':'exploratory proxy; not a calibrated THD measurement'})
    pd.DataFrame(nr).to_csv(D/'nonlinearity_summary.csv',index=False)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
