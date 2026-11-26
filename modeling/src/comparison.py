"""Descriptive standardization; experimental paired calendar-block uncertainty.
F1/F2 provenance is in docs/FORMULA_PROVENANCE.md. This sampler is an
explicit adaptation, not a theorem guaranteeing flight-data interval coverage.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import rankdata


def calendar_episodes(dates):
    """Contiguous observed dates within one calendar year and meteorological season.
    December is not joined to January, and missing calendar dates break runs.
    """
    dates=pd.DatetimeIndex(dates)
    if dates.hasnans or not dates.is_unique or not dates.is_monotonic_increasing:
        raise ValueError('dates must be sorted, unique and nonmissing')
    season=np.array([0 if m in (12,1,2) else 1 if m in (3,4,5) else 2 if m in (6,7,8) else 3 for m in dates.month])
    if len(dates)==0:return []
    cut=np.r_[True,np.asarray((dates[1:]-dates[:-1])!=pd.Timedelta(days=1))|(np.diff(dates.year)!=0)|(np.diff(season)!=0)]
    return np.split(np.arange(len(dates)),np.flatnonzero(cut)[1:])


def block_weights(dates,reps=500,block=7,seed=2701):
    """Moving blocks, no circular wrap, exact observed count per calendar episode.
    The same date weights apply to all airports. Rare cells may still be empty:
    the caller must diagnose and must not silently redraw/drop replicates.
    """
    if reps<1 or block<1:raise ValueError('reps and block must be positive')
    rng=np.random.default_rng(seed);weights=np.zeros((reps,len(dates)),dtype=np.int32)
    for ix in calendar_episodes(dates):
        n=len(ix);length=min(block,n)
        for b in range(reps):
            starts=rng.integers(0,n-length+1,size=int(np.ceil(n/length)))
            drawn=(starts[:,None]+np.arange(length)).ravel()[:n]
            weights[b,ix]=np.bincount(drawn,minlength=n)
    return weights


def _ratio(num,den):
    return np.divide(num,den,out=np.full(np.shape(num),np.nan,dtype=float),where=den>0)


def compare(df,outdir,reps=500,*,threshold=15,strata=('season','time_bin','distance_bin'),
            min_known=30,blocks=(1,7,14),seed=2701):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    core=df[df.year.between(2023,2025) & df.date.notna()].copy()
    if core.empty:return {'status':'no_records'}
    if threshold<=0 or min_known<1:raise ValueError('positive threshold/support count required')
    core['stratum']=core[list(strata)].astype('string').fillna('MISSING').agg('|'.join,axis=1)
    core['success']=(core.completed & core.ArrDelay.lt(threshold)).astype(int)
    core['unknown']=core.state.eq('unknown').astype(int);core['known']=1-core.unknown
    airports=sorted(core.Origin.unique())
    cells=core.groupby(['Origin','stratum'],observed=True).agg(n=('success','size'),success=('success','sum'),known=('known','sum'),unknown=('unknown','sum'),observed_days=('date','nunique'))
    support=cells.known.unstack('Origin').reindex(columns=airports).fillna(0)
    common=support.index[(support>=min_known).all(axis=1)]
    table=cells.reset_index();table['common_support']=table.stratum.isin(common)
    table['rate_lower']=table.success/table.n;table['rate_upper']=(table.success+table.unknown)/table.n
    table.to_csv(outdir/'standardization_cells.csv',index=False)
    if len(common)==0:
        result={'status':'no_common_support','strata':list(strata),'min_known':min_known}
        (outdir/'comparison_status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
    cell_n=cells.n.unstack('Origin').reindex(index=common,columns=airports).fillna(0)
    w=cell_n.div(cell_n.sum(axis=0),axis=1).mean(axis=1);w=w/w.sum()
    w.rename('standard_weight').to_csv(outdir/'standard_population_weights.csv')
    supported=core[core.stratum.isin(common)]
    total=core.groupby('Origin',observed=True).size();kept=supported.groupby('Origin',observed=True).size().reindex(airports,fill_value=0)
    coverage=kept/total
    pd.DataFrame({'total_n':total,'supported_n':kept,'coverage':coverage}).rename_axis('airport').to_csv(outdir/'common_support_coverage.csv')
    dates=pd.DatetimeIndex(sorted(core.date.unique()))
    ag=core.groupby(['date','Origin'],observed=True).agg(n=('success','size'),s=('success','sum'),u=('unknown','sum'))
    def full(col):return ag[col].unstack('Origin').reindex(index=dates,columns=airports).fillna(0).to_numpy()
    raw_n,raw_s,raw_u=map(full,['n','s','u'])
    idx=pd.MultiIndex.from_product([airports,common],names=['Origin','stratum'])
    daily=supported.groupby(['date','Origin','stratum'],observed=True).agg(n=('success','size'),s=('success','sum'),u=('unknown','sum'))
    def cell(col):return daily[col].unstack(['Origin','stratum']).reindex(index=dates,columns=idx).fillna(0).to_numpy()
    std_n,std_s,std_u=map(cell,['n','s','u']);A,S=len(airports),len(common)
    cn=std_n.sum(axis=0);cs=std_s.sum(axis=0);cu=std_u.sum(axis=0)
    point_raw=_ratio(raw_s.sum(axis=0),raw_n.sum(axis=0));upper_raw=point_raw+_ratio(raw_u.sum(axis=0),raw_n.sum(axis=0))
    point_std=_ratio(cs,cn).reshape(A,S)@w.to_numpy();upper_std=point_std+(_ratio(cu,cn).reshape(A,S)@w.to_numpy())
    shared_n=std_n.reshape(len(dates),A,S).sum(axis=2);shared_s=std_s.reshape(len(dates),A,S).sum(axis=2)
    point_shared=_ratio(shared_s.sum(axis=0),shared_n.sum(axis=0));upper_shared=point_shared+_ratio(cu.reshape(A,S).sum(axis=1),cn.reshape(A,S).sum(axis=1))
    # Exposure concentration is a descriptive diagnostic, NOT independent sample size.
    exposures=[]
    for j,(a,s) in enumerate(idx):
        n=std_n[:,j];exposures.append({'airport':a,'stratum':s,'positive_count_days':int((n>0).sum()),'equal_count_equivalent_days':float(n.sum()**2/(n@n))})
    pd.DataFrame(exposures).to_csv(outdir/'cell_day_exposure.csv',index=False)
    episodes=[{'start':str(dates[ix[0]].date()),'end':str(dates[ix[-1]].date()),'observed_days':len(ix)} for ix in calendar_episodes(dates)]
    (outdir/'resampling_calendar_episodes.json').write_text(json.dumps(episodes,indent=2),encoding='utf-8')
    rows=[];pairs=[];diagnostics=[];empty_rows=[]
    for block in blocks:
        bw=block_weights(dates,reps=reps,block=block,seed=seed)
        bn=bw@std_n;bs=bw@std_s;empty=bn<=0;valid=~empty.any(axis=1)
        rb=_ratio(bw@raw_s,bw@raw_n);sharedb=_ratio(bw@shared_s,bw@shared_n)
        sb=_ratio(bs,bn).reshape(reps,A,S)@w.to_numpy()
        diagnostics.append({'block_days':block,'requested_reps':reps,'valid_common_support_reps':int(valid.sum()),'invalid_reps':int((~valid).sum()),'empty_cell_draws':int(empty.sum()),'redraws':0,'dropped_reps':0,'policy':'If ANY common-support replicate is invalid, suppress standardized intervals; retain all point estimates and diagnostics.'})
        for j,(a,s) in enumerate(idx):empty_rows.append({'block_days':block,'airport':a,'stratum':s,'empty_reps':int(empty[:,j].sum()),'requested_reps':reps})
        for mode,point,upper,boots in [('raw',point_raw,upper_raw,rb),('raw_common_support',point_shared,upper_shared,sharedb),('standardized',point_std,upper_std,sb)]:
            admissible=np.isfinite(boots).all() and (mode!='standardized' or valid.all())
            ranks=rankdata(-boots,axis=1,method='average') if admissible else None
            pr=rankdata(-point,method='average')
            for j,a in enumerate(airports):
                rows.append(dict(airport=a,mode=mode,threshold_minutes=threshold,block_days=block,rate=point[j],identification_lower=point[j],identification_upper=upper[j],ci_lower=np.quantile(boots[:,j],.025) if admissible else np.nan,ci_upper=np.quantile(boots[:,j],.975) if admissible else np.nan,rank=pr[j],rank_lower=np.quantile(ranks[:,j],.025) if admissible else np.nan,rank_upper=np.quantile(ranks[:,j],.975) if admissible else np.nan,common_support_coverage=coverage[a],common_strata=S,interval_status='EXPERIMENTAL_conditional_fixed_reference_weights' if admissible else 'SUPPRESSED_empty_resampled_cell',estimand='success_count_per_all_retained_scheduled_records_lower_bound',reference_scope='full_observed_sample' if mode=='raw' else 'common_support_only'))
            for j,a in enumerate(airports):
                for k in range(j+1,A):
                    diff=boots[:,j]-boots[:,k]
                    pairs.append(dict(a=a,b=airports[k],mode=mode,threshold_minutes=threshold,block_days=block,difference=point[j]-point[k],identification_difference_lower=point[j]-upper[k],identification_difference_upper=upper[j]-point[k],ci_lower=np.quantile(diff,.025) if admissible else np.nan,ci_upper=np.quantile(diff,.975) if admissible else np.nan,prob_a_better=float((diff>0).mean()) if admissible else np.nan,interpretation='experimental paired-date conditional interval; NOT posterior probability or multiplicity-adjusted inference'))
    pd.DataFrame(rows).to_csv(outdir/'rank_intervals.csv',index=False);pd.DataFrame(pairs).to_csv(outdir/'pairwise_comparisons.csv',index=False)
    pd.DataFrame(diagnostics).to_csv(outdir/'bootstrap_diagnostics.csv',index=False);pd.DataFrame(empty_rows).to_csv(outdir/'empty_cell_frequencies.csv',index=False)
    decomposed=[]
    for j,a in enumerate(airports):
        for k in range(j+1,A):
            raw=point_raw[j]-point_raw[k];adjusted=point_std[j]-point_std[k];shared=point_shared[j]-point_shared[k]
            mix=shared-adjusted;restriction=raw-shared;residual=raw-adjusted-mix-restriction
            assert abs(residual)<1e-12
            decomposed.append(dict(a=a,b=airports[k],raw_gap=raw,raw_gap_common_support=shared,adjusted_gap=adjusted,mix_component=mix,support_restriction_component=restriction,identity_residual=residual,point_rank_reversal=bool(raw*adjusted<0),interpretation='D7 descriptive accounting identity; NOT airport causal effect'))
    pd.DataFrame(decomposed).to_csv(outdir/'mix_decomposition.csv',index=False)
    result={'status':'computed' if all(x['invalid_reps']==0 for x in diagnostics) else 'computed_points_intervals_partly_suppressed','n':len(core),'months':sorted(core.date.dt.to_period('M').astype(str).unique()),'threshold_minutes':threshold,'strata':list(strata),'min_known':min_known,'common_strata':S,'bootstrap_reps':reps,'block_days':list(blocks),'resampling':'paired noncircular moving blocks within contiguous year-season observed-date episodes','coverage_min':float(coverage.min()),'coverage_max':float(coverage.max()),'uncertainty':'EXPERIMENTAL; source and stationarity/local-exchangeability conditions not established for flights; fixed reference weights; no parameter uncertainty','point_reversals':sum(x['point_rank_reversal'] for x in decomposed),'strict_full_population_rank_allowed':False}
    (outdir/'comparison_status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
