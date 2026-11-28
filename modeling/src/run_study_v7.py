"""Frozen v7 time-out and pre-departure information experiments."""
from datetime import UTC, datetime
from pathlib import Path
import argparse
import hashlib
import json
import platform

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from comparison import block_weights
from joint_candidate_v6 import SharedFiveLeafModel
from predeparture_v7 import TAF_FEATURES, match_origin_taf, read_taf
from prediction import (DirectJointModel, HistoricalBaseline, SequentialModel, apply_sigmoid, combine,
                        estimator, evaluate, features, fit_sigmoid, joint_target, prob, stable_flight_key)
from run_validation_v5 import ROOT, audit_months, save_json, sha
from audit import KEY

PROTOCOL = ROOT/'docs/VALIDATION_V7.json'
THRESHOLDS = (15,60)
SCORES = ['brier','log_loss','ece_10_fixed_bins']
# Published observed dates on the 2026 OPM calendar. September is descriptive only.
HOLIDAYS = ['2026-01-01','2026-01-19','2026-02-16','2026-05-25',
            '2026-06-19','2026-07-03','2026-09-07']


def new_directory(path):
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f'Requires a fresh output directory: {path}')
    path.mkdir(parents=True,exist_ok=True)


def prepare(data, protocol, out):
    fit = protocol['fit_scope']
    train_months = pd.period_range(fit['from'],fit['through'],freq='M').astype(str).tolist()
    calibration_months = fit['calibration_months']
    holdouts = protocol['holdout_months']+protocol['previously_inspected_months']
    required = set(train_months+calibration_months+holdouts)
    if len(required) != len(train_months+calibration_months+holdouts):
        raise ValueError('Overlapping fit, calibration or test windows')
    if max(calibration_months)>=min(holdouts) or max(train_months)>=min(calibration_months):
        raise ValueError('A test or calibration month is not strictly after preceding stages')
    frame, observed = audit_months(data,required,out,extra_columns=KEY)
    if required != observed:
        raise ValueError(f'Missing verified data months: {sorted(required-observed)}')
    known = frame.state.ne('unknown')
    month = frame.date.dt.to_period('M')
    train = frame.loc[known & frame.date.between(fit['from'],fit['through'])]
    calibrate = frame.loc[known & month.isin(pd.PeriodIndex(calibration_months,freq='M'))]
    test = frame.loc[known & month.isin(pd.PeriodIndex(holdouts,freq='M'))]
    if train.empty or calibrate.empty or test.empty:
        raise ValueError('Missing fit, calibration or test support')
    return train, calibrate, test


def groups(frame):
    for month, flight in frame.groupby(frame.date.dt.to_period('M'),sort=True):
        yield str(month),flight


def pooled(rows, extras=()):
    result=[]
    for key, group in rows.groupby(['scope','threshold_minutes','method',*extras],sort=False):
        record=dict(zip(['scope','threshold_minutes','method',*extras],key))
        n=int(group.n.sum())
        record.update(n=n,events=int(group.events.sum()),months=int(group.period.nunique()),
                      observed=group.events.sum()/n)
        for column in ['predicted','brier','log_loss']:
            record[column]=float(np.average(group[column],weights=group.n))
        result.append(record)
    return pd.DataFrame(result)


def score(rows, bins, period, scope, threshold, name, y, prediction, digest):
    meta={'period':period,'scope':scope,'threshold_minutes':threshold,'method':name}
    rows.append({**meta,'identity_sha256':digest,**evaluate(y,prediction)})
    for index in range(10):
        mask=np.minimum((prediction*10).astype(int),9)==index
        if mask.any():
            bins.append({**meta,'lower':index/10,'upper':(index+1)/10,'n':int(mask.sum()),
                         'events':int(y[mask].sum()),'observed':float(y[mask].mean()),
                         'predicted':float(prediction[mask].mean())})


def identity_digest(frame):
    return hashlib.sha256(('\n'.join(sorted(stable_flight_key(frame)))+'\n').encode()).hexdigest()


def losses(day_rows, date, threshold, label, delta):
    daily=pd.DataFrame({'date':date.to_numpy(),'delta':delta}).groupby('date').delta.agg(['sum','size'])
    for day, total, count in daily.itertuples():
        day_rows.append({'date':day,'threshold_minutes':threshold,'contrast':label,
                         'n':int(count),'sum_delta':float(total)})


