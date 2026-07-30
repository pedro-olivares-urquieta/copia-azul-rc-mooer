from __future__ import annotations
import json, math, itertools, shutil
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
from scipy import ndimage
from scipy.optimize import differential_evolution

ROOT=Path('/mnt/data/PEDAL_MOOER_MULTIZONE_MASTER'); DATA=ROOT/'data'; PLOTS=ROOT/'plots'
for f in ['optimization_candidates_all.csv','pareto_candidates.csv','monte_carlo_candidates.csv','final_preset_selection_metrics.csv','final_presets.csv','final_metrics_by_region.csv','sensitivity_plus_minus_0_5db.csv','historical_comparison_same_metrics.csv','cross_validation.csv','smoothing_validation.csv','ideal_vs_calibrated_model.csv','final_curves_and_residuals.csv','balanced_band_contributions.csv','error_by_octave.csv','results_summary.json']:
    p=DATA/f
    if p.exists():p.unlink()
curves=pd.read_csv(DATA/'refined_curves_192ppo.csv');freq=curves.frequency_hz.to_numpy();N=len(freq)
SETUPS=('bass','hybrid','guitar');NAMES={'bass':'Bajo','hybrid':'Híbrido','guitar':'Guitarra'}
FREQS=np.array([30.,148.,735.,3637.,18000.]);GVALS=np.arange(-16,16.0001,.5);GLOBAL=3.;Q=.3
REGIONS=[('Subgraves',20,60),('Graves',60,250),('Medios',250,2000),('Presencia',2000,8000),('Brillo',8000,15500)]
OLD={'bass':np.array([15.,3.5,-3.5,16.,-3.5]),'hybrid':np.array([-1.5,3.,4.,8.5,1.5]),'guitar':np.array([-10.,4.5,3.,9.5,1.])}
OLD30={'bass':np.array([15.5,2.,0.,12.,-.5]),'hybrid':np.array([-1.,1.5,6.5,5.5,4.]),'guitar':np.array([-9.,3.,5.,7.5,2.5])}
OPT=np.arange(0,N,8);of=freq[OPT]
rm={name:(freq>=lo)&(freq<(hi if hi<15500 else hi+1)) for name,lo,hi in REGIONS};orm={k:v[OPT] for k,v in rm.items()}
idx30=int(np.argmin(abs(freq-30)));oidx30=int(np.argmin(abs(of-30)))
m2540=(freq>=25)&(freq<=40);om2540=m2540[OPT];m2060=(freq>=20)&(freq<=60);om2060=m2060[OPT]

def bell(f,fc,g,gc=.75,q0=.569,qs=-.0026):
    A=10**(gc*g/40);q=Q*(q0+qs*g);r=f/fc
    return 10*np.log10(((1-r*r)**2+(A*r/q)**2)/((1-r*r)**2+(r/(A*q))**2))
def bank(f,ideal=False):
    b=np.empty((5,65,len(f)))
    for i,fc in enumerate(FREQS):
        for j,g in enumerate(GVALS):
            if ideal:
                A=10**(g/40);q=.3;r=f/fc;b[i,j]=10*np.log10(((1-r*r)**2+(A*r/q)**2)/((1-r*r)**2+(r/(A*q))**2))
            else:b[i,j]=bell(f,fc,g)
    return b
BANK=bank(freq);OB=BANK[:,:,OPT];IDEAL=bank(freq,True);OIDEAL=IDEAL[:,:,OPT]
def iof(g):return np.clip(np.round((np.asarray(g)+16)*2).astype(int),0,64)
def gof(i):return GVALS[np.asarray(i,int)]
def one_resp(b,idx):return GLOBAL+sum(b[k,int(idx[k])] for k in range(5))
def batch_resp(b,idx):
    Y=np.full((len(idx),b.shape[2]),GLOBAL)
    for k in range(5):Y+=b[k,idx[:,k]]
    return Y

