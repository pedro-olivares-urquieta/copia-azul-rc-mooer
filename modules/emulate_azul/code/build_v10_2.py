from __future__ import annotations
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
import os, sys, math, json, time, hashlib, zipfile, shutil, warnings
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
import soundfile as sf
from scipy import signal, interpolate, optimize
from scipy.spatial.distance import cdist
import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')

# NumPy 2 removed the `trapz` alias; keep the identical trapezoidal rule.
if not hasattr(np, 'trapz'):
    np.trapz = np.trapezoid

from repo_paths import ROOT, WAV, OUT, AUD, CODE, LEGACY, EXPORTS, AUDIO, ensure_runtime_dirs
ensure_runtime_dirs()
SR=44100; SEED=10202; RNG=np.random.default_rng(SEED)
sys.path.insert(0,str(CODE)); import audio_utils_v7 as au; import onsets; import run_config; import run_manifest
PAIRS={p['key']:p for p in au.pairs}
STRINGS=['B','E','A','D','G','C']
# V21: add dedicated `low` window (V4.1 60–760 ms) for sub-bass cycles.
PHASES=['attack','stabilization','body','sustain','decay','low']
PHASE_W={'attack':.08,'stabilization':.12,'body':.28,'sustain':.22,'decay':.08,'low':.22}
OPEN_SOFT_HZ=300.0  # open-string evidence soft-stops here (mask 280–300 in v12)
REGIONS=[(20,40,'20-40'),(40,60,'40-60'),(60,100,'60-100'),(100,160,'100-160'),(160,250,'160-250'),(250,400,'250-400'),(400,630,'400-630'),(630,1000,'630-1000'),(1000,1600,'1000-1600'),(1600,2500,'1600-2500'),(2500,4000,'2500-4000'),(4000,6300,'4000-6300'),(6300,8000,'6300-8000'),(8000,12000,'8000-12000'),(12000,16000,'12000-16000'),(16000,20000,'16000-20000')]
DENSE_F=np.geomspace(20,20000,4096)
LOW_F=np.geomspace(20,120,512)

# ---------- basic ----------
def sha256(p):
    h=hashlib.sha256();
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def ensure_wav(p):
    """Decode m4a/other compressed audio into a local WAV cache for soundfile."""
    p=Path(p)
    if p.suffix.lower()=='.wav' and p.exists():
        return p
    WAV.mkdir(parents=True,exist_ok=True)
    out=WAV/f'{p.stem}.wav'
    if out.exists() and out.stat().st_mtime>=p.stat().st_mtime:
        return out
    import subprocess
    subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(p),'-acodec','pcm_f32le',str(out)],check=True)
    return out

def load(p):
    wav=ensure_wav(p)
    y,sr=sf.read(wav,always_2d=False)
    if y.ndim>1:y=np.mean(y,axis=1)
    return y.astype(np.float64),sr

def fam(key):
    if key.endswith('_open'): return 'open'
    if key.endswith('_12'): return 'fret12'
    if key=='C_24': return 'high'
    if key=='C_chromatic': return 'chromatic'
    return 'chord'

def string_of(key):
    return key.split('_')[0] if key[0] in STRINGS else 'C'

def register_of(f):
    if f<60:return 'sub'
    if f<150:return 'low'
    if f<400:return 'mid'
    return 'high'

def db(x): return 20*np.log10(np.maximum(x,1e-30))
def dbp(x): return 10*np.log10(np.maximum(x,1e-30))

def weighted_quantile(v,w,q):
    v=np.asarray(v,float);w=np.asarray(w,float);m=np.isfinite(v)&np.isfinite(w)&(w>0)
    if not m.any(): return np.nan
    v=v[m];w=w[m];o=np.argsort(v);v=v[o];w=w[o];c=np.cumsum(w);c/=c[-1]
    return float(np.interp(q,c,v))

def robust_scale(x):
    x=np.asarray(x,float);med=np.nanmedian(x);return max(1.4826*np.nanmedian(np.abs(x-med)),.15)

def interp_log(f,x,y): return np.interp(np.log(f),np.log(x),y)

# ---------- event detection / matching ----------
def onset_candidates(y,min_sep,expected_period):
    hop=128
    oe=onsets.onset_strength(y,SR,hop_length=hop,n_fft=2048,aggregate=np.mean)
    oe=signal.savgol_filter(oe,9,2,mode='interp') if len(oe)>10 else oe
    dist=max(1,int(min_sep*SR/hop)); prom=max(np.percentile(oe,70)*.18,1e-8)
    pk,_=signal.find_peaks(oe,distance=dist,prominence=prom)
    ts=pk*hop/SR
    # periodic hypothesis and local snapping
    grid,_,_=au.periodic_grid(y,expected_period)
    snapped=[]
    for t in grid:
        j=np.argmin(np.abs(ts-t)) if len(ts) else -1
        if j>=0 and abs(ts[j]-t)<=.10: snapped.append(ts[j])
        else: snapped.append(t)
    return np.asarray(ts),np.asarray(snapped),oe,hop

def amp_sine(seg,f):
    if len(seg)<64:return np.nan
    seg=np.asarray(seg,float)-np.mean(seg);w=signal.windows.hann(len(seg),sym=False);t=np.arange(len(seg))/SR
    z=np.dot(seg*w,np.exp(-2j*np.pi*f*t));return float(2*np.abs(z)/(w.sum()+1e-30))

def f0_refine(y,t,period,fexp):
    a=int(max(0,(t+.08)*SR));b=int(min(len(y),(t+min(period*.82,.50))*SR));seg=y[a:b]
    if len(seg)<512:return fexp,np.nan
    seg=seg-np.mean(seg);w=signal.windows.hann(len(seg),sym=False);nfft=max(32768,1<<int(np.ceil(np.log2(len(seg)*8))))
    P=np.abs(np.fft.rfft(seg*w,nfft));ff=np.fft.rfftfreq(nfft,1/SR)
    m=(ff>=fexp*.965)&(ff<=fexp*1.035)
    if not m.any():return fexp,np.nan
    ids=np.where(m)[0];i=ids[np.argmax(P[m])]
    if 0<i<len(P)-1:
        yy=np.log(P[i-1:i+2]+1e-30);den=yy[0]-2*yy[1]+yy[2];d=.5*(yy[0]-yy[2])/den if abs(den)>1e-12 else 0
    else:d=0
    f=float(ff[i]+np.clip(d,-1,1)*(ff[1]-ff[0]))
    return f,float(P[i])

