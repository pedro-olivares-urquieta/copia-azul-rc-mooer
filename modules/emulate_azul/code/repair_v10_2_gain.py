import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from pathlib import Path
import sys, numpy as np, pandas as pd, soundfile as sf
from scipy import signal
from repo_paths import OUT, CODE, ensure_runtime_dirs
ensure_runtime_dirs(); sys.path.insert(0,str(CODE))
import build_v10_2 as m

def noise_amp(y,f,dur):
    vals=[]
    regions=[(0,min(1.25,len(y)/m.SR)),(max(0,len(y)/m.SR-1.0),len(y)/m.SR)]
    for a,b in regions:
        st=a
        while st+dur<=b:
            vals.append(m.amp_sine(y[int(st*m.SR):int((st+dur)*m.SR)],f));st+=max(dur,.04)
    vals=np.array(vals,float);vals=vals[np.isfinite(vals)]
    return float(np.median(vals)) if len(vals) else 1e-8

traj=pd.read_csv(OUT/'TRAYECTORIAS_FUNDAMENTALES_V10_2.csv')
match=pd.read_csv(OUT/'MATCHING_EVENTOS_V10_2.csv')[['pair','event_cafe','event_azul','match_cost']].copy()
# event in traj is matched event index; derive mapping order from matching rows
match['event']=match.groupby('pair').cumcount()
traj=traj.merge(match[['pair','event','match_cost']],on=['pair','event'],how='left')
phase_dur={'attack':.075,'stabilization':.08,'body':.165,'sustain':.17,'decay':.12}
phase_w=m.PHASE_W
noise_cache={}
fund=[]
for key,z in traj.groupby('pair'):
    p=m.PAIRS[key];yc,_=m.load(p['cafe']);ya,_=m.load(p['azul'])
    for _,r in z.iterrows():
        if not np.isfinite(r.delta_db) or not np.isfinite(r.f0_cafe_hz) or not np.isfinite(r.f0_azul_hz):continue
        dur=phase_dur.get(r.phase,.1);kc=(key,'c',round(r.f0_cafe_hz,2),dur);ka=(key,'a',round(r.f0_azul_hz,2),dur)
        if kc not in noise_cache:noise_cache[kc]=noise_amp(yc,r.f0_cafe_hz,dur)
        if ka not in noise_cache:noise_cache[ka]=noise_amp(ya,r.f0_azul_hz,dur)
        snc=m.db(r.amplitude_cafe)-m.db(noise_cache[kc]);sna=m.db(r.amplitude_azul)-m.db(noise_cache[ka])
        fg=float(np.sqrt(r.f0_cafe_hz*r.f0_azul_hz))
        fund.append(dict(pair=key,family=m.fam(key),string=m.string_of(key),register=m.register_of(fg),event=int(r.event),phase=r.phase,f=fg,f0=fg,y=float(r.delta_db),snr=float(min(snc,sna)),match_cost=float(r.match_cost),kind='fundamental',weight_base=m.PHASE_W.get(r.phase,.1)))

harm=pd.read_csv(OUT/'TRAYECTORIAS_ARMONICAS_V10_2.csv').to_dict('records')
obs=fund+harm
pd.DataFrame(fund).to_csv(OUT/'FUNDAMENTALES_CORREGIDAS_V10_2.csv',index=False)
print('fund rows',len(fund),'snr',pd.DataFrame(fund).snr.describe().to_dict(),'median y',pd.DataFrame(fund).y.median())
lc,lr,cv,agg=m.cross_validate(obs);print('selected',lc,lr)
bc,dfc,sup=m.fit_model(obs,lc,'JOINT');br,_,_=m.fit_model(obs,lr,'JOINT')
print('gain',bc[m.IG],'offsets',bc[m.IS:m.IS+6]);print('curve pts',[(f,m.eval_q(bc,np.array([f]))[0]) for f in [31,41.2,55,120,250,500,800,1000,1250,1600,2000,3150,5000,8000,12000]])
np.savez(OUT/'repair_preview.npz',beta=bc)