def full_metrics(y,t,u):
    e=y-t;regs={};rs=[]
    for name,lo,hi in REGIONS:
        m=rm[name];w=1/(u[m]**2+.12**2);w/=w.sum();v=e[m];x=np.log2(freq[m]);xc=x-np.sum(w*x)
        d={'rmse':float(np.sqrt(np.sum(w*v*v))),'mae':float(np.sum(w*abs(v))),'bias':float(np.sum(w*v)),'p95':float(np.percentile(abs(v),95)),'max':float(np.max(abs(v))),'slope_error':float(np.sum(w*xc*v)/(np.sum(w*xc*xc)+1e-30)),'correlation':float(np.corrcoef(t[m]-t[m].mean(),y[m]-y[m].mean())[0,1])};regs[name]=d;rs.append(d['rmse'])
    w=1/(u**2+.12**2);w*=np.where(freq<=15500,1,np.clip((18000-freq)/2500,.05,1));w/=w.sum();ae=abs(e)
    return {'regions':regs,'worst':max(rs),'avg':float(np.mean(rs)),'global':float(np.sqrt(np.sum(w*e*e))),'uniform':float(np.sqrt(np.mean(e*e))),'mae':float(np.mean(ae)),'p50':float(np.percentile(ae,50)),'p90':float(np.percentile(ae,90)),'p95':float(np.percentile(ae,95)),'max_reliable':float(np.max(ae[freq<=15500])),'max_total':float(np.max(ae)),'bias':float(np.mean(e)),'slope_mean':float(np.mean([abs(v['slope_error']) for v in regs.values()])),'e30':float(e[idx30]),'ae30':float(ae[idx30]),'r2540':float(np.sqrt(np.mean(e[m2540]**2))),'r2060':float(np.sqrt(np.mean(e[m2060]**2))),'r8k':float(np.sqrt(np.mean(e[freq<=8000]**2))),'r15500':float(np.sqrt(np.mean(e[freq<=15500]**2)))}

def scores(Y,t,u):
    rr=[]
    for name,_,_ in REGIONS:
        m=orm[name];w=1/(u[m]**2+.12**2);w/=w.sum();rr.append(np.sqrt(np.sum(w[None]*(Y[:,m]-t[m][None])**2,1)))
    rr=np.stack(rr,1);e=Y-t[None];w=1/(u**2+.12**2);w*=np.where(of<=15500,1,np.clip((18000-of)/2500,.05,1));w/=w.sum();glob=np.sqrt(np.sum(w[None]*e*e,1));p95=np.percentile(abs(e),95,1);r25=np.sqrt(np.mean(e[:,om2540]**2,1));ae30=abs(e[:,oidx30])
    worst=rr.max(1);avg=rr.mean(1);sub=rr[:,0]
    return {'balanced':worst+.35*avg+.10*glob+.025*p95+.04*r25+.015*ae30,'subgrave':1.2*sub+.65*r25+.10*ae30+.35*worst+.16*avg+.05*glob,'global':glob+.15*avg+.07*worst+.02*p95,'worst':worst,'avg':avg,'glob':glob,'sub':sub,'r25':r25,'ae30':ae30}

def keep_top(store,kind,idx,vals,k=250):
    if len(idx)==0:return store
    order=np.argpartition(vals,min(k,len(vals))-1)[:min(k,len(vals))]
    for j in order:
        key=tuple(int(x) for x in idx[j]);v=float(vals[j])
        if key not in store or v<store[key]:store[key]=v
    return store

def coord(idx,t,u,kind,b=OB):
    idx=idx.copy();y=one_resp(b,idx);s=float(scores(y[None],t,u)[kind][0])
    for _ in range(10):
        ch=False
        for bandi in range(5):
            base=y-b[bandi,idx[bandi]];Y=base[None]+b[bandi];S=scores(Y,t,u)[kind];j=int(np.argmin(S))
            if S[j]<s-1e-12:idx[bandi]=j;y=Y[j];s=float(S[j]);ch=True
        if not ch:break
    return idx