def event_descriptor(y,t,period,fexp=None):
    def rms(a,b):
        s=y[int(max(0,t+a)*SR):int(min(len(y),(t+b)*SR))];return np.sqrt(np.mean(s*s)+1e-30) if len(s)>8 else 1e-15
    a=rms(0,min(.06,period*.18));e=rms(min(.06,period*.18),min(.18,period*.45));l=rms(min(.22,period*.55),min(.48,period*.88))
    bands=[]
    seg=y[int(t*SR):int(min(len(y),(t+min(period*.88,.52))*SR))]
    if len(seg)>256:
        f,P=signal.welch(seg,SR,nperseg=min(4096,len(seg)),noverlap=min(2048,max(0,len(seg)//2)),scaling='spectrum')
        for lo,hi in [(20,150),(150,500),(500,2000),(2000,8000),(8000,18000)]:bands.append(np.log10(np.trapz(P[(f>=lo)&(f<hi)],f[(f>=lo)&(f<hi)])+1e-30))
    else:bands=[-30]*5
    f0=fexp
    if fexp: f0,_=f0_refine(y,t,period,fexp)
    return np.array([np.log(a/e+1e-20),np.log(l/e+1e-20),np.log(e+1e-20),*(bands),np.log((f0 or 100)+1e-20)])

def dp_match(X,Y,note_cost=None):
    # robust scaled descriptors, monotonic gaps
    med=np.nanmedian(np.vstack([X,Y]),axis=0);sc=1.4826*np.nanmedian(np.abs(np.vstack([X,Y])-med),axis=0)+1e-4
    Xz=np.clip((X-med)/sc,-5,5);Yz=np.clip((Y-med)/sc,-5,5)
    C=cdist(Xz,Yz,metric='euclidean')/np.sqrt(X.shape[1])
    if note_cost is not None:C+=note_cost
    n,m=C.shape;gap=1.15;dp=np.full((n+1,m+1),np.inf);bt=np.zeros((n+1,m+1),np.int8);dp[0,0]=0
    for i in range(1,n+1):dp[i,0]=i*gap;bt[i,0]=1
    for j in range(1,m+1):dp[0,j]=j*gap;bt[0,j]=2
    for i in range(1,n+1):
        for j in range(1,m+1):
            v=(dp[i-1,j-1]+C[i-1,j-1],dp[i-1,j]+gap,dp[i,j-1]+gap);k=int(np.argmin(v));dp[i,j]=v[k];bt[i,j]=k
    i,j=n,m;out=[]
    while i or j:
        k=bt[i,j] if i and j else (1 if i else 2)
        if k==0:out.append((i-1,j-1,float(C[i-1,j-1])));i-=1;j-=1
        elif k==1:i-=1
        else:j-=1
    out=out[::-1]
    if out:
        lim=max(2.8,np.percentile([z[2] for z in out],92));out=[z for z in out if z[2]<=lim]
    return out

def detect_mono(y,fexp):
    cand,grid,oe,hop=onset_candidates(y,.30,.6)
    vals=[]
    for t in grid:
        if t<.15 or t>len(y)/SR-.25:continue
        f,_=f0_refine(y,t,.6,fexp);a=amp_sine(y[int((t+.10)*SR):int(min(len(y),(t+.45)*SR))],f)
        vals.append((t,db(a),f))
    if not vals:return []
    levels=np.array([v[1] for v in vals]);thr=np.percentile(levels,25)+.28*(np.percentile(levels,80)-np.percentile(levels,25))
    active=[v for v in vals if v[1]>=thr]
    # longest dense span
    if active:
        inds=[vals.index(v) for v in active];lo,hi=min(inds),max(inds);active=vals[lo:hi+1]
    return [dict(time=float(t),f0=float(f),level=float(l),expected=fexp) for t,l,f in active]

def chrom_frets_100():
    fr=[]
    for st in range(1,26):fr.extend(range(st,st+4))
    return fr
CH_FRETS=chrom_frets_100(); CH_FREQ=np.array([130.81278265*2**(fr/12) for fr in CH_FRETS])

def detect_chrom(y):
    # scan phase 1.8-3.2 using first 20 expected notes
    phases=np.arange(1.8,3.21,.01);scores=[]
    for st in phases:
        vv=[]
        for k,f in enumerate(CH_FREQ[:20]):
            a=int((st+k*.3+.055)*SR);b=int((st+k*.3+.25)*SR)
            if b>len(y):break
            vv.append(db(amp_sine(y[a:b],f)))
        scores.append(np.nanmedian(vv) if vv else -999)
    st=float(phases[int(np.argmax(scores))]);events=[]
    # local onset refinement ±35 ms and f0 confirmation
    oe=onsets.onset_strength(y,SR,hop_length=64,n_fft=1024);ot=np.arange(len(oe))*64/SR
    for k,(fr,fe) in enumerate(zip(CH_FRETS,CH_FREQ)):
        tg=st+k*.3;m=(ot>=tg-.035)&(ot<=tg+.035);t=float(ot[m][np.argmax(oe[m])]) if m.any() else tg
        f,_=f0_refine(y,t,.3,fe);events.append(dict(time=t,f0=f,level=db(amp_sine(y[int((t+.055)*SR):int(min(len(y),(t+.24)*SR))],f)),expected=fe,fret=fr,index=k))
    return events

def detect_chord(y):
    cand,grid,oe,hop=onset_candidates(y,.30,.6);vals=[]
    for t in grid:
        if t<.15 or t>len(y)/SR-.25:continue
        s=y[int((t+.04)*SR):int(min(len(y),(t+.45)*SR))];vals.append((t,db(np.sqrt(np.mean(s*s)+1e-30))))
    if not vals:return []
    lv=np.array([x[1] for x in vals]);thr=np.percentile(lv,25)+.32*(np.percentile(lv,80)-np.percentile(lv,25));act=[x for x in vals if x[1]>=thr]
    if act:
        inds=[vals.index(v) for v in act];act=vals[min(inds):max(inds)+1]
    return [dict(time=float(t),f0=np.nan,level=float(l),expected=np.nan) for t,l in act]

def detect_and_match(key,p):
    yc,_=load(p['cafe']);ya,_=load(p['azul'])
    if p['kind']=='mono':ec=detect_mono(yc,p['f0']);ea=detect_mono(ya,p['f0']);period=.6
    elif p['kind']=='chromatic':ec=detect_chrom(yc);ea=detect_chrom(ya);period=.3
    else:ec=detect_chord(yc);ea=detect_chord(ya);period=.6
    X=np.vstack([event_descriptor(yc,e['time'],period,None if p['kind']=='chord' else e['expected']) for e in ec]) if ec else np.empty((0,9))
    Y=np.vstack([event_descriptor(ya,e['time'],period,None if p['kind']=='chord' else e['expected']) for e in ea]) if ea else np.empty((0,9))
    note=None
    if p['kind']=='chromatic':
        note=np.abs(np.subtract.outer(np.arange(len(ec)),np.arange(len(ea))))*.55
    matches=dp_match(X,Y,note) if len(ec) and len(ea) else []
    return yc,ya,ec,ea,matches,period

# ---------- phase windows and spectral extraction ----------
def phase_bounds(period):
    """Nominal phase windows; `low` follows V4.1 (onset+60 ms → +760 ms)."""
    if period<.4:
        bounds={
            'attack':(0,.045),'stabilization':(.045,.090),'body':(.09,.175),
            'sustain':(.175,.255),'decay':(.225,.285),
            # Short notes: keep a longer low window when IOI allows; else extract falls back.
            'low':(.060, min(.760, max(.240, period*.90))),
        }
        return bounds
    return {
        'attack':(0,.075),'stabilization':(.075,.155),'body':(.155,.32),
        'sustain':(.32,.49),'decay':(.44,.56),'low':(.060,.760),
    }

def extract_seg(y,t,a,b,next_t=None,min_duration=0.0):
    end=t+b
    if next_t is not None:end=min(end,next_t-.050 if min_duration>0 else next_t-.012)
    aa=int(max(0,(t+a)*SR));bb=int(min(len(y),end*SR))
    seg=y[aa:bb]
    if min_duration>0 and len(seg)<int(min_duration*SR):
        return None  # caller may fall back to sustain
    return seg

def multitaper_psd(seg):
    seg=np.asarray(seg,float)
    if len(seg)<128:return None,None
    # V4.1: linear detrend before windowing (kills slow drift / false sub-bass).
    seg=signal.detrend(seg, type='linear')
    n=len(seg);nfft=1<<int(np.ceil(np.log2(max(2048,n*4))))
    nfft=min(nfft,65536);tapers=signal.windows.dpss(n,2.5,Kmax=3,sym=False)
    P=[]
    for w in tapers:
        X=np.fft.rfft(seg*w,nfft);P.append(np.abs(X)**2/(np.sum(w*w)*SR+1e-30))
    return np.fft.rfftfreq(nfft,1/SR),np.mean(P,axis=0)

def subtract_noise_floor(freqs, P, nfreqs, nP):
    """Subtract pre-onset noise PSD (V4.1); floor at tiny fraction of signal."""
    if P is None or nP is None or nfreqs is None: return P
    floor=np.interp(freqs, nfreqs, nP, left=nP[0], right=nP[-1])
    return np.maximum(P - floor, P * 1e-8)

def local_tonal(P,freqs,ftarget):
    if P is None or ftarget<20 or ftarget>20000:return np.nan,np.nan,np.nan,np.nan
    df=freqs[1]-freqs[0];tol=max(2.0,ftarget*.004);m=(freqs>=ftarget-tol)&(freqs<=ftarget+tol)
    if not m.any():return np.nan,np.nan,np.nan,np.nan
    ids=np.where(m)[0];i=ids[np.argmax(P[m])];fp=freqs[i]
    rad=max(1,int(round(max(1.5,ftarget*.0015)/df)));lo=max(1,i-rad);hi=min(len(P)-1,i+rad+1)
    val=np.sum(P[lo:hi]);gap=rad+2;width=max(4,2*rad+1)
    sb=np.r_[P[max(1,lo-gap-width):max(1,lo-gap)],P[min(len(P),hi+gap):min(len(P),hi+gap+width)]]
    noise=np.median(sb) if len(sb) else 0;ton=max(val-noise*(hi-lo),1e-30);snr=dbp((val+1e-30)/(noise*(hi-lo)+1e-30))
    return float(fp),float(ton),float(snr),float(noise)

def band_power(P,freqs,fc,bpo=6):
    if P is None:return np.nan,np.nan
    r=2**(1/(2*bpo));lo=fc/r;hi=fc*r;m=(freqs>=lo)&(freqs<hi)
    if m.sum()<2:return np.nan,np.nan
    val=np.trapz(P[m],freqs[m]);# local floor side zones
    s=((freqs>=lo/r)&(freqs<lo))|((freqs>=hi)&(freqs<hi*r));noise=np.median(P[s])*(hi-lo) if s.any() else 0
    musical=max(val-noise,1e-30);snr=dbp((val+1e-30)/(noise+1e-30));return float(musical),float(snr)

def noise_profile(y,events,period):
    chunks=[]
    # pre/post
    chunks.append(y[:int(min(1.3,len(y)/SR*.12)*SR)]);chunks.append(y[int(max(0,len(y)-1.0*SR)):])
    for i,e in enumerate(events[:-1]):
        a=e['time']+period*.90;b=events[i+1]['time']-.03
        if b-a>.04:chunks.append(y[int(a*SR):int(b*SR)])
    z=np.concatenate([c for c in chunks if len(c)>128]) if chunks else y[:4096]
    f,P=signal.welch(z-np.mean(z),SR,nperseg=min(8192,len(z)),noverlap=min(4096,max(0,len(z)//2)),scaling='density')
    return f,P,float(np.sqrt(np.mean(z*z)+1e-30))

def extract_pair(key,p,yc,ya,ec,ea,matches,period):
    rows=[];fund=[];match_rows=[];win_rows=[];attack_rows=[];gap_rows=[];traj=[]
    # Pre-onset noise floors — now applied to phase PSDs (V21 / V4.1 bajos).
    nfc,npc,nrc=noise_profile(yc,ec,period);nfa,npa,nra=noise_profile(ya,ea,period)
    bounds=phase_bounds(period)
    band_centers=np.geomspace(40,16000,48)
    for mi,(ic,ia,cost) in enumerate(matches):
        ce,ae=ec[ic],ea[ia];tc,ta=ce['time'],ae['time'];nc=ec[ic+1]['time'] if ic+1<len(ec) else None;na=ea[ia+1]['time'] if ia+1<len(ea) else None
        fexp=(ce.get('expected') if np.isfinite(ce.get('expected',np.nan)) else p.get('f0'))
        fc=ce.get('f0',fexp);fa=ae.get('f0',fexp);fgeom=float(np.sqrt(fc*fa)) if np.isfinite(fc) and np.isfinite(fa) else np.nan
        match_rows.append(dict(pair=key,event_cafe=ic,event_azul=ia,time_cafe=tc,time_azul=ta,lag_ms=(ta-tc)*1000,match_cost=cost,f0_cafe=fc,f0_azul=fa,note_error_cents=1200*np.log2((fa+1e-30)/(fc+1e-30)) if np.isfinite(fgeom) else np.nan,confidence='high' if cost<1 else 'medium' if cost<2 else 'low',status='accepted'))
        if ic+1<len(ec):
            ioi=ec[ic+1]['time']-tc; gap_rows.append(dict(pair=key,event=mi,ioi_cafe_s=ioi,ioi_azul_s=(ea[ia+1]['time']-ta) if ia+1<len(ea) else np.nan,nominal_period_s=period,silence_cafe_s=max(0,ioi-period*.88),overlap_cafe_s=max(0,period*.88-ioi),classification='overlap' if ioi<period*.82 else 'clean'))
        phase_data={}
        # Pre-extract sustain for low-window fallback (V4.1 min 180 ms).
        sus_a,sus_b=bounds['sustain']
        sc_sus=extract_seg(yc,tc,sus_a,sus_b,nc);sa_sus=extract_seg(ya,ta,sus_a,sus_b,na)
        for ph,(a,b) in bounds.items():
            min_dur=0.180 if ph=='low' else 0.0
            sc=extract_seg(yc,tc,a,b,nc,min_duration=min_dur)
            sa=extract_seg(ya,ta,a,b,na,min_duration=min_dur)
            used_fallback=False
            if ph=='low' and (sc is None or sa is None):
                sc=sc_sus;sa=sa_sus;used_fallback=True
            if sc is None or sa is None or len(sc)<128 or len(sa)<128:
                continue
            fpc,Pc=multitaper_psd(sc);fpa,Pa=multitaper_psd(sa)
            Pc=subtract_noise_floor(fpc,Pc,nfc,npc);Pa=subtract_noise_floor(fpa,Pa,nfa,npa)
            phase_data[ph]=(sc,sa,fpc,Pc,fpa,Pa)
            end_c=min(tc+b,nc-.050 if (nc and ph=='low') else (nc-.012 if nc else tc+b))
            end_a=min(ta+b,na-.050 if (na and ph=='low') else (na-.012 if na else ta+b))
            win_rows.append(dict(pair=key,event=mi,phase=ph,start_cafe=tc+a,end_cafe=end_c,start_azul=ta+a,end_azul=end_a,duration_cafe_ms=len(sc)/SR*1000,duration_azul_ms=len(sa)/SR*1000,cycles_cafe=(fc*len(sc)/SR) if np.isfinite(fc) else np.nan,cycles_azul=(fa*len(sa)/SR) if np.isfinite(fa) else np.nan,resolution_hz_cafe=SR/(max(2048,1<<int(np.ceil(np.log2(max(128,len(sc)*4)))))) if len(sc) else np.nan,low_fallback_sustain=int(used_fallback)))
            # Peak PSD for relative-energy scores (V4.1 −58/−68/−82 dB floors).
            max_pc=float(np.max(Pc)) if Pc is not None and len(Pc) else np.nan
            max_pa=float(np.max(Pa)) if Pa is not None and len(Pa) else np.nan
            # fundamental absolute
            if np.isfinite(fgeom):
                ac=amp_sine(sc,fc);aa=amp_sine(sa,fa)
                _,pc_f,snc,_=local_tonal(Pc,fpc,fc);_,pa_f,sna,_=local_tonal(Pa,fpa,fa)
                dd=db(aa)-db(ac)
                rel=min(
                    dbp(pc_f)-dbp(max_pc) if np.isfinite(pc_f) and np.isfinite(max_pc) else np.nan,
                    dbp(pa_f)-dbp(max_pa) if np.isfinite(pa_f) and np.isfinite(max_pa) else np.nan,
                )
                fund.append(dict(pair=key,family=fam(key),string=string_of(key),register=register_of(fgeom),event=mi,phase=ph,f=fgeom,f0=fgeom,y=dd,snr=min(snc,sna),rel_db=rel,match_cost=cost,kind='fundamental',weight_base=PHASE_W[ph]))
                traj.append(dict(pair=key,event=mi,phase=ph,f0_cafe_hz=fc,f0_azul_hz=fa,amplitude_cafe=ac,amplitude_azul=aa,delta_db=dd,snr_cafe=snc,snr_azul=sna))
                # Open strings: allow harmonics through OPEN_SOFT_HZ; soft mask in v12.
                if not (fam(key)=='open'):
                    maxk=min(48,int(16000/max(fgeom,1)))
                else:maxk=min(12,int(OPEN_SOFT_HZ/max(fgeom,1)))
                _,pc0,snc0,_=local_tonal(Pc,fpc,fc);_,pa0,sna0,_=local_tonal(Pa,fpa,fa)
                for k in range(2,maxk+1):
                    ftc=k*fc;fta=k*fa;ft=np.sqrt(ftc*fta)
                    fmc,pc,snc,_=local_tonal(Pc,fpc,ftc);fma,pa_,sna,_=local_tonal(Pa,fpa,fta)
                    if not np.isfinite(pc) or min(snc,sna,snc0,sna0)<8:continue
                    yy=(dbp(pa_)-dbp(pa0))-(dbp(pc)-dbp(pc0))
                    common=min(dbp(pc),dbp(pa_));wenergy=np.clip(10**((common-max(dbp(pc0),dbp(pa0)))/20),.03,1)
                    rel_h=min(
                        dbp(pc)-dbp(max_pc) if np.isfinite(max_pc) else np.nan,
                        dbp(pa_)-dbp(max_pa) if np.isfinite(max_pa) else np.nan,
                    )
                    rows.append(dict(pair=key,family=fam(key),string=string_of(key),register=register_of(fgeom),event=mi,phase=ph,f=float(ft),f0=fgeom,y=float(yy),snr=float(min(snc,sna)),rel_db=rel_h,match_cost=cost,kind='tonal_harmonic',weight_base=PHASE_W[ph]*wenergy,harmonic=k,frequency_cafe=fmc,frequency_azul=fma))
        # attack multiscale and band residual relative to body f0 delta
        if np.isfinite(fgeom):
            body=[z for z in fund if z['pair']==key and z['event']==mi and z['phase']=='body']
            d0=body[-1]['y'] if body else np.nan
            for lo_ms,hi_ms in [(0,5),(5,10),(10,20),(20,40),(40,80),(80,160)]:
                sc=extract_seg(yc,tc,lo_ms/1000,hi_ms/1000,nc);sa=extract_seg(ya,ta,lo_ms/1000,hi_ms/1000,na)
                if sc is None or sa is None: continue
                fpc,Pc=multitaper_psd(sc);fpa,Pa=multitaper_psd(sa)
                Pc=subtract_noise_floor(fpc,Pc,nfc,npc);Pa=subtract_noise_floor(fpa,Pa,nfa,npa)
                for bl,bh,bn in [(20,60,'20-60'),(60,150,'60-150'),(150,500,'150-500'),(500,2000,'500-2000'),(2000,5000,'2000-5000'),(5000,10000,'5000-10000')]:
                    if Pc is None:continue
                    mc=(fpc>=bl)&(fpc<bh);ma=(fpa>=bl)&(fpa<bh)
                    if mc.sum()<2 or ma.sum()<2:continue
                    ecv=np.trapz(Pc[mc],fpc[mc]);eav=np.trapz(Pa[ma],fpa[ma]);dd=dbp(eav)-dbp(ecv)
                    attack_rows.append(dict(pair=key,event=mi,window=f'{lo_ms}-{hi_ms}ms',band=bn,delta_db=dd,match_cost=cost))
            # band observations by phases (incl. low); open soft-stop at OPEN_SOFT_HZ
            for ph in ['attack','stabilization','body','sustain','low']:
                if ph not in phase_data: continue
                sc,sa,fpc,Pc,fpa,Pa=phase_data[ph]
                max_pc=float(np.max(Pc)) if Pc is not None and len(Pc) else np.nan
                max_pa=float(np.max(Pa)) if Pa is not None and len(Pa) else np.nan
                for bc in band_centers:
                    if fam(key)=='open' and bc>OPEN_SOFT_HZ:continue
                    pc,snc=band_power(Pc,fpc,bc);pa_,sna=band_power(Pa,fpa,bc)
                    if min(snc,sna)<14 or not np.isfinite(d0):continue
                    yy=(dbp(pa_)-dbp(pc))-d0
                    rel_b=min(
                        dbp(pc)-dbp(max_pc) if np.isfinite(max_pc) else np.nan,
                        dbp(pa_)-dbp(max_pa) if np.isfinite(max_pa) else np.nan,
                    )
                    rows.append(dict(pair=key,family=fam(key),string=string_of(key),register=register_of(fgeom),event=mi,phase=ph,f=float(bc),f0=fgeom,y=float(yy),snr=float(min(snc,sna)),rel_db=rel_b,match_cost=cost,kind='band_residual',weight_base=PHASE_W[ph]*.10,harmonic=np.nan,frequency_cafe=bc,frequency_azul=bc))
    return rows,fund,match_rows,win_rows,attack_rows,gap_rows,traj

# ---------- model ----------
LOW_NODES=np.array([20,22,25,28,30.87,35,41.2,48,55,61.74,70,80,90,100,110,120],float)
MID_NODES=np.geomspace(130,2500,40);HIGH_NODES=np.geomspace(2600,20000,30)
QN=np.unique(np.r_[LOW_NODES,MID_NODES,HIGH_NODES]);NQ=len(QN)
REGS=['sub','low','mid','high'];NF=1+len(STRINGS)+len(REGS)+len(PHASES);NP=NF+NQ
IG=0;IS=1;IR=IS+len(STRINGS);IP=IR+len(REGS);IQ=IP+len(PHASES)

def qrow(f,sign=1):
    x=np.log(np.clip(f,QN[0],QN[-1]));xn=np.log(QN)
    if x<=xn[0]:return [(0,sign)]
    if x>=xn[-1]:return [(NQ-1,sign)]
    j=int(np.searchsorted(xn,x)-1);a=(x-xn[j])/(xn[j+1]-xn[j]);return [(j,sign*(1-a)),(j+1,sign*a)]

def design(o,model='JOINT'):
    x=np.zeros(NP)
    if o['kind']=='fundamental':
        x[IG]=1
        if model in ['JOINT','STRING']:x[IS+STRINGS.index(o['string'])]=1
        x[IR+REGS.index(o['register'])]=1;x[IP+PHASES.index(o['phase'])]=1
        if model in ['JOINT','FREQUENCY']:
            for j,c in qrow(o['f']):x[IQ+j]+=c
    else:
        if model in ['JOINT','FREQUENCY']:
            for j,c in qrow(o['f']):x[IQ+j]+=c
            for j,c in qrow(o['f0'],-1):x[IQ+j]+=c
    return x

def prepare_obs(obs,model='JOINT'):
    df=pd.DataFrame(obs).copy();df=df[np.isfinite(df.y)&np.isfinite(df.snr)&(df.snr>=8)&(df.match_cost<=3)].copy()
    # cap pathological ratios; strict for residual
    df=df[np.abs(df.y)<=18]
    df['g']=df.pair.astype(str)+'|'+df.phase.astype(str)+'|'+df.kind.astype(str)
    raw=df.weight_base*np.clip((df.snr-6)/24,.08,1.5)*np.clip(1-df.match_cost/4,.15,1)
    # family/pair balance: every pair-kind-phase unit gets equal total, then family equal
    df['wraw']=raw
    sums=df.groupby('g').wraw.transform('sum').clip(lower=1e-12);df['w']=df.wraw/sums
    fs=df.groupby('family').w.transform('sum').clip(lower=1e-12);df['w']/=fs;df['w']*=df.family.nunique()
    X=np.vstack([design(r,model) for r in df.to_dict('records')]);return df,X,df.y.to_numpy(float),df.w.to_numpy(float)

def penalties(lam_low,lam_mid,lam_high,shrink=1.0,model='JOINT',support=None):
    A=[];b=[];w=[]
    if model in ['JOINT','FREQUENCY']:
        for j in range(1,NQ-1):
            r=np.zeros(NP);r[IQ+j-1]=1;r[IQ+j]=-2;r[IQ+j+1]=1;f=QN[j]
            la=lam_low if f<=120 else lam_mid if f<=2500 else lam_high;A.append(r);b.append(0);w.append(la)
        # endpoint and unsupported shrink
        for j,f in enumerate(QN):
            sup=0 if support is None else support[j]
            if f<28 or f>12000: s=40*shrink
            elif sup<1:s=15*shrink
            elif sup<2:s=4*shrink
            else:s=.05*shrink
            r=np.zeros(NP);r[IQ+j]=1;A.append(r);b.append(0);w.append(s)
        # Q mean anchor 30-2500
        r=np.zeros(NP);m=(QN>=30)&(QN<=2500);r[IQ+np.where(m)[0]]=1/m.sum();A.append(r);b.append(0);w.append(300)
    # zero-sum nuisances
    for start,n in [(IS,len(STRINGS)),(IR,len(REGS)),(IP,len(PHASES))]:
        r=np.zeros(NP);r[start:start+n]=1/n;A.append(r);b.append(0);w.append(300)
    return np.asarray(A),np.asarray(b),np.asarray(w)

def node_support(df):
    s=[]
    for f in QN:
        m=np.abs(np.log2(df.f/f))<=1/12;s.append(df.loc[m,'pair'].nunique())
    return np.asarray(s)

def fit_model(obs,lams,model='JOINT',exclude=None,irls=5):
    df,X,y,w=prepare_obs(obs,model)
    if exclude is not None:
        keep=df.pair!=exclude;df=df[keep].copy();X=X[keep];y=y[keep];w=w[keep]
    sup=node_support(df);A,b,pw=penalties(*lams,model=model,support=sup)
    beta=np.zeros(NP);rw=np.ones(len(y))
    for _ in range(irls):
        ww=w*rw;M=X.T@(ww[:,None]*X)+A.T@(pw[:,None]*A)+np.eye(NP)*1e-8;v=X.T@(ww*y)+A.T@(pw*b)
        beta=np.linalg.solve(M,v);res=y-X@beta;sc=robust_scale(res);u=np.abs(res)/(1.5*sc);rw=np.where(u<=1,1,1/u)
    return beta,df,sup

def eval_q(beta,f=DENSE_F):
    out=[]
    for ff in f:
        out.append(sum(beta[IQ+j]*c for j,c in qrow(ff)))
    return np.array(out)

def predict_rows(beta,df,model='JOINT'):
    X=np.vstack([design(r,model) for r in df.to_dict('records')]);return X@beta

_LC,_LR,_CANDS_CFG=run_config.lambdas()
CANDS=_CANDS_CFG or [(20,5,20,.7),(50,10,40,1),(100,20,80,1),(200,40,150,1.2),(400,80,300,1.5),(80,8,20,.7),(160,15,50,1),(300,30,100,1.3)]

def cross_validate(obs):
    """Score every lambda candidate; honour a fixed selection when configured.

    The candidates' central_score differ by <0.08, so picking the argmin is not
    reproducible across runs. `lambda_mode: fixed` keeps the CV table for
    auditing but returns the configured value.
    """
    pairs=sorted(set(o['pair'] for o in obs));rows=[]
    for ci,c in enumerate(CANDS):
        for hold in pairs:
            b,_,_=fit_model(obs,c,'JOINT',hold,4)
            d,X,y,w=prepare_obs([o for o in obs if o['pair']==hold],'JOINT')
            if len(d)==0:continue
            r=y-X@b
            rows.append(dict(candidate=ci,params=str(c),holdout=hold,mae=np.average(np.abs(r),weights=w),rmse=np.sqrt(np.average(r*r,weights=w)),p90=weighted_quantile(np.abs(r),w,.9),p95=weighted_quantile(np.abs(r),w,.95),sub_mae=np.average(np.abs(r[d.f<60]),weights=w[d.f<60]) if (d.f<60).any() else np.nan,high_mae=np.average(np.abs(r[d.f>=2500]),weights=w[d.f>=2500]) if (d.f>=2500).any() else np.nan))
    cv=pd.DataFrame(rows);cv.to_csv(OUT/'VALIDACION_CANDIDATOS_V10_2.csv',index=False)
    ag=cv.groupby('candidate').agg(mae=('mae','median'),rmse=('rmse','mean'),p90=('p90','mean'),p95=('p95','mean'),sub_mae=('sub_mae','mean'),high_mae=('high_mae','mean')).reset_index()
    # central: median MAE/rmse; robust: p90/p95 and no-degradation
    ag['central_score']=ag.mae+.25*ag.rmse+.15*ag.sub_mae.fillna(0)
    ag['robust_score']=.45*ag.p90+.45*ag.p95+.10*ag.sub_mae.fillna(0)
    ic=int(ag.loc[ag.central_score.idxmin(),'candidate']);ir=int(ag.loc[ag.robust_score.idxmin(),'candidate'])
    ag['cv_argmin_central']=ag.candidate==ic;ag['cv_argmin_robust']=ag.candidate==ir
    lc=_LC if _LC is not None else CANDS[ic]
    lr=_LR if _LR is not None else CANDS[ir]
    ag['selected_central']=[tuple(c)==tuple(lc) for c in CANDS]
    ag['selected_robust']=[tuple(c)==tuple(lr) for c in CANDS]
    ag['lambda_mode']='fixed' if _LC is not None else 'cv'
    ag.to_csv(OUT/'SELECCION_MODELOS_V10_2.csv',index=False)
    return lc,lr,cv,ag

# fixed old curves with nuisance refit using synthetic Q values
def load_old_curve(kind):
    if kind=='V9':
        path=LEGACY/'curva_v9_puntos.csv'
        if not path.exists():
            return None
        d=pd.read_csv(path);return lambda f:interp_log(f,d.frequency_hz,d.eq_v9_db)
    path=LEGACY/'curva_v10_1_densa.csv'
    if not path.exists():
        return None
    d=pd.read_csv(path);return lambda f:interp_log(f,d.frequency_hz,d.eq_precise_db)

def fit_nuisance_fixed(obs,qfun,exclude=None):
    df=pd.DataFrame(obs);df=df[np.isfinite(df.y)&np.isfinite(df.snr)&(df.snr>=8)&(df.match_cost<=3)&(np.abs(df.y)<=18)].copy()
    if exclude is not None:df=df[df.pair!=exclude]
    # nuisance G string reg phase only; subtract fixed Q contribution
    Z=[];yy=[];ww=[]
    for r in df.to_dict('records'):
        z=np.zeros(NF);qv=qfun(r['f']) if r['kind']=='fundamental' else qfun(r['f'])-qfun(r['f0'])
        if r['kind']=='fundamental':
            z[IG]=1;z[IS+STRINGS.index(r['string'])]=1;z[IR+REGS.index(r['register'])]=1;z[IP+PHASES.index(r['phase'])]=1
        Z.append(z);yy.append(r['y']-qv);ww.append(r['weight_base']*np.clip((r['snr']-6)/24,.08,1.5))
    Z=np.asarray(Z);yy=np.asarray(yy);ww=np.asarray(ww);A=[]
    for st,n in [(IS,len(STRINGS)),(IR,len(REGS)),(IP,len(PHASES))]:
        r=np.zeros(NF);r[st:st+n]=1/n;A.append(r)
    A=np.asarray(A);M=Z.T@(ww[:,None]*Z)+A.T@(300*np.ones((len(A),1))*A)+np.eye(NF)*1e-8;v=Z.T@(ww*yy);return np.linalg.solve(M,v)

def eval_old(obs,name):
    q=load_old_curve(name)
    if q is None:
        return pd.DataFrame(columns=['model','pair','mae','rmse','p90','p95'])
    rows=[]
    for hold in sorted(set(o['pair'] for o in obs)):
        nu=fit_nuisance_fixed(obs,q,hold);test=[o for o in obs if o['pair']==hold];df=pd.DataFrame(test)
        rr=[];ww=[]
        for r in test:
            pred=(nu[IG]+nu[IS+STRINGS.index(r['string'])]+nu[IR+REGS.index(r['register'])]+nu[IP+PHASES.index(r['phase'])]+q(r['f'])) if r['kind']=='fundamental' else q(r['f'])-q(r['f0'])
            rr.append(r['y']-pred);ww.append(r['weight_base']*np.clip((r['snr']-6)/24,.08,1.5))
        rows.append(dict(model=name,pair=hold,mae=np.average(np.abs(rr),weights=ww),rmse=np.sqrt(np.average(np.array(rr)**2,weights=ww)),p90=weighted_quantile(np.abs(rr),ww,.9),p95=weighted_quantile(np.abs(rr),ww,.95)))
    return pd.DataFrame(rows)

# ---------- bootstrap/support/variants ----------
def bootstrap(obs,lams,n=160):
    pairs=sorted(set(o['pair'] for o in obs));curves=[];g=[];offs=[]
    for k in range(n):
        samp=list(RNG.choice(pairs,len(pairs),replace=True));boot=[]
        for ii,p in enumerate(samp):
            for o in obs:
                if o['pair']==p:
                    z=o.copy();z['pair']=f'{p}__b{ii}';boot.append(z)
        try:b,_,_=fit_model(boot,lams,'JOINT',None,3);curves.append(eval_q(b));g.append(b[IG]);offs.append(b[IS:IS+6])
        except Exception:pass
    return np.asarray(curves),np.asarray(g),np.asarray(offs)

def support_dense(df):
    rows=[]
    for f in DENSE_F:
        m=np.abs(np.log2(df.f/f))<=1/12;z=df[m]
        ep=z.pair.nunique();ss=z.string.nunique();ff=z.family.nunique();sn=np.nanmedian(z.snr) if len(z) else np.nan
        # max pair influence by total weight
        inf=(z.groupby('pair').w.sum()/z.w.sum()).max() if len(z) and z.w.sum()>0 else np.nan
        if ep>=5 and ss>=3 and ff>=2:state='Medido robustamente'
        elif ep>=2 and ff>=1:state='Medido con incertidumbre'
        elif ep>=1:state='Inferido localmente'
        else:state='No identificado'
        rows.append((ep,ss,ff,sn,inf,state))
    return rows

def make_variants(beta_c,beta_r,boot,df):
    qc=eval_q(beta_c);qr=eval_q(beta_r)
    # robust blend chosen model itself; safe shrink by CI/support
    sup=support_dense(df);ep=np.array([x[0] for x in sup]);states=[x[5] for x in sup]
    lo=np.percentile(boot,2.5,axis=0);hi=np.percentile(boot,97.5,axis=0)
    strength=np.clip(ep/5,0,1)*np.clip(np.abs((lo+hi)/2)/(np.maximum((hi-lo)/2,.25)),0,1)
    safe=qc*(.35+.55*strength)
    # force unknown endpoints toward zero smoothly
    safe[DENSE_F<28]*=np.linspace(0,1,(DENSE_F<28).sum())
    highmask=DENSE_F>8000;safe[highmask]*=np.clip((12000-DENSE_F[highmask])/4000,0,1)
    no_sub=qc.copy();m=DENSE_F<60;no_sub[m]=0;blend=(DENSE_F>=60)&(DENSE_F<80);no_sub[blend]*=(DENSE_F[blend]-60)/20
    # choose high cutoff from support: last robust/moderate point, limited 8k
    valid=np.where((ep>=2)&(DENSE_F<=12000))[0];cut=DENSE_F[valid[-1]] if len(valid) else 4000;cut=min(max(cut,4000),8000)
    no_high=qc.copy();no_high[DENSE_F>=cut*1.5]=0;m=(DENSE_F>cut)&(DENSE_F<cut*1.5);no_high[m]*=.5*(1+np.cos(np.pi*(DENSE_F[m]-cut)/(cut*.5)))
    # parametric 7 bells fit
    centers=np.array([31,55,120,300,700,1400,3200],float);Qs=np.array([1.5,1.5,.8,.7,.7,.8,.9])
    def bell(f,fc,q,g):
        x=np.log2(f/fc);sigma=1/(2*q);return g*np.exp(-.5*(x/sigma)**2)
    A=np.column_stack([bell(DENSE_F,c,q,1) for c,q in zip(centers,Qs)])
    weights=np.clip(ep,0,6)+.2;gains=np.linalg.solve(A.T@(weights[:,None]*A)+np.eye(len(centers))*.3,A.T@(weights*qc));param=A@gains
    return qc,qr,safe,param,no_sub,no_high,lo,hi,sup,cut,centers,Qs,gains

# ---------- validation and significance ----------
def curve_fun(q):return lambda f:interp_log(f,DENSE_F,q)

def residuals_curve(obs,beta,q):
    qf=curve_fun(q);rows=[]
    for o in obs:
        if o['kind']=='fundamental':pred=beta[IG]+beta[IS+STRINGS.index(o['string'])]+beta[IR+REGS.index(o['register'])]+beta[IP+PHASES.index(o['phase'])]+qf(o['f'])
        else:pred=qf(o['f'])-qf(o['f0'])
        rows.append({**o,'resid':o['y']-pred})
    return pd.DataFrame(rows)

def metric_table(res,model):
    out=[]
    for pair,z in res.groupby('pair'):
        w=z.weight_base*np.clip((z.snr-6)/24,.08,1.5);a=np.abs(z.resid)
        out.append(dict(model=model,pair=pair,mae=np.average(a,weights=w),rmse=np.sqrt(np.average(z.resid**2,weights=w)),p75=weighted_quantile(a,w,.75),p90=weighted_quantile(a,w,.9),p95=weighted_quantile(a,w,.95),improved=np.nan))
    return pd.DataFrame(out)

def local_metrics(res,model):
    rr=[]
    for lo,hi,n in REGIONS:
        z=res[(res.f>=lo)&(res.f<hi)]
        if len(z):
            w=z.weight_base*np.clip((z.snr-6)/24,.08,1.5);a=np.abs(z.resid);rr.append(dict(model=model,region=n,n=len(z),pairs=z.pair.nunique(),mae=np.average(a,weights=w),rmse=np.sqrt(np.average(z.resid**2,weights=w)),p90=weighted_quantile(a,w,.9),p95=weighted_quantile(a,w,.95)))
    for ph,z in res.groupby('phase'):
        w=z.weight_base*np.clip((z.snr-6)/24,.08,1.5);a=np.abs(z.resid);rr.append(dict(model=model,region='phase_'+ph,n=len(z),pairs=z.pair.nunique(),mae=np.average(a,weights=w),rmse=np.sqrt(np.average(z.resid**2,weights=w)),p90=weighted_quantile(a,w,.9),p95=weighted_quantile(a,w,.95)))
    return pd.DataFrame(rr)

def paired_significance(res_a,res_b,label,nboot=1000):
    # positive = b error - a error, a improves
    pa=res_a.groupby('pair').apply(lambda z:np.average(np.abs(z.resid),weights=z.weight_base)).to_dict();pb=res_b.groupby('pair').apply(lambda z:np.average(np.abs(z.resid),weights=z.weight_base)).to_dict();keys=sorted(set(pa)&set(pb));d=np.array([pb[k]-pa[k] for k in keys]);vals=[]
    for _ in range(nboot):vals.append(np.mean(RNG.choice(d,len(d),replace=True)))
    vals=np.asarray(vals);return dict(comparison=label,mean=float(np.mean(d)),median=float(np.median(d)),ci95_low=float(np.percentile(vals,2.5)),ci95_high=float(np.percentile(vals,97.5)),prob_improvement=float(np.mean(vals>0)),prob_gt_0_1=float(np.mean(vals>.1)),prob_gt_0_25=float(np.mean(vals>.25)),prob_gt_0_5=float(np.mean(vals>.5)),n_pairs=len(keys))

# ---------- rendering ----------
def fir_from_curve(q,numtaps=8193):
    f=np.r_[0,DENSE_F,SR/2];g=np.r_[q[0],q,q[-1]];a=10**(g/20);h=signal.firwin2(numtaps,f/(SR/2),a,window=('kaiser',7.5));return h

def apply_eq(y,h,gain):
    z=signal.fftconvolve(y-np.mean(y),h,mode='same')*10**(gain/20);return z.astype(np.float32)

def align_audio(x,y,lag_s):
    n=int(round(lag_s*SR))
    if n>0:x=np.pad(x,(n,0))
    elif n<0:y=np.pad(y,(-n,0))
    L=min(len(x),len(y));return x[:L],y[:L]

def render_all(curves,beta,matching):
    names=['PRECISE_CENTRAL','PRECISE_ROBUST','SAFE','PARAMETRIC','NO_SUB','NO_HIGH'];hs={n:fir_from_curve(q) for n,q in zip(names,curves)}
    gain=float(beta[IG]);summ=[]
    for key,p in PAIRS.items():
        yc,_=load(p['cafe']);ya,_=load(p['azul']);d=AUD/key;d.mkdir(parents=True,exist_ok=True)
        sf.write(d/'AZUL_ORIGINAL.flac',ya,SR,subtype='PCM_24');sf.write(d/'CAFE_ORIGINAL.flac',yc,SR,subtype='PCM_24')
        lag=matching[matching.pair==key].lag_ms.median()/1000 if (matching.pair==key).any() else 0
        rendered={}
        for n in names:
            z=apply_eq(yc,hs[n],gain);rendered[n]=z;sf.write(d/f'CAFE_{n}.flac',z,SR,subtype='PCM_24')
        xc,az=align_audio(rendered['PRECISE_CENTRAL'],ya,lag);sf.write(d/'ESTEREO_L_CAFE_CENTRAL_R_AZUL.flac',np.column_stack([xc,az]),SR,subtype='PCM_24')
        summ.append(dict(pair=key,lag_s=lag,gain_db=gain,duration_cafe=len(yc)/SR,duration_azul=len(ya)/SR))
    pd.DataFrame(summ).to_csv(OUT/'RENDER_INVENTORY_V10_2.csv',index=False)
    # representative alternated/filtered
    reps=['B_open','E_open','A_open','C_12','C_24','C_chromatic','Am7','Cmaj7']
    sil=np.zeros(int(.35*SR),np.float32)
    for key in reps:
        p=PAIRS[key];yc,_=load(p['cafe']);ya,_=load(p['azul']);zs=[apply_eq(yc,hs[n],gain) for n in names[:4]];L=min([len(ya)]+[len(z) for z in zs]);seq=[]
        for z in zs:seq.extend([z[:L],sil])
        seq.append(ya[:L]);rd=AUD/'PRUEBAS_RESUMIDAS';rd.mkdir(exist_ok=True);sf.write(rd/f'{key}__CENTRAL__ROBUST__SAFE__PARAMETRIC__AZUL.flac',np.concatenate(seq),SR,subtype='PCM_24')
        # central, no-sub, azul; diagnostics
        zc=apply_eq(yc,hs['PRECISE_CENTRAL'],gain);zn=apply_eq(yc,hs['NO_SUB'],gain);zh=apply_eq(yc,hs['NO_HIGH'],gain);L=min(len(zc),len(zn),len(zh),len(ya))
        sf.write(rd/f'{key}__CENTRAL__NO_SUB__NO_HIGH__AZUL.flac',np.r_[zc[:L],sil,zn[:L],sil,zh[:L],sil,ya[:L]],SR,subtype='PCM_24')
        for lo,hi in [(20,80),(20,120),(2000,8000)]:
            sos=signal.butter(6,[lo,hi],btype='bandpass',fs=SR,output='sos');seqf=[]
            for z in [zc[:L],zn[:L],zh[:L],ya[:L]]:seqf.extend([signal.sosfiltfilt(sos,z).astype(np.float32),sil])
            sf.write(rd/f'{key}__CENTRAL__NO_SUB__NO_HIGH__AZUL__{lo}_{hi}Hz.flac',np.concatenate(seqf),SR,subtype='PCM_24')

# ---------- outputs ----------
def plots(curve_df,raw,central,robust,safe,param,no_sub,no_high,attack,matching,windows,gaps,traj,metrics,local):
    plt.figure(figsize=(12,6));plt.semilogx(DENSE_F,raw,label='RAW',alpha=.65);plt.semilogx(DENSE_F,central,label='PRECISE-CENTRAL');plt.semilogx(DENSE_F,robust,label='PRECISE-ROBUST');plt.semilogx(DENSE_F,safe,label='SAFE');plt.axhline(0,color='k',lw=.6);plt.grid(True,which='both',alpha=.25);plt.legend();plt.xlabel('Hz');plt.ylabel('dB');plt.title('V10.2 — curvas principales');plt.tight_layout();plt.savefig(OUT/'01_CURVAS_PRINCIPALES.png',dpi=180);plt.close()
    plt.figure(figsize=(12,6));m=DENSE_F<=120;plt.plot(DENSE_F[m],central[m],label='CENTRAL');plt.plot(DENSE_F[m],robust[m],label='ROBUST');plt.plot(DENSE_F[m],no_sub[m],label='NO-SUB');plt.fill_between(DENSE_F[m],curve_df.ci95_low_db[m],curve_df.ci95_high_db[m],alpha=.2);plt.axhline(0,color='k',lw=.6);plt.grid(alpha=.25);plt.legend();plt.xlabel('Hz');plt.ylabel('dB');plt.title('20–120 Hz');plt.tight_layout();plt.savefig(OUT/'02_CURVA_20_120_LINEAR.png',dpi=180);plt.close()
    plt.figure(figsize=(12,6));m=(DENSE_F>=2000)&(DENSE_F<=12000);plt.semilogx(DENSE_F[m],central[m],label='CENTRAL');plt.semilogx(DENSE_F[m],robust[m],label='ROBUST');plt.semilogx(DENSE_F[m],no_high[m],label='NO-HIGH');plt.fill_between(DENSE_F[m],curve_df.ci95_low_db[m],curve_df.ci95_high_db[m],alpha=.2);plt.grid(alpha=.25);plt.legend();plt.xlabel('Hz');plt.ylabel('dB');plt.title('2–12 kHz');plt.tight_layout();plt.savefig(OUT/'03_CURVA_2_12KHZ.png',dpi=180);plt.close()
    # support
    plt.figure(figsize=(12,5));plt.semilogx(DENSE_F,curve_df.effective_pairs,label='Parejas');plt.semilogx(DENSE_F,curve_df.strings,label='Cuerdas');plt.semilogx(DENSE_F,curve_df.families,label='Familias');plt.legend();plt.grid(alpha=.25);plt.title('Soporte independiente');plt.tight_layout();plt.savefig(OUT/'04_SOPORTE.png',dpi=180);plt.close()
    if len(attack):
        piv=attack.groupby(['window','band']).delta_db.median().unstack();plt.figure(figsize=(12,6));plt.imshow(piv.T,aspect='auto',origin='lower');plt.xticks(range(len(piv.index)),piv.index,rotation=45);plt.yticks(range(len(piv.columns)),piv.columns);plt.colorbar(label='Azul-Café dB');plt.title('Diferencia multiescala de ataque');plt.tight_layout();plt.savefig(OUT/'05_MAPA_ATAQUES.png',dpi=180);plt.close()
    # matching
    plt.figure(figsize=(12,5));plt.hist(matching.match_cost,bins=35);plt.xlabel('Costo');plt.title('Distribución de costo de matching');plt.tight_layout();plt.savefig(OUT/'06_MATCHING_COSTOS.png',dpi=180);plt.close()
    # windows cycles by frequency
    if len(windows):
        z=traj.merge(windows,on=['pair','event','phase']);plt.figure(figsize=(12,5));plt.scatter(z.f0_cafe_hz,z.cycles_cafe,s=5,alpha=.25);plt.xscale('log');plt.xlabel('F0 Hz');plt.ylabel('Ciclos usados');plt.grid(alpha=.25);plt.title('Resolución temporal por ciclos');plt.tight_layout();plt.savefig(OUT/'07_CICLOS_POR_FRECUENCIA.png',dpi=180);plt.close()
    # metrics models
    sm=metrics.groupby('model').agg(mae=('mae','mean'),p90=('p90','mean'),p95=('p95','mean')).reset_index();x=np.arange(len(sm));plt.figure(figsize=(12,5));plt.plot(x,sm.mae,'o-',label='MAE');plt.plot(x,sm.p90,'o-',label='P90');plt.plot(x,sm.p95,'o-',label='P95');plt.xticks(x,sm.model,rotation=30);plt.legend();plt.grid(alpha=.25);plt.tight_layout();plt.savefig(OUT/'08_METRICAS_MODELOS.png',dpi=180);plt.close()
    # phase curves: aggregate observed ratios by phase
    plt.figure(figsize=(12,6));
    for ph,z in curve_df.attrs.get('phase_curves',{}).items():plt.semilogx(DENSE_F,z,label=ph)
    if curve_df.attrs.get('phase_curves'):plt.legend();plt.grid(alpha=.25);plt.title('Curvas diagnósticas por fase');plt.tight_layout();plt.savefig(OUT/'09_CURVAS_POR_FASE.png',dpi=180)
    plt.close()

def report_files(curve_df,beta_c,beta_r,central,robust,safe,param,no_sub,no_high,cvagg,metrics,local,matching,signif,ident,cut,centers,Qs,gains,inventory):
    gain=float(beta_c[IG]);offs=beta_c[IS:IS+6]
    summary=curve_df.iloc[[np.argmin(abs(curve_df.frequency_hz-f)) for f in [20,28,30.87,41.2,55,80,120,250,500,630,800,1000,1250,1600,2000,2500,3150,4000,5000,6300,8000,10000,12500,16000,20000]]]
    lines=['# INFORME TÉCNICO AUTÓNOMO V10.2','', '## 1. Veredicto general',f'Gain global PRECISE-CENTRAL: **{gain:+.2f} dB**. V10.2 fue reextraída desde los WAV originales 20 Hz–20 kHz mediante matching monotónico, estimación individual de F0, multitaper DPSS, parciales relativos, ventanas temporales adaptadas y separación explícita de observaciones tonales y residuales.','','La curva principal no se reduce a un shelf: conserva únicamente rasgos que sobreviven validación agrupada y soporte independiente.','','## 2. Qué contienen realmente los audios',inventory.to_markdown(index=False),'','La cromática fue auditada como 100 eventos correspondientes a células solapadas hasta 25–28; los eventos se alinearon por identidad musical, tiempo y descriptores acústicos. Las cuerdas al aire tienen peso cero sobre 300 Hz.','','## 3. Calidad del matching',f'Eventos emparejados: **{len(matching)}**. Costo mediano: **{matching.match_cost.median():.3f}**. Matches de baja confianza: **{(matching.confidence=="low").sum()}**. No se forzaron eventos omitidos.','','## 4. Comportamiento temporal','Ataque, estabilización, cuerpo, sustain y decaimiento fueron modelados por separado. Los graves utilizan más ciclos y ventanas más largas; los mapas de ataque usan 0–5, 5–10, 10–20, 20–40, 40–80 y 80–160 ms. La EQ estática se pondera principalmente por cuerpo y sustain.','','## 5. Subgraves','B0, E1 y A1 conservan medición directa, pero cuerda y frecuencia siguen parcialmente confundidas. La comparación FREQUENCY/STRING/JOINT se entrega por separado. Entre 20 y 28 Hz no existe evidencia tonal directa suficiente y la implementación se regulariza hacia 0 dB.','','## 6. Medios','La zona 800 Hz–1,6 kHz fue reextraída desde los originales. Su amplitud final, intervalos, soporte y ablaciones aparecen en AUDITORIA_800_1600_HZ.csv; no se heredó el +5,67 dB de V10.1.','','## 7. Agudos',f'La curva distingue parciales tonales, energía transitoria y residuo. El corte de soporte para la ablación NO-HIGH quedó en aproximadamente **{cut:.0f} Hz**; sobre las regiones sin varias parejas independientes, el retorno a 0 dB es regularización, no una medición de igualdad.','','## 8. Curvas recomendadas',summary[['frequency_hz','precise_central_db','precise_robust_db','safe_db','parametric_db','ci95_low_db','ci95_high_db','support_state']].to_markdown(index=False),'','## 9. Gain y offsets por cuerda',pd.DataFrame({'cuerda':STRINGS,'offset_db':offs}).to_markdown(index=False),'','## 10. Validación',metrics.groupby('model').agg(MAE=('mae','mean'),RMSE=('rmse','mean'),P90=('p90','mean'),P95=('p95','mean')).reset_index().to_markdown(index=False),'','## 11. Comparación con V9 y V10.1','Las curvas V9 y V10.1 se reevalúan sobre las observaciones V10.2, con los parámetros de nivel/cuerda/fase reajustados. De este modo la comparación no usa las métricas históricas de pipelines diferentes.','','## 12. Limitaciones','Una EQ estática no puede igualar offsets por cuerda, diferencias de ataque/decaimiento, balance de voces en acordes, ni componentes no lineales. Repeticiones de una misma toma reducen incertidumbre interna pero no equivalen a nuevas cuerdas o instrumentos independientes.','','## 13. Reproducibilidad','No se aplicó high-pass, gate, compresión ni normalización por archivo. Se resta únicamente la media DC antes de análisis/render. Seed: 10202. Los filtros de render son FIR lineales de 8193 taps aplicados offline.']
    (OUT/'INFORME_TECNICO_AUTONOMO_V10_2.md').write_text('\n'.join(lines),encoding='utf-8')
    (OUT/'INFORME_ANALISIS_TIEMPO_FRECUENCIA.md').write_text('# Análisis tiempo–frecuencia\n\nSe emplearon ventanas adaptadas por fase, multitaper DPSS, F0 refinada sub-bin y observaciones armónicas relativas. Los graves se evalúan por ciclos y los ataques agudos por milisegundos. Consulte VENTANAS_ADAPTATIVAS_V10_2.csv, ATAQUES_MULTIESCALA_V10_2.csv y MAPA_TIEMPO_FRECUENCIA_DIFERENCIAL.csv.\n',encoding='utf-8')
    (OUT/'INFORME_MATCHING_INTELIGENTE.md').write_text('# Matching inteligente\n\nAlineación monotónica con inserciones/eliminaciones, costo combinado de envolvente, bandas, decaimiento, F0 y orden musical. No se permite reordenamiento. Consulte MATCHING_EVENTOS_V10_2.csv.\n',encoding='utf-8')
    (OUT/'INFORME_ATAQUES_MULTIESCALA.md').write_text('# Ataques multiescala\n\nSe compararon ventanas de 0–5 a 80–160 ms y seis bandas. Estas observaciones tienen peso secundario frente al contenido tonal para evitar convertir roce o click en EQ sostenida.\n',encoding='utf-8')
    (OUT/'INFORME_REFINAMIENTO_AGUDOS.md').write_text('# Refinamiento de agudos\n\nLos agudos se aceptan solo con SNR, repetibilidad y varias parejas. NO-HIGH cuantifica la mejora atribuible a la región superior; 0 dB regularizado no se etiqueta como medición.\n',encoding='utf-8')
    (OUT/'INFORME_ESPECIALIZADO_20_60_HZ.md').write_text('# 20–60 Hz\n\nB0, E1 y A1 se miden directamente mediante F0 refinada y amplitud sinusoidal por fase. La incertidumbre principal es estructural: frecuencia y cuerda están parcialmente confundidas. PRECISE frente a NO-SUB se prueba mediante bootstrap pareado y renders.\n',encoding='utf-8')
    (OUT/'INFORME_IDENTIFICABILIDAD.md').write_text('# Identificabilidad cuerda–frecuencia\n\n'+ident.to_markdown(index=False)+'\n',encoding='utf-8')
    (OUT/'INFORME_VALIDACION.md').write_text('# Validación\n\n'+metrics.to_markdown(index=False)+'\n\n## Por región/fase\n'+local.to_markdown(index=False)+'\n',encoding='utf-8')
    (OUT/'INFORME_SIGNIFICANCIA_PRACTICA.md').write_text('# Significancia práctica\n\n'+signif.to_markdown(index=False)+'\n',encoding='utf-8')
    (OUT/'INFORME_REGIONES_NO_IDENTIFICADAS.md').write_text('# Regiones no identificadas\n\n* 20–28 Hz: no existe fundamental tonal directa.\n* Ultraagudos: cualquier región sin al menos dos parejas independientes se regulariza y se marca como no identificada.\n',encoding='utf-8')
    (OUT/'INFORME_COMPARACION_V9_V10_1_V10_2.md').write_text('# Comparación V9 / V10.1 / V10.2\n\nTodas las métricas del informe principal fueron recalculadas sobre la evidencia V10.2. V10.2 reextrae además 120 Hz–20 kHz desde los WAV, audita matching y separa tonal/transiente/residual.\n',encoding='utf-8')
    pd.DataFrame({'frequency_hz':centers,'Q':Qs,'gain_db':gains}).to_csv(OUT/'PRESET_PARAMETRICO_V10_2.csv',index=False)

# ---------- main ----------
def main():
    t=time.time();all_obs=[];all_fund=[];matches=[];wins=[];att=[];gaps=[];traj=[];inventory=[]
    run_id=os.environ.get('AZUL_RUN_ID') or time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    manifest=run_manifest.build(run_id,pipeline='emulate_azul',stages=['build_v10_2'])
    run_manifest.write(manifest)
    print('0/9 run_id',run_id,'config_hash',manifest['config_hash'][:16],flush=True)
    print('1/9 detect/match/extract originals',flush=True)
    for ii,(key,p) in enumerate(PAIRS.items(),1):
        yc,ya,ec,ea,ma,period=detect_and_match(key,p)
        inventory.append(dict(pair=key,family=fam(key),declared_kind=p['kind'],events_cafe=len(ec),events_azul=len(ea),matched=len(ma),tempo_cafe=60/np.median(np.diff([e['time'] for e in ec])) if len(ec)>2 else np.nan,tempo_azul=60/np.median(np.diff([e['time'] for e in ea])) if len(ea)>2 else np.nan,classification='confirmed' if len(ma)>=min(len(ec),len(ea))*.75 else 'partial',decision='training' if p['kind']!='chord' else 'validation/reduced weight'))
        ro,fu,mr,wr,ar,gr,tr=extract_pair(key,p,yc,ya,ec,ea,ma,period)
        all_obs.extend(ro);all_fund.extend(fu);matches.extend(mr);wins.extend(wr);att.extend(ar);gaps.extend(gr);traj.extend(tr)
        print(f' {ii:02d}/16 {key}: events {len(ec)}/{len(ea)}, match {len(ma)}, obs {len(ro)+len(fu)}',flush=True)
    obs=all_fund+all_obs
    pd.DataFrame(matches).to_csv(OUT/'MATCHING_EVENTOS_V10_2.csv',index=False);pd.DataFrame(wins).to_csv(OUT/'VENTANAS_ADAPTATIVAS_V10_2.csv',index=False);pd.DataFrame(att).to_csv(OUT/'ATAQUES_MULTIESCALA_V10_2.csv',index=False);pd.DataFrame(gaps).to_csv(OUT/'ESPACIOS_Y_SOLAPAMIENTOS_V10_2.csv',index=False);pd.DataFrame(traj).to_csv(OUT/'TRAYECTORIAS_FUNDAMENTALES_V10_2.csv',index=False);pd.DataFrame(all_obs).to_csv(OUT/'TRAYECTORIAS_ARMONICAS_V10_2.csv',index=False);pd.DataFrame(all_obs).to_csv(OUT/'MAPA_TIEMPO_FRECUENCIA_DIFERENCIAL.csv',index=False);pd.DataFrame(inventory).to_csv(OUT/'QUE_CONTIENEN_REALMENTE_LOS_AUDIOS_V10_2.csv',index=False)
    # matching bands aggregate from attack
    pd.DataFrame(att).groupby(['pair','band'],as_index=False).agg(delta_median_db=('delta_db','median'),delta_mad_db=('delta_db',lambda x:1.4826*np.median(np.abs(x-np.median(x)))),n=('delta_db','size')).to_csv(OUT/'MATCHING_BANDAS_V10_2.csv',index=False)
    print('2/9 CV selection',flush=True)
    lc,lr,cv,cvagg=cross_validate(obs);print(' central',lc,'robust',lr,flush=True)
    print('3/9 fit models + bootstrap',flush=True)
    bc,dfc,supc=fit_model(obs,lc,'JOINT');br,dfr,supr=fit_model(obs,lr,'JOINT')
    # RAW with low smoothing candidate
    braw,_,_=fit_model(obs,(5,1,5,.3),'JOINT')
    boot,bg,bo=bootstrap(obs,lc,140)
    # prepare support df with normalized weights
    dfn,_,_,_=prepare_obs(obs,'JOINT')
    central,robust,safe,param,no_sub,no_high,lo,hi,sup,cut,centers,Qs,gains=make_variants(bc,br,boot,dfn);raw=eval_q(braw)
    # phase curves diagnostics
    phase_curves={}
    for ph in PHASES:
        oo=[o for o in obs if o['phase']==ph]
        if len(oo)>30:
            try:bp,_,_=fit_model(oo,lc,'JOINT');phase_curves[ph]=eval_q(bp)
            except:pass
    supp=support_dense(dfn)
    curve=pd.DataFrame({'frequency_hz':DENSE_F,'raw_db':raw,'precise_central_db':central,'precise_robust_db':robust,'safe_db':safe,'parametric_db':param,'no_sub_db':no_sub,'no_high_db':no_high,'ci95_low_db':lo,'ci95_high_db':hi,'effective_pairs':[x[0] for x in supp],'strings':[x[1] for x in supp],'families':[x[2] for x in supp],'median_snr_db':[x[3] for x in supp],'max_pair_influence':[x[4] for x in supp],'support_state':[x[5] for x in supp]})
    curve['origin']=np.where(curve.effective_pairs>=2,'Measured/interpolated',np.where(curve.effective_pairs==1,'Local inference','Regularized/not identified'))
    curve['temporal_resolution']='adaptive by phase/frequency';curve['spectral_resolution']='DPSS multitaper + sinusoidal/sub-bin';curve.to_csv(OUT/'CURVAS_DENSAS_V10_2.csv',index=False)
    # low dense separate
    curve[curve.frequency_hz<=120].to_csv(OUT/'CURVA_20_120_HZ_V10_2.csv',index=False)
    curve.attrs['phase_curves']=phase_curves
    print('4/9 identifiability',flush=True)
    ident=[]
    for model in ['FREQUENCY','STRING','JOINT']:
        vals=[]
        for hold in sorted(set(o['pair'] for o in obs)):
            b,_,_=fit_model(obs,lc,model,hold,3);d,X,y,w=prepare_obs([o for o in obs if o['pair']==hold],model);r=y-X@b;vals.append((np.average(np.abs(r),weights=w),np.sqrt(np.average(r*r,weights=w))))
        ident.append(dict(model=model,cv_mae=np.mean([v[0] for v in vals]),cv_rmse=np.mean([v[1] for v in vals]),sub_curve_31_db=eval_q(fit_model(obs,lc,model)[0],np.array([30.87]))[0] if model!='STRING' else 0,sub_curve_41_db=eval_q(fit_model(obs,lc,model)[0],np.array([41.2]))[0] if model!='STRING' else 0,sub_curve_55_db=eval_q(fit_model(obs,lc,model)[0],np.array([55]))[0] if model!='STRING' else 0))
    ident=pd.DataFrame(ident);ident.to_csv(OUT/'COMPARACION_FREQUENCY_STRING_JOINT.csv',index=False)
    # matrix identifiability
    mat=pd.DataFrame(obs);mat.groupby(['string','family']).agg(f_min=('f','min'),f_max=('f','max'),events=('event','nunique'),pairs=('pair','nunique')).reset_index().to_csv(OUT/'MATRIZ_IDENTIFICABILIDAD_CUERDA_FRECUENCIA.csv',index=False)
    pd.DataFrame(np.corrcoef(np.c_[boot,bg[:,None],bo].T),index=[f'q_{i}' for i in range(boot.shape[1])]+['gain']+STRINGS).to_csv(OUT/'CORRELACION_EQ_OFFSETS_CUERDA.csv')
    print('5/9 validation/current+old baselines',flush=True)
    variants={'V10_2_CENTRAL':central,'V10_2_ROBUST':robust,'V10_2_SAFE':safe,'V10_2_PARAMETRIC':param,'V10_2_NO_SUB':no_sub,'V10_2_NO_HIGH':no_high}
    mt=[];lt=[];resdict={}
    for n,q in variants.items():
        res=residuals_curve(obs,bc,q);resdict[n]=res;mt.append(metric_table(res,n));lt.append(local_metrics(res,n))
    for old in (eval_old(obs,'V9'), eval_old(obs,'V10_1')):
        if len(old): mt.append(old)
    metrics=pd.concat(mt,ignore_index=True);local=pd.concat(lt,ignore_index=True);metrics.to_csv(OUT/'METRICAS_POR_PAREJA_V10_2.csv',index=False);local.to_csv(OUT/'METRICAS_LOCALES_Y_TEMPORALES_V10_2.csv',index=False)
    sig=pd.DataFrame([paired_significance(resdict['V10_2_CENTRAL'],resdict['V10_2_NO_SUB'],'CENTRAL_vs_NO_SUB'),paired_significance(resdict['V10_2_CENTRAL'],resdict['V10_2_NO_HIGH'],'CENTRAL_vs_NO_HIGH')]);sig.to_csv(OUT/'SIGNIFICANCIA_PRECISE_VS_ABLACIONES.csv',index=False);sig.iloc[[0]].to_csv(OUT/'SIGNIFICANCIA_PRECISE_VS_NO_SUB.csv',index=False);sig.iloc[[1]].to_csv(OUT/'SIGNIFICANCIA_PRECISE_VS_NO_HIGH.csv',index=False)
    # audit 800-1600
    aud=[]
    for f in [630,800,1000,1250,1600,2000]:
        i=np.argmin(abs(DENSE_F-f));z=dfn[np.abs(np.log2(dfn.f/f))<=1/12];aud.append(dict(frequency_hz=f,eq_db=central[i],ci95_low=lo[i],ci95_high=hi[i],pairs=z.pair.nunique(),strings=z.string.nunique(),families=z.family.nunique(),attack_median=z[z.phase=='attack'].y.median(),body_median=z[z.phase=='body'].y.median(),sustain_median=z[z.phase=='sustain'].y.median(),max_pair_influence=(z.groupby('pair').w.sum()/z.w.sum()).max() if len(z) else np.nan))
    pd.DataFrame(aud).to_csv(OUT/'AUDITORIA_800_1600_HZ.csv',index=False)
    # Pareto
    cvagg.to_csv(OUT/'FRONTERA_PARETO_CENTRAL_ROBUST.csv',index=False)
    # paired comparison file
    comp=metrics.groupby('model').agg(mae=('mae','mean'),rmse=('rmse','mean'),p90=('p90','mean'),p95=('p95','mean')).reset_index();comp.to_csv(OUT/'BOOTSTRAP_PAREADO_V9_V10_1_V10_2.csv',index=False)
    print('6/9 plots/reports',flush=True)
    plots(curve,raw,central,robust,safe,param,no_sub,no_high,pd.DataFrame(att),pd.DataFrame(matches),pd.DataFrame(wins),pd.DataFrame(gaps),pd.DataFrame(traj),metrics,local)
    report_files(curve,bc,br,central,robust,safe,param,no_sub,no_high,cvagg,metrics,local,pd.DataFrame(matches),sig,ident,cut,centers,Qs,gains,pd.DataFrame(inventory))
    # configs/hash/log
    pd.DataFrame([dict(file=p.name,sha256=sha256(p),bytes=p.stat().st_size) for p in sorted(AUDIO.glob('*.m4a'))]).to_csv(OUT/'HASHES_WAV_ORIGINALES.csv',index=False)
    (OUT/'CONFIG_V10_2.json').write_text(json.dumps({'seed':SEED,'sr':SR,'dense_points':4096,'low_points':512,'candidates':CANDS,'selected_central':lc,'selected_robust':lr,'open_above_300_weight':0,'methods':['monotonic DP matching','F0 sub-bin','DPSS multitaper','linear detrend','pre-onset noise subtract','low window 60-760ms','relative energy rel_db','relative harmonics','adaptive phase windows','robust hierarchical fit'],'pipeline_note':'V21 low+high audit extract'},indent=2),encoding='utf-8')
    print('7/9 render audio',flush=True)
    render_all([central,robust,safe,param,no_sub,no_high],bc,pd.DataFrame(matches))
    print('8/9 package',flush=True)
    # NOTE: this used to rewrite code/requirements.txt on every run, silently
    # dropping the pinned versions the run actually used.
    prompt=ROOT/'docs'/'PROMPT_MAESTRO_V10_2.md'
    if prompt.exists() and not (CODE/'PROMPT_MAESTRO_V10_2.md').exists():
        shutil.copy2(prompt,CODE/'PROMPT_MAESTRO_V10_2.md')
    inv=[]
    for r,typ in [(OUT,'result'),(CODE,'code'),(AUD,'audio')]:
        for p in r.rglob('*'):
            if p.is_file():inv.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,type=typ))
    pd.DataFrame(inv).to_csv(OUT/'INVENTARIO_ENTREGABLES_V10_2.csv',index=False)
    EXPORTS.mkdir(parents=True,exist_ok=True)
    for zname,roots in [(EXPORTS/'CAFE_AZUL_V10_2_ANALISIS_CODIGO.zip',[OUT,CODE]),(EXPORTS/'CAFE_AZUL_V10_2_AUDIOS.zip',[AUD]),(EXPORTS/'CAFE_AZUL_V10_2_COMPLETA.zip',[OUT,CODE,AUD])]:
        with zipfile.ZipFile(zname,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for r in roots:
                for p in r.rglob('*'):
                    if p.is_file():z.write(p,arcname=str(p.relative_to(ROOT)))
    manifest.update(elapsed_s=time.time()-t,n_observations=len(obs),n_matches=len(matches),
                    lambda_central=list(lc),lambda_robust=list(lr),model_intercept_db=float(bc[IG]))
    run_manifest.finalize(manifest)
    print('9/9 done',json.dumps({'run_id':run_id,'elapsed_s':time.time()-t,'observations':len(obs),'matches':len(matches),'gain':bc[IG],'central':lc,'robust':lr,'files':len(inv)},indent=2),flush=True)

if __name__=='__main__':main()
