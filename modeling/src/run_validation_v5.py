"""Audit month files, then score the frozen primary models without tuning on holdouts."""
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

from audit import KEY, audit, metrics
from calibration_diagnostics import analyze_saved
from comparison import compare
from fetch_bts import AIRPORTS
from forecast_protocol import parse_forecast_protocol
from prediction import apply_sigmoid, evaluate, features, fit_binary, fit_sigmoid, prob, run_prediction
from stress import stress_tests

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'docs/VALIDATION_V5.json'
EVENTS = ROOT / 'docs/EXTERNAL_EVENTS_V5.json'
CORE = {f'{year}-{month:02}' for year in range(2023, 2026) for month in range(1, 13)}
FEATURE_COLUMNS = [
    'date', 'year', 'month', 'quarter', 'weekday', 'season', 'Origin', 'Dest',
    'Reporting_Airline', 'state', 'completed', 'bad', 'ArrDelay', 'dep_minutes',
    'arr_minutes', 'time_bin', 'distance_bin', 'Distance', 'CRSElapsedTime',
]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save_json(value, path):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def audit_months(data, periods, out, *, extra_columns=()):
    columns = list(dict.fromkeys([*FEATURE_COLUMNS, *extra_columns]))
    frames, monthly, coverage, unknown, sources = [], [], [], [], []
    for path in sorted(data.glob('bts_????_??.csv.gz')):
        period = path.name[4:11].replace('_', '-')
        if period not in periods:
            continue
        source = path.with_name(path.name.replace('.csv.gz', '.json'))
        record = json.loads(source.read_text(encoding='utf-8-sig'))
        if record['period'] != period or record['filtered_file'] != path.name:
            raise ValueError(f'Month metadata does not match {path.name}')
        if sha(path) != record['sha256_filtered']:
            raise ValueError(f'Filtered SHA mismatch: {path.name}')
        raw = pd.read_csv(path, low_memory=False)
        if len(raw) != record['selected_origin_rows']:
            raise ValueError(f'Month row count mismatch: {path.name}')
        date = pd.to_datetime(raw.FlightDate, errors='raise')
        expected_days = pd.date_range(f'{period}-01', pd.Period(period).end_time.normalize())
        for origin, group in raw.assign(date=date).groupby('Origin', observed=True):
            days = pd.DatetimeIndex(group.date.unique()).sort_values()
            if not days.equals(expected_days):
                raise ValueError(f'Incomplete or out-of-month dates for {origin} in {period}')
        if set(raw.Origin.unique()) != set(AIRPORTS):
            raise ValueError(f'Airport scope mismatch in {path.name}')
        frame, counts = audit(raw)
        counts.update(period=period, national_rows=record['national_rows'], verified_days=len(expected_days))
        monthly.append(counts)
        selected = frame.loc[frame.state.eq('unknown'), [
            'FlightDate', 'Origin', 'Dest', 'Reporting_Airline', 'Flight_Number_Reporting_Airline', 'audit_reason'
        ]]
        if not selected.empty:
            unknown.append(selected)
        for (carrier, carrier_id), group in frame.groupby(
                ['Reporting_Airline', 'DOT_ID_Reporting_Airline'], dropna=False):
            coverage.append({'period':period, 'reporting_airline':carrier, 'dot_id':carrier_id,
                             'retained_rows':len(group), 'observed_days':group.date.nunique(),
                             'airports':group.Origin.nunique()})
        frames.append(frame[columns])
        sources.append(record)
        print(f'audited {period}: {len(frame)} rows, unknown={counts["unknown"]}', flush=True)
    if not frames:
        raise ValueError('No verified monthly extracts')
    pd.DataFrame(monthly).to_csv(out/'audit_by_month.csv', index=False)
    pd.DataFrame(coverage).to_csv(out/'reporting_carrier_coverage.csv', index=False)
    if unknown:
        pd.concat(unknown, ignore_index=True).to_csv(out/'unknown_records.csv', index=False)
    save_json({'records':sources, 'total_rows':sum(rec['retained_rows'] for rec in monthly)}, out/'data_snapshot.json')
    frame = pd.concat(frames, ignore_index=True)
    for name in ('season','Origin','Dest','Reporting_Airline','state','distance_bin'):
        frame[name] = frame[name].astype('category')
    return frame, {monthly_row['period'] for monthly_row in monthly}


