"""Deterministic outcome audit. Missing outcomes are never filled with zero."""
from __future__ import annotations
import numpy as np
import pandas as pd

KEY = ['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime']
STATES = ['on_time','late','cancelled','diverted','unknown']


def valid_hhmm(values):
    x = pd.to_numeric(values, errors='coerce')
    return x.notna() & (x == np.floor(x)) & (((x >= 0) & (x <= 2359) & (x % 100 < 60)) | x.eq(2400))


def hhmm_minutes(values):
    x = pd.to_numeric(values, errors='coerce')
    return ((x // 100)*60 + x % 100).where(valid_hhmm(x)).replace(1440,0)


def audit(frame):
    raw_n = len(frame)
    df = frame.drop_duplicates().copy().reset_index(drop=True)
    numeric = ['CRSDepTime','CRSArrTime','DepTime','ArrTime','ArrDelay','Cancelled','Diverted',
               'Distance','CRSElapsedTime','ArrDel15','DivReachedDest','DivArrDelay']
    for name in numeric:
        if name not in df:
            df[name] = np.nan
        df[name] = pd.to_numeric(df[name],errors='coerce')
    date = pd.to_datetime(df.FlightDate,errors='coerce')
    invalid_identity = date.isna()
    for name in KEY:
        invalid_identity |= df[name].isna() | df[name].astype('string').str.strip().eq('').fillna(True)
    invalid_identity |= ~valid_hhmm(df.CRSDepTime)
    conflicting_key = df.duplicated(KEY,keep=False)
    invalid_flags = ~df.Cancelled.isin([0,1]) | ~df.Diverted.isin([0,1])
    contradictory = df.Cancelled.eq(1) & df.Diverted.eq(1)
    cancelled_with_arrival = df.Cancelled.eq(1) & (df.ArrTime.notna() | df.ArrDelay.notna())
    normal = df.Cancelled.eq(0) & df.Diverted.eq(0)
    missing_normal_arrival = normal & (~valid_hhmm(df.ArrTime) | ~np.isfinite(df.ArrDelay))
    bad = invalid_identity | conflicting_key | invalid_flags | contradictory | cancelled_with_arrival | missing_normal_arrival
    state = np.select([bad,df.Cancelled.eq(1),df.Diverted.eq(1),df.ArrDelay.lt(15)],
                      ['unknown','cancelled','diverted','on_time'],default='late')
    df['state'] = pd.Categorical(state,categories=STATES)
    df['date'] = date.dt.normalize()
    df['year'] = date.dt.year
    df['month'] = date.dt.month
    df['quarter'] = date.dt.quarter
    df['weekday'] = date.dt.day_of_week
    df['season'] = date.dt.month.map({12:'winter',1:'winter',2:'winter',3:'spring',4:'spring',5:'spring',6:'summer',7:'summer',8:'summer',9:'autumn',10:'autumn',11:'autumn'})
    # Preserve the source token without asserting a FlightDate shift.
    df['scheduled_dep_2400'] = df.CRSDepTime.eq(2400)
    df['scheduled_arr_2400'] = df.CRSArrTime.eq(2400)
    df['dep_minutes'] = hhmm_minutes(df.CRSDepTime)
    df['arr_minutes'] = hhmm_minutes(df.CRSArrTime)
    df['time_bin'] = (df.dep_minutes//360).fillna(-1).astype('int8')
    df['distance_bin'] = pd.cut(df.Distance,[-np.inf,500,1000,1500,np.inf],right=False,labels=['short','medium','long','very_long']).astype('string')
    df['completed'] = df.state.isin(['on_time','late'])
    df['bad'] = df.state.isin(['cancelled','diverted']) | (df.completed & df.ArrDelay.ge(60))
    audit_counts = {
        'input_rows':raw_n,'exact_duplicates_removed':raw_n-len(df),'retained_rows':len(df),
        'invalid_identity':int(invalid_identity.sum()),'conflicting_key_rows':int(conflicting_key.sum()),
        'invalid_flags':int(invalid_flags.sum()),'both_cancelled_and_diverted':int(contradictory.sum()),
        'cancelled_with_arrival':int(cancelled_with_arrival.sum()),
        'missing_or_invalid_normal_arrival':int(missing_normal_arrival.sum()),
        'cancel_code_missing':int((df.Cancelled.eq(1) & (df.CancellationCode.isna() | df.CancellationCode.astype('string').str.strip().eq(''))).sum()),
        'scheduled_dep_2400':int(df.scheduled_dep_2400.sum()),
        'scheduled_arr_2400':int(df.scheduled_arr_2400.sum()),
        'diverted_reached_destination':int((df.state.eq('diverted') & df.DivReachedDest.eq(1)).sum()),
        'diverted_not_reached_destination':int((df.state.eq('diverted') & df.DivReachedDest.eq(0)).sum()),
        'diverted_reached_status_missing_invalid':int((df.state.eq('diverted') & ~df.DivReachedDest.isin([0,1])).sum()),
        'arrdel15_disagreement':int((normal & df.ArrDelay.notna() & df.ArrDel15.notna() & df.ArrDel15.ne(df.ArrDelay.ge(15).astype(int))).sum()),
        **{s:int(df.state.eq(s).sum()) for s in STATES}}
    assert sum(audit_counts[s] for s in STATES) == len(df)
    df['audit_reason'] = ''
    for reason,mask in [('identity',invalid_identity),('conflicting_key',conflicting_key),('flags',invalid_flags),('both_flags',contradictory),('cancel_with_arrival',cancelled_with_arrival),('normal_arrival_missing',missing_normal_arrival)]:
        df.loc[mask,'audit_reason'] += reason+';'
    return df,audit_counts


def metrics(df, group=('Origin',)):
    output = []
    for key,part in df.groupby(list(group),observed=True,dropna=False):
        key = key if isinstance(key,tuple) else (key,)
        n = len(part); k = int(part.completed.sum()); u = int(part.state.eq('unknown').sum())
        row = dict(zip(group,key))
        row.update(n=n,completed=k,unknown=u,unknown_rate=u/n,
                   cancellation_rate=float(part.state.eq('cancelled').mean()),diversion_rate=float(part.state.eq('diverted').mean()),
                   completion_lower=k/n,completion_upper=(k+u)/n,
                   conditional_on_time=float(part.loc[part.completed,'ArrDelay'].lt(15).mean()) if k else np.nan,
                   conditional_long_delay=float(part.loc[part.completed,'ArrDelay'].ge(60).mean()) if k else np.nan,
                   unconditional_long_delay=float((part.completed & part.ArrDelay.ge(60)).mean()),
                   delay_p90_completed=float(part.loc[part.completed,'ArrDelay'].quantile(.9)) if k else np.nan,
                   delay_p99_completed=float(part.loc[part.completed,'ArrDelay'].quantile(.99)) if k else np.nan)
        if 'DivReachedDest' in part:
            diverted=part.state.eq('diverted');reached=diverted & part.DivReachedDest.eq(1)
            row.update(diverted_n=int(diverted.sum()),diverted_reached_n=int(reached.sum()),
                       diverted_reached_rate=float(reached.sum()/diverted.sum()) if diverted.any() else np.nan,
                       final_destination_documented_lower=float((part.completed | reached).mean()),
                       diverted_reached_delay_valid_n=int((reached & part.DivArrDelay.notna()).sum()),
                       diverted_reached_delay_median=float(part.loc[reached,'DivArrDelay'].median()) if reached.any() else np.nan)
        for threshold in [0,15,30,60,120]:
            success=int((part.completed & part.ArrDelay.lt(threshold)).sum())
            row[f'reliability_{threshold}_lower']=success/n
            row[f'reliability_{threshold}_upper']=(success+u)/n
        if k:
            assert abs(row['completion_lower']*row['conditional_on_time']-row['reliability_15_lower'])<1e-12
        output.append(row)
    return pd.DataFrame(output)