def pair(idx,t,u,kind,b=OB):
    idx=coord(idx,t,u,kind,b);y=one_resp(b,idx);s=float(scores(y[None],t,u)[kind][0])
    for a in range(5):
        for c in range(a+1,5):
            base=y-b[a,idx[a]]-b[c,idx[c]];best=(idx[a],idx[c]);bs=s;by=y
            for ia in range(65):
                Y=base[None]+b[a,ia][None]+b[c];S=scores(Y,t,u)[kind];ic=int(np.argmin(S))
                if S[ic]<bs:best=(ia,ic);bs=float(S[ic]);by=Y[ic]
            idx[a],idx[c]=best;y=by;s=bs
    return idx

def de(t,u,kind,seed):
    def f(g):
        y=np.full_like(of,GLOBAL)
        for fc,x in zip(FREQS,g):y+=bell(of,fc,x)
        return scores(y[None],t,u)[kind][0]
    r=differential_evolution(f,[(-16,16)]*5,seed=seed,popsize=5,maxiter=18,tol=1e-4,polish=True);return iof(np.round(r.x*2)/2)
def anneal(start,t,u,kind,rng,steps=500):
    x=start.copy();y=one_resp(OB,x);s=float(scores(y[None],t,u)[kind][0]);best=(x.copy(),s)
    for j in range(steps):
        b=int(rng.integers(5));z=x.copy();z[b]=np.clip(z[b]+rng.choice([-4,-2,-1,1,2,4]),0,64);ny=y-OB[b,x[b]]+OB[b,z[b]];ns=float(scores(ny[None],t,u)[kind][0]);T=.04*(1-j/steps)+.001
        if ns<s or rng.random()<math.exp(min(0,(s-ns)/T)):x=z;y=ny;s=ns
        if s<best[1]:best=(x.copy(),s)
    return best[0]
def pareto(rows):
    K=['worst','avg','global','p95','r2060'];out=[]
    for i,a in enumerate(rows):
        va=np.array([a['m'][k] for k in K]);dom=False
        for j,b in enumerate(rows):
            if i==j:continue
            vb=np.array([b['m'][k] for k in K])
            if np.all(vb<=va+1e-10) and np.any(vb<va-1e-10):dom=True;break
        if not dom:out.append(a)
    return out

outs={};cand_csv=[];par_csv=[]
for si,setup in enumerate(SETUPS):
    print('SEARCH',setup,flush=True);tf=curves[f'{setup}_recommended_analog_db'].to_numpy();uf=curves[f'{setup}_uncertainty_db'].to_numpy();t=tf[OPT];u=uf[OPT];rng=np.random.default_rng(2000+si)
    stores={k:{} for k in ['balanced','subgrave','global']};sources={}
    # Historical, DE, annealing.
    seeds=[iof(OLD[setup]),iof(OLD30[setup]),np.full(5,32,int)]
    for kind in stores:
        for x,src in [(z,'historical') for z in seeds]+[(de(t,u,kind,500+si),'DE')]:
            x=coord(x,t,u,kind);key=tuple(x);stores[kind][key]=float(scores(one_resp(OB,x)[None],t,u)[kind][0]);sources.setdefault(key,set()).add(src)
        for k in range(1):
            x=coord(anneal(seeds[k%3],t,u,kind,np.random.default_rng(8000+si*10+k)),t,u,kind);key=tuple(x);stores[kind][key]=float(scores(one_resp(OB,x)[None],t,u)[kind][0]);sources.setdefault(key,set()).add('anneal')
    # Massive discrete random sampling by batches.
    total=30000;batch=3000
    for start in range(0,total,batch):
        X=rng.integers(0,65,size=(min(batch,total-start),5));Y=batch_resp(OB,X);S=scores(Y,t,u)
        for kind in stores:stores[kind]=keep_top(stores[kind],kind,X,S[kind],250)
    # Exact local cubes ±1.5 dB around historical and current tops.
    centers=[iof(OLD[setup]),iof(OLD30[setup])]
    for kind in stores:
        centers += [np.array(x) for x,_ in sorted(stores[kind].items(),key=lambda kv:kv[1])[:3]]
    centers={tuple(x):np.array(x) for x in centers}.values()
    for c in centers:
        opts=[np.arange(max(0,z-3),min(64,z+3)+1) for z in c]
        combos=np.array(list(itertools.product(*opts)),dtype=int)
        for st in range(0,len(combos),2000):
            X=combos[st:st+2000];S=scores(batch_resp(OB,X),t,u)
            for kind in stores:stores[kind]=keep_top(stores[kind],kind,X,S[kind],300)
    # Refine top candidates by coordinate/pairwise.
    allkeys=set()
    for kind in stores:
        for key,_ in sorted(stores[kind].items(),key=lambda kv:kv[1])[:12]:
            x=coord(np.array(key),t,u,kind);allkeys.add(tuple(x));sources.setdefault(tuple(x),set()).add('coordinate_refine')
    allkeys.update(tuple(iof(x)) for x in [OLD[setup],OLD30[setup]])
    rows=[]
    for key in allkeys:
        x=np.array(key);y=one_resp(BANK,x);m=full_metrics(y,tf,uf);rows.append({'idx':x,'g':gof(x),'y':y,'m':m,'sources':','.join(sorted(sources.get(key,{'batch'})))})
    pf=pareto(rows);outs[setup]={'rows':rows,'pareto':pf,'target':tf,'unc':uf};print(' rows',len(rows),'pareto',len(pf),flush=True)
    for r in rows:cand_csv.append({'setup':NAMES[setup],'gains_db':json.dumps(r['g'].tolist()),'sources':r['sources'],**{k:v for k,v in r['m'].items() if k!='regions'}})
    for r in pf:par_csv.append({'setup':NAMES[setup],'gains_db':json.dumps(r['g'].tolist()),**{k:v for k,v in r['m'].items() if k!='regions'}})
