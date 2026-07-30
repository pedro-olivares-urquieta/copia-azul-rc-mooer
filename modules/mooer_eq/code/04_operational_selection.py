import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from pathlib import Path
import json,math,numpy as np,pandas as pd
from scipy import ndimage
import matplotlib.pyplot as plt
from repo_paths import MODULE as ROOT, DATA as D, PLOTS as P, curves_csv, ensure_runtime_dirs
ensure_runtime_dirs()
c=pd.read_csv(curves_csv());freq=c.frequency_hz.to_numpy();N=len(freq)
F=np.array([30.,148.,735.,3637.,18000.]);Q=.3;REG=[('Subgraves',20,60),('Graves',60,250),('Medios',250,2000),('Presencia',2000,8000),('Brillo',8000,15500)];KEY={'Bajo':'bass','Híbrido':'hybrid','Guitarra':'guitar'}
OLD={'Bajo':np.array([15.,3.5,-3.5,16.,-3.5]),'Híbrido':np.array([-1.5,3.,4.,8.5,1.5]),'Guitarra':np.array([-10.,4.5,3.,9.5,1.])}
MINIMAX={'Bajo':np.array([16.,2.,-2.5,16.,-4.]),'Híbrido':np.array([-2.,3.5,2.5,10.5,0.]),'Guitarra':np.array([-10.,5.5,.5,13.,-2.])}
SUB={'Bajo':np.array([15.5,2.,-.5,13.,-1.5]),'Híbrido':np.array([-2.,3.5,2.,10.5,0.]),'Guitarra':np.array([-10.,5.,.5,12.5,-1.5])}
GLOBAL={'Bajo':OLD['Bajo'],'Híbrido':np.array([-.5,.5,8.,3.5,5.5]),'Guitarra':np.array([-9.,3.,5.,7.5,2.5])}
OP={'Bajo':OLD['Bajo'],'Híbrido':OLD['Híbrido'],'Guitarra':np.array([-10.5,5.5,2.,10.5,0.])}
REASON={'Bajo':'Se conserva el anterior: el minimax empeora Graves y Medios por encima de la incertidumbre de medición.','Híbrido':'Se conserva el anterior: el minimax mejora subgrave/peor zona, pero degrada Graves y Medios más que la incertidumbre.','Guitarra':'Nuevo preset aceptado: reduce peor RMSE y promedio regional sin degradaciones superiores a la incertidumbre regional.'}
def bell(f,fc,g,gc=.75,q0=.569,qs=-.0026):
 A=10**(gc*g/40);q=Q*(q0+qs*g);r=f/fc
 return 10*np.log10(((1-r*r)**2+(A*r/q)**2)/((1-r*r)**2+(r/(A*q))**2))
def resp(g,gc=.75,q0=.569,qs=-.0026,sh=None):
 y=np.full_like(freq,3.);sh=np.zeros(5) if sh is None else sh
 for fc,x,d in zip(F,g,sh):y+=bell(freq,fc*(1+d),x,gc,q0,qs)
 return y
def metrics(y,t,u):
 e=y-t;regs={};rs=[]
 for name,lo,hi in REG:
  m=(freq>=lo)&(freq<(hi if hi<15500 else hi+1));w=1/(u[m]**2+.12**2);w/=w.sum();v=e[m];x=np.log2(freq[m]);xc=x-np.sum(w*x);z={'rmse':np.sqrt(np.sum(w*v*v)),'mae':np.sum(w*abs(v)),'bias':np.sum(w*v),'p95':np.percentile(abs(v),95),'max':np.max(abs(v)),'slope_error':np.sum(w*xc*v)/(np.sum(w*xc*xc)+1e-30),'correlation':np.corrcoef(t[m]-t[m].mean(),y[m]-y[m].mean())[0,1]};regs[name]=z;rs.append(z['rmse'])
 w=1/(u**2+.12**2);w*=np.where(freq<=15500,1,np.clip((18000-freq)/2500,.05,1));w/=w.sum();ae=abs(e);i30=np.argmin(abs(freq-30));m25=(freq>=25)&(freq<=40);m60=(freq>=20)&(freq<=60)
 return {'regions':regs,'worst':max(rs),'avg':np.mean(rs),'global':np.sqrt(np.sum(w*e*e)),'uniform':np.sqrt(np.mean(e*e)),'mae':np.mean(ae),'p50':np.percentile(ae,50),'p90':np.percentile(ae,90),'p95':np.percentile(ae,95),'max_reliable':np.max(ae[freq<=15500]),'max_total':np.max(ae),'bias':np.mean(e),'slope_mean':np.mean([abs(z['slope_error']) for z in regs.values()]),'e30':e[i30],'ae30':ae[i30],'r2540':np.sqrt(np.mean(e[m25]**2)),'r2060':np.sqrt(np.mean(e[m60]**2)),'r8k':np.sqrt(np.mean(e[freq<=8000]**2)),'r15500':np.sqrt(np.mean(e[freq<=15500]**2))}
def target_sample(key,t,u,rng):
 p=c[f'{key}_pink_db'].to_numpy();s=c[f'{key}_sweep_aligned_db'].to_numpy();pr=c[f'{key}_precise_1_24oct_db'].to_numpy();me=c[f'{key}_measured_1_12oct_db'].to_numpy();z=ndimage.gaussian_filter1d(rng.normal(size=N),10);z/=z.std()+1e-30;q=t+rng.normal(0,.2)*(p-t)+rng.normal(0,.2)*(s-t)+rng.uniform(-.3,.3)*(pr-me)+.4*u*z;return np.where(freq<=15500,q,t+.35*(q-t))
