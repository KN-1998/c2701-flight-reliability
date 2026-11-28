"""Post-v7 descriptive audit; never refits to the reviewed 2026 outcomes.

Reconstruct the frozen weather fit, retain every threshold inversion and quantify
matched/unmatched outcome composition. Zero inversions do not authorize a joint card.
"""
from pathlib import Path
from datetime import datetime, UTC
import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from prediction import apply_sigmoid, evaluate, joint_target, prob, stable_flight_key
from predeparture_v7 import TAF_NUMBERS
from run_study_v7 import (PROTOCOL, ROOT, THRESHOLDS, attach, fit_weather_models,
                          groups, identity_digest, new_directory, prepare, weather_features)
from predeparture_v7 import read_taf

ATOL = 1e-12
METHODS = ('schedule_proxy_only', 'schedule_plus_origin_taf')
DETAIL = ['flight_key', 'date', 'period', 'scope', 'method',
          'lower_probability', 'upper_probability', 'upper_minus_lower']


def threshold_tables(flights, predictions, period, scope, *, atol=ATOL):
    """Pair by an identical audited frame; preserve raw probabilities, not a repair."""
    if not np.isfinite(atol) or atol < 0 or flights.empty:
        raise ValueError('A nonempty frame and finite nonnegative tolerance are required')
    keys = stable_flight_key(flights)
    if keys.duplicated().any():
        raise ValueError('Duplicate audited flight key')
    if set(predictions) != set(METHODS):
        raise ValueError('Exactly both frozen weather methods are required')
    actual_months = flights.date.dt.strftime('%Y-%m')
    if not actual_months.eq(period).all():
        raise ValueError('Flight dates differ from the declared month')
    low_y, high_y = (joint_target(flights, t) for t in THRESHOLDS)
    if np.any(high_y > low_y):
        raise ValueError('Observed threshold events are not nested')
    rows, detail = [], []
    for method in METHODS:
        pair = predictions[method]
        if set(pair) != set(THRESHOLDS):
            raise ValueError('Both threshold predictions are required')
        low, high = (np.asarray(pair[t], dtype=float) for t in THRESHOLDS)
        for arr in (low, high):
            if arr.shape != (len(flights),) or not np.isfinite(arr).all() or np.any((arr < 0) | (arr > 1)):
                raise ValueError('Invalid paired probabilities')
        gap = high - low
        violated = gap > atol
        rows.append({'period': period, 'scope': scope, 'method': method, 'n': len(flights),
                     'identity_sha256': identity_digest(flights),
                     'lower_events': int(low_y.sum()), 'upper_events': int(high_y.sum()),
                     'violations': int(violated.sum()), 'violation_rate': float(violated.mean()),
                     'max_upper_minus_lower': float(gap.max()),
                     'mean_lower_probability': float(low.mean()), 'mean_upper_probability': float(high.mean()),
                     'lower_minutes': 15, 'upper_minutes': 60, 'atol': atol})
        for pos in np.flatnonzero(violated):
            detail.append({'flight_key': keys.iloc[pos], 'date': str(flights.date.iloc[pos].date()),
                           'period': period, 'scope': scope, 'method': method,
                           'lower_probability': float(low[pos]), 'upper_probability': float(high[pos]),
                           'upper_minus_lower': float(gap[pos])})
    return pd.DataFrame(rows), pd.DataFrame(detail, columns=DETAIL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=ROOT/'data')
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    parser.add_argument('--taf', type=Path, default=ROOT/'data/taf_v7/taf_prevailing_normalized.csv.gz')
    parser.add_argument('--taf-products', type=Path, default=ROOT/'data/taf_v7/taf_products_normalized.csv.gz')
    parser.add_argument('--reference', type=Path, default=ROOT/'results/v7_20261128/weather/taf_monthly.csv')
    parser.add_argument('--predictions-dir', type=Path, help='Optional NEW external directory for all raw paired probabilities')
    args = parser.parse_args()
    new_directory(args.out)
    if args.predictions_dir:
        new_directory(args.predictions_dir)
    protocol = json.loads(args.protocol.read_text(encoding='utf-8-sig'))
    train, cal, test = prepare(args.data, protocol, args.out)
    taf = read_taf(args.taf, args.taf_products)
    info = protocol['information_experiment']
    train = attach(train, taf, info)
    cal = attach(cal, taf, info)
    fitted = {t: fit_weather_models(train, cal, protocol['fit_scope'], t)[0] for t in THRESHOLDS}
    del train, cal
    summaries, details, scores, composition, missingness, inventories = [], [], [], [], [], []
    for period, flight in groups(test):
        scope = 'frozen_followup' if period in protocol['holdout_months'] else 'previously_reviewed'
        data = attach(flight, taf, info)
        for group, subset in [('matched', data), ('unmatched', flight.loc[~flight.index.isin(data.index)])]:
            for origin, part in [('ALL', subset), *list(subset.groupby('Origin', observed=True))]:
                for threshold in THRESHOLDS:
                    y = joint_target(part, threshold)
                    composition.append({'period': period, 'scope': scope, 'group': group, 'Origin': origin,
                                        'threshold_minutes': threshold, 'n': len(part), 'events': int(y.sum()),
                                        'observed': float(y.mean()) if len(y) else None})
        predictions = {name: {} for name in METHODS}
        for threshold, models in fitted.items():
            y = joint_target(data, threshold)
            for use_weather, (model, calibrator) in models.items():
                name = METHODS[int(use_weather)]
                p = apply_sigmoid(prob(model, weather_features(data, use_weather)), calibrator)
                predictions[name][threshold] = p
                scores.append({'period': period, 'scope': scope, 'threshold_minutes': threshold,
                               'method': name, 'identity_sha256': identity_digest(data), **evaluate(y, p)})
        summary, detail = threshold_tables(data, predictions, period, scope)
        summaries.append(summary)
        details.append(detail)
        for group, part in [('all_matched', data), ('no_adverse_signal', data.loc[data.adverse_forecast.eq(0)])]:
            missingness.append({'period': period, 'scope': scope, 'group': group, 'n': len(part),
                                **{name+'_missing': int(part[name].isna().sum()) for name in TAF_NUMBERS},
                                'unknown_ceiling': int((part.clear_ceiling.eq(0) & part.ceiling_ft_agl.isna()).sum()),
                                'visibility_and_ceiling_unknown': int((part.clear_ceiling.eq(0) & part.ceiling_ft_agl.isna() & part.visibility_sm.isna()).sum())})
        if args.predictions_dir:
            raw = pd.DataFrame({'flight_key': stable_flight_key(data).to_numpy()})
            for method in METHODS:
                for threshold in THRESHOLDS:
                    raw[f'{method}_{threshold}'] = predictions[method][threshold]
            path = args.predictions_dir/f'weather_paired_{period}.csv.gz'
            raw.to_csv(path, index=False, compression={'method': 'gzip', 'mtime': 0})
            inventories.append({'file': path.name, 'bytes': path.stat().st_size,
                                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        print('Weather coherence audited', period, len(data), summary.violations.tolist(), flush=True)
    monthly = pd.concat(summaries, ignore_index=True)
    counterexamples = pd.concat(details, ignore_index=True)
    if counterexamples.duplicated(['flight_key', 'method']).any():
        raise ValueError('Duplicate inversion flight and method')
    monthly.to_csv(args.out/'weather_threshold_monthly.csv', index=False)
    counterexamples.to_csv(args.out/'weather_threshold_inversions.csv', index=False)
    totals = []
    for (scope, method), group in monthly.groupby(['scope', 'method'], sort=True):
        totals.append({'scope': scope, 'method': method, 'n': int(group.n.sum()),
                       'violations': int(group.violations.sum()),
                       'violation_rate': float(group.violations.sum()/group.n.sum()),
                       'max_upper_minus_lower': float(group.max_upper_minus_lower.max())})
    pd.DataFrame(totals).to_csv(args.out/'weather_threshold_pooled.csv', index=False)
    pd.DataFrame(composition).to_csv(args.out/'match_outcome_composition.csv', index=False)
    pd.DataFrame(missingness).to_csv(args.out/'forecast_missingness.csv', index=False)
    result = pd.DataFrame(scores)
    result.to_csv(args.out/'reconstructed_weather_scores.csv', index=False)
    frozen = pd.read_csv(args.reference)
    key = ['period', 'scope', 'threshold_minutes', 'method']
    a, b = result.set_index(key).sort_index(), frozen.set_index(key).sort_index()
    if not a.index.equals(b.index) or not a.n.equals(b.n) or not a.events.equals(b.events) or not a.identity_sha256.equals(b.identity_sha256):
        raise ValueError('Reconstructed weather identity or denominator differs')
    delta = (a[['predicted', 'brier', 'log_loss']]-b[['predicted', 'brier', 'log_loss']]).abs().max().max()
    if not np.isfinite(delta) or delta > 1e-10:
        raise ValueError('Reconstructed weather scores differ')
    status = {'status': 'DESCRIPTIVE_POST_V7_AUDIT_COMPLETE', 'completed_utc': datetime.now(UTC).isoformat(),
              'maximum_reference_score_abs_difference': float(delta), 'summary': totals,
              'inversion_records': len(counterexamples), 'strict_gap_tolerance': ATOL,
              'joint_weather_card_authorized': False, 'live_2027_forecast_authorized': False,
              'role': 'Previously inspected 2026 outcomes; no new blind validation and no model repair',
              'raw_paired_prediction_inventory': inventories}
    (args.out/'WEATHER_AUDIT_STATUS.json').write_text(json.dumps(status, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