pd.DataFrame(cand_csv).to_csv(DATA/'optimization_candidates_all.csv',index=False);pd.DataFrame(par_csv).to_csv(DATA/'pareto_candidates.csv',index=False)

# MC robust candidates
def target_sample(setup,t,u,rng):
    p=curves[f'{setup}_pink_db'].to_numpy();s=curves[f'{setup}_sweep_aligned_db'].to_numpy();pr=curves[f'{setup}_precise_1_24oct_db'].to_numpy();me=curves[f'{setup}_measured_1_12oct_db'].to_numpy();z=ndimage.gaussian_filter1d(rng.normal(size=N),10);z/=z.std()+1e-30
    q=t+rng.normal(0,.2)*(p-t)+rng.normal(0,.2)*(s-t)+rng.uniform(-.3,.3)*(pr-me)+.4*u*z;return np.where(freq<=15500,q,t+.35*(q-t))
def model_sample(g,rng):
    y=np.full_like(freq,GLOBAL);gc=rng.normal(.75,.015);q0=rng.normal(.569,.01);qs=rng.normal(-.0026,.0003);sh=rng.normal(0,.003,5)
    for fc,x,d in zip(FREQS,g,sh):y+=bell(freq,fc*(1+d),x,gc,q0,qs)
    return y
mcrows=[]
for si,setup in enumerate(SETUPS):
    o=outs[setup];short=sorted(o['pareto'],key=lambda r:(r['m']['worst'],r['m']['avg']))[:15]+[min(o['rows'],key=lambda r:r['m']['global']),min(o['rows'],key=lambda r:(r['m']['r2060'],r['m']['worst']))]
    for g in [OLD[setup],OLD30[setup]]:
        x=iof(g);short.append({'idx':x,'g':g,'y':one_resp(BANK,x),'m':full_metrics(one_resp(BANK,x),o['target'],o['unc']),'sources':'history'})
    short={tuple(r['idx']):r for r in short}.values();rng=np.random.default_rng(6000+si);ts=[target_sample(setup,o['target'],o['unc'],rng) for _ in range(96)]
    for r in short:
        V=[]
        for t in ts:
            m=full_metrics(model_sample(r['g'],rng),t,o['unc']);V.append([m['worst'],m['global'],m['p95'],m['max_reliable']])
        V=np.array(V);mcrows.append({'setup':NAMES[setup],'gains_db':json.dumps(r['g'].tolist()),'mc_worst_mean':V[:,0].mean(),'mc_worst_p95':np.percentile(V[:,0],95),'mc_global_mean':V[:,1].mean(),'mc_global_p95':np.percentile(V[:,1],95),'mc_p95_error_p95':np.percentile(V[:,2],95),'mc_max_reliable_p95':np.percentile(V[:,3],95),'prob_p95_gt_0_5':np.mean(V[:,2]>.5),'prob_p95_gt_1':np.mean(V[:,2]>1),'prob_p95_gt_2':np.mean(V[:,2]>2)})
