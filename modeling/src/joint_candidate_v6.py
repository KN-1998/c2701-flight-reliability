"""Retrospective evaluation of one F1/F2 tree shared by the 15- and 60-minute thresholds.

P1 (v2 PDF p4) supplies the local logistic construction and P2 (v1 PDF p5,
Definition 2) supplies the path product. Here a is delay >= 60 given normal
completion and b is delay >= 15 given normal completion and delay < 60.
Their leaves split the completed mass into a, (1-a)*b and (1-a)*(1-b).
Thresholds share those leaves by construction. Calibration and sampling are
engineering choices. This candidate has no untouched future evaluation.
"""
from __future__ import annotations

import hashlib
import json
from numbers import Real
from pathlib import Path

import numpy as np
import pandas as pd

from audit import KEY
from forecast_protocol import parse_forecast_protocol
from prediction import CATS, NUMS, apply_sigmoid, evaluate, features, fit_binary, fit_sigmoid, prob

METHOD = 'shared_five_leaf'
BRANCHES = ('cancel', 'divert_given_not_cancel', 'delay60_given_completed',
            'delay15_given_completed_and_below60')
LEAVES = ('cancelled', 'diverted', 'completed_delay_ge60', 'completed_delay_15_to_lt60',
          'completed_delay_lt15')
MONTH_SCOPES = ('previously_scored_months', 'new_core_months', 'late_months')
ROW_HASH_COLUMNS = ['date', 'Origin', 'Dest', 'Reporting_Airline', 'dep_minutes']
TOLERANCE = 1e-12


def path_probabilities(local):
    """Return five mutually exclusive leaves and nested 15/60-minute risks."""
    local = np.asarray(local, dtype=float)
    if (local.ndim != 2 or local.shape[1] != len(BRANCHES)
            or not np.isfinite(local).all() or ((local < 0) | (local > 1)).any()):
        raise ValueError('Expected four finite branch probabilities in [0, 1] per row')
    cancel, divert, delay60, delay15_given_below60 = local.T
    not_cancelled = 1 - cancel
    completed = not_cancelled * (1 - divert)
    completed_below60 = completed * (1 - delay60)
    early = completed_below60 * (1 - delay15_given_below60)
    leaves = np.column_stack((
        cancel,
        not_cancelled * divert,
        completed * delay60,
        completed_below60 * delay15_given_below60,
        early,
    ))
    # Complementary expressions stay in [0, 1] near the endpoints.
    p15 = 1 - early
    p60 = 1 - completed_below60
    return leaves, p15, p60


def observed_leaves(frame):
    state = frame.state
    if not state.isin(['cancelled', 'diverted', 'on_time', 'late']).all():
        raise ValueError('Five-leaf risk sets require known audited flight outcomes')
    cancelled = state.eq('cancelled').to_numpy(dtype=bool)
    diverted = state.eq('diverted').to_numpy(dtype=bool)
    completed = state.isin(['on_time', 'late']).to_numpy(dtype=bool)
    if frame.completed.isna().any() or not np.array_equal(
            frame.completed.to_numpy(), completed):
        raise ValueError('Normal completion indicator disagrees with audited outcome')
    delay = frame.ArrDelay.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(delay[completed]).all():
        raise ValueError('Normal completion requires finite arrival delay')
    if not np.array_equal(state.eq('late').to_numpy(dtype=bool), completed & (delay >= 15)):
        raise ValueError('Normal completion state disagrees with the 15-minute audit boundary')
    return np.column_stack((cancelled, diverted, completed & (delay >= 60),
                            completed & (delay >= 15) & (delay < 60),
                            completed & (delay < 15)))


def _risk_sets(leaves):
    cancelled, diverted, delay60, delay15_to_lt60, early = leaves.T
    completed_below60 = delay15_to_lt60 | early
    completed = delay60 | completed_below60
    return ((np.ones(len(leaves), dtype=bool), cancelled),
            (~cancelled, diverted),
            (completed, delay60),
            (completed_below60, delay15_to_lt60))


