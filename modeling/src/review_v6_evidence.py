"""Audit saved v6 tables; optional archive comparison is not a new fit or blind test.

Run after run_delivery_v6.py, retaining the independent output directory. All
forecast tolerances below are engineering comparison tolerances, not uncertainty
bounds or evidence that modeling assumptions hold.
"""
from pathlib import Path
import argparse,hashlib,json,platform
import numpy as np
import pandas as pd
from threshold_coherence import DEFAULT_ATOL, METHODS

ROOT=Path(__file__).resolve().parents[1]

def require(ok, message):
    if not ok:
        raise ValueError(message)

def check_inversion_inventory(results, structure, scored, expected_status):
    folder = results/'threshold_coherence'
    summary = pd.read_csv(folder/'threshold_coherence.csv', float_precision='round_trip')
    detail = pd.read_csv(folder/'threshold_coherence_examples.csv', float_precision='round_trip')
    identities = pd.read_csv(folder/'paired_identity_months.csv')
    status = json.loads((folder/'threshold_coherence_status.json').read_text(encoding='utf-8'))

    require(identities.period.is_unique and set(identities.period) == set(structure.period),
            'Paired month inventory differs')
    require(identities.flight_key_set_sha256.astype('string').str.fullmatch(r'[0-9a-f]{64}', na=False).all(),
            'Malformed paired flight fingerprint')
    by_month = identities.set_index('period')
    require(structure.n.eq(structure.period.map(by_month.n)).all(),
            'Candidate and paired monthly denominators differ')
    require(scored.flight_identity_sha256.eq(scored.period.map(by_month.flight_key_set_sha256)).all(),
            'Scored flight identity fingerprint differs from pairing')

    indexed = summary.set_index(['period', 'method'])
    expected = pd.MultiIndex.from_product([['ALL', *by_month.index], METHODS], names=indexed.index.names)
    require(indexed.index.is_unique and indexed.index.sort_values().equals(expected.sort_values()),
            'Missing or duplicate monthly or pooled inversion summary')
    require(summary.lower_minutes.eq(15).all() and summary.upper_minutes.eq(60).all()
            and summary.atol.eq(DEFAULT_ATOL).all(), 'Inversion thresholds or tolerance differ')
    overall = indexed.loc['ALL']
    monthly = indexed.drop(index='ALL', level='period')
    pooled_n = int(by_month.n.sum())
    require(monthly.n.eq(monthly.index.get_level_values('period').map(by_month.n)).all()
            and overall.n.eq(pooled_n).all(), 'Inversion summary denominator differs')
    counts = pd.to_numeric(indexed.violations, errors='coerce')
    require(np.isfinite(counts).all() and counts.mod(1).eq(0).all() and counts.between(0, indexed.n).all(),
            'Invalid inversion count')
    rates = pd.to_numeric(indexed.violation_rate, errors='coerce')
    require(np.allclose(rates, counts / indexed.n, atol=1e-15, rtol=0),
            'Inversion rates disagree with the summary counts and denominators')

    flight_key = detail.flight_key.astype('string')
    require(flight_key.str.fullmatch(r'\d{4}-\d{2}-\d{2}(?:\|[^|\r\n]+){5}', na=False).all(),
            'Malformed inversion flight key')
    require(not detail.duplicated(['flight_key', 'method']).any(),
            'Duplicate inversion flight key and method')
    dates = pd.to_datetime(detail.date, format='%Y-%m-%d', errors='coerce')
    require(dates.dt.strftime('%Y-%m-%d').eq(detail.date).all()
            and flight_key.str.slice(0, 10).eq(detail.date).all(),
            'Invalid inversion date or flight-key date mismatch')
    periods = dates.dt.strftime('%Y-%m')
    require(detail.method.isin(METHODS).all() and periods.isin(by_month.index).all(),
            'Unexpected inversion period or method')

    probabilities = detail[['lower_probability', 'upper_probability', 'upper_minus_lower']].apply(
        pd.to_numeric, errors='coerce').astype(float)
    require(np.isfinite(probabilities.to_numpy(dtype=float)).all()
            and probabilities.ge(0).all().all() and probabilities.le(1).all().all(),
            'Invalid inversion probability or difference')
    gap = probabilities.upper_probability - probabilities.lower_probability
    require(gap.gt(DEFAULT_ATOL).all(), 'Inversion difference must exceed the decision tolerance')
    require(np.allclose(gap, probabilities.upper_minus_lower, atol=1e-15, rtol=0),
            'Stored inversion difference disagrees with the probabilities')

    detail_by_group = detail.assign(period=periods, gap=gap).groupby(['period', 'method']).gap
    actual = detail_by_group.size().reindex(monthly.index, fill_value=0)
    require(actual.eq(monthly.violations).all(), 'Monthly inversion count differs from detail')
    pooled_counts = actual.groupby(level='method').sum().reindex(overall.index)
    require(pooled_counts.eq(overall.violations).all(), 'Pooled inversion count differs from monthly counts')
    for claimed, observed in [
        (monthly, detail_by_group.max()),
        (overall, gap.groupby(detail.method).max()),
    ]:
        # Below-tolerance positive differences may be summarized without a detail row.
        maximum = pd.to_numeric(claimed.max_upper_minus_lower, errors='coerce')
        reported = pd.to_numeric(claimed.max_positive_excess, errors='coerce')
        require(np.isfinite(maximum).all() and maximum.between(-1, 1).all()
                and np.allclose(maximum.clip(lower=0), reported, atol=1e-15, rtol=0),
                'Invalid inversion summary maximum')
        expected_excess = observed.reindex(claimed.index, fill_value=0)
        require(claimed.violations.gt(0).eq(maximum.gt(DEFAULT_ATOL)).all()
                and np.allclose(reported[claimed.violations.gt(0)],
                                expected_excess[claimed.violations.gt(0)], atol=1e-15, rtol=0),
                'Inversion maximum differs from detail')

    require(status == expected_status and status.get('inversions_are_exhaustive') is True
            and status.get('unique_flight_keys_checked') is True
            and status.get('probability_tolerance') == DEFAULT_ATOL
            and status.get('paired_rows') == pooled_n and status.get('months') == len(by_month),
            'Pairing status disagrees with the exhaustive inversion inventory')
    summary_counts = overall.violations.astype(int).to_dict()
    by_method = status['joint_display_by_method']
    require(set(by_method) == set(summary_counts) and all(
        by_method[method]['violations'] == count for method, count in summary_counts.items()),
        'Per-method inversion status disagrees with the summary')
    return summary_counts, detail