mc=pd.DataFrame(mcrows);mc.to_csv(DATA/'monte_carlo_candidates.csv',index=False)

# Select
selected={};selrows=[];pres=[];reg=[];sens=[]
for setup in SETUPS:
    o=outs[setup];L={tuple(json.loads(r.gains_db)):r for _,r in mc[mc.setup==NAMES[setup]].iterrows()};pool=[]
    for r in o['rows']:
        z=L.get(tuple(r['g'].tolist()))
        if z is not None:pool.append({**r,'mc':z})
    minw=min(r['m']['worst'] for r in pool);mina=min(r['m']['avg'] for r in pool);bp=[r for r in pool if r['m']['worst']<=minw+.06 and r['m']['avg']<=mina+.08]
    A=min(bp,key=lambda r:(r['mc'].mc_worst_p95,r['m']['worst'],r['m']['avg']));sp=[r for r in pool if r['m']['worst']<=A['m']['worst']+.15 and r['m']['avg']<=A['m']['avg']+.10];B=min(sp,key=lambda r:(r['m']['r2060'],r['m']['r2540'],r['m']['ae30']));C=min(pool,key=lambda r:(r['m']['global'],r['m']['p95']));selected[setup]={'balanced':A,'subgrave':B,'global':C}
    for v,r in selected[setup].items():
        row={'setup':NAMES[setup],'variant':v,'gains_db':json.dumps(r['g'].tolist()),**{k:x for k,x in r['m'].items() if k!='regions'}};row.update({k:r['mc'][k] for k in r['mc'].index if k.startswith('mc_') or k.startswith('prob_')});selrows.append(row)
        for i,(fc,g) in enumerate(zip(FREQS,r['g']),1):pres.append({'setup':NAMES[setup],'variant':v,'global_gain_db':3,'band':i,'frequency_hz':int(fc),'gain_display_db':g,'q_display':.3,'gain_effective_db':.75*g,'q_effective':.3*(.569-.0026*g),'at_limit':abs(g)==16})
        for name,_,_ in REGIONS:reg.append({'setup':NAMES[setup],'variant':v,'region':name,**r['m']['regions'][name]})
    for i in range(5):
        for d in [-.5,.5]:
            g=A['g'].copy();g[i]=np.clip(g[i]+d,-16,16);m=full_metrics(one_resp(BANK,iof(g)),o['target'],o['unc']);sens.append({'setup':NAMES[setup],'band_hz':int(FREQS[i]),'delta_db':d,'worst_change':m['worst']-A['m']['worst'],'global_change':m['global']-A['m']['global'],'sub_change':m['r2060']-A['m']['r2060']})
pd.DataFrame(selrows).to_csv(DATA/'final_preset_selection_metrics.csv',index=False);pd.DataFrame(pres).to_csv(DATA/'final_presets.csv',index=False);pd.DataFrame(reg).to_csv(DATA/'final_metrics_by_region.csv',index=False);pd.DataFrame(sens).to_csv(DATA/'sensitivity_plus_minus_0_5db.csv',index=False)

# Historical
H=[]
for setup in SETUPS:
    o=outs[setup];D={'refined_previous':OLD[setup],'point_30hz_previous':OLD30[setup],'new_balanced':selected[setup]['balanced']['g'],'new_subgrave':selected[setup]['subgrave']['g'],'new_global':selected[setup]['global']['g']}
    for lab,g in D.items():m=full_metrics(one_resp(BANK,iof(g)),o['target'],o['unc']);H.append({'setup':NAMES[setup],'preset':lab,'gains_db':json.dumps(g.tolist()),**{k:x for k,x in m.items() if k!='regions'}})
pd.DataFrame(H).to_csv(DATA/'historical_comparison_same_metrics.csv',index=False)