def mc_eval(name,key,g):
 rng=np.random.default_rng(10100+list(KEY).index(name));t=c[f'{key}_recommended_analog_db'].to_numpy();u=c[f'{key}_uncertainty_db'].to_numpy();V=[]
 for _ in range(128):
  ts=target_sample(key,t,u,rng);y=resp(g,rng.normal(.75,.015),rng.normal(.569,.01),rng.normal(-.0026,.0003),rng.normal(0,.003,5));m=metrics(y,ts,u);V.append([m['worst'],m['global'],m['p95'],m['max_reliable']])
 V=np.array(V);return {'mc_worst_mean':V[:,0].mean(),'mc_worst_p95':np.percentile(V[:,0],95),'mc_global_mean':V[:,1].mean(),'mc_global_p95':np.percentile(V[:,1],95),'mc_p95_error_p95':np.percentile(V[:,2],95),'mc_max_reliable_p95':np.percentile(V[:,3],95),'prob_p95_gt_0_5':np.mean(V[:,2]>.5),'prob_p95_gt_1':np.mean(V[:,2]>1),'prob_p95_gt_2':np.mean(V[:,2]>2)}
rows=[];prows=[];rrows=[];cur=pd.DataFrame({'frequency_hz':freq})
for name,key in KEY.items():
 t=c[f'{key}_recommended_analog_db'].to_numpy();u=c[f'{key}_uncertainty_db'].to_numpy();variants={'balanced_recommended':OP[name],'subgrave_alternative':SUB[name],'global_rmse_audit':GLOBAL[name],'minimax_regional_audit':MINIMAX[name]}
 cur[f'{key}_target_db']=t;cur[f'{key}_uncertainty_db']=u
 for v,g in variants.items():
  y=resp(g);m=metrics(y,t,u);mc=mc_eval(name,key,g) if v=='balanced_recommended' else {};row={'setup':name,'variant':v,'gains_db':json.dumps(g.tolist()),'selection_reason':REASON[name] if v=='balanced_recommended' else '',**{k:x for k,x in m.items() if k!='regions'},**mc};rows.append(row);cur[f'{key}_{v}_response_db']=y;cur[f'{key}_{v}_error_db']=y-t
  for i,(fc,x) in enumerate(zip(F,g),1):prows.append({'setup':name,'variant':v,'global_gain_db':3,'band':i,'frequency_hz':int(fc),'gain_display_db':x,'q_display':.3,'gain_effective_db':.75*x,'q_effective':.3*(.569-.0026*x),'at_limit':abs(x)==16})
  for reg in REG:rrows.append({'setup':name,'variant':v,'region':reg[0],**m['regions'][reg[0]]})
pd.DataFrame(rows).to_csv(D/'final_preset_selection_metrics.csv',index=False);pd.DataFrame(prows).to_csv(D/'final_presets.csv',index=False);pd.DataFrame(rrows).to_csv(D/'final_metrics_by_region.csv',index=False);cur.to_csv(D/'final_curves_and_residuals.csv',index=False)
# decision table
cmp=[]
for name,key in KEY.items():
 for label,g in [('previous',OLD[name]),('recommended',OP[name]),('minimax_audit',MINIMAX[name]),('subgrave',SUB[name]),('global',GLOBAL[name])]:
  m=metrics(resp(g),c[f'{key}_recommended_analog_db'].to_numpy(),c[f'{key}_uncertainty_db'].to_numpy());cmp.append({'setup':name,'preset':label,'gains_db':json.dumps(g.tolist()),**{k:x for k,x in m.items() if k!='regions'}})
pd.DataFrame(cmp).to_csv(D/'historical_comparison_same_metrics.csv',index=False)
# Regenerate key comparison and residual plots with operational recommendation.
for name,key in KEY.items():
 t=c[f'{key}_recommended_analog_db'].to_numpy();u=c[f'{key}_uncertainty_db'].to_numpy();y=resp(OP[name]);old=resp(OLD[name]);mm=resp(MINIMAX[name]);sub=resp(SUB[name]);glob=resp(GLOBAL[name])
 fig,ax=plt.subplots(figsize=(11,6));ax.semilogx(freq,t,lw=2.5,label='Objetivo');ax.semilogx(freq,old,ls=':',label='Anterior');ax.semilogx(freq,y,ls='--',lw=2.2,label='Recomendado operativo');ax.semilogx(freq,mm,ls='-.',label='Minimax auditoría');ax.fill_between(freq,t-u,t+u,alpha=.1);ax.legend();ax.grid(True,which='both',alpha=.3);ax.set(xlim=(20,18000),title=f'{name}: decisión final',xlabel='Hz',ylabel='dB');fig.savefig(P/f'{key}_01_curves.png',dpi=160,bbox_inches='tight');plt.close(fig)
 fig,ax=plt.subplots(figsize=(11,5));ax.semilogx(freq,y-t,label='Recomendado');ax.semilogx(freq,sub-t,label='Subgrave');ax.semilogx(freq,glob-t,label='Global');ax.semilogx(freq,mm-t,label='Minimax');ax.axhline(0,color='k',lw=.7);ax.legend();ax.grid(True,which='both',alpha=.3);ax.set(xlim=(20,18000),title=f'{name}: residuos finales');fig.savefig(P/f'{key}_02_residual.png',dpi=160,bbox_inches='tight');plt.close(fig)
summary={'version':'3.1-operational-selection','recommendations':{name:{'gains_db':OP[name].tolist(),'reason':REASON[name]} for name in KEY}}
(D/'results_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(pd.DataFrame(rows)[['setup','variant','gains_db','worst','avg','global','r2060','ae30','selection_reason']].to_string(index=False))
