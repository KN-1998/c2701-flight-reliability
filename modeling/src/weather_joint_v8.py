"""Evaluate one coherent archived-weather five-leaf distribution at both thresholds.

Both threshold estimates come from the same cancellation, diversion and delay
leaves. The two matched models use identical branch risk sets and samples.
The default retrospective comparison does not select a model or authorize live use.
"""
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
import argparse
import json
import platform
import warnings

import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from joint_candidate_v6 import BRANCHES, LEAVES, SharedFiveLeafModel, _structure, observed_leaves
from prediction import CATS, NUMS, estimator, evaluate, joint_target
from predeparture_v7 import TAF_FEATURES, read_taf
from run_study_v7 import (
    HOLIDAYS, PROTOCOL, ROOT, THRESHOLDS, attach, date_blocks, groups, identity_digest,
    losses, new_directory, pooled, prepare, save_json, score, sha, taf_coverage, weather_features,
)


SCHEDULE = 'shared_schedule'
WEATHER = 'shared_schedule_plus_origin_taf'
FALLBACK = 'shared_taf_with_schedule_fallback'
MATCHED = 'taf_matched'
ALL = 'all_eligible'
JAN_AUG = 'retrospective_2026_jan_aug'
SEPTEMBER = 'separately_reviewed_2026_sep'
LATER = 'prespecified_after_september_2026'
V8_PROTOCOL = ROOT / 'docs/VALIDATION_V8.json'
HOLIDAYS_2026 = [*HOLIDAYS, '2026-10-12', '2026-11-11', '2026-11-26', '2026-12-25']
KEYS = ['period', 'threshold_minutes']
REFERENCE_METHODS = {'schedule_proxy_only', 'schedule_plus_origin_taf'}


def weather_binary(features, outcomes, regularization_c):
    """V7 TAF preprocessing on one branch's exact sampled risk set."""
    if len(outcomes) == 0:
        raise ValueError('Empty weather branch training set')
    if len(np.unique(outcomes)) == 1:
        return float(outcomes.mean()), []
    model = estimator(regularization_c)
    preparation = model.named_steps['features']
    weather = Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True)),
                        ('scale', StandardScaler())])
    preparation.transformers.append(('archived_taf', weather, TAF_FEATURES))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model.fit(features, outcomes)
    return model, [str(warning.message) for warning in caught]


def fit_pair(train, cal, fit):
    settings = {'regularization_c': fit['C'], 'fit_cap': fit['fit_cap'], 'seed': fit['random_seed']}
    schedule = SharedFiveLeafModel(**settings).fit(train, cal)
    with_taf = SharedFiveLeafModel(
        **settings, feature_builder=partial(weather_features, use_weather=True),
        binary_fitter=weather_binary,
    ).fit(train, cal)
    for baseline, augmented in zip(schedule.risk_counts, with_taf.risk_counts, strict=True):
        ignored = {'fit_warnings'}
        if ({k: v for k, v in baseline.items() if k not in ignored} !=
                {k: v for k, v in augmented.items() if k not in ignored}):
            raise ValueError('The shared five-leaf models require identical branch risk sets')
    return schedule, with_taf


def apply_fallback(full_index, matched_index, schedule, with_taf):
    """Populate all eligible rows with matched TAF predictions and schedule otherwise."""
    if not full_index.is_unique or not matched_index.is_unique:
        raise ValueError('Fallback requires unique audited row indexes')
    positions = full_index.get_indexer(matched_index)
    if np.any(positions < 0):
        raise ValueError('Every TAF matched row must belong to the scoring population')
    if (len(schedule) != len(with_taf) or any(
            len(base) != len(full_index) or len(new) != len(matched_index)
            or base.shape[1:] != new.shape[1:] for base, new in zip(schedule, with_taf))):
        raise ValueError('Fallback probability rows or leaves do not agree with the audited indexes')
    output = tuple(prediction.copy() for prediction in schedule)
    for combined, prediction in zip(output, with_taf):
        combined[positions] = prediction
    return output


