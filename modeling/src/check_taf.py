"""Check forecast validity nesting, identities, archive coverage and output hashes."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path

import pandas as pd
from download_taf import STATIONS

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('out',type=Path)
args=parser.parse_args()
out=args.out
manifest=json.loads((out/'taf_normalization_manifest.json').read_text(encoding='utf-8'))
assert not manifest['partial']
for name,expected in manifest['normalized_sha256'].items():
    with (out/name).open('rb') as stream:
        assert file_digest(stream,'sha256').hexdigest()==expected
products=pd.read_csv(out/'taf_products_normalized.csv.gz')
segments=pd.read_csv(out/'taf_prevailing_normalized.csv.gz')
id_cols=['station','product_id']
date_cols=['issued_utc','available_utc','product_valid_from_utc','product_valid_to_utc']
for field in date_cols:
    products[field]=pd.to_datetime(products[field],utc=True)
    segments[field]=pd.to_datetime(segments[field],utc=True)
for field in ['valid_from_utc','valid_to_utc']:
    segments[field]=pd.to_datetime(segments[field],utc=True)
assert set(products.station)==set(segments.station)==set(STATIONS)
assert len(segments)==manifest['prevailing_segments']
assert not products.duplicated(id_cols).any()
assert not segments.duplicated(id_cols+['valid_from_utc','valid_to_utc']).any()
assert (products.available_utc>=products.issued_utc).all()
for time,matches in products[products.duplicated(['station','available_utc'],keep=False)].groupby(['station','available_utc']):
    assert matches.product_status.eq('ambiguous_same_availability_minute').all(),time
assert (segments.valid_from_utc<segments.valid_to_utc).all()
assert (segments.valid_from_utc>=segments.product_valid_from_utc).all()
assert (segments.valid_to_utc<=segments.product_valid_to_utc).all()
assert segments.product_status.eq('usable').all()
merged=segments.merge(products,on=id_cols,validate='many_to_one',suffixes=('_seg','_prod'))
assert len(merged)==len(segments)
for field in ['issued_utc','available_utc','product_valid_from_utc','product_valid_to_utc','product_status']:
    assert merged[field+'_seg'].eq(merged[field+'_prod']).all(),field
usable=products.loc[products.product_status.eq('usable'),id_cols]
assert set(usable.itertuples(index=False,name=None))==set(segments[id_cols].itertuples(index=False,name=None))
segments=segments.sort_values(id_cols+['valid_from_utc'])
group=segments.groupby(id_cols)
first=group.head(1)
last=group.tail(1)
assert first.valid_from_utc.eq(first.product_valid_from_utc).all()
assert last.valid_to_utc.eq(last.product_valid_to_utc).all()
following=group.valid_from_utc.shift(-1)
assert (following.isna() | following.eq(segments.valid_to_utc)).all()
period = products.issued_utc.dt.strftime('%Y-%m')
coverage=(products.assign(period=period,usable=products.product_status.eq('usable'))
          .groupby(['station','period']).agg(products=('product_id','size'),usable_products=('usable','sum'))
          .reset_index())
expected={str(p) for a,b in [('2023-01','2024-06'),('2026-01','2026-09')] for p in pd.period_range(a,b,freq="M")}
needed=coverage[coverage.period.isin(expected)]
assert needed.groupby('station').period.nunique().eq(len(expected)).all()
assert len(needed)==len(STATIONS)*len(expected) and needed.usable_products.gt(0).all()
coverage.to_csv(out/'taf_product_coverage_by_month.csv',index=False)
status={
    'qc':'PASS',
    'stations':sorted(STATIONS),
    'products_total_including_barrier':len(products),
    'usable_products':len(usable),
    'segments':len(segments),
    'included_target_station_months':len(needed),
    'target_station_months_min_usable_products':int(needed.usable_products.min()),
    'chronological_product_barrier_blocks_unpaired_and_ambiguous':True,
}
(out/'taf_qc.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print(json.dumps(status,indent=2))

