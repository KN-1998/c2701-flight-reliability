"""Common-support descriptive standardization and paired date-block uncertainty."""
import numpy as np
import pandas as pd
from scipy.stats import rankdata


def block_weights(dates,reps=500,block=7,seed=2701):
    rng=np.random.default_rng(seed); weights=np.zeros((reps,len(dates)))
    # Preserve observed year shares, sample common calendar dates across all airports.
    for year in sorted(set(dates.year)):
        ix=np.flatnonzero(dates.year==year); n=len(ix)
        for b in range(reps):
            starts=rng.integers(0,n,size=int(np.ceil(n/block)))
            drawn=((starts[:,None]+np.arange(block))%n).ravel()[:n]
            weights[b,ix]=np.bincount(drawn,minlength=n)
    return weights


def compare(df,outdir,reps=500):
    core=df[df.year.between(2023,2025)].copy()
    core['stratum']=core.season.astype(str)+'|'+core.time_bin.astype(str)+'|'+core.distance_bin.astype(str)
    core['success']=(core.completed & core.ArrDelay.lt(15)).astype(int)
    core['known']=core.state.ne('unknown').astype(int)
    airports=sorted(core.Origin.unique())
    cells=core.groupby(['Origin','stratum'],observed=True).agg(n=('success','size'),success=('success','sum'),known=('known','sum'))
    support=cells.known.unstack('Origin').reindex(columns=airports).fillna(0)
    common=support.index[(support>=30).all(axis=1)]
    if len(common)==0:
        return {'status':'no_common_support'}
    cell_n=cells.n.unstack('Origin').reindex(index=common,columns=airports).fillna(0)
    w=cell_n.div(cell_n.sum(axis=0),axis=1).mean(axis=1)
    w=w/w.sum()
    w.rename('standard_weight').to_csv(outdir/'standard_population_weights.csv')
    supported=core[core.stratum.isin(common)]
    coverage=supported.groupby('Origin',observed=True).size()/core.groupby('Origin',observed=True).size()
    table=cells.reset_index();table['common_support']=table.stratum.isin(common)
    table['rate_lower']=table.success/table.n
    table.to_csv(outdir/'standardization_cells.csv',index=False)
    dates=pd.DatetimeIndex(sorted(core.date.dropna().unique()))
    ag=core.groupby(['date','Origin'],observed=True).agg(n=('success','size'),s=('success','sum'))
    raw_n=ag.n.unstack('Origin').reindex(index=dates,columns=airports).fillna(0).to_numpy()
    raw_s=ag.s.unstack('Origin').reindex(index=dates,columns=airports).fillna(0).to_numpy()
    idx=pd.MultiIndex.from_product([airports,common],names=['Origin','stratum'])
    daily=supported.groupby(['date','Origin','stratum'],observed=True).agg(n=('success','size'),s=('success','sum'))
    std_n=daily.n.unstack(['Origin','stratum']).reindex(index=dates,columns=idx).fillna(0).to_numpy()
    std_s=daily.s.unstack(['Origin','stratum']).reindex(index=dates,columns=idx).fillna(0).to_numpy()
    point_raw=raw_s.sum(axis=0)/raw_n.sum(axis=0)
    point_std=(std_s.sum(axis=0)/std_n.sum(axis=0)).reshape(len(airports),len(common))@w.to_numpy()
    # Same-support raw rates separate composition from support restriction (D7).
    point_raw_supported=std_s.sum(axis=0).reshape(len(airports),len(common)).sum(axis=1)/std_n.sum(axis=0).reshape(len(airports),len(common)).sum(axis=1)
    rows=[];pairs=[]
    for block in [1,7,14]:
        bw=block_weights(dates,reps=reps,block=block)
        rb=(bw@raw_s)/(bw@raw_n)
        sb=((bw@std_s)/(bw@std_n)).reshape(reps,len(airports),len(common))@w.to_numpy()
        if not np.isfinite(sb).all():
            raise ValueError('Bootstrap common-support cell empty; coarsen strata or expand sample.')
        for mode,point,boots in [('raw',point_raw,rb),('standardized',point_std,sb)]:
            ranks=rankdata(-boots,axis=1,method='average')
            pr=rankdata(-point,method='average')
            for j,a in enumerate(airports):
                rows.append(dict(airport=a,mode=mode,block_days=block,rate=point[j],ci_lower=np.quantile(boots[:,j],.025),ci_upper=np.quantile(boots[:,j],.975),rank=pr[j],rank_lower=np.quantile(ranks[:,j],.025),rank_upper=np.quantile(ranks[:,j],.975),common_support_coverage=coverage[a],common_strata=len(common)))
            if block==7:
                for j,a in enumerate(airports):
                    for k in range(j+1,len(airports)):
                        difference=boots[:,j]-boots[:,k]
                        pairs.append(dict(a=a,b=airports[k],mode=mode,difference=point[j]-point[k],ci_lower=np.quantile(difference,.025),ci_upper=np.quantile(difference,.975),prob_a_better=float((difference>0).mean()),interpretation='pairwise exploratory; not multiplicity adjusted'))
    result=pd.DataFrame(rows);result.to_csv(outdir/'rank_intervals.csv',index=False)
    paired=pd.DataFrame(pairs);paired.to_csv(outdir/'pairwise_comparisons.csv',index=False)
    decomposed=[]
    for j,a in enumerate(airports):
        for k in range(j+1,len(airports)):
            raw=point_raw[j]-point_raw[k]; residual=point_std[j]-point_std[k]
            same_support=point_raw_supported[j]-point_raw_supported[k]
            mix=same_support-residual
            support_restriction=raw-same_support
            check=raw-(residual+mix+support_restriction)
            assert abs(check)<1e-12
            decomposed.append(dict(a=a,b=airports[k],raw_gap=raw,
                                   raw_gap_common_support=same_support,standardized_gap=residual,
                                   mix_component=mix,support_restriction_component=support_restriction,
                                   identity_residual=check,
                                   decomposition='D7: full raw = adjusted + same-support mix + support restriction; descriptive only',
                                   point_rank_reversal=bool(raw*residual<0)))
    pd.DataFrame(decomposed).to_csv(outdir/'mix_decomposition.csv',index=False)
    return {'status':'computed','common_strata':len(common),'bootstrap_reps':reps,'block_days':[1,7,14],'coverage_min':float(coverage.min()),'point_reversals':sum(x['point_rank_reversal'] for x in decomposed)}