class SharedFiveLeafModel:
    def __init__(self, *, regularization_c, fit_cap, seed):
        if (isinstance(fit_cap, bool) or not isinstance(fit_cap, int) or fit_cap < 1
                or isinstance(seed, bool) or not isinstance(seed, int) or seed < 0
                or isinstance(regularization_c, bool) or not isinstance(regularization_c, Real)
                or not np.isfinite(regularization_c)
                or regularization_c <= 0):
            raise ValueError('Expected a positive cap and C and a nonnegative integer seed')
        self.regularization_c = regularization_c
        self.fit_cap = fit_cap
        self.seed = seed
        self.models = []
        self.calibrators = []
        self.risk_counts = []

    def fit(self, train, cal):
        training_sets = _risk_sets(observed_leaves(train))
        calibration_sets = _risk_sets(observed_leaves(cal))
        generator = np.random.default_rng(self.seed)
        models, calibrators, counts = [], [], []
        cal_x = features(cal)
        for name, (train_mask, train_y), (cal_mask, cal_y) in zip(
                BRANCHES, training_sets, calibration_sets):
            available = np.flatnonzero(train_mask)
            if not len(available):
                raise ValueError(f'Five-leaf branch {name} does not have training support')
            indices = available
            if len(available) > self.fit_cap:
                indices = np.sort(generator.choice(available, self.fit_cap, replace=False))
            y = train_y[indices]
            model, warnings = fit_binary(features(train.iloc[indices]), y, self.regularization_c)
            cal_target = cal_y[cal_mask]
            calibrator = None
            if len(cal_target) and cal_target.any() and not cal_target.all():
                calibrator = fit_sigmoid(prob(model, cal_x.loc[cal_mask]), cal_target)
            models.append(model)
            calibrators.append(calibrator)
            counts.append({'branch': name, 'training_available': len(available),
                           'training_available_events': int(train_y[train_mask].sum()),
                           'training_n': len(indices), 'training_events': int(y.sum()),
                           'fit_warnings': json.dumps(warnings), 'calibration_n': len(cal_target),
                           'calibration_events': int(cal_target.sum()),
                           'calibration_applied': calibrator is not None})
        self.models, self.calibrators, self.risk_counts = models, calibrators, counts
        return self

    def predict(self, frame):
        if not self.models:
            raise ValueError('Fit the five-leaf model before predicting')
        x = features(frame)
        local = np.column_stack([apply_sigmoid(prob(model, x), calibrator)
                                 for model, calibrator in zip(self.models, self.calibrators)])
        return path_probabilities(local)


def _month_groups(protocol):
    return {month: scope for scope in MONTH_SCOPES for month in getattr(protocol, scope)}


def _structure(leaves, p15, p60):
    max_leaf_sum_error = float(np.abs(leaves.sum(axis=1) - 1).max())
    max_threshold_error = max(float(np.abs(leaves[:, :4].sum(axis=1) - p15).max()),
                              float(np.abs(leaves[:, :3].sum(axis=1) - p60).max()))
    violations = int((p60 > p15).sum())
    if (violations or (leaves < 0).any() or max_leaf_sum_error > TOLERANCE
            or max_threshold_error > TOLERANCE):
        raise ValueError('Five-leaf probability composition failed structural checks')
    return {'min_leaf_probability': float(leaves.min()),
            'max_leaf_sum_error': max_leaf_sum_error,
            'max_threshold_reconstruction_error': max_threshold_error,
            'threshold_violations': violations,
            'max_p60_minus_p15': float((p60 - p15).max())}


def _pooled(joint):
    for (scope, threshold), rows in joint.groupby(['scope', 'threshold_minutes'], sort=False):
        yield {'scope': scope, 'threshold_minutes': int(threshold), 'method': METHOD,
               'month_count': len(rows), 'n': int(rows.n.sum()), 'events': int(rows.events.sum()),
               'observed': rows.events.sum() / rows.n.sum(),
               'predicted': np.average(rows.predicted, weights=rows.n),
               'pooled_brier': np.average(rows.brier, weights=rows.n),
               'equal_month_brier': rows.brier.mean(),
               'pooled_log_loss': np.average(rows.log_loss, weights=rows.n)}


