"""Three-year historical EWR/LGA to DEN card with a shared outcome partition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from comparison import block_weights


AIRPORTS = ('EWR', 'LGA')
STRATA = ('Reporting_Airline', 'season', 'time_bin')
REQUIRED = ('date', 'Origin', 'Dest', 'state', 'completed', 'ArrDelay', *STRATA)
CORE_MONTHS = tuple(f'{year}-{month:02d}' for year in (2023, 2024, 2025) for month in range(1, 13))
LEAVES = ('cancelled', 'diverted', 'completed_under_15', 'completed_15_to_under_60',
          'completed_at_least_60', 'unknown')
TARGETS = {
    'cancellation': '取消',
    'diversion': '改航',
    'long_delay_60_per_scheduled': '正常完成且延误至少 60 分钟',
    'long_delay_60_given_completed': '正常完成条件下延误至少 60 分钟',
    'joint_bad_15': '15 分钟联合不满意',
    'joint_bad_60': '60 分钟联合不满意',
}
BLOCKS = (1, 7, 14)
POOLED = '2023-2025'


def _rate(num, den):
    return np.divide(num, den, out=np.full(np.shape(num), np.nan, dtype=float), where=den > 0)


def outcome_rates(masses):
    """Map final-axis leaf masses to observed rates and identification bounds."""
    cancel, divert, early, medium, long, unknown = np.moveaxis(masses, -1, 0)
    completed = early + medium + long
    planned = cancel + divert + completed + unknown
    counts = (cancel, divert, long, long, cancel + divert + medium + long, cancel + divert + long)
    denominators = (planned, planned, planned, completed, planned, planned)
    rate = {}
    for (target, numerator), den in zip(zip(TARGETS, counts), denominators):
        point = _rate(numerator, den)
        possible_den = den + unknown if target == 'long_delay_60_given_completed' else den
        rate[target] = (point, _rate(numerator, possible_den),
                        _rate(numerator + unknown, possible_den))
    return rate


def _leaves(route):
    """Map mutually exclusive audited outcomes to one count column per leaf."""
    state = route.state
    completed = state.isin(['on_time', 'late'])
    delay = pd.to_numeric(route.ArrDelay, errors='coerce')
    if (not state.isin(['cancelled', 'diverted', 'on_time', 'late', 'unknown']).all()
            or not route.completed.eq(completed).fillna(False).all()
            or not np.isfinite(delay[completed]).all()):
        raise ValueError('Expected audited outcomes with finite delay for completed flights')
    leaves = pd.DataFrame({
        'cancelled': state.eq('cancelled'),
        'diverted': state.eq('diverted'),
        'completed_under_15': completed & delay.lt(15),
        'completed_15_to_under_60': completed & delay.ge(15) & delay.lt(60),
        'completed_at_least_60': completed & delay.ge(60),
        'unknown': state.eq('unknown'),
    }, index=route.index).astype('int8')
    if not leaves.sum(axis=1).eq(1).all():
        raise ValueError('Audited outcome partition does not close')
    return leaves


def _eligible_cells(route, min_known):
    known = route.loc[route.unknown.eq(0)].groupby(['cell', 'Origin'], observed=True).size()
    if known.empty:
        return pd.Index([], name='cell')
    counts = known.unstack('Origin').reindex(columns=AIRPORTS).fillna(0)
    return counts.index[counts.ge(min_known).all(axis=1)]


def _cell_index(cells):
    return pd.MultiIndex.from_product([AIRPORTS, cells], names=['Origin', 'cell'])


def _reference(route, cells):
    if len(cells) == 0:
        return np.zeros(0, dtype=float)
    n = route.groupby(['Origin','cell'], observed=True).size().reindex(_cell_index(cells)).to_numpy().reshape(2,-1)
    return (n/n.sum(axis=1, keepdims=True)).mean(axis=0)


def _raw_stats(period, route):
    rows = []
    for airport in AIRPORTS:
        counts = route.loc[route.Origin.eq(airport), LEAVES].sum().to_numpy(dtype=int)
        row = {'period':period, 'airport':airport, 'n_planned':int(counts.sum()),
               'n_completed':int(counts[2:5].sum()), **dict(zip(LEAVES, counts))}
        for target, (point, low, high) in outcome_rates(counts).items():
            row[target] = float(point)
            row[f'{target}_identified_low'] = float(low)
            row[f'{target}_identified_high'] = float(high)
        rows.append(row)
    return rows


def _cell_draws(supported, dates, cells, reps, seed):
    daily = supported.groupby(['date','Origin','cell'], observed=True)[list(LEAVES)].sum()
    idx = _cell_index(cells)
    cube = np.stack([daily[leaf].unstack(['Origin','cell']).reindex(
        index=dates, columns=idx).fillna(0).to_numpy(dtype=float) for leaf in LEAVES], axis=-1)
    for block in BLOCKS:
        weights = block_weights(dates, reps=reps, block=block, seed=seed)
        counts = (weights @ cube.reshape(len(dates),-1)).reshape(reps,2,len(cells),len(LEAVES))
        yield block, counts


def _standardized(count, weights):
    cell_probability = _rate(count, count.sum(axis=-1, keepdims=True))
    return np.einsum('...sl,s->...l', cell_probability, weights)


def _matched(period, scope, route, cells, weights, reps, seed):
    supported = route[route.cell.isin(cells)]
    coverage = []
    for airport in AIRPORTS:
        count = int(route.Origin.eq(airport).sum())
        a = supported[supported.Origin.eq(airport)]
        coverage.append({
            'period':period, 'reference_scope':scope, 'airport':airport,
            'n_planned':count, 'n_supported':len(a),
            'n_supported_known':int(a.unknown.eq(0).sum()),
            'n_supported_completed':int(a[list(LEAVES[2:5])].sum().sum()),
            'coverage':len(a)/count if count else np.nan, 'shared_cells':len(cells),
        })
    if len(cells) == 0:
        return coverage, []

    grouped = supported.groupby(['Origin','cell'], observed=True)[list(LEAVES)].sum()
    counts = grouped.reindex(_cell_index(cells)).to_numpy().reshape(2,len(cells),len(LEAVES))
    estimate = outcome_rates(_standardized(counts, weights))
    dates = pd.DatetimeIndex(sorted(route.date.unique()))
    rows = []
    for block, drawn in _cell_draws(supported,dates,cells,reps,seed):
        sampled = outcome_rates(_standardized(drawn, weights))
        for target, (point, low, high) in estimate.items():
            values = sampled[target][0]
            differences = values[:,0] - values[:,1]
            valid = np.isfinite(differences)
            # Never discard or redraw failed replicates. A conditional denominator
            # can also be zero even if every scheduled cell is present.
            limits = np.quantile(differences, [.025, .975]) if valid.all() else (np.nan, np.nan)
            rows.append({
                'period':period, 'reference_scope':scope, 'target':target, 'block_days':block,
                'shared_cells':len(cells), 'EWR_adjusted_rate':point[0], 'LGA_adjusted_rate':point[1],
                'adjusted_difference':point[0]-point[1],
                'identified_difference_low':low[0]-high[1], 'identified_difference_high':high[0]-low[1],
                'experimental_95_low':limits[0], 'experimental_95_high':limits[1],
                'reps':reps, 'invalid_reps':int((~valid).sum()),
                'interval_status':'EXPERIMENTAL_FIXED_REFERENCE' if valid.all() else 'SUPPRESSED_EMPTY_DENOMINATOR',
            })
    return coverage, rows


def _percent(value):
    return f'{value:.2%}' if np.isfinite(value) else '—'


def _pp(value):
    return f'{100*value:+.2f}' if np.isfinite(value) else '—'


def _preference(rows, target):
    relevant = [r for r in rows if r['period'] == POOLED and r['target'] == target]
    if relevant and all(r['experimental_95_low'] > 0 and r['identified_difference_low'] > 0 for r in relevant):
        return '在该历史共同支持范围内，可以先查看 LGA 的可比选项。'
    if relevant and all(r['experimental_95_high'] < 0 and r['identified_difference_high'] < 0 for r in relevant):
        return '在该历史共同支持范围内，可以先查看 EWR 的可比选项。'
    return '可同时保留 EWR 和 LGA 两边的选项，结合具体航司与时段再比较。'


def _markdown(status, raw, coverage, matched):
    n, months = status['n'], len(status['periods'])
    lines = [
        '# EWR 与 LGA 飞往 DEN 的历史旅客记分卡', '',
        f'分析使用 2023 至 2025 年间取得的 {months} 个核心月，共 {n:,} 条保留计划航段。',
        '这里的概率来自历史航段，可作为 2027 年样卡的历史参考。', '',
        '## 航班总体与共同支持', '',
        '|机场|计划航段|正常完成|结局未知|共同支持航段|覆盖率|',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for a, b in zip(raw[:2], coverage[:2]):
        lines.append(f"|{a['airport']}|{a['n_planned']:,}|{a['n_completed']:,}|{a['unknown']:,}|{b['n_supported']:,}|{_percent(b['coverage'])}|")
    lines += ['', '对比以相同运营航司、季节和 6 小时时段分格，两机场各自达到最少已知航段数后纳入。'
              '原始率使用全部可用航段。调整率使用两机场共同支持内航班构成的等权平均。'
              '年度对比使用各观察年均过门槛的固定分格及固定参考权重。', '',
              '## 三年原始风险和调整对照', '',
              '|指标|EWR 原始|LGA 原始|EWR 调整|LGA 调整|调整差 pp|7 日实验区间 pp|',
              '|---|---:|---:|---:|---:|---:|---:|']
    for key, title in TARGETS.items():
        row = next((r for r in matched if (r['period'],r['block_days'],r['target']) == (POOLED,7,key)), None)
        measures = ('—','—','—','—')
        if row:
            lower = row['experimental_95_low']
            upper = row['experimental_95_high']
            interval = f"[{_pp(lower)}, {_pp(upper)}]" if np.isfinite(lower) else '—'
            measures = (_percent(row['EWR_adjusted_rate']), _percent(row['LGA_adjusted_rate']),
                        _pp(row['adjusted_difference']),interval)
        lines.append('|'+ '|'.join((title, _percent(raw[0][key]), _percent(raw[1][key]), *measures))+'|')
    lines += [
        '',
        '15/60 分钟联合风险包含取消、改航及正常完成且达到对应延误阈值。'
        '除明确写明“正常完成条件下”的一行，分母为计划航段。'
        '未知结局产生的识别上下界和 1、7、14 日配对区块实验区间见配套表。区间以固定构成为条件。',
        '', '## 年度同构成对照', '',
        '|年份|EWR 支持覆盖|LGA 支持覆盖|取消率差 pp|长延误率差 pp|',
        '|---|---:|---:|---:|---:|',
    ]
    for year in sorted({str(period)[:4] for period in status['periods']}):
        a, b = [r for r in coverage if r['period'] == year]
        estimates = {r['target']:r['adjusted_difference'] for r in matched
                     if (r['period'],r['block_days']) == (year,7)}
        cancel = _pp(estimates.get('cancellation', np.nan))
        long = _pp(estimates.get('long_delay_60_per_scheduled', np.nan))
        lines.append(f"|{year}|{_percent(a['coverage'])}|{_percent(b['coverage'])}|{cancel}|{long}|")
    lines += [
        '', '差值为 EWR 减 LGA。长延误率以计划航段为分母。年度和三年估计各有其共同支持范围。',
        '', '## 给两类旅客的建议', '',
        f"- **优先避免取消**。{_preference(matched, 'cancellation')}",
        f"- **优先避免长延误**。{_preference(matched, 'long_delay_60_per_scheduled')}同时查看取消和改航，按自己的偏好选择。",
        '', '航段量、覆盖率、结局口径和以日期为单位的区间应随 BTS 新月批复核。价格、衔接、地面行程和实际购票信息另行查阅。',
    ]
    if status['coverage_status'] != 'FULL_CORE':
        lines.insert(4, '月份覆盖不齐，所有合并和年度结果对应当前已取得的月份。')
    return '\n'.join(lines)+'\n'


def build_traveler_card(core, out, *, reps=1000, min_known=30, seed=2701):
    """Build the historical card from audited BTS rows. Takes an empty output path."""
    if min_known < 1 or reps < 1:
        raise ValueError('min_known and reps must be positive')
    missing = set(REQUIRED).difference(core.columns)
    if missing:
        raise ValueError(f'Missing audited card columns {sorted(missing)}')
    out = Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('Use a fresh or empty traveler-card output directory')
    dates = pd.to_datetime(core.date)
    selected = dates.dt.year.between(2023,2025)
    months = sorted(dates.loc[selected].dt.to_period('M').astype(str).unique())
    route = core.loc[selected & core.Origin.isin(AIRPORTS) & core.Dest.eq('DEN'), list(REQUIRED)].copy()
    route.reset_index(drop=True, inplace=True)
    route['date'] = pd.to_datetime(route.date).dt.normalize()
    strata = route[list(STRATA)].astype('string').fillna('MISSING')
    route['cell'] = strata.iloc[:,0].str.cat([strata.iloc[:,1],strata.iloc[:,2]], sep='|')
    route = route.join(_leaves(route))
    pooled_cells = _eligible_cells(route,min_known)
    years = sorted({int(m[:4]) for m in months})
    by_year = {str(year):route[route.date.dt.year.eq(year)] for year in years}
    shared_annual = pooled_cells
    for group in by_year.values():
        shared_annual = shared_annual.intersection(_eligible_cells(group,min_known),sort=False)
    pooled_weights = _reference(route,pooled_cells)
    annual_weights = _reference(route,shared_annual)

    raw, coverage, comparisons = [], [], []
    scopes = [(POOLED, 'pooled_common_support', route, pooled_cells, pooled_weights)]
    scopes.extend((year,'fixed_cross_year_common_support',group,shared_annual,annual_weights)
                  for year,group in by_year.items())
    for period, scope, group, cells, weights in scopes:
        raw.extend(_raw_stats(period,group))
        table, estimates = _matched(period,scope,group,cells,weights,reps,seed)
        coverage.extend(table)
        comparisons.extend(estimates)
    references = [
        {'reference_scope':kind, 'cell':cell, 'weight':w}
        for kind, cells, weights in [('pooled_common_support',pooled_cells,pooled_weights),
                                     ('fixed_cross_year_common_support',shared_annual,annual_weights)]
        for cell,w in zip(cells,weights)
    ]
    comparison_columns = [
        'period','reference_scope','target','block_days','shared_cells','EWR_adjusted_rate',
        'LGA_adjusted_rate','adjusted_difference','identified_difference_low',
        'identified_difference_high','experimental_95_low','experimental_95_high','reps',
        'invalid_reps','interval_status',
    ]
    status = {
        'status':'computed' if len(pooled_cells) else ('no_common_support' if len(route) else 'no_route_rows'),
        'coverage_status':'FULL_CORE' if tuple(months) == CORE_MONTHS else 'INCOMPLETE_CORE_MONTHS',
        'missing_core_months':sorted(set(CORE_MONTHS).difference(months)),
        'periods':months, 'n':len(route), 'authoritative_outcome':'historical_BTS_reporting_carrier',
        'destination':'DEN', 'origins':AIRPORTS, 'shared_cells':len(pooled_cells),
        'shared_fixed_annual_cells':len(shared_annual), 'strata':STRATA, 'min_known':min_known,
        'conditional_denominator':'normal completions in the same standardized mixture',
        'paired_block_days':BLOCKS, 'block_reps':reps, 'block_seed':seed,
        'published_rate_scope':'historical reference',
    }
    out.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(raw).to_csv(out/'route_rates.csv',index=False)
    pd.DataFrame(comparisons,columns=comparison_columns).to_csv(out/'matched_comparisons.csv',index=False)
    pd.DataFrame(coverage).to_csv(out/'support_coverage.csv',index=False)
    pd.DataFrame(references,columns=['reference_scope','cell','weight']).to_csv(out/'reference_weights.csv',index=False)
    (out/'TRAVELER_CARD.md').write_text(_markdown(status,raw,coverage,comparisons),encoding='utf-8')
    (out/'card_status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
    return status


def main():
    from run_validation_v5 import ROOT, audit_months

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        audited, periods = audit_months(args.data, set(CORE_MONTHS), Path(tmp))
        if periods != set(CORE_MONTHS):
            parser.error(f'Missing core months {sorted(set(CORE_MONTHS).difference(periods))}')
        result = build_traveler_card(audited,args.out)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