# Cross-validation simplified
sweep_long=pd.read_csv(DATA/'sweep_repetitions_long.csv');CV=[]
def quick(tfull,u,starts,b=OB):
    t=tfull[OPT];uu=u[OPT];best=None
    for x in starts:
        z=coord(x,t,uu,'balanced',b);s=float(scores(one_resp(b,z)[None],t,uu)['balanced'][0])
        if best is None or s<best[1]:best=(z,s)
    return best[0]
for si,setup in enumerate(SETUPS):
    o=outs[setup];u=o['unc'];p=curves[f'{setup}_pink_db'].to_numpy();s=curves[f'{setup}_sweep_aligned_db'].to_numpy();starts=[iof(OLD[setup]),iof(selected[setup]['balanced']['g']),np.full(5,32,int)]
    for tr,t,vl,v in [('pink',p,'sweep',s),('sweep',s,'pink',p)]:
        x=quick(t,u,starts);y=one_resp(BANK,x);CV.append({'setup':NAMES[setup],'fold':f'train_{tr}_validate_{vl}','gains_db':json.dumps(gof(x).tolist()),'train_worst':full_metrics(y,t,u)['worst'],'validation_worst':full_metrics(y,v,u)['worst'],'validation_global':full_metrics(y,v,u)['global']})
    sub=sweep_long[sweep_long.setup==NAMES[setup]];runs=[]
    for r in sorted(sub.run.unique()):
        z=sub[sub.run==r].sort_values('frequency_hz').transfer_db.to_numpy();m=(freq>=30)&(freq<=14000);z-=np.median(z[m]-s[m]);runs.append(z)
    runs=np.array(runs)
    for hold in range(4):
        t=np.median(np.delete(runs,hold,0),0);x=quick(t,u,starts);y=one_resp(BANK,x);CV.append({'setup':NAMES[setup],'fold':f'leave_run_{hold+1}_out','gains_db':json.dumps(gof(x).tolist()),'train_worst':full_metrics(y,t,u)['worst'],'validation_worst':full_metrics(y,runs[hold],u)['worst'],'validation_global':full_metrics(y,runs[hold],u)['global']})
    for lab,a,b in [('ascending_vs_descending',np.median(runs[[0,2]],0),np.median(runs[[1,3]],0)),('repetition1_vs_repetition2',np.median(runs[[0,1]],0),np.median(runs[[2,3]],0))]:
        d=a-b;CV.append({'setup':NAMES[setup],'fold':lab,'gains_db':'','train_worst':np.nan,'validation_worst':max(np.sqrt(np.mean(d[rm[x[0]]]**2)) for x in REGIONS),'validation_global':np.sqrt(np.mean(d[freq<=15500]**2))})
pd.DataFrame(CV).to_csv(DATA/'cross_validation.csv',index=False)

# Smoothing & ideal
SM=[];ID=[]
for si,setup in enumerate(SETUPS):
    o=outs[setup];u=o['unc'];pr=curves[f'{setup}_precise_1_24oct_db'].to_numpy();T={'1_24':pr,'1_12':curves[f'{setup}_measured_1_12oct_db'].to_numpy(),'1_6':ndimage.gaussian_filter1d(pr,(1/6)*192/2.355),'1_3':ndimage.gaussian_filter1d(pr,(1/3)*192/2.355),'recommended':o['target']};A=selected[setup]['balanced']
    for lab,t in T.items():m=full_metrics(A['y'],t,u);SM.append({'setup':NAMES[setup],'smoothing':lab,'worst':m['worst'],'avg':m['avg'],'global':m['global']})
    x=quick(o['target'],u,[iof(OLD[setup]),np.full(5,32,int)],OIDEAL);im=full_metrics(one_resp(IDEAL,x),o['target'],u);cm=full_metrics(one_resp(BANK,x),o['target'],u);ID.append({'setup':NAMES[setup],'ideal_gains_db':json.dumps(gof(x).tolist()),'ideal_predicted_worst':im['worst'],'same_gains_calibrated_worst':cm['worst'],'same_gains_calibrated_global':cm['global']})