def run_joint_candidate(frame, protocol, out, *, regularization_c=0.1):
    """Refit on the frozen windows and score the registered, already seen months.

    Use the existing v5 protocol mapping and the same audited rows as run_prediction.
    The fixed candidate C is not selected using any holdout or used to promote one.
    """
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('Use a fresh output directory for the five-leaf candidate')
    model_columns = CATS + NUMS + ['state', 'completed', 'ArrDelay']
    required = set(model_columns + ROW_HASH_COLUMNS)
    if missing := required.difference(frame.columns):
        raise ValueError(f'Missing five-leaf input columns: {sorted(missing)}')
    protocol = parse_forecast_protocol(protocol)
    if protocol.thresholds_minutes != (15, 60):
        raise ValueError('The five-leaf partition requires thresholds [15, 60]')
    scopes = _month_groups(protocol)
    periods = frame.date.dt.to_period('M')
    holdouts = pd.PeriodIndex(protocol.holdout_months, freq='M')
    declared = pd.PeriodIndex(protocol.required_months + protocol.holdout_months, freq='M')
    if absent := sorted(set(declared) - set(periods.unique())):
        raise ValueError(f'Missing five-leaf fitting, calibration or holdout months: {list(map(str, absent))}')

    known = frame.date.notna() & frame.state.ne('unknown')
    train = frame.loc[known & frame.date.between(protocol.fit_start, protocol.refit_end), model_columns]
    cal = frame.loc[known & frame.date.between(protocol.calibration_start, protocol.calibration_end),
                    model_columns]
    if train.empty or cal.empty:
        raise ValueError('Five-leaf fitting and calibration require known outcomes')
    model = SharedFiveLeafModel(regularization_c=regularization_c,
                                fit_cap=protocol.fit_cap, seed=protocol.seed).fit(train, cal)
    del train, cal

    joint_rows, leaf_rows, bins, structures, examples = [], [], [], [], []
    for month in holdouts:
        period = str(month)
        print(f'Five-leaf candidate scoring {period}', flush=True)
        test = frame.loc[known & periods.eq(month)]
        if test.empty:
            raise ValueError(f'No known five-leaf outcomes in {period}')
        observed = observed_leaves(test)
        leaves, p15, p60 = model.predict(test)
        row_hash = hashlib.sha256(pd.util.hash_pandas_object(
            test[ROW_HASH_COLUMNS], index=True).values.tobytes()).hexdigest()
        meta = {'period': period, 'scope': scopes[period], 'method': METHOD}
        structures.append({**meta, 'n': len(test), 'test_row_hash': row_hash,
                           **_structure(leaves, p15, p60)})
        example = test.iloc[0]
        example_columns = list(dict.fromkeys(ROW_HASH_COLUMNS + [col for col in KEY if col in test]))
        examples.append({**meta, **example[example_columns].to_dict(), 'p15': p15[0], 'p60': p60[0],
                         **dict(zip(LEAVES, leaves[0]))})
        for threshold, y, predicted in (
                (15, observed[:, :4].any(axis=1), p15), (60, observed[:, :3].any(axis=1), p60)):
            joint_meta = {**meta, 'threshold_minutes': threshold}
            joint_rows.append({**joint_meta, 'target': 'joint', 'test_row_hash': row_hash,
                               **evaluate(y, predicted)})
            labels = np.minimum((predicted * 10).astype(int), 9)
            for bin_index in range(10):
                mask = labels == bin_index
                n = int(mask.sum())
                events = int(y[mask].sum())
                bins.append({**joint_meta, 'bin_left': bin_index / 10,
                             'bin_right': (bin_index + 1) / 10, 'n': n, 'events': events,
                             'observed': events / n if n else None,
                             'predicted': float(predicted[mask].mean()) if n else None})
        for name, y, prob_leaf in zip(LEAVES, observed.T, leaves.T):
            leaf_rows.append({**meta, 'leaf': name, 'n': len(test), 'events': int(y.sum()),
                              'observed': float(y.mean()), 'predicted': float(prob_leaf.mean()),
                              'brier': float(np.mean((y - prob_leaf) ** 2))})

    joint = pd.DataFrame(joint_rows)
    status = {
        'status': 'retrospective_candidate_scored',
        'method': METHOD,
        'evidence_level': 'retrospective comparison on already examined holdouts',
        'actual_flight_prediction_authorized': False,
        'independent_later_validation_completed': False,
        'thresholds_minutes': [15, 60],
        'training_start': protocol.fit_start,
        'training_end': protocol.refit_end,
        'calibration_start': protocol.calibration_start,
        'calibration_end': protocol.calibration_end,
        'calibration_months': list(protocol.calibration_months),
        'seed': model.seed,
        'fit_cap_per_branch': model.fit_cap,
        'regularization_C': model.regularization_c,
        'regularization_basis': 'Fixed engineering setting. The default repeats the prior v5 tree C.',
        'features': CATS + NUMS,
        'risk_sets': model.risk_counts,
        'holdout_months': list(map(str, holdouts)),
        'holdout_row_count': sum(month['n'] for month in structures),
        'threshold_violations': sum(month['threshold_violations'] for month in structures),
        'max_leaf_sum_error': max(month['max_leaf_sum_error'] for month in structures),
        'max_threshold_reconstruction_error': max(
            month['max_threshold_reconstruction_error'] for month in structures),
        'row_hash_definition': 'Same month rows, columns and index order as v5 primary diagnostics.',
        'data_scope': 'Known audited outcomes with static and reported schedule proxy features.',
        'examples': 'First row of each month, for illustrating the probability columns.',
    }
    out.mkdir(parents=True, exist_ok=True)
    joint.to_csv(out / 'candidate_joint_monthly.csv', index=False)
    pd.DataFrame(_pooled(joint)).to_csv(out / 'candidate_joint_pooled.csv', index=False)
    pd.DataFrame(leaf_rows).to_csv(out / 'candidate_leaf_monthly.csv', index=False)
    pd.DataFrame(bins).to_csv(out / 'candidate_calibration_bins.csv', index=False)
    pd.DataFrame(structures).to_csv(out / 'candidate_structure_monthly.csv', index=False)
    pd.DataFrame(examples).to_csv(out / 'candidate_probability_examples.csv', index=False)
    pd.DataFrame(model.risk_counts).to_csv(out / 'candidate_risk_sets.csv', index=False)
    (out / 'candidate_status.json').write_text(
        json.dumps(status, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return status