def compare_reference(candidate, path, variant):
    """Require exact paired denominators, events and BTS identity against a binary reference."""
    reference = pd.read_csv(path)
    expected = candidate.loc[candidate.method.eq(WEATHER), [
        *KEYS, 'n', 'events', 'identity_sha256',
    ]].sort_values(KEYS).reset_index(drop=True)
    if set(reference.method) != REFERENCE_METHODS:
        raise ValueError('Unexpected reference method inventory')
    for method, frame in reference.groupby('method', sort=False):
        if not frame[list(expected.columns)].sort_values(KEYS).reset_index(drop=True).equals(expected):
            raise ValueError(f'Unpaired reference scores for {variant}/{method}')
    remap = {JAN_AUG: 'frozen_followup', SEPTEMBER: 'previously_reviewed'}
    scopes = candidate[['period', 'scope']].drop_duplicates().set_index('period').scope
    if not reference.scope.eq(reference.period.map(scopes).map(remap)).all():
        raise ValueError(f'Incorrect source month labels in {variant}')
    reference = reference.assign(scope=reference.period.map(scopes))
    # Keep shared scores and binary references side by side without replacing either.
    return reference.assign(method=variant + '_' + reference.method)


def record_population(population, frame, period, scope, predictions, monthly, bins, structure, leaf):
    digest = identity_digest(frame)
    for method, (leaves, p15, p60) in predictions.items():
        meta = {'period': period, 'scope': scope, 'method': method, 'n': len(frame),
                'identity_sha256': digest, 'population': population}
        structure.append({**meta, **_structure(leaves, p15, p60)})
    for threshold_index, threshold in enumerate(THRESHOLDS, start=1):
        outcome = joint_target(frame, threshold)
        for method, estimates in predictions.items():
            score(monthly, bins, period, scope, threshold, method, outcome, estimates[threshold_index], digest)
    observed = observed_leaves(frame)
    for method, (leaves, _, _) in predictions.items():
        for name, outcome, predicted in zip(LEAVES, observed.T, leaves.T, strict=True):
            leaf.append({'period': period, 'scope': scope, 'method': method, 'leaf': name,
                         'n': len(frame), 'events': int(outcome.sum()), 'observed': float(outcome.mean()),
                         'predicted': float(predicted.mean()), 'brier': float(np.mean((outcome-predicted)**2)),
                         'identity_sha256': digest, 'population': population})


def study_months(base, registry, later_months):
    """Separate later months from retrospective results before auditing any flight rows."""
    early = registry['retrospective_score_months']
    reviewed = registry['retrospective_reference_months']
    if early != base['holdout_months'] or reviewed != base['previously_inspected_months']:
        raise ValueError('V8 retrospective month registry disagrees with V7 score months')
    if not later_months:
        return base, (dict.fromkeys(early, JAN_AUG) | dict.fromkeys(reviewed, SEPTEMBER))
    selected = set(later_months)
    if (len(selected) != len(later_months) or not selected.issubset(registry['prospective_months'])
            or any(month <= max(early + reviewed) for month in selected)):
        raise ValueError('Later readouts require distinct registered months after September 2026')
    return ({**base, 'holdout_months': sorted(selected), 'previously_inspected_months': []},
            dict.fromkeys(sorted(selected), LATER))