def inspect_evidence(results, archive=None):
    """Cross-check saved tables only. This is not a refit or independent validation."""
    results=Path(results)
    read=lambda name: pd.read_csv(results/name)
    status=json.loads((results/'delivery_status.json').read_text(encoding='utf-8'))
    checks=[]
    months=read('audit_by_month.csv')
    core=months.loc[months.period.str[:4].isin(['2023','2024','2025'])]
    require(months.period.is_unique, 'Duplicate audit month')
    expected_core = set(pd.period_range('2023-01', '2025-12', freq='M').astype(str))
    require(set(core.period) == expected_core and set(months.period) == expected_core | {'2026-09'},
            'Expected 36 core and 1 late month')
    require(int(core.retained_rows.sum())==status['core_rows'],'Core denominator differs')
    require(int(months.retained_rows.sum())==status['all_rows'],'Full denominator differs')
    checks.append('monthly_denominators')
    struct=read('joint_candidate/candidate_structure_monthly.csv')
    candidate=read('joint_candidate/candidate_joint_monthly.csv')
    require(len(struct)==19 and struct.period.is_unique,'Candidate month identities differ')
    require((struct.threshold_violations==0).all(),'Candidate threshold inversion found')
    require((struct.max_leaf_sum_error<=1e-12).all(),'Candidate leaves do not close')
    require((struct.max_threshold_reconstruction_error<=1e-12).all(),'Candidate margins do not reconstruct')
    require(set(candidate.period) == set(struct.period), 'Candidate structure months differ')
    paired = candidate.merge(struct[['period', 'n', 'test_row_hash']], on='period',
                             suffixes=('', '_structure'), validate='many_to_one')
    for field in ('n', 'test_row_hash'):
        require(paired[field].eq(paired[field + '_structure']).all(),
                'Candidate structure identity differs: ' + field)
    require(candidate.groupby('period').size().eq(2).all(),'Missing or duplicate candidate threshold')
    require(candidate.threshold_minutes.isin([15,60]).all(),'Unexpected threshold')
    require(candidate.groupby(['period','threshold_minutes']).size().eq(1).all(),'Duplicate candidate score')
    all_old=[]
    replay_diff=[]
    for threshold in (15,60):
        old=read(f'primary_t{threshold}/joint_monthly_v5.csv')
        current=candidate.loc[candidate.threshold_minutes.eq(threshold)]
        require(set(old.period) == set(current.period), 'Historical/candidate months differ')
        for table in (old, current):
            require(np.isfinite(table[['n','events','brier']].to_numpy()).all(), 'Nonfinite score')
            require((table.n > 0).all() and table.events.between(0, table.n).all(), 'Invalid denominator')
            require(table.brier.between(0, 1).all(), 'Invalid Brier score')
        merged=old.merge(current,on=['period','threshold_minutes'],suffixes=('_old','_candidate'),validate='many_to_one')
        require(len(merged)==len(old),'Candidate omitted scored rows')
        for col in ['n','events','test_row_hash']:
            require(merged[col+'_old'].eq(merged[col+'_candidate']).all(),'Candidate row identity differs: '+col)
        all_old.append(old)
        if archive:
            for table in ['prediction_metrics.csv','joint_monthly_v5.csv','joint_pooled_v5.csv','external_event_scores.csv']:
                a=read(f'primary_t{threshold}/{table}')
                b=pd.read_csv(Path(archive)/f'primary_t{threshold}'/table)
                require(set(b.columns).issubset(a.columns) and set(a.columns)-set(b.columns)<= {'flight_identity_sha256'} and len(a)==len(b),'Replay table schema differs: '+table)
                common=list(b.columns)
                for column in common:
                    if not pd.api.types.is_numeric_dtype(b[column]):
                        require(a[column].fillna('').eq(b[column].fillna('')).all(),'Text/identity mismatch: '+table+' '+column)
                a,b=a[common],b[common]
                numeric=[c for c in a if pd.api.types.is_numeric_dtype(a[c]) and pd.api.types.is_numeric_dtype(b[c])]
                # Identities and labels must match exactly. Floating forecasts may
                # differ across libraries; report differences rather than hide them.
                ids=[c for c in a if c not in numeric]
                for c in ids:
                    require(a[c].fillna('<NA>').eq(b[c].fillna('<NA>')).all(),'Replay identity differs: '+c)
                for c in numeric:
                    if c in ['n','events','days','month_count','expected_months','threshold_minutes','cancelled']:
                        require(a[c].eq(b[c]).all(),'Replay denominator differs: '+c)
                delta=max([float((a[c]-b[c]).abs().max()) for c in numeric if len(a)] or [0.])
                replay_diff.append({'threshold':threshold,'table':table,'max_abs_numeric_difference':delta})
    checks.append('candidate_same_rows_labels_and_fingerprints')
    old=pd.concat(all_old,ignore_index=True)
    selected=old.loc[(old.threshold_minutes.eq(15)&old.method.eq('direct_joint'))|
                     (old.threshold_minutes.eq(60)&old.method.eq('conditional_tree'))]
    comparisons=[]
    for (scope,t), group in candidate.groupby(['scope','threshold_minutes']):
        ref=selected.loc[selected.scope.eq(scope)&selected.threshold_minutes.eq(t)]
        require(set(group.period)==set(ref.period),'Selection scope mismatch')
        baseline=float(np.average(ref.brier,weights=ref.n))
        score=float(np.average(group.brier,weights=group.n))
        comparisons.append({'scope':scope,'threshold_minutes':int(t),'n':int(group.n.sum()),
                            'selected_brier':baseline,'candidate_brier':score,'candidate_minus_selected':score-baseline})
    checks.append('weighted_candidate_tradeoff')
    inversion_counts, detail = check_inversion_inventory(
        results, struct, old, status.get('paired_thresholds'))
    checks.append('exhaustive_inversion_inventory')
    rates=read('traveler_card/route_rates.csv')
    leaves=['cancelled','diverted','completed_under_15','completed_15_to_under_60','completed_at_least_60','unknown']
    require(rates[leaves].sum(axis=1).eq(rates.n_planned).all(),'Card outcome counts do not close')
    require((rates.joint_bad_15+1e-12>=rates.joint_bad_60).all(),'Card historical rates invert')
    coverage=read('traveler_card/support_coverage.csv')
    require(np.allclose(coverage.coverage,coverage.n_supported/coverage.n_planned),'Card support coverage differs')
    require(int(rates.loc[rates.period.eq('2023-2025'),'n_planned'].sum())==24023,'Card scope changed')
    checks.append('historical_card_counts_and_support')
    events=read('primary_t60/external_event_scores.csv')
    events=events.loc[events.window.eq('external_event')]
    require(np.allclose(events.observed,events.events/events.n),'Event observed proportions differ')
    require((events.cancelled<=events.events).all(),'Event labels violate cancellation subset')
    checks.append('event_denominators_and_cancellation_subset')
    for gate in ['new_unseen_validation','live_2027_forecast_authorized']:
        require(status[gate] is False,'Retrospective gate was upgraded: '+gate)
    checks.append('retrospective_boundary_preserved')
    fingerprints={p.relative_to(results).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(results.rglob('*')) if p.is_file()}
    return {'status':'SAVED_EVIDENCE_CROSSCHECK_PASSED','scope':'saved tables; not a new fit or blind validation',
            'checks':checks,'core_months':36,'all_months':37,'core_rows':int(core.retained_rows.sum()),
            'all_rows':int(months.retained_rows.sum()),'holdout_rows':int(struct.n.sum()),
            'candidate_tradeoffs':comparisons,'inversions_by_method':inversion_counts,
            'inversion_records':detail.to_dict('records'),'pooled_card_coverage':coverage.loc[coverage.period.eq('2023-2025')].to_dict('records'),
            'events_60':events[['event','method','n','events','cancelled','observed','predicted']].to_dict('records'),
            'replay_comparison':replay_diff,'source_file_sha256':fingerprints,
            'environment':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__}}

