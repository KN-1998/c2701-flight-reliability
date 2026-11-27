"""Reproduce the frozen C2701 experiments and build the v6 historical deliverables."""
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import hashlib
import json

import numpy as np
import pandas as pd

from forecast_protocol import parse_forecast_protocol
from run_validation_v5 import EVENTS, PROTOCOL, ROOT, run_validation, save_json, sha
from threshold_coherence import coherence_tables, write_coherence_results
from verify_handoff import verify


def audit_threshold_pairs(low_path, high_path, out):
    """Audit locally generated forecasts one month at a time, preserving every inversion."""
    low = pd.read_pickle(low_path)
    high = pd.read_pickle(high_path)
    lower_groups = low.groupby(low.date.dt.to_period('M'), sort=True)
    higher_groups = high.groupby(high.date.dt.to_period('M'), sort=True)
    if low.date.isna().any() or high.date.isna().any():
        raise ValueError('Paired forecasts require valid dates')
    if set(lower_groups.groups) != set(higher_groups.groups) or not len(lower_groups):
        raise ValueError('Thresholds must cover the same nonempty set of months')
    monthly, inversions, integrity = [], [], []
    for month, lower in lower_groups:
        higher = higher_groups.get_group(month)
        scores, violations = coherence_tables(lower, higher, example_limit=None)
        monthly.append(scores.loc[scores.period.ne('ALL')])
        inversions.append(violations)
        key_bytes = ('\n'.join(sorted(lower.flight_key))+'\n').encode()
        integrity.append({
            'period':str(month), 'n':len(lower),
            'flight_key_set_sha256':hashlib.sha256(key_bytes).hexdigest(),
        })
        print(f'Paired thresholds {month} n={len(lower)}', flush=True)

    by_month = pd.concat(monthly, ignore_index=True)
    overall = []
    for _, group in by_month.groupby('method', sort=False):
        row = group.iloc[0].to_dict()
        row['period'] = 'ALL'
        for name in ('n','observed_low_events','observed_high_events','observed_between_events','violations'):
            row[name] = int(group[name].sum())
        row['violation_rate'] = row['violations']/row['n']
        for name in ('max_upper_minus_lower','max_positive_excess'):
            row[name] = float(group[name].max())
        for name in ('mean_low_probability','mean_high_probability','mean_implied_between_probability'):
            row[name] = float(np.average(group[name], weights=group.n))
        overall.append(row)
    pooled = pd.DataFrame(overall)
    examples = pd.concat(inversions, ignore_index=True)
    if len(examples) != pooled.violations.sum():
        raise ValueError('Inversion counts disagree with the saved detail')
    status = write_coherence_results(pd.concat([pooled,by_month], ignore_index=True),
                                     examples, out, refit=True)
    pd.DataFrame(integrity).to_csv(out/'paired_identity_months.csv', index=False)
    status['months'] = len(integrity)
    status['inversions_are_exhaustive'] = True
    save_json(status,out/'threshold_coherence_status.json')
    return status


def compare_candidate(output, candidate_output):
    old = pd.concat([
        pd.read_csv(output/f'primary_t{threshold}'/'joint_monthly_v5.csv')
        for threshold in (15,60)
    ], ignore_index=True)
    candidate = pd.read_csv(candidate_output/'candidate_joint_monthly.csv')
    keys = ['period','threshold_minutes']
    shared = ['n','events','test_row_hash']
    heads = old[keys].drop_duplicates()
    if len(candidate) != len(heads):
        raise ValueError('Candidate has different month/threshold coverage')
    selection = candidate[keys+shared+['brier','log_loss']].rename(
        columns={key:f'candidate_{key}' for key in shared+['brier','log_loss']}
    )
    result = old.merge(selection, on=keys, how='left', validate='many_to_one')
    if any(not result[name].eq(result[f'candidate_{name}']).all() for name in shared):
        raise ValueError('Candidate and historical forecast counts, labels or row fingerprints differ')
    result['candidate_brier_minus_existing'] = result.candidate_brier - result.brier
    result['candidate_log_loss_minus_existing'] = result.candidate_log_loss - result.log_loss
    result.to_csv(candidate_output/'candidate_comparison.csv', index=False)


def run_delivery(data, output, *, protocol_path=PROTOCOL, events_path=EVENTS, verify_package=True):
    """Publish only after the full historical delivery finishes successfully."""
    from joint_candidate_v6 import run_joint_candidate
    from traveler_card_v6 import build_traveler_card

    data, output, protocol_path, events_path = map(Path, (data, output, protocol_path, events_path))
    if output.exists():
        raise ValueError(f'Use a fresh output directory: {output}')
    protocol = json.loads(protocol_path.read_text(encoding='utf-8-sig'))
    forecast = parse_forecast_protocol(protocol)
    if tuple(forecast.thresholds_minutes) != (15,60):
        raise ValueError('v6 delivery requires the registered 15 and 60 minute thresholds')
    if verify_package:
        package = verify(ROOT.parent)
        if not package['successful']:
            raise ValueError('Handoff fingerprint verification failed: '+ '; '.join(package['errors']))

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f'.{output.name}-', dir=output.parent) as temp:
        work = Path(temp)
        frame, state = run_validation(data, work, protocol_path=protocol_path, events_path=events_path,
                                      keep_predictions=True, save_flight_identity=True,
                                      require_full_data=True)
        files = [work/f'primary_t{t}'/'predictions.pkl' for t in (15,60)]
        print('Verifying frozen thresholds on the same BTS flight identities', flush=True)
        state['paired_thresholds'] = audit_threshold_pairs(*files, work/'threshold_coherence')
        for file in files:
            file.unlink()
        print('Building the 2023–2025 historical traveler card', flush=True)
        core = frame.loc[frame.year.between(2023,2025)]
        state['traveler_card'] = build_traveler_card(core, work/'traveler_card')
        del core
        print('Scoring the exploratory five-leaf candidate on observed holdouts', flush=True)
        candidate_out = work/'joint_candidate'
        state['joint_candidate'] = run_joint_candidate(frame, protocol, candidate_out)
        compare_candidate(work, candidate_out)
        state['delivery_status'] = 'COMPLETE_HISTORICAL_AND_RETROSPECTIVE'
        state['archived_method_selection_unchanged_by_candidate'] = True
        state['new_unseen_validation'] = False
        state['live_2027_forecast_authorized'] = False
        state['inputs'] = {'data_snapshot_sha256':sha(work/'data_snapshot.json')}
        save_json(state, work/'delivery_status.json')
        if output.exists():
            raise ValueError(f'Output directory appeared during the run: {output}')
        work.rename(output)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=ROOT/'data')
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    parser.add_argument('--events', type=Path, default=EVENTS)
    args = parser.parse_args()
    state = run_delivery(args.data,args.out,protocol_path=args.protocol,events_path=args.events)
    print(f"Delivery {state['delivery_status']}: {args.out}", flush=True)


if __name__ == '__main__':
    main()

