"""Replay the frozen binary methods with revised TAF, or score later official BTS months."""
from datetime import UTC, datetime
from pathlib import Path
import argparse
import json
import platform

import numpy as np
import pandas as pd
import scipy
import sklearn

from run_study_v7 import (HOLIDAYS, PROTOCOL, ROOT, date_blocks, new_directory,
                          prepare, save_json, sha, weather)


V8_PROTOCOL = ROOT / 'docs/VALIDATION_V8.json'
V7_RESULTS = ROOT / 'results/v7_20261128/weather'
V7_PRODUCTS = ROOT / 'data/taf_v7/taf_products_normalized.csv.gz'
STATIC = 'schedule_proxy_only'
TAF = 'schedule_plus_origin_taf'
CONTRAST = 'revised_taf_minus_original_taf'
HOLIDAYS_2026_EXTENSION = ('2026-10-12', '2026-11-11', '2026-11-26', '2026-12-25')


def protocol_for_months(prospective_months=()):
    v8 = json.loads(V8_PROTOCOL.read_text(encoding='utf-8-sig'))
    if sha(PROTOCOL) != v8['v7_protocol_sha256']:
        raise ValueError('The v7 protocol differs from the locked v8 reference')
    original = json.loads(PROTOCOL.read_text(encoding='utf-8-sig'))
    if (original['holdout_months'] != v8['retrospective_score_months'] or
            original['previously_inspected_months'] != v8['retrospective_reference_months']):
        raise ValueError('The retrospective scopes differ from the v7 reference')
    months = sorted(prospective_months)
    if not months:
        return original
    if len(months) != len(set(months)) or not set(months) <= set(v8['prospective_months']):
        raise ValueError('Select unique prospective months from VALIDATION_V8.json')
    return {**original, 'holdout_months': months, 'previously_inspected_months': []}


def read_pair(first, second, name, keys, validate):
    combined = pd.read_csv(first/name).merge(
        pd.read_csv(second/name), on=keys, how='outer', validate=validate,
        indicator=True, suffixes=('_original','_revised'))
    if not combined['_merge'].eq('both').all() or combined.empty:
        raise ValueError(f'Unpaired result rows in {name}')
    return combined.drop(columns=['_merge'])


def compare(original, revised, protocol):
    """Verify outcomes/identities and subtract the same static reference losses."""
    monthly = read_pair(original, revised, 'taf_monthly.csv',
                        ['period','scope','threshold_minutes','method'], 'one_to_one')
    for name in ('identity_sha256','n','events'):
        if not monthly[f'{name}_original'].equals(monthly[f'{name}_revised']):
            raise ValueError(f'The revised forecast has a different {name}')
    for name in ('brier','log_loss','predicted'):
        schedule = monthly.loc[monthly.method.eq(STATIC)]
        if schedule.empty or not np.allclose(schedule[f'{name}_original'],
                                             schedule[f'{name}_revised'], atol=1e-10, rtol=0):
            raise ValueError(f'Schedule-only comparison changed: {name}')
    pooled = read_pair(original, revised, 'taf_pooled.csv',
                       ['scope','threshold_minutes','method'], 'one_to_one')
    for name in ('n','events','months'):
        if not pooled[f'{name}_original'].equals(pooled[f'{name}_revised']):
            raise ValueError(f'The pooled forecast has a different {name}')
    summary = pooled.loc[pooled.method.eq(TAF),
                         ['scope','threshold_minutes','n_original','observed_original',
                          'predicted_original','predicted_revised','brier_original','brier_revised',
                          'log_loss_original','log_loss_revised']].copy()
    summary.rename(columns={'n_original':'n','observed_original':'observed'}, inplace=True)
    summary['brier_change'] = summary.brier_revised-summary.brier_original
    summary['log_loss_change'] = summary.log_loss_revised-summary.log_loss_original
    summary['scope'] = summary.scope.map({'frozen_followup':'retrospective_jan_aug',
                                          'previously_reviewed':'retrospective_september'})
    if summary.scope.isna().any():
        raise ValueError('Unexpected retrospective scope')
    daily = read_pair(original, revised, 'taf_daily_losses.csv',
                      ['date','threshold_minutes','contrast'], 'one_to_one')
    if not daily.n_original.equals(daily.n_revised):
        raise ValueError('Weather contrast lost paired days')
    paired = pd.DataFrame({'date':daily.date,'threshold_minutes':daily.threshold_minutes,
                           'n':daily.n_original,'sum_delta':daily.sum_delta_revised-daily.sum_delta_original,
                           'contrast':CONTRAST})
    dates = pd.to_datetime(paired.date).dt.to_period('M').astype(str)
    for scope, months in [('retrospective_jan_aug',protocol['holdout_months']),
                          ('retrospective_september',protocol['previously_inspected_months'])]:
        for threshold, group in paired.loc[dates.isin(months)].groupby('threshold_minutes'):
            expected = summary.loc[summary.scope.eq(scope) & summary.threshold_minutes.eq(threshold),
                                   'brier_change'].item()
            if abs(group.sum_delta.sum()/group.n.sum() - expected) > 1e-10:
                raise ValueError('Daily and pooled source-correction contrasts disagree')
    summary.to_csv(revised/'taf_source_impact_pooled.csv',index=False)
    paired.to_csv(revised/'taf_source_impact_daily.csv',index=False)
    date_blocks(paired,protocol).to_csv(revised/'taf_source_impact_date_blocks.csv',index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--taf',type=Path,required=True)
    parser.add_argument('--taf-products',type=Path,default=V7_PRODUCTS)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--reference',type=Path,default=V7_RESULTS)
    parser.add_argument('--prospective-month', action='append', default=[])
    args = parser.parse_args()
    protocol = protocol_for_months(args.prospective_month)
    mode = 'prospective_registered_windows' if args.prospective_month else 'retrospective_source_replay'
    new_directory(args.out)
    train, cal, test = prepare(args.data,protocol,args.out)
    result = weather(train,cal,test,protocol,args.taf,args.taf_products,args.out,
                     holidays=HOLIDAYS+list(HOLIDAYS_2026_EXTENSION))
    if not args.prospective_month:
        compare(args.reference,args.out,protocol)
    save_json({'status':'completed','mode':mode,'v8_protocol_sha256':sha(V8_PROTOCOL),
               'v7_protocol_sha256':sha(PROTOCOL),'scored_months':protocol['holdout_months'],
               'reference_months':protocol['previously_inspected_months'],
               'newly_unseen_outcome_claim':False,'live_2027_forecast_authorized':False,
               'training_n':len(train),'calibration_n':len(cal),
               'weather':result,'completed_utc':datetime.now(UTC).isoformat(),
               'environment':{'python':platform.python_version(),'numpy':np.__version__,
                              'pandas':pd.__version__,'scipy':scipy.__version__,
                              'sklearn':sklearn.__version__}}, args.out/'study_status.json')


if __name__ == '__main__':
    main()