def date_blocks(daily, protocol):
    result=[]
    # The reviewed September is never counted in follow-up block intervals.
    dates=pd.to_datetime(daily.date)
    months=dates.dt.to_period('M').astype(str)
    selected=daily.assign(date=dates).loc[months.isin(protocol['holdout_months'])]
    for (threshold, contrast),group in selected.groupby(['threshold_minutes','contrast']):
        cal=pd.date_range(group.date.min(),group.date.max())
        cal=cal[cal.to_period('M').astype(str).isin(protocol['holdout_months'])]
        aligned=group.set_index('date')[['n','sum_delta']].reindex(cal,fill_value=0)
        n=aligned.n.to_numpy(dtype=float)
        delta=aligned.sum_delta.to_numpy(dtype=float)
        for size in (1,7,14):
            weights=block_weights(cal,reps=1000,block=size,seed=protocol['fit_scope']['random_seed'])
            count=weights@n
            valid=count>0
            boot=(weights@delta)[valid]/count[valid]
            result.append({'threshold_minutes':threshold,'contrast':contrast,'block_days':size,
                           'n':int(n.sum()),'estimate':float(delta.sum()/n.sum()),
                           'low':float(np.quantile(boot,.025)) if len(boot) else None,
                           'high':float(np.quantile(boot,.975)) if len(boot) else None,
                           'valid_reps':int(valid.sum()),
                           'interpretation':'Exploratory paired date-block range. No coverage or causal claim.'})
    return pd.DataFrame(result)


def direct_tree_contrast(daily, protocol):
    cols=['date','threshold_minutes','n','sum_delta']
    direct=daily.loc[daily.contrast.eq('direct_joint_minus_baseline'),cols]
    tree=daily.loc[daily.contrast.eq('conditional_tree_minus_baseline'),cols]
    paired=direct.merge(tree,on=['date','threshold_minutes'],how='outer',validate='one_to_one',
                        suffixes=('_direct','_tree'))
    if not paired.n_direct.eq(paired.n_tree).all():
        raise ValueError('Unequal direct/tree date exposures')
    paired['n']=paired.n_direct
    paired['sum_delta']=paired.sum_delta_direct-paired.sum_delta_tree
    paired['contrast']='direct_joint_minus_conditional_tree'
    return date_blocks(paired,protocol)


def primary(train,cal,test,protocol,out):
    fit=protocol['fit_scope']
    choices={'regularization_c':fit['C'],'fit_cap':fit['fit_cap'],'seed':fit['random_seed']}
    five=SharedFiveLeafModel(**choices).fit(train,cal)
    models={}
    for threshold in THRESHOLDS:
        kws={'C':fit['C'],'threshold':threshold,'fit_cap':fit['fit_cap'],'seed':fit['random_seed']}
        models[threshold]=(
            HistoricalBaseline(fit['history_strength'],threshold).fit(train),
            DirectJointModel(**kws).fit(train).calibrate(cal),
            SequentialModel(**kws).fit(train).calibrate(cal),
        )
    rows,bins,daily,integrity=[], [], [], []
    for period,flight in groups(test):
        scope='frozen_followup' if period in protocol['holdout_months'] else 'previously_reviewed'
        digest=identity_digest(flight)
        leaves,p15,p60=five.predict(flight)
        error=float(np.abs(leaves.sum(axis=1)-1).max())
        inversions=int(np.sum(p60>p15))
        if error>1e-12 or inversions or np.any(leaves<0):
            raise ValueError('Five-leaf structural contract failed')
        integrity.append({'period':period,'scope':scope,'n':len(flight),'identity_sha256':digest,
                          'max_leaf_sum_error':error,'inversions':inversions})
        for threshold,pfive in zip(THRESHOLDS,[p15,p60]):
            y=joint_target(flight,threshold)
            baseline,direct,tree=models[threshold]
            probabilities={'historical_baseline':1-combine(baseline.predict(flight))[:,3],
                           'direct_joint':direct.predict(flight),
                           'conditional_tree':1-combine(tree.predict(flight))[:,3],
                           'shared_five_leaf':pfive}
            ref=probabilities['historical_baseline']
            for name,p in probabilities.items():
                score(rows,bins,period,scope,threshold,name,y,p,digest)
                if name!='historical_baseline':
                    losses(daily,flight.date,threshold,name+'_minus_baseline',(p-y)**2-(ref-y)**2)
        print('Frozen reference scores',period,len(flight),flush=True)
    monthly=pd.DataFrame(rows)
    monthly.to_csv(out/'followup_monthly.csv',index=False)
    pooled(monthly).to_csv(out/'followup_pooled.csv',index=False)
    pd.DataFrame(bins).to_csv(out/'followup_calibration.csv',index=False)
    pd.DataFrame(integrity).to_csv(out/'followup_identity.csv',index=False)
    day=pd.DataFrame(daily)
    day.to_csv(out/'followup_daily_losses.csv',index=False)
    date_blocks(day,protocol).to_csv(out/'followup_date_blocks.csv',index=False)
    direct_tree_contrast(day,protocol).to_csv(out/'followup_direct_tree_date_blocks.csv',index=False)