def run(data, protocol_file, registry_file, later_months, segment_file, product_file,
        original_weather, corrected_weather, out):
    base = json.loads(protocol_file.read_text(encoding='utf-8-sig'))
    registry = json.loads(registry_file.read_text(encoding='utf-8-sig'))
    if sha(protocol_file) != registry['v7_protocol_sha256']:
        raise ValueError('Unexpected freeze protocol fingerprint')
    protocol, periods = study_months(base, registry, later_months)
    if later_months and (original_weather is not None or corrected_weather is not None):
        raise ValueError('Do not compare retrospective reference tables with later-month readouts')
    if not later_months and original_weather is None:
        raise ValueError('Retrospective V7 binary reference is required')
    new_directory(out)
    train, calibration, test = prepare(data, protocol, out)
    taf = read_taf(segment_file, product_file)
    timing = protocol['information_experiment']
    matched_train = attach(train, taf, timing)
    matched_cal = attach(calibration, taf, timing)
    coverage = (taf_coverage('fit', 'all', train, matched_train) +
                taf_coverage('calibration', 'all', calibration, matched_cal))
    fit_input_counts = {'fit_eligible': len(train), 'fit_matched': len(matched_train),
                        'calibration_eligible': len(calibration), 'calibration_matched': len(matched_cal)}
    print('Matched branch fit/calibration input', len(matched_train), len(matched_cal), flush=True)
    del train, calibration
    schedule, with_taf = fit_pair(matched_train, matched_cal, protocol['fit_scope'])
    del matched_train, matched_cal
    risk_rows = [{**row, 'method': name} for name, model in ((SCHEDULE, schedule), (WEATHER, with_taf))
                 for row in model.risk_counts]
    pd.DataFrame(risk_rows).to_csv(out / 'shared_weather_risk_sets.csv', index=False)

    monthly, bins, all_monthly, all_bins, structure, leaf, daily, stress = [], [], [], [], [], [], [], []
    holidays = pd.to_datetime(HOLIDAYS_2026)
    holiday_window = {day + pd.Timedelta(days=delta) for day in holidays for delta in (-1, 0, 1)}
    for period, flight in groups(test):
        scope = periods[period]
        matched = attach(flight, taf, timing)
        if matched.empty and not later_months:
            raise ValueError(f'No eligible archived TAF matches in {period}')
        coverage.extend(taf_coverage('score', period, flight, matched))
        schedule_all = schedule.predict(flight)
        matched_positions = flight.index.get_indexer(matched.index)
        if (matched_positions < 0).any():
            raise ValueError('Matched TAF rows absent from original test rows')
        schedule_matched = tuple(p[matched_positions] for p in schedule_all)
        weather_matched = with_taf.predict(matched) if not matched.empty else schedule_matched
        hybrid = apply_fallback(flight.index, matched.index, schedule_all, weather_matched)
        if not matched.empty:
            record_population(MATCHED, matched, period, scope, {SCHEDULE: schedule_matched, WEATHER: weather_matched},
                              monthly, bins, structure, leaf)
        record_population(ALL, flight, period, scope, {SCHEDULE: schedule_all, FALLBACK: hybrid},
                          all_monthly, all_bins, structure, leaf)
        masks = {
            'adverse_forecast': matched.adverse_forecast.eq(1),
            'no_adverse_signal': matched.adverse_forecast.ne(1),
            'holiday_proxy_window': matched.date.isin(holiday_window),
            'other_calendar_days': ~matched.date.isin(holiday_window),
        }
        for threshold_index, threshold in enumerate(THRESHOLDS, start=1):
            outcome = joint_target(matched, threshold)
            matched_ref, matched_taf = schedule_matched[threshold_index], weather_matched[threshold_index]
            losses(daily, matched.date, threshold, WEATHER + '_minus_' + SCHEDULE,
                   (outcome-matched_taf)**2 - (outcome-matched_ref)**2)
            full_outcome = joint_target(flight, threshold)
            losses(daily, flight.date, threshold, FALLBACK + '_minus_' + SCHEDULE,
                   (full_outcome-hybrid[threshold_index])**2 - (full_outcome-schedule_all[threshold_index])**2)
            for group, mask in masks.items():
                if mask.any():
                    for method, prediction in ((SCHEDULE, matched_ref), (WEATHER, matched_taf)):
                        stress.append({'period': period, 'scope': scope, 'threshold_minutes': threshold,
                                       'method': method, 'group': group, **evaluate(outcome[mask], prediction[mask])})
        print('Shared weather scores', period, f'{len(matched)}/{len(flight)}', flush=True)

    monthly = pd.DataFrame(monthly)
    references = []
    if original_weather is not None:
        references.append(compare_reference(monthly, original_weather, 'archived_binary'))
    if corrected_weather is not None:
        references.append(compare_reference(monthly, corrected_weather, 'corrected_binary'))
    all_monthly = pd.DataFrame(all_monthly)
    same_sample = pd.concat([monthly, *references], ignore_index=True)
    daily = pd.DataFrame(daily)
    stress = pd.DataFrame(stress)
    tables = {
        'shared_weather_leaf_monthly': pd.DataFrame(leaf),
        'shared_weather_structure': pd.DataFrame(structure),
        'shared_weather_coverage_by_airport': pd.DataFrame(coverage),
        'shared_weather_fallback_monthly': all_monthly,
        'shared_weather_fallback_pooled': pooled(all_monthly),
        'shared_weather_fallback_calibration': pd.DataFrame(all_bins),
        'shared_weather_daily_losses': daily,
        'shared_weather_date_blocks': date_blocks(daily, protocol),
    }
    if not monthly.empty:
        tables.update(
            shared_weather_monthly=monthly,
            shared_weather_pooled=pooled(monthly),
            shared_weather_calibration=pd.DataFrame(bins),
            shared_weather_stress_monthly=stress,
            shared_weather_stress_pooled=pooled(stress, extras=('group',)),
            shared_weather_comparison_monthly=same_sample,
            shared_weather_comparison_pooled=pooled(same_sample),
        )
    for name, table in tables.items():
        table.to_csv(out / (name + '.csv'), index=False)
    save_json({
        'status': ('later_month_coherent_candidate_scored' if later_months
                   else 'retrospective_coherent_weather_candidate_scored'),
        'months_and_labels': periods,
        'v7_evaluation_months_were_already_observed': True,
        'later_month_scoring_completed': bool(later_months),
        'first_access_to_later_outcomes_requires_external_confirmation': bool(later_months),
        'live_prediction_authorized': False,
        'refit_settings': protocol['fit_scope'],
        'as_of_matching_rule': timing,
        'sample_pairing': 'Both models use the same audited matched pool, branch masks, ordered seed and fit cap.',
        'fallback': ('Both whole-population forecasts share the matched-pool schedule model for rows without '
                     'a usable TAF. This is a retrospective fallback policy check.'),
        'threshold_minutes': list(THRESHOLDS),
        'leaf_names': list(LEAVES),
        'branch_names': list(BRANCHES),
        'schedule_features': CATS + NUMS,
        'additional_weather_features': TAF_FEATURES,
        'probability_structure': 'Per-branch sigmoid calibration precedes multiplication. No threshold reordering.',
        'reference_counts_and_identity_checked': bool(references),
        'matched_score_months': sorted(monthly.period.unique()) if not monthly.empty else [],
        'fit_input_counts': fit_input_counts,
        'max_leaf_sum_error': max(row['max_leaf_sum_error'] for row in structure),
        'max_reconstruction_error': max(row['max_threshold_reconstruction_error'] for row in structure),
        'threshold_violations': sum(row['threshold_violations'] for row in structure),
        'input_sha256': {'protocol': sha(protocol_file), 'v8_registry': sha(registry_file),
                         'taf_segments': sha(segment_file), 'taf_products': sha(product_file),
                         'v7_binary': sha(original_weather) if original_weather is not None else None,
                         'v8_binary': sha(corrected_weather) if corrected_weather is not None else None},
        'environment': {'python': platform.python_version(), 'numpy': np.__version__,
                        'pandas': pd.__version__, 'scipy': scipy.__version__, 'sklearn': sklearn.__version__},
        'completed_utc': datetime.now(UTC).isoformat(),
    }, out / 'shared_weather_status.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT / 'data')
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    parser.add_argument('--v8-protocol', type=Path, default=V8_PROTOCOL)
    parser.add_argument('--prospective-month', action='append', default=[],
                        help='Score a registered later month supplied in the audited data (repeatable)')
    parser.add_argument('--taf', type=Path, required=True)
    parser.add_argument('--taf-products', type=Path, default=ROOT / 'data/taf_v7/taf_products_normalized.csv.gz')
    parser.add_argument('--original-weather', type=Path)
    parser.add_argument('--corrected-weather', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    original = args.original_weather
    if not args.prospective_month and original is None:
        original = ROOT / 'results/v7_20261128/weather/taf_monthly.csv'
    run(args.data, args.protocol, args.v8_protocol, args.prospective_month, args.taf, args.taf_products,
        original, args.corrected_weather, args.out)


if __name__ == '__main__':
    main()
