from pathlib import Path
import sys, os, json, zipfile, shutil, time
import numpy as np, pandas as pd
from scipy import signal
ROOT=Path('/mnt/data/reanalysis_cafe_azul');OUT=ROOT/'v10_2_results';AUD=ROOT/'v10_2_audio';CODE=ROOT/'v10_2_code';sys.path.insert(0,str(CODE))
import build_v10_2 as m
RNG=np.random.default_rng(10203)

def source_obs():
    fund=pd.read_csv(OUT/'FUNDAMENTALES_CORREGIDAS_V10_2.csv');ton=pd.read_csv(OUT/'TONAL_HARMONICS_CORRECTED_V10_2.csv');res=pd.read_csv(OUT/'TRAYECTORIAS_ARMONICAS_V10_2.csv');res=res[res.kind=='band_residual'].copy();res['weight_base']*=.35
    return fund,ton,res,fund.to_dict('records')+ton.to_dict('records')+res.to_dict('records')

def calculate_gains(q,matching,fund):
    qfun=m.curve_fun(q)
    z=fund[(fund.snr>=10)&(fund.match_cost<=2.8)&fund.phase.isin(['body','sustain'])].copy();z['g_need']=z.y-z.f.apply(qfun)
    gf=z.groupby('pair').agg(gain_fundamental_db=('g_need','median'),fundamental_mad=('g_need',lambda x:1.4826*np.median(np.abs(x-np.median(x)))),n_fund=('g_need','size')).reset_index()
    h=m.fir_from_curve(q,4097);ge=[]
    for key,zz in matching.groupby('pair'):
        p=m.PAIRS[key];yc,_=m.load(p['cafe']);ya,_=m.load(p['azul']);zc=m.apply_eq(yc,h,0);vals=[]
        for _,r in zz.iterrows():
            per=.3 if p['kind']=='chromatic' else .6
            for a,b in ((.09,.175),(.175,.255)) if per<.4 else ((.155,.32),(.32,.49)):
                sc=zc[int((r.time_cafe+a)*m.SR):int(min(len(zc),(r.time_cafe+b)*m.SR))];sa=ya[int((r.time_azul+a)*m.SR):int(min(len(ya),(r.time_azul+b)*m.SR))]
                if len(sc)>100 and len(sa)>100:vals.append(20*np.log10(np.sqrt(np.mean(sa*sa)+1e-30)/np.sqrt(np.mean(sc*sc)+1e-30)))
        if vals:ge.append(dict(pair=key,gain_energy_db=np.median(vals),energy_mad=1.4826*np.median(np.abs(vals-np.median(vals))),n_energy=len(vals)))
    ge=pd.DataFrame(ge);g=gf.merge(ge,on='pair',how='outer')
    g['gain_combined_db']=np.where(g.gain_fundamental_db.notna()&g.gain_energy_db.notna(),.65*g.gain_fundamental_db+.35*g.gain_energy_db,g.gain_fundamental_db.fillna(g.gain_energy_db))
    g['weight']=np.sqrt(g.n_fund.fillna(0)+g.n_energy.fillna(0))/np.maximum(g.fundamental_mad.fillna(g.energy_mad).fillna(2),.5)
    rec=m.weighted_quantile(g.gain_combined_db,g.weight,.5)
    vals=[]
    for _ in range(2000):
        idx=RNG.integers(0,len(g),len(g));gg=g.iloc[idx];vals.append(m.weighted_quantile(gg.gain_combined_db,gg.weight,.5))
    ci=(np.percentile(vals,2.5),np.percentile(vals,97.5))
    return g,float(rec),float(ci[0]),float(ci[1]),float(np.nanmedian(g.gain_fundamental_db)),float(np.nanmedian(g.gain_energy_db))

def clean_metrics(res,model):
    res=res[np.isfinite(res.resid)&np.isfinite(res.snr)&(res.snr>=8)&(res.match_cost<=3)].copy();return m.metric_table(res,model),m.local_metrics(res,model),res

