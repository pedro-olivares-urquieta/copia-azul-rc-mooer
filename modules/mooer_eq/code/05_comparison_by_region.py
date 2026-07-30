from pathlib import Path
import json,numpy as np,pandas as pd
D=Path('/mnt/data/PEDAL_MOOER_MULTIZONE_MASTER/data');c=pd.read_csv(D/'refined_curves_192ppo.csv');p=pd.read_csv(D/'final_presets.csv');freq=c.frequency_hz.to_numpy()
F=np.array([30.,148.,735.,3637.,18000.]);Q=.3
OLD={'Bajo':[15.,3.5,-3.5,16.,-3.5],'Híbrido':[-1.5,3.,4.,8.5,1.5],'Guitarra':[-10.,4.5,3.,9.5,1.]};OLD30={'Bajo':[15.5,2.,0.,12.,-.5],'Híbrido':[-1.,1.5,6.5,5.5,4.],'Guitarra':[-9.,3.,5.,7.5,2.5]};KEY={'Bajo':'bass','Híbrido':'hybrid','Guitarra':'guitar'};REG=[('Subgraves',20,60),('Graves',60,250),('Medios',250,2000),('Presencia',2000,8000),('Brillo',8000,15500)]
def bell(f,fc,g):
 A=10**(.75*g/40);q=.3*(.569-.0026*g);r=f/fc
 return 10*np.log10(((1-r*r)**2+(A*r/q)**2)/((1-r*r)**2+(r/(A*q))**2))
def resp(g):
 y=np.full_like(freq,3.)
 for fc,x in zip(F,g):y+=bell(freq,fc,x)
 return y
rows=[]
for name,key in KEY.items():
 t=c[f'{key}_recommended_analog_db'].to_numpy();u=c[f'{key}_uncertainty_db'].to_numpy()
 variants={'refined_previous':OLD[name],'point_30hz_previous':OLD30[name]}
 for v in ['balanced','subgrave','global']:variants['new_'+v]=p[(p.setup==name)&(p.variant==v)].sort_values('band').gain_display_db.tolist()
 for label,g in variants.items():
  e=resp(g)-t
  for reg,lo,hi in REG:
   m=(freq>=lo)&(freq<(hi if hi<15500 else hi+1));w=1/(u[m]**2+.12**2);w/=w.sum();rows.append({'setup':name,'preset':label,'region':reg,'rmse':np.sqrt(np.sum(w*e[m]**2)),'mae':np.sum(w*abs(e[m])),'bias':np.sum(w*e[m]),'p95':np.percentile(abs(e[m]),95),'max':np.max(abs(e[m])),'median_uncertainty':np.median(u[m])})
r=pd.DataFrame(rows);r.to_csv(D/'historical_metrics_by_region.csv',index=False)
sig=[]
for name in KEY:
 old=r[(r.setup==name)&(r.preset=='refined_previous')].set_index('region');new=r[(r.setup==name)&(r.preset=='new_balanced')].set_index('region')
 for reg in old.index:
  delta=new.loc[reg,'rmse']-old.loc[reg,'rmse'];unc=max(old.loc[reg,'median_uncertainty'],new.loc[reg,'median_uncertainty'])
  sig.append({'setup':name,'region':reg,'old_rmse':old.loc[reg,'rmse'],'new_rmse':new.loc[reg,'rmse'],'delta_new_minus_old':delta,'median_measurement_uncertainty':unc,'change_exceeds_uncertainty':abs(delta)>unc})
pd.DataFrame(sig).to_csv(D/'improvement_vs_measurement_uncertainty.csv',index=False)
print(pd.DataFrame(sig).to_string(index=False))
