"""Audit nested-threshold predictions without changing forecasts or claiming new validation.
Derivation: docs/THRESHOLD_COHERENCE_20261127.md, from the existing F1/F2 model.
CSV inputs require a stable, unique flight_key, NOT a generated row number.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from calibration_diagnostics import validate_saved_predictions

METHODS = {
    'conditional_tree': ('model_p', 'model_p'),
    'direct_joint': ('direct_p', 'direct_p'),
    'historical_baseline': ('baseline_p', 'baseline_p'),
    'selected_direct_low_tree_high': ('direct_p', 'model_p'),
}
METADATA = ['date', 'Origin', 'Dest', 'Reporting_Airline', 'state', 'completed', 'ArrDelay']


def aligned_inputs(low, high, *, lower=15, upper=60, atol=1e-12):
    if not np.isfinite([lower, upper, atol]).all() or not (0 < lower < upper) or lower != int(lower) or upper != int(upper) or atol < 0:
        raise ValueError('Ordered positive integer thresholds and finite nonnegative tolerance required')
    for df, threshold in [(low, lower), (high, upper)]:
        validate_saved_predictions(df)
        required = set(METADATA + ['flight_key', 'model_p', 'direct_p', 'baseline_p'])
        if not required.issubset(df.columns):
            raise ValueError('Stable flight key, metadata and all three methods required')
        key = df.flight_key
        if key.isna().any() or not key.map(lambda x: isinstance(x, str) and bool(x.strip())).all() or key.duplicated().any():
            raise ValueError('Nonempty unique string flight keys required')
        if not df.target_threshold_minutes.eq(threshold).all():
            raise ValueError('Threshold metadata does not match the requested task')
    a = low.set_index('flight_key', verify_integrity=True).copy()
    b = high.set_index('flight_key', verify_integrity=True).copy()
    if set(a.index) != set(b.index):
        raise ValueError('Thresholds must have the identical flight key set; no inner-join deletion')
    b = b.loc[a.index].copy()
    for col in METADATA:
        av = pd.to_datetime(a[col], errors='raise') if col == 'date' else a[col]
        bv = pd.to_datetime(b[col], errors='raise') if col == 'date' else b[col]
        eq = (av == bv) | (av.isna() & bv.isna())
        if not eq.fillna(False).all():
            raise ValueError('Mismatched paired metadata: ' + col)
    if (b.bad.to_numpy() > a.bad.to_numpy()).any():
        raise ValueError('Observed labels violate nested events')
    return a, b


def coherence_tables(low, high, *, lower=15, upper=60, atol=1e-12):
    a, b = aligned_inputs(low, high, lower=lower, upper=upper, atol=atol)
    months = pd.to_datetime(a.date).dt.strftime('%Y-%m').to_numpy()
    groups = [('ALL', np.ones(len(a), dtype=bool))]
    groups += [(m, months == m) for m in sorted(set(months))]
    rows, examples = [], []
    for method, (lo_col, hi_col) in METHODS.items():
        lp = a[lo_col].to_numpy(dtype=float)
        hp = b[hi_col].to_numpy(dtype=float)
        gap = hp - lp
        for period, mask in groups:
            excess = gap[mask]
            violated = excess > atol
            ylo, yhi = a.bad.to_numpy()[mask], b.bad.to_numpy()[mask]
            rows.append(dict(period=period, method=method, lower_minutes=lower, upper_minutes=upper,
                             n=int(mask.sum()), observed_low_events=int(ylo.sum()), observed_high_events=int(yhi.sum()),
                             observed_between_events=int((ylo-yhi).sum()), violations=int(violated.sum()),
                             violation_rate=float(violated.mean()), max_upper_minus_lower=float(excess.max()),
                             max_positive_excess=float(max(0., excess.max())),
                             mean_low_probability=float(lp[mask].mean()), mean_high_probability=float(hp[mask].mean()),
                             mean_implied_between_probability=float((lp[mask]-hp[mask]).mean()),
                             atol=atol, interpretation='DESCRIPTIVE_ONLY_NOT_NEW_HOLDOUT'))
        # At most five examples per method, deterministic order, no replacement forecast.
        for pos in np.flatnonzero(gap > atol)[:5]:
            examples.append(dict(flight_key=a.index[pos], date=str(pd.Timestamp(a.date.iloc[pos]).date()),
                                 method=method, lower_probability=float(lp[pos]), upper_probability=float(hp[pos]),
                                 upper_minus_lower=float(gap[pos])))
    return pd.DataFrame(rows), pd.DataFrame(examples, columns=['flight_key','date','method','lower_probability','upper_probability','upper_minus_lower'])


def write_diagnostics(low, high, out, *, lower=15, upper=60, atol=1e-12):
    # Validate and calculate before creating output; never modify either input.
    summary, examples = coherence_tables(low, high, lower=lower, upper=upper, atol=atol)
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('Fresh output directory required')
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out/'threshold_coherence.csv', index=False)
    examples.to_csv(out/'threshold_coherence_examples.csv', index=False)
    status = dict(status='DESCRIPTIVE_ONLY', paired_rows=len(low), lower_minutes=lower, upper_minutes=upper,
                  forecasts_modified=False, v5_reproduced=False, new_training=False,
                  counterfactual_warning='Mixed-method check does not reselect or endorse a model',
                  unique_flight_keys_checked=True, probability_tolerance=atol,
                  gate='Coherence alone does not establish calibration, skill, or future transportability')
    (out/'threshold_coherence_status.json').write_text(json.dumps(status, indent=2)+'\n', encoding='utf-8')
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--low-csv', type=Path, required=True)
    p.add_argument('--high-csv', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--lower', type=int, default=15)
    p.add_argument('--upper', type=int, default=60)
    args = p.parse_args()
    write_diagnostics(pd.read_csv(args.low_csv, dtype={'flight_key':str}),
                      pd.read_csv(args.high_csv, dtype={'flight_key':str}),
                      args.out, lower=args.lower, upper=args.upper)

if __name__ == '__main__':
    main()