def main():
    t=time.time();fund,ton,resband,obs=source_obs();print('1 corrected observations',len(fund),len(ton),len(resband),flush=True)
    lc,lr,cv,agg=m.cross_validate(obs);print('2 selected',lc,lr,flush=True)
    bc,dfc,_=m.fit_model(obs,lc,'JOINT');br,_,_=m.fit_model(obs,lr,'JOINT');braw,_,_=m.fit_model(obs,(5,1,5,.3),'JOINT')
    boot,bg,bo=m.bootstrap(obs,lc,120);dfn,_,_,_=m.prepare_obs(obs,'JOINT')
    central,robust,safe,param,no_sub,no_high,lo,hi,supp,cut,centers,Qs,gains=m.make_variants(bc,br,boot,dfn);raw=m.eval_q(braw)
    matching=pd.read_csv(OUT/'MATCHING_EVENTOS_V10_2.csv');gain_table,gain,gl,gh,gfund,genergy=calculate_gains(central,matching,fund);gain_table.to_csv(OUT/'GAIN_POR_PAREJA_Y_FUENTE_V10_2.csv',index=False)
    pd.DataFrame([dict(gain_recommended_db=gain,ci95_low_db=gl,ci95_high_db=gh,fundamental_only_median_db=gfund,energy_only_median_db=genergy,model_intercept_diagnostic_db=bc[m.IG])]).to_csv(OUT/'GAIN_GLOBAL_V10_2.csv',index=False)
    # final beta uses independently estimated gain
    bc[m.IG]=gain;br[m.IG]=gain
    support=m.support_dense(dfn)
    curve=pd.DataFrame({'frequency_hz':m.DENSE_F,'raw_db':raw,'precise_central_db':central,'precise_robust_db':robust,'safe_db':safe,'parametric_db':param,'no_sub_db':no_sub,'no_high_db':no_high,'ci95_low_db':lo,'ci95_high_db':hi,'effective_pairs':[x[0] for x in support],'strings':[x[1] for x in support],'families':[x[2] for x in support],'median_snr_db':[x[3] for x in support],'max_pair_influence':[x[4] for x in support],'support_state':[x[5] for x in support]})
    curve['origin']=np.where(curve.effective_pairs>=2,'Measured/interpolated',np.where(curve.effective_pairs==1,'Local inference','Regularized/not identified'));curve['temporal_resolution']='adaptive';curve['spectral_resolution']='sinusoidal + DPSS + sub-bin';curve['total_central_with_gain_db']=curve.precise_central_db+gain;curve.to_csv(OUT/'CURVAS_DENSAS_V10_2.csv',index=False);curve[curve.frequency_hz<=120].to_csv(OUT/'CURVA_20_120_HZ_V10_2.csv',index=False)
    # metrics
    variants={'V10_2_CENTRAL':central,'V10_2_ROBUST':robust,'V10_2_SAFE':safe,'V10_2_PARAMETRIC':param,'V10_2_NO_SUB':no_sub,'V10_2_NO_HIGH':no_high};mts=[];lts=[];resdict={}
    for n,q in variants.items():
        rr=m.residuals_curve(obs,bc,q);mt,lt,rr=clean_metrics(rr,n);mts.append(mt);lts.append(lt);resdict[n]=rr
    old9=m.eval_old(obs,'V9');old10=m.eval_old(obs,'V10_1');metrics=pd.concat(mts+[old9,old10],ignore_index=True);local=pd.concat(lts,ignore_index=True);metrics.to_csv(OUT/'METRICAS_POR_PAREJA_V10_2.csv',index=False);local.to_csv(OUT/'METRICAS_LOCALES_Y_TEMPORALES_V10_2.csv',index=False)
    sig=pd.DataFrame([m.paired_significance(resdict['V10_2_CENTRAL'],resdict['V10_2_NO_SUB'],'CENTRAL_vs_NO_SUB'),m.paired_significance(resdict['V10_2_CENTRAL'],resdict['V10_2_NO_HIGH'],'CENTRAL_vs_NO_HIGH')]);sig.to_csv(OUT/'SIGNIFICANCIA_PRECISE_VS_ABLACIONES.csv',index=False);sig.iloc[[0]].to_csv(OUT/'SIGNIFICANCIA_PRECISE_VS_NO_SUB.csv',index=False);sig.iloc[[1]].to_csv(OUT/'SIGNIFICANCIA_PRECISE_VS_NO_HIGH.csv',index=False)
    # compact correlation at critical freqs
    crit=[30.87,41.2,55,120,250,500,800,1000,1250,1600,2000,3150,5000,8000];B=np.column_stack([np.array([m.interp_log(f,m.DENSE_F,row) for f in crit]) for row in boot]).T if False else np.array([[m.interp_log(f,m.DENSE_F,row) for f in crit] for row in boot])
    C=np.corrcoef(np.c_[B,bg[:,None],bo].T);labs=[f'Q_{f:g}' for f in crit]+['gain_model']+m.STRINGS;pd.DataFrame(C,index=labs,columns=labs).to_csv(OUT/'CORRELACION_EQ_OFFSETS_CUERDA.csv')
    # identifiability refresh
    ident=[]
    for model in ['FREQUENCY','STRING','JOINT']:
        vals=[]
        for hold in sorted(set(o['pair'] for o in obs)):
            b,_,_=m.fit_model(obs,lc,model,hold,3);d,X,y,w=m.prepare_obs([o for o in obs if o['pair']==hold],model);r=y-X@b;vals.append((np.average(np.abs(r),weights=w),np.sqrt(np.average(r*r,weights=w))))
        bb,_,_=m.fit_model(obs,lc,model);ident.append(dict(model=model,cv_mae=np.mean([v[0] for v in vals]),cv_rmse=np.mean([v[1] for v in vals]),q31=m.eval_q(bb,np.array([30.87]))[0] if model!='STRING' else 0,q41=m.eval_q(bb,np.array([41.2]))[0] if model!='STRING' else 0,q55=m.eval_q(bb,np.array([55]))[0] if model!='STRING' else 0))
    ident=pd.DataFrame(ident);ident.to_csv(OUT/'COMPARACION_FREQUENCY_STRING_JOINT.csv',index=False)
    # 800-1600 audit
    audit=[]
    for f in [630,800,1000,1250,1600,2000]:
        i=np.argmin(abs(m.DENSE_F-f));z=dfn[np.abs(np.log2(dfn.f/f))<=1/12];audit.append(dict(frequency_hz=f,eq_db=central[i],ci95_low=lo[i],ci95_high=hi[i],pairs=z.pair.nunique(),strings=z.string.nunique(),families=z.family.nunique(),tonal_observations=(z.kind=='tonal_harmonic').sum(),residual_observations=(z.kind=='band_residual').sum(),attack_median=z[z.phase=='attack'].y.median(),body_median=z[z.phase=='body'].y.median(),sustain_median=z[z.phase=='sustain'].y.median(),max_pair_influence=(z.groupby('pair').w.sum()/z.w.sum()).max() if len(z) else np.nan))
    pd.DataFrame(audit).to_csv(OUT/'AUDITORIA_800_1600_HZ.csv',index=False)
    # param preset
    pd.DataFrame({'frequency_hz':centers,'Q':Qs,'gain_db':gains}).to_csv(OUT/'PRESET_PARAMETRICO_V10_2.csv',index=False)
    # reports overwrite concise but accurate
    inv=pd.read_csv(OUT/'QUE_CONTIENEN_REALMENTE_LOS_AUDIOS_V10_2.csv')
    m.report_files(curve,bc,br,central,robust,safe,param,no_sub,no_high,agg,metrics,local,matching,sig,ident,cut,centers,Qs,gains,inv)
    # append gain correction/audit to main report
    p=OUT/'INFORME_TECNICO_AUTONOMO_V10_2.md';txt=p.read_text();txt=txt.replace(f'Gain global PRECISE-CENTRAL: **{gain:+.2f} dB**.',f'Gain global recomendado: **{gain:+.2f} dB** (IC95 {gl:+.2f} a {gh:+.2f} dB). Fundamental-only: {gfund:+.2f} dB; energía-only: {genergy:+.2f} dB.').replace('model_intercept','')
    txt+='\n\n## Auditoría de correcciones internas\n\nLa primera ejecución V10.2 rechazó fundamentales y parciales por un estimador de SNR contaminado por leakage de la propia línea. Esos resultados no se conservaron. La versión final estima el piso desde silencios reales y vuelve a ajustar curva, gain, bootstrap, validación y renders.\n';p.write_text(txt)
    print('3 rerender corrected gain',gain,flush=True)
    shutil.rmtree(AUD);AUD.mkdir();m.render_all([central,robust,safe,param,no_sub,no_high],bc,matching)
    # package overwrite
    for z in ['/mnt/data/CAFE_AZUL_V10_2_ANALISIS_CODIGO.zip','/mnt/data/CAFE_AZUL_V10_2_AUDIOS.zip','/mnt/data/CAFE_AZUL_V10_2_COMPLETA.zip']:
        try:os.remove(z)
        except:pass
    inventory=[]
    for r,typ in [(OUT,'result'),(CODE,'code'),(AUD,'audio')]:
        for f in r.rglob('*'):
            if f.is_file():inventory.append(dict(path=str(f.relative_to(ROOT)),bytes=f.stat().st_size,type=typ))
    pd.DataFrame(inventory).to_csv(OUT/'INVENTARIO_ENTREGABLES_V10_2.csv',index=False)
    for zname,roots in [('/mnt/data/CAFE_AZUL_V10_2_ANALISIS_CODIGO.zip',[OUT,CODE]),('/mnt/data/CAFE_AZUL_V10_2_AUDIOS.zip',[AUD]),('/mnt/data/CAFE_AZUL_V10_2_COMPLETA.zip',[OUT,CODE,AUD])]:
        with zipfile.ZipFile(zname,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for r in roots:
                for f in r.rglob('*'):
                    if f.is_file():z.write(f,arcname=str(f.relative_to(ROOT)))
    print(json.dumps({'elapsed':time.time()-t,'gain':gain,'ci':[gl,gh],'fund':gfund,'energy':genergy,'central':lc,'robust':lr,'curve_max':float(central.max()),'curve_min':float(central.min())},indent=2),flush=True)
if __name__=='__main__':main()