def attach(frame,taf,info):
    timing=match_origin_taf(frame,taf,lead_minutes=info['decision_lead_minutes'],
                            availability_lag_minutes=info['issuance_safety_lag_minutes'])
    return frame.join(timing,how='inner',validate='one_to_one')


def weather_features(frame,use_weather):
    x=features(frame)
    if use_weather:
        return x.join(frame[TAF_FEATURES],validate='one_to_one')
    return x


def fit_weather_models(train, cal, fit, threshold):
    # Select exactly the same sampled rows and calibration denominators.
    take=np.arange(len(train))
    if len(take)>fit['fit_cap']:
        rng=np.random.default_rng(fit['random_seed'])
        take=np.sort(rng.choice(take,fit['fit_cap'],replace=False))
    sampled=train.iloc[take]
    y=joint_target(sampled,threshold)
    cy=joint_target(cal,threshold)
    if len(np.unique(y))!=2 or len(np.unique(cy))!=2:
        raise ValueError('The matched train/calibration data require both outcomes')
    models={}
    for use_weather in (False,True):
        model=estimator(fit['C'])
        if use_weather:
            prep=model.named_steps['features']
            weather_encoder=Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True)),
                                      ('scale',StandardScaler())])
            prep.transformers=[*prep.transformers, ('archived_taf',weather_encoder,TAF_FEATURES)]
        model.fit(weather_features(sampled,use_weather),y)
        cal_fit=fit_sigmoid(prob(model,weather_features(cal,use_weather)),cy)
        models[use_weather]=(model,cal_fit)
    return models, len(take)


def taf_coverage(role, period, eligible, matched):
    rows=[]
    for origin, group in eligible.groupby('Origin',observed=True):
        available = matched.loc[matched.Origin.eq(origin)]
        n, hits = len(group),len(available)
        preview = (available.scheduled_utc-available.available_utc).dt.total_seconds()/60 if hits else None
        rows.append({'role':role,'period':period,'Origin':origin,'n':n,'matched':hits,
                     'share':hits/n,'min_release_lead_minutes':float(preview.min()) if hits else None})
    return rows