def compare_csv_trees(results, archive, *, atol=1e-10):
    """Compare every CSV, retaining measured differences and failing on identities.

    Row order is part of the archived contract. Strings and integer fields are
    exact; finite floats use an explicit engineering absolute tolerance. Empty
    columns represented as NaN must have identical missingness. This does not
    compare narrative documents or certify inference or independent holdouts.
    """
    results, archive = Path(results), Path(archive)
    require(np.isfinite(atol) and atol >= 0, 'Invalid comparison tolerance')
    paths = sorted(p.relative_to(archive) for p in archive.rglob('*.csv'))
    require(set(paths) == {p.relative_to(results) for p in results.rglob('*.csv')},
            'CSV inventory differs')
    tables = []
    for path in paths:
        a, b = pd.read_csv(results/path), pd.read_csv(archive/path)
        require(list(a.columns) == list(b.columns) and a.shape == b.shape,
                'CSV schema/shape differs: ' + str(path))
        differences = {}
        for col in a:
            require(a[col].isna().eq(b[col].isna()).all(), 'CSV missingness differs: ' + str(path) + ':' + col)
            if pd.api.types.is_bool_dtype(a[col]) or pd.api.types.is_bool_dtype(b[col]):
                require(a[col].equals(b[col]), 'Boolean CSV field differs: ' + str(path) + ':' + col)
            elif pd.api.types.is_numeric_dtype(a[col]) and pd.api.types.is_numeric_dtype(b[col]):
                av, bv = a[col].dropna(), b[col].dropna()
                require(np.isfinite(av).all() and np.isfinite(bv).all(), 'Nonfinite CSV values')
                if pd.api.types.is_integer_dtype(a[col]) and pd.api.types.is_integer_dtype(b[col]):
                    require(av.eq(bv).all(), 'Integer CSV field differs: ' + str(path) + ':' + col)
                delta = float((av-bv).abs().max()) if len(av) else 0.0
                require(delta <= atol, 'CSV numeric tolerance exceeded: ' + str(path) + ':' + col)
                differences[col] = delta
            else:
                require(a[col].fillna('<NA>').eq(b[col].fillna('<NA>')).all(),
                        'CSV identity/text differs: ' + str(path) + ':' + col)
        tables.append({'path': path.as_posix(), 'rows': len(a),
                       'max_abs_numeric_difference': max(differences.values(), default=0.0),
                       'numeric_columns': differences})
    return {'status': 'ALL_CSV_COMPARISON_PASSED', 'tables_compared': len(tables),
            'absolute_tolerance': atol, 'scope': 'engineering reproducibility, not forecast uncertainty',
            'maximum_observed_abs_difference': max((t['max_abs_numeric_difference'] for t in tables), default=0.0),
            'tables': tables}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=ROOT/'results/implementation_v6')
    p.add_argument('--archive',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--compare-all-csv', action='store_true', help='Requires same-version --archive')
    args=p.parse_args()
    require(not args.out.exists(),'Use a new evidence report path')
    value=inspect_evidence(args.results,args.archive)
    if args.compare_all_csv:
        require(args.archive is not None, '--compare-all-csv requires --archive')
        value['all_csv_comparison'] = compare_csv_trees(args.results, args.archive)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in value.items() if k not in ['source_file_sha256','inversion_records','events_60','pooled_card_coverage']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