pd.DataFrame(SM).to_csv(DATA/'smoothing_validation.csv',index=False);pd.DataFrame(ID).to_csv(DATA/'ideal_vs_calibrated_model.csv',index=False)

# Curves, contributions, octaves
CO=pd.DataFrame({'frequency_hz':freq});CON=[];OCT=[]
for setup in SETUPS:
    o=outs[setup];CO[f'{setup}_target_db']=o['target'];CO[f'{setup}_uncertainty_db']=o['unc']
    for v,r in selected[setup].items():CO[f'{setup}_{v}_response_db']=r['y'];CO[f'{setup}_{v}_error_db']=r['y']-o['target']
    A=selected[setup]['balanced'];x=iof(A['g'])
    for i,(fc,g) in enumerate(zip(FREQS,A['g'])):
        for f,z in zip(freq,BANK[i,x[i]]):CON.append({'setup':NAMES[setup],'band':i+1,'center_hz':int(fc),'gain_db':g,'frequency_hz':f,'contribution_db':z})
    e=A['y']-o['target'];edges=20*2**np.arange(math.ceil(math.log2(18000/20))+1)
    for lo,hi in zip(edges[:-1],edges[1:]):
        m=(freq>=lo)&(freq<min(hi,18000));
        if m.any():OCT.append({'setup':NAMES[setup],'low_hz':lo,'high_hz':min(hi,18000),'rmse_db':np.sqrt(np.mean(e[m]**2)),'squared_error_sum':np.sum(e[m]**2)})
CO.to_csv(DATA/'final_curves_and_residuals.csv',index=False);pd.DataFrame(CON).to_csv(DATA/'balanced_band_contributions.csv',index=False);pd.DataFrame(OCT).to_csv(DATA/'error_by_octave.csv',index=False)

