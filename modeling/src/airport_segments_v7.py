"""Report historical subgroup outcomes and the cost of stricter common support."""
from pathlib import Path
import argparse
import json

import pandas as pd

from audit import audit
from fetch_bts import AIRPORTS
from run_validation_v5 import ROOT, sha

CORE = pd.period_range('2023-01','2025-12',freq='M').astype(str)
DIMENSIONS = ['season','time_bin','Reporting_Airline','Dest','distance_bin']
SPECS = {
    'season_time_distance': ['season','time_bin','distance_bin'],
    'season_time_distance_carrier': ['season','time_bin','distance_bin','Reporting_Airline'],
    'season_time_destination_carrier': ['season','time_bin','Dest','Reporting_Airline'],
}
COUNTS = ['n','known','unknown','cancelled','diverted','on_time15','bad60']


def aggregate(frame,keys):
    return frame.groupby(keys,observed=True,dropna=False)[COUNTS].sum().reset_index()


def collect(data):
    pieces, supports = [], {label:[] for label in SPECS}
    sources=[]
    for period in CORE:
        stem='bts_'+period.replace('-','_')
        source=data/f'{stem}.csv.gz'
        record=json.loads((data/f'{stem}.json').read_text(encoding='utf-8-sig'))
        if record['period']!=period or sha(source)!=record['sha256_filtered']:
            raise ValueError(f'Unexpected historical source for {period}')
        raw=pd.read_csv(source,low_memory=False)
        if len(raw)!=record['selected_origin_rows']:
            raise ValueError(f'Source count mismatch for {period}')
        frame,counts=audit(raw)
        if not frame.date.dt.to_period('M').eq(period).all() or set(frame.Origin)!=set(AIRPORTS):
            raise ValueError(f'Unexpected date or airport scope in {period}')
        sources.append({'period':period,'sha256_filtered':record['sha256_filtered'],
                        'retained_rows':counts['retained_rows']})
        part=frame[['year','Origin',*DIMENSIONS]].copy()
        part['n']=1
        part['known']=frame.state.ne('unknown').astype(int)
        for label in ['unknown','cancelled','diverted']:
            part[label]=frame.state.eq(label).astype(int)
        part['on_time15']=(frame.completed & frame.ArrDelay.lt(15)).astype(int)
        part['bad60']=frame.bad.astype(int)
        for field in DIMENSIONS:
            cell=aggregate(part,['year','Origin',field]).rename(columns={field:'level'})
            cell['level']=cell.level.astype('string')
            cell['dimension']=field
            pieces.append(cell)
        for label,keys in SPECS.items():
            supports[label].append(aggregate(part,['Origin',*keys]))
        print('Historical airport groups',period,len(frame),flush=True)
    out=aggregate(pd.concat(pieces,ignore_index=True),['year','Origin','dimension','level'])
    return out,supports,sources


def coverage(supports,min_known):
    records=[]
    for label,keys in SPECS.items():
        counts=aggregate(pd.concat(supports[label],ignore_index=True),['Origin',*keys])
        common=counts.pivot(index=keys,columns='Origin',values='known').reindex(columns=AIRPORTS).fillna(0)
        allowed=common.index[common.ge(min_known).all(axis=1)]
        eligible=counts.set_index(keys).index.isin(allowed)
        for airport,rows in counts.assign(common=eligible).groupby('Origin'):
            n=int(rows.n.sum())
            matched=int(rows.loc[rows.common,'n'].sum())
            records.append({'stratification':label,'Origin':airport,'common_cells':len(allowed),
                            'n':n,'n_supported':matched,'coverage':matched/n})
    return pd.DataFrame(records)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    args=parser.parse_args()
    if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
        parser.error('A fresh output directory is required')
    table,supports,inputs=collect(args.data)
    table['strict15_lower']=table.on_time15/table.n
    table['strict15_upper']=(table.on_time15+table.unknown)/table.n
    table['bad60_lower']=table.bad60/table.n
    table['bad60_upper']=(table.bad60+table.unknown)/table.n
    min_known=30
    detail=coverage(supports,min_known)
    totals=detail.groupby(['stratification','common_cells'],as_index=False)[['n','n_supported']].sum()
    totals['coverage']=totals.n_supported/totals.n
    args.out.mkdir(parents=True,exist_ok=True)
    table.to_csv(args.out/'airport_subgroups.csv',index=False)
    detail.to_csv(args.out/'stricter_support_by_airport.csv',index=False)
    totals.to_csv(args.out/'stricter_support_pooled.csv',index=False)
    (args.out/'subgroup_status.json').write_text(json.dumps({
        'source_months':inputs,
        'scope':'Ten BTS origins, 2023–2025, reported operating-carrier dataset',
        'minimum_known_per_airport_cell':min_known,
        'publication':'Historical subgroup frequencies and coverage, not causal rankings',
    },indent=2)+'\n',encoding='utf-8')
    print(totals.to_string(index=False),flush=True)


if __name__=='__main__':
    main()