def summarize_holdouts(scores, protocol, out):
    joint = scores.loc[scores.target.eq('joint')].copy()
    primary = scores.threshold_minutes.iloc[0]
    expected = {'historical_baseline','conditional_tree','direct_joint'}
    shared = ['n', 'events', 'test_row_hash']
    if 'flight_identity_sha256' in joint:
        shared.append('flight_identity_sha256')
    for period, rows in joint.groupby('period'):
        if set(rows.method) != expected or len(rows) != 3 or any(
                rows[col].nunique() != 1 for col in shared):
            raise ValueError(f'Unequal test rows across models in {period}')
    group_names = {
        'new_core_months': protocol['new_core_months'],
        'previously_scored_months': protocol['previously_scored_months'],
        'late_months': protocol['late_months'],
    }
    month_scopes = {month: scope for scope, months in group_names.items() for month in months}
    joint['scope'] = joint.period.map(month_scopes)
    if joint.scope.isna().any():
        raise ValueError('Unregistered holdout month')
    benchmark = joint.loc[joint.method.eq('historical_baseline')].set_index('period').brier
    joint['brier_minus_baseline'] = joint.brier - joint.period.map(benchmark)
    joint.to_csv(out/'joint_monthly_v5.csv', index=False)
    rows = []
    for (scope, method), group in joint.groupby(['scope','method']):
        n = group.n.sum()
        rows.append({
            'scope':scope,'method':method,'threshold_minutes':primary,
            'month_count':len(group),'expected_months':len(group_names[scope]),
            'n':n,'events':group.events.sum(),'observed':group.events.sum()/n,
            'predicted':np.average(group.predicted,weights=group.n),
            'pooled_brier':np.average(group.brier,weights=group.n),
            'equal_month_brier':group.brier.mean(),
            'pooled_log_loss':np.average(group.log_loss,weights=group.n),
            'wins_vs_baseline':int((group.brier_minus_baseline<0).sum()),
        })
    pooled = pd.DataFrame(rows)
    pooled.to_csv(out/'joint_pooled_v5.csv', index=False)
    seen = set(joint.loc[joint.scope.eq('new_core_months'),'period'])
    missing = sorted(set(protocol['new_core_months'])-seen)
    selection = 'historical_baseline'
    if seen and not missing:
        new = pooled.loc[pooled.scope.eq('new_core_months')]
        base_score = new.loc[new.method.eq('historical_baseline'),'pooled_brier'].item()
        candidates = new.loc[(new.pooled_brier < base_score) & (new.wins_vs_baseline > len(seen)/2)]
        if not candidates.empty:
            selection = candidates.sort_values('pooled_brier').iloc[0].method
    return {'selection':selection, 'missing_new_core_holdouts':missing,
            'late_months_separate':True, 'uncertainty':'descriptive; late month is a separate drift check'}


def check_diversion_fit_cap(frame, protocol, forecast, regularization, out):
    """Change one cap or seed at a time within the existing diversion risk set."""
    new_months = ['2025-02','2025-08','2026-09']
    date = frame.date
    known = frame.state.ne('unknown')
    not_cancelled = frame.state.ne('cancelled')
    train_all = frame.loc[known & date.between(forecast.fit_start, forecast.refit_end)]
    training = train_all.loc[train_all.state.ne('cancelled')]
    month = date.dt.to_period('M').astype(str)
    calibration = frame.loc[known & not_cancelled & month.isin(protocol['calibration_months'])]
    observed_cal = calibration.state.eq('diverted').to_numpy()
    cal_x = features(calibration)
    cases = {}
    for period in new_months:
        data = frame.loc[known & not_cancelled & month.eq(period)]
        if not data.empty:
            cases[period] = (features(data), data.state.eq('diverted').to_numpy())
    rows = []
    cap_main, seed_main = protocol['fit_cap'], protocol['seed']
    for cap, seed in [(cap_main,seed_main),(3*cap_main,seed_main),(cap_main,seed_main+1)]:
        generator = np.random.default_rng(seed)
        if len(train_all) > cap:
            # The main tree draws the cancellation branch before the diversion branch.
            generator.choice(len(train_all), cap, replace=False)
        indices = np.arange(len(training))
        if len(indices) > cap:
            indices = np.sort(generator.choice(indices, cap, replace=False))
        selected = training.iloc[indices]
        target = selected.state.eq('diverted').to_numpy()
        model, warnings = fit_binary(features(selected), target, regularization)
        calibrator = fit_sigmoid(prob(model, cal_x), observed_cal)
        for period, (x, y) in cases.items():
            rows.append({
                'period':period,'fit_cap':cap,'seed':seed,'fitted_n':len(selected),
                'fitted_events':int(target.sum()),'regularization_C':regularization,
                'fit_warning_count':len(warnings),
                **evaluate(y,apply_sigmoid(prob(model,x),calibrator)),
            })
    if rows:
        pd.DataFrame(rows).to_csv(out/'diversion_fit_sensitivity_v5.csv',index=False)
    return {'periods':list(cases),'scopes_compared':len(rows),
            'purpose':'Conditional diversion branch sensitivity; no model selection on these scores.'}