# Plots
rdf=pd.DataFrame(reg);sdf=pd.DataFrame(sens);odf=pd.DataFrame(OCT)
for setup in SETUPS:
    name=NAMES[setup];o=outs[setup];A=selected[setup]['balanced'];B=selected[setup]['subgrave'];C=selected[setup]['global'];t=o['target'];u=o['unc'];old=one_resp(BANK,iof(OLD[setup]));old30=one_resp(BANK,iof(OLD30[setup]))
    def sv(fig,x):fig.savefig(PLOTS/f'{setup}_{x}.png',dpi=150,bbox_inches='tight');plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,6));ax.semilogx(freq,t,lw=2.4,label='Objetivo');ax.semilogx(freq,old,ls=':',label='Anterior refinado');ax.semilogx(freq,old30,ls='-.',label='Anterior 30 Hz');ax.semilogx(freq,A['y'],ls='--',lw=2,label='Nuevo equilibrado');ax.fill_between(freq,t-u,t+u,alpha=.1);ax.legend();ax.grid(True,which='both',alpha=.3);ax.set(xlim=(20,18000),title=f'{name}: comparación',xlabel='Hz',ylabel='dB');sv(fig,'01_curves')
    fig,ax=plt.subplots(figsize=(11,5));ax.semilogx(freq,A['y']-t,label='Equilibrado');ax.semilogx(freq,B['y']-t,label='Subgrave');ax.semilogx(freq,C['y']-t,label='Global');ax.axhline(0,color='k',lw=.7);ax.legend();ax.grid(True,which='both',alpha=.3);ax.set(xlim=(20,18000),title=f'{name}: residuos');sv(fig,'02_residual')
    for k,(lo,hi,lab) in enumerate([(20,100,'subgrave'),(20,250,'graves'),(250,2000,'medios'),(2000,8000,'presencia'),(8000,18000,'brillo')],3):
        m=(freq>=lo)&(freq<=hi);fig,ax=plt.subplots(figsize=(10,5));ax.semilogx(freq[m],t[m],lw=2.3,label='Objetivo');ax.semilogx(freq[m],A['y'][m],ls='--',label='Equilibrado');ax.semilogx(freq[m],B['y'][m],ls=':',label='Subgrave');ax.fill_between(freq[m],t[m]-u[m],t[m]+u[m],alpha=.12);ax.legend();ax.grid(True,which='both',alpha=.3);ax.set(title=f'{name}: {lo}-{hi} Hz');sv(fig,f'{k:02d}_zoom_{lab}')
    fig,ax=plt.subplots(figsize=(9,5));rdf[rdf.setup==name].pivot(index='region',columns='variant',values='rmse').reindex([x[0] for x in REGIONS]).plot.bar(ax=ax);ax.set(title=f'{name}: RMSE regional',ylabel='dB');sv(fig,'08_region_rmse')
    fig,ax=plt.subplots(figsize=(9,5));z=odf[odf.setup==name];ax.bar(range(len(z)),z.rmse_db);ax.set_xticks(range(len(z)),[f'{int(a)}-{int(b)}' for a,b in zip(z.low_hz,z.high_hz)],rotation=35);ax.set(title=f'{name}: error por octava');sv(fig,'09_error_octave')
    pr=pd.DataFrame([{'e30':r['m']['ae30'],'sub':r['m']['r2060'],'worst':r['m']['worst'],'glob':r['m']['global']} for r in o['pareto']]);fig,ax=plt.subplots(figsize=(8,6));sc=ax.scatter(pr.e30,pr.glob,c=pr.worst);fig.colorbar(sc,ax=ax,label='Peor RMSE');ax.set(xlabel='|Error 30 Hz|',ylabel='RMSE global',title=f'{name}: Pareto 30/global');sv(fig,'10_pareto_30_global')
    fig,ax=plt.subplots(figsize=(8,6));sc=ax.scatter(pr['sub'],pr.worst,c=pr.glob);fig.colorbar(sc,ax=ax,label='RMSE global');ax.set(xlabel='RMSE 20-60',ylabel='Peor regional',title=f'{name}: Pareto subgrave');sv(fig,'11_pareto_sub_worst')
    fig,ax=plt.subplots(figsize=(9,5));z=sdf[sdf.setup==name].copy();z['lab']=z.band_hz.astype(str)+' '+z.delta_db.map(lambda x:f'{x:+.1f}');ax.bar(z.lab,z.worst_change);ax.axhline(0,color='k');ax.tick_params(axis='x',rotation=45);ax.set(title=f'{name}: sensibilidad ±0,5');sv(fig,'12_sensitivity')
    fig,ax=plt.subplots(figsize=(8,5));mr=A['mc'];ax.bar(['MC global media','MC global P95','MC peor P95'],[mr.mc_global_mean,mr.mc_global_p95,mr.mc_worst_p95]);ax.set(title=f'{name}: Monte Carlo',ylabel='dB');sv(fig,'13_monte_carlo')
    fig,ax=plt.subplots(figsize=(10,5));ax.semilogx(freq,u);ax.axvspan(15500,18000,alpha=.15);ax.grid(True,which='both',alpha=.3);ax.set(xlim=(20,18000),title=f'{name}: incertidumbre');sv(fig,'14_confidence')
    fig,ax=plt.subplots(figsize=(11,6));x=iof(A['g']);run=np.full_like(freq,GLOBAL);ax.semilogx(freq,run,label='Global +3');
    for i,(fc,g) in enumerate(zip(FREQS,A['g'])):z=BANK[i,x[i]];run+=z;ax.semilogx(freq,z,label=f'{int(fc)} {g:+.1f}')
    ax.semilogx(freq,run,color='k',lw=2.5,label='Suma');ax.legend(ncol=2);ax.grid(True,which='both',alpha=.3);ax.set(xlim=(20,18000),title=f'{name}: contribuciones');sv(fig,'15_contributions')

summary={'version':'3.0-multizone','global_gain_db':3,'frequencies_hz':FREQS.tolist(),'q_display':.3,'selections':{}}
for setup in SETUPS:summary['selections'][setup]={v:{'gains_db':r['g'].tolist(),'metrics':{k:x for k,x in r['m'].items() if k!='regions'}} for v,r in selected[setup].items()}
(DATA/'results_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(pd.DataFrame(selrows)[['setup','variant','gains_db','worst','avg','global','r2060','ae30','mc_worst_p95']].to_string(index=False))