def weather(train,cal,test,protocol,taf_path,products_path,out):
    taf=read_taf(taf_path,products_path)
    info=protocol['information_experiment']
    train_known=attach(train,taf,info)
    cal_known=attach(cal,taf,info)
    train_count, cal_count = len(train_known),len(cal_known)
    print('Matched TAF train/calibration',train_count,cal_count,flush=True)
    fitted={}
    for threshold in THRESHOLDS:
        fitted[threshold],n_sampled=fit_weather_models(train_known,cal_known,protocol['fit_scope'],threshold)
    coverage=[{'role':'fit','period':'all','n':len(train),'matched':len(train_known)},
              {'role':'calibration','period':'all','n':len(cal),'matched':len(cal_known)}]
    coverage_detail=taf_coverage('fit','all',train,train_known)+taf_coverage('calibration','all',cal,cal_known)
    del train_known, cal_known
    rows,bins,daily,stress,stress_daily=[], [], [], [], []
    holiday_days=set(pd.to_datetime(HOLIDAYS))
    holiday_window={date+pd.Timedelta(days=d) for date in holiday_days for d in (-1,0,1)}
    for period,flight in groups(test):
        scope='frozen_followup' if period in protocol['holdout_months'] else 'previously_reviewed'
        data=attach(flight,taf,info)
        coverage.append({'role':'score','period':period,'n':len(flight),'matched':len(data)})
        coverage_detail.extend(taf_coverage('score',period,flight,data))
        if data.empty:
            continue
        digest=identity_digest(data)
        adverse=data.adverse_forecast.eq(1)
        holiday=data.date.isin(holiday_window)
        for threshold,models in fitted.items():
            y=joint_target(data,threshold)
            ps={}
            for use_weather,(model,calibrator) in models.items():
                name='schedule_plus_origin_taf' if use_weather else 'schedule_proxy_only'
                p=apply_sigmoid(prob(model,weather_features(data,use_weather)),calibrator)
                ps[name]=p
                score(rows,bins,period,scope,threshold,name,y,p,digest)
                for label,mask in [('adverse_forecast',adverse),('no_adverse_signal',~adverse),
                                   ('holiday_proxy_window',holiday),('other_calendar_days',~holiday)]:
                    if mask.any():
                        rec=evaluate(y[mask],p[mask])
                        stress.append({'period':period,'scope':scope,'threshold_minutes':threshold,
                                       'method':name,'group':label,'days':int(data.loc[mask,'date'].nunique()),**rec})
                        losses(stress_daily,data.loc[mask,'date'],threshold,name+'_'+label+'_observed_minus_predicted',
                               y[mask]-p[mask])
            aug,control=ps['schedule_plus_origin_taf'],ps['schedule_proxy_only']
            losses(daily,data.date,threshold,'schedule_plus_origin_taf_minus_schedule_proxy_only',
                   (aug-y)**2-(control-y)**2)
        print('TAF experiment',period,len(data),flush=True)
    if not rows:
        raise ValueError('No time-eligible TAF matched flights in the test data')
    coverage=pd.DataFrame(coverage)
    coverage['share']=coverage.matched/coverage.n
    coverage.to_csv(out/'taf_coverage.csv',index=False)
    pd.DataFrame(coverage_detail).to_csv(out/'taf_coverage_by_airport.csv',index=False)
    result=pd.DataFrame(rows)
    result.to_csv(out/'taf_monthly.csv',index=False)
    pooled(result).to_csv(out/'taf_pooled.csv',index=False)
    pd.DataFrame(bins).to_csv(out/'taf_calibration.csv',index=False)
    exposure=pd.DataFrame(stress)
    exposure.to_csv(out/'taf_stress_monthly.csv',index=False)
    summary=pooled(exposure,extras=('group',))
    summary['observed_minus_predicted']=summary.observed-summary.predicted
    summary.to_csv(out/'taf_stress_pooled.csv',index=False)
    day=pd.DataFrame(daily)
    day.to_csv(out/'taf_daily_losses.csv',index=False)
    date_blocks(day,protocol).to_csv(out/'taf_date_blocks.csv',index=False)
    stress_day=pd.DataFrame(stress_daily)
    stress_day.to_csv(out/'taf_stress_daily_residuals.csv',index=False)
    date_blocks(stress_day,protocol).to_csv(out/'taf_stress_date_blocks.csv',index=False)
    return {'normalized_taf_sha256':sha(taf_path),'taf_product_inventory_sha256':sha(products_path),'training_match_n':train_count,
            'sampled_training_rows':n_sampled,'calibration_match_n':cal_count,
            'match_rule':info,'coverage_months':int(result.period.nunique()),
            'calendar_proxy_2026':HOLIDAYS,
            'calibration_scope':'Same time-eligible schedule proxy flights for both models'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=PROTOCOL)
    parser.add_argument('--stage',choices=['primary','weather','all'],default='all')
    parser.add_argument('--taf',type=Path)
    parser.add_argument('--taf-products',type=Path)
    args=parser.parse_args()
    if args.stage in ('all','weather') and (args.taf is None or args.taf_products is None):
        parser.error('--taf and --taf-products are required for the weather stage')
    protocol=json.loads(args.protocol.read_text(encoding='utf-8-sig'))
    new_directory(args.out)
    train, cal, test=prepare(args.data,protocol,args.out)
    result={'status':'completed','stage':args.stage,'protocol_sha256':sha(args.protocol),
            'scored_after_rule_freeze':protocol['holdout_months'],
            'previously_reviewed':protocol['previously_inspected_months'],
            'training_n':len(train),'calibration_n':len(cal),
            'archived_2027_live_forecast_authorized':False,
            'environment':{'python':platform.python_version(),'numpy':np.__version__,
                           'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__}}
    if args.stage in ('all','primary'):
        primary(train,cal,test,protocol,args.out)
    if args.stage in ('all','weather'):
        result['weather']=weather(train,cal,test,protocol,args.taf,args.taf_products,args.out)
    result['completed_utc']=datetime.now(UTC).isoformat()
    save_json(result,args.out/'study_status.json')


if __name__=='__main__':
    main()

