"""Data-derived sample rationale and a destination-matched traveler example.
No airport/route causality or inferred traveler utility weights.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from audit import audit,metrics
from comparison import block_weights
ROOT=Path(__file__).resolve().parents[1]
def traveler_case(df,outdir,reps=1000,min_known=30):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    sub=df[df.Origin.isin(['EWR','LGA']) & df.Dest.eq('DEN')].copy()
    if sub.empty:return {'status':'no_route_rows'}
    sub['airport']=sub.Origin.astype(str);sub['u']=sub.state.eq('unknown').astype(int)
    targets={'cancellation':sub.state.eq('cancelled'),'diversion':sub.state.eq('diverted'),'long_delay_60_per_scheduled':sub.completed & sub.ArrDelay.ge(60),'joint_bad_60':sub.state.isin(['cancelled','diverted']) | (sub.completed & sub.ArrDelay.ge(60))}
    raw=[]
    for target,values in targets.items():
        sub[target]=values.astype(int)
        for a,g in sub.groupby('airport'):
            raw.append({'departure_airport':a,'target':target,'n':len(g),'rate_lower':float(g[target].mean()),'rate_upper':float((g[target]+g.u).mean())})
    pd.DataFrame(raw).to_csv(outdir/'raw_route_rates.csv',index=False)
    cols=['Reporting_Airline','season','time_bin'];strings=sub[cols].astype('string').fillna('MISSING');key=strings.iloc[:,0]
    for c in strings.columns[1:]:key=key+'|'+strings[c]
    sub['cell']=key;cell=sub.groupby(['airport','cell'],observed=True).size().unstack('airport').fillna(0)
    known=sub[sub.u.eq(0)].groupby(['airport','cell'],observed=True).size().unstack('airport').reindex(index=cell.index,columns=['EWR','LGA']).fillna(0)
    common=known.index[(known>=min_known).all(axis=1)]
    if len(common)==0:return {'status':'no_common_cells'}
    supported=sub[sub.cell.isin(common)].copy();airports=['EWR','LGA'];idx=pd.MultiIndex.from_product([airports,common],names=['airport','cell'])
    totals=sub.groupby('airport').size();supported_counts=supported.groupby('airport').size();coverage=supported_counts/totals
    pd.DataFrame({'n':totals,'supported_n':supported_counts,'coverage':coverage}).to_csv(outdir/'support_coverage.csv')
    n=supported.groupby(['airport','cell'],observed=True).size().reindex(idx).to_numpy();mix=n.reshape(2,-1);mix=mix/mix.sum(axis=1,keepdims=True);w=mix.mean(axis=0)
    pd.DataFrame({'cell':common,'weight':w}).to_csv(outdir/'reference_weights.csv',index=False)
    dates=pd.DatetimeIndex(sorted(sub.date.unique()));g=supported.groupby(['date','airport','cell'],observed=True)
    daily_n=g.size().unstack(['airport','cell']).reindex(index=dates,columns=idx).fillna(0).to_numpy()
    rows=[]
    for target in targets:
        count=supported.groupby(['airport','cell'],observed=True)[target].sum().reindex(idx).to_numpy()
        point=count.reshape(2,-1)/n.reshape(2,-1)@w
        daily_s=g[target].sum().unstack(['airport','cell']).reindex(index=dates,columns=idx).fillna(0).to_numpy()
        for block in [1,7,14]:
            bw=block_weights(dates,reps=reps,block=block);bn=bw@daily_n;bs=bw@daily_s;valid=(bn>0).all(axis=1)
            boots=np.divide(bs,bn,out=np.full(bs.shape,np.nan),where=bn>0).reshape(reps,2,-1)@w;diff=boots[:,0]-boots[:,1]
            rows.append({'target':target,'contrast':'EWR_minus_LGA','block_days':block,'common_cells':len(common),'EWR_adjusted_rate':point[0],'LGA_adjusted_rate':point[1],'adjusted_difference':point[0]-point[1],'ci_lower':np.quantile(diff,.025) if valid.all() else np.nan,'ci_upper':np.quantile(diff,.975) if valid.all() else np.nan,'invalid_reps':int((~valid).sum()),'reps':reps,'interpretation':'EXPERIMENTAL conditional paired interval; no causal or coverage guarantee; same-carrier/season/time shared cells only'})
    pd.DataFrame(rows).to_csv(outdir/'matched_route_differences.csv',index=False)
    result={'status':'computed','periods':sorted(sub.date.dt.strftime('%Y-%m').unique()),'n':len(sub),'shared_cells':len(common),'coverage':coverage.to_dict(),'strata':cols,'min_known':min_known,'reference':'equal departure-airport average mix restricted to shared cells','preferences':'No observed utility weights; report cancellation and long-delay tradeoff separately','limitation':'Same destination DEN, alternative departure airports EWR/LGA; no causal claim, ground transport or fare data not present'}
    (outdir/'case_status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result

def airport_rationale(df,outdir):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True);rows=[]
    for a,g in df.groupby('Origin',observed=True):
        carriers=g.Reporting_Airline.value_counts();carriers=carriers[carriers>0];dests=g.Dest.value_counts();dests=dests[dests>0];months=g.groupby('month',observed=True).size()
        rows.append({'airport':a,'scheduled_n':len(g),'share_within_selected_ten':len(g)/len(df),'carrier_count':len(carriers),'top_carrier':str(carriers.index[0]),'top_carrier_share':carriers.iloc[0]/len(g),'destination_count':len(dests),'top_destination':str(dests.index[0]),'top_destination_share':dests.iloc[0]/len(g),'departure_18_24_share':float(g.dep_minutes.ge(1080).mean()),'monthly_count_min':int(months.min()),'monthly_count_max':int(months.max())})
    pd.DataFrame(rows).to_csv(outdir/'airport_selection_evidence_2023.csv',index=False)
    for col in ['season','time_bin','distance_bin']:
        z=df.groupby(['Origin',col],observed=True).size().rename('n').reset_index();z['within_airport_share']=z.n/z.groupby('Origin').n.transform('sum');z.to_csv(outdir/f'airport_selection_{col}_2023.csv',index=False)
    metrics(df).to_csv(outdir/'metrics_2023_airports.csv',index=False)
    return rows
