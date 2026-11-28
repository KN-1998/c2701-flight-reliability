"""Check saved v7 identities and arithmetic; this cannot certify a new blind test."""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from run_study_v7 import PROTOCOL, pooled

ATOL = 1e-10
KEY = ['period','scope','threshold_minutes','method']
PRIMARY = {'historical_baseline','direct_joint','conditional_tree','shared_five_leaf'}
WEATHER = {'schedule_proxy_only','schedule_plus_origin_taf'}
DECILES = {(index/10, (index+1)/10) for index in range(10)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_equal(actual, expected, keys, columns):
    require(not actual.duplicated(keys).any() and not expected.duplicated(keys).any(), 'Duplicate evidence key')
    a,b = (x.set_index(keys).sort_index() for x in (actual,expected))
    require(a.index.equals(b.index), 'Evidence key inventory differs')
    for column in columns:
        require(a[column].isna().eq(b[column].isna()).all(), 'Evidence missingness differs: '+column)
        av,bv = a[column].dropna(),b[column].dropna()
        if column in {'n','events','matched'} or not pd.api.types.is_numeric_dtype(av):
            require(av.equals(bv), 'Evidence identity/count differs: '+column)
        else:
            require(np.isfinite(av).all() and np.isfinite(bv).all()
                    and np.allclose(av,bv,atol=ATOL,rtol=0), 'Evidence arithmetic differs: '+column)


def valid_counts(total, events):
    return (total.gt(0).all() and total.mod(1).eq(0).all()
            and events.mod(1).eq(0).all() and events.between(0,total).all())


def inspect_evidence(root):
    root = Path(root)
    protocol = json.loads(PROTOCOL.read_text(encoding='utf-8-sig'))
    frozen_scope = {
        **dict.fromkeys(protocol['holdout_months'], 'frozen_followup'),
        **dict.fromkeys(protocol['previously_inspected_months'], 'previously_reviewed'),
    }
    checked = []
    frames = {}
    for folder,prefix,methods in [('followup','followup',PRIMARY),('weather','taf',WEATHER)]:
        base=root/folder
        monthly=pd.read_csv(base/(prefix+'_monthly.csv'))
        require(not monthly.duplicated(KEY).any(), 'Duplicate monthly score')
        require(set(monthly.period)==set(frozen_scope), 'Score month inventory differs from frozen protocol')
        require(monthly.scope.eq(monthly.period.map(frozen_scope)).fillna(False).all(),
                'Monthly score scope differs from frozen protocol')
        require(monthly.threshold_minutes.isin([15,60]).all(), 'Unexpected threshold')
        for period,group in monthly.groupby('period'):
            expected={(t,m) for t in (15,60) for m in methods}
            require(set(zip(group.threshold_minutes,group.method))==expected, 'Missing method or threshold')
            require(group.n.nunique()==1 and group.identity_sha256.nunique()==1,
                    'Monthly paired denominator or identity differs')
            require(group.identity_sha256.astype('string').str.fullmatch(r'[0-9a-f]{64}',na=False).all(),
                    'Invalid identity digest')
            for _,part in group.groupby('threshold_minutes'):
                require(part.events.nunique()==1, 'Monthly outcome counts differ')
        require(valid_counts(monthly.n,monthly.events), 'Invalid count')
        require(np.allclose(monthly.observed,monthly.events/monthly.n,atol=ATOL,rtol=0),'Observed rate disagrees')
        require(monthly.predicted.between(0,1).all() and monthly.brier.between(0,1).all(),'Invalid score')
        saved=pd.read_csv(base/(prefix+'_pooled.csv'))
        check_equal(saved,pooled(monthly),['scope','threshold_minutes','method'],
                    ['n','events','months','observed','predicted','brier','log_loss'])
        bins=pd.read_csv(base/(prefix+'_calibration.csv'))
        require(not bins.duplicated(KEY+['lower','upper']).any(),'Duplicate calibration bin')
        require(set(zip(bins.lower,bins.upper)).issubset(DECILES), 'Invalid calibration decile bounds')
        # Saved calibrated means can round to a neighboring bin edge.
        require(bins.predicted.between(0,1).all()
                and bins.predicted.between(bins.lower-ATOL,bins.upper+ATOL).all(),
                'Mean prediction lies outside its calibration decile')
        require(valid_counts(bins.n,bins.events),'Invalid calibration count')
        require(np.allclose(bins.observed,bins.events/bins.n,atol=ATOL,rtol=0),'Calibration event rate differs')
        aggregate=[]
        for key,part in bins.groupby(KEY):
            aggregate.append({**dict(zip(KEY,key)), 'n':int(part.n.sum()),'events':int(part.events.sum()),
                              'predicted':float(np.average(part.predicted,weights=part.n))})
        check_equal(pd.DataFrame(aggregate),monthly,KEY,['n','events','predicted'])
        day=pd.read_csv(base/(prefix+'_daily_losses.csv'))
        require(not day.duplicated(['date','threshold_minutes','contrast']).any(),'Duplicate daily loss')
        day['period']=pd.to_datetime(day.date,errors='raise').dt.strftime('%Y-%m')
        day_totals=day.groupby(['period','threshold_minutes','contrast'])[['n','sum_delta']].sum()
        for period,group in monthly.groupby('period'):
            for threshold,part in group.groupby('threshold_minutes'):
                table=part.set_index('method')
                pairs=[(m+'_minus_baseline',m,'historical_baseline') for m in methods-{'historical_baseline'}] if folder=='followup' else [('schedule_plus_origin_taf_minus_schedule_proxy_only','schedule_plus_origin_taf','schedule_proxy_only')]
                for label,first,second in pairs:
                    rec=day_totals.loc[(period,threshold,label)]
                    require(rec.n==table.loc[first,'n'], 'Daily denominator differs')
                    require(abs(rec.sum_delta/rec.n-(table.loc[first,'brier']-table.loc[second,'brier']))<=ATOL,
                            'Daily paired Brier difference disagrees')
        checked.extend([f'{folder}/{prefix}_{suffix}.csv' for suffix in ('monthly','pooled','calibration','daily_losses')])
        frames[folder]=monthly
    coverage=pd.read_csv(root/'weather/taf_coverage.csv')
    require(not coverage.duplicated(['role','period']).any(),'Duplicate coverage month')
    expected_coverage={('fit','all'),('calibration','all')} | {('score',month) for month in frozen_scope}
    require(set(zip(coverage.role,coverage.period))==expected_coverage, 'Coverage window differs from frozen protocol')
    detail=pd.read_csv(root/'weather/taf_coverage_by_airport.csv')
    require(not detail.duplicated(['role','period','Origin']).any(),'Duplicate airport coverage')
    require(valid_counts(detail.n,detail.matched),'Invalid airport coverage')
    check_equal(coverage,detail.groupby(['role','period'],as_index=False)[['n','matched']].sum(),['role','period'],['n','matched'])
    require(np.allclose(coverage.share,coverage.matched/coverage.n,atol=ATOL,rtol=0),'Coverage share differs')
    require(detail.loc[detail.matched.gt(0),'min_release_lead_minutes'].ge(150).all(),'TAF cutoff violated')
    selected=coverage.loc[coverage.role.eq('score')].set_index('period')
    for period,row in selected.iterrows():
        require(frames['followup'].loc[frames['followup'].period.eq(period),'n'].eq(row.n).all(), 'Total eligibility differs')
        require(frames['weather'].loc[frames['weather'].period.eq(period),'n'].eq(row.matched).all(),'Matched eligibility differs')
    stress=pd.read_csv(root/'weather/taf_stress_monthly.csv')
    require(not stress.duplicated(KEY+['group']).any(),'Duplicate stress row')
    require(valid_counts(stress.n,stress.events),'Invalid stress count')
    require(np.allclose(stress.observed,stress.events/stress.n,atol=ATOL,rtol=0),'Stress observed rate differs')
    for key,group in stress.groupby(['period','scope','threshold_minutes','group']):
        require(set(group.method)==WEATHER and group.n.nunique()==1 and group.events.nunique()==1,'Stress paired counts differ')
    for first,second in [('adverse_forecast','no_adverse_signal'),('holiday_proxy_window','other_calendar_days')]:
        subtotal=stress.loc[stress.group.isin([first,second])].groupby(KEY,as_index=False)[['n','events']].sum()
        check_equal(subtotal,frames['weather'],KEY,['n','events'])
    check_equal(pd.read_csv(root/'weather/taf_stress_pooled.csv'),pooled(stress,extras=('group',)),
                ['scope','threshold_minutes','method','group'],['n','events','observed','predicted','brier','log_loss'])
    checked.extend(['weather/taf_coverage.csv','weather/taf_coverage_by_airport.csv','weather/taf_stress_monthly.csv','weather/taf_stress_pooled.csv'])
    return {'status':'V7_SAVED_ARITHMETIC_AND_PAIRING_PASS','engineering_absolute_tolerance':ATOL,
            'checked_files':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in checked},
            'scope':'Saved arithmetic, matching counts and identities only; no blind-test chronology or live availability proof'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    require(not args.out.exists(),'Use a new evidence output file')
    result=inspect_evidence(args.results)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