def run_validation(data, out, *, protocol_path=PROTOCOL, events_path=EVENTS,
                   skip_comparison=False, keep_predictions=False,
                   save_flight_identity=False, require_full_data=False):
    data, out = Path(data), Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('Use a fresh output directory')
    protocol = json.loads(protocol_path.read_text(encoding='utf-8-sig'))
    forecast = parse_forecast_protocol(protocol)
    needed = set(forecast.required_months) | set(forecast.holdout_months)
    out.mkdir(parents=True,exist_ok=True)
    extra = [*KEY, 'DivReachedDest', 'DivArrDelay'] if save_flight_identity else ()
    frame, periods = audit_months(data, CORE | needed, out, extra_columns=extra)
    if require_full_data:
        absent = sorted((CORE | needed)-periods)
        if absent:
            raise ValueError(f'Incomplete verified data, missing months: {absent}')
    core = frame[frame.year.between(2023,2025)]
    missing = sorted(CORE-periods)
    state = {
        'core_status':'FULL_CORE' if not missing else 'PARTIAL_CORE',
        'core_months':len(CORE & periods),'core_missing_months':missing,
        'core_rows':len(core),'late_months':sorted(set(protocol['late_months']) & periods),
        'all_rows':len(frame),'core_unknown':int(core.state.eq('unknown').sum()),
        'protocol_sha256':sha(protocol_path),'events_sha256':sha(events_path),
        'generated_utc':datetime.now(UTC).isoformat(),
        'environment':{'python':platform.python_version(),'numpy':np.__version__,
                       'pandas':pd.__version__,'scipy':scipy.__version__,'sklearn':sklearn.__version__},
    }
    save_json(state,out/'validation_status.json')
    metrics(core).to_csv(out/'historical_airport_scorecard.csv',index=False)
    metrics(frame,('year','Origin')).to_csv(out/'metrics_by_year_airport.csv',index=False)
    if not missing and not skip_comparison:
        state['comparison'] = compare(core,out/'comparison_2023_2025',reps=1000)
        save_json(state,out/'validation_status.json')
    for threshold in forecast.thresholds_minutes:
        output = out / f'primary_t{threshold}'
        result = run_prediction(frame,output,threshold=threshold,protocol=forecast,
                                save_baseline_branches=True, save_flight_identity=save_flight_identity)
        if result['status'] != 'fitted' or result['training_end'] != protocol['refit_end']:
            raise ValueError(f'Prediction does not meet frozen time protocol for {threshold}: {result}')
        if require_full_data and {item['period'] for item in result['holdout_months']} != set(forecast.holdout_months):
            raise ValueError(f'Prediction lacks eligible flights in one or more planned holdouts for {threshold}')
        state[f'primary_t{threshold}'] = summarize_holdouts(
            pd.read_csv(output/'prediction_metrics.csv'),protocol,output)
        state[f'events_t{threshold}'] = stress_tests(
            frame, output, events_config=events_path, fitted_dates=(forecast.fit_start, forecast.refit_end))
        predictions = output/'predictions.pkl'
        calibration = analyze_saved(pd.read_pickle(predictions),output/'calibration')
        save_json(calibration,output/'calibration/calibration_status_v4.json')
        if not keep_predictions:
            predictions.unlink()
        save_json(state,out/'validation_status.json')
        if threshold == 60:
            print('Checking diversion fit cap and seed on fixed months', flush=True)
            state['diversion_fit_sensitivity'] = check_diversion_fit_cap(
                frame, protocol, forecast, result['chosen_C']['conditional_tree'], output
            )
            save_json(state,out/'validation_status.json')
    return frame, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--skip-comparison',action='store_true')
    parser.add_argument('--keep-local-predictions',action='store_true')
    args = parser.parse_args()
    _, state = run_validation(args.data, args.out, skip_comparison=args.skip_comparison,
                              keep_predictions=args.keep_local_predictions)
    print(json.dumps(state,indent=2),flush=True)


if __name__ == '__main__':
    main()

