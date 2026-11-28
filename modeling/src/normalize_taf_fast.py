"""Normalize archived NWS TAF products and prevailing time segments for as-of joins."""
import argparse
from collections import defaultdict
from ast import literal_eval
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
from hashlib import file_digest
import io
import json
import math
from pathlib import Path
import re

import pandas as pd


OVERLAY=re.compile(r'^(TEMPO|PROB[34]0)\b')
NIL_OR_CANCEL=re.compile(r'(?:^|\s)(?:CNL|NIL)(?:\s|=|$)')

PRODUCT_COLS = ['station','product_id','issued_utc','available_utc','product_valid_from_utc',
                'product_valid_to_utc','is_amendment','product_status','has_tempo_or_prob']
SEGMENT_COLS = PRODUCT_COLS + ['valid_from_utc','valid_to_utc','visibility_sm',
                              'visibility_relation','ceiling_ft_agl','ceiling_status',
                              'wind_speed_kt','gust_kt','weather_codes','segment_kind','source_forecast_text']


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def utc(value):
    return pd.to_datetime(value,utc=True,errors='coerce',format='mixed')


def utc_series(series):
    return pd.to_datetime(series,utc=True,errors='coerce',format='mixed')


def optional_number(value):
    if value is None or value=='':
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def list_value(value):
    if value is None or value=='':
        return []
    result = literal_eval(value)
    if not isinstance(result,list):
        raise ValueError(f'Expected archived list value: {value!r}')
    return result


def segment_values(row):
    cover = list_value(row.skyc)
    level = list_value(row.skyl)
    if len(cover)!=len(level):
        raise ValueError(f'Mismatched sky fields in {row.product_id}: {cover}, {level}')
    ceiling_types = {'BKN','OVC','VV'}
    ceilings = [optional_number(l) for c,l in zip(cover,level) if c in ceiling_types]
    known = [value for value in ceilings if value is not None]
    ceiling = min(known) if known and len(known)==len(ceilings) else None
    if ceiling is not None:
        ceiling_status='present'
    elif cover and not ceilings:
        ceiling_status='none'
    else:
        ceiling_status='unknown'
    visibility = optional_number(row.visibility)
    relation = 'not_reported' if visibility is None else 'encoded_value'
    if re.search(r'(?<!\S)P[\d/.]+SM\b',row.raw):
        relation = 'greater_than'
    elif re.search(r'(?<!\S)M[\d/.]+SM\b',row.raw):
        relation = 'less_than'
    return {
        'visibility_sm':visibility,'visibility_relation':relation,
        'ceiling_ft_agl':ceiling,'ceiling_status':ceiling_status,
        'wind_speed_kt':optional_number(row.sknt),'gust_kt':optional_number(row.gust),
        'weather_codes':' '.join(list_value(row.presentwx)),
        'source_forecast_text':row.raw,
    }


def segment_records(product, groups, metrics):
    start, end = product['product_valid_from_utc'], product['product_valid_to_utc']
    if pd.isna(start) or pd.isna(end) or start>=end:
        product['product_status']='invalid_or_missing_product_validity'
        return []
    if groups is None:
        product['product_status']='parsed_group_missing'
        return []
    kinds={row.ftype for row in groups}
    texts=[row.raw for row in groups]
    product['has_tempo_or_prob']=bool(kinds&{'Temporary','Probability 30','Probability 40','TEMPO','PROB30','PROB40'} or
                                      any(OVERLAY.match(line) for line in texts))
    if any(line.startswith('BECMG') for line in texts) or kinds&{'Becoming','BECMG'}:
        product['product_status']='contains_becoming_group'
        return []
    if any(NIL_OR_CANCEL.search(line) for line in texts):
        product['product_status']='cancelled_or_nil'
        return []
    rows=[row for row in groups if row.ftype in {'Observation','Forecast'}]
    if not rows or any(pd.isna(row.group_start) for row in rows) or len({row.group_start for row in rows})!=len(rows):
        product['product_status']='absent_or_nonunique_prevailing_group'
        return []
    rows.sort(key=lambda row:row.group_start)
    first=rows[0]
    if first.ftype!='Observation':
        product['product_status']='initial_group_missing'
        return []
    if first.group_start!=start:
        metrics['initial_group_start_differs_from_product_valid_start']+=1
    if any(row.group_start<start for row in rows[1:]):
        product['product_status']='forecasts_start_before_product_validity'
        return []
    product['product_status']='usable'
    result = []
    for i,row in enumerate(rows):
        left=start if i==0 else row.group_start
        right=min(end,rows[i+1].group_start) if i+1<len(rows) else end
        if left>=right:
            metrics['segment_at_or_after_expiry_or_empty']+=1
            continue
        result.append({
            **product,'valid_from_utc':left,'valid_to_utc':right,
            'segment_kind':'initial' if i==0 else 'FM',**segment_values(row),
        })
    if not result:
        product['product_status']='empty_prevailing_intervals'
    return result


def manifest_paths(raw, allow_partial):
    manifest=json.loads((raw/'download_manifest.json').read_text(encoding='utf-8'))
    if not allow_partial and (manifest['errors'] or len(manifest['successes'])!=manifest['planned']):
        raise ValueError('Raw acquisition is incomplete')
    paths=[]
    for item in manifest['successes']:
        path=raw/item['file']
        if not path.is_file() or path.stat().st_size!=item['bytes'] or sha(path)!=item['sha256']:
            raise ValueError(f'Invalid archive file {path.name}')
        paths.append(path)
    return manifest,paths


def product_frame(paths):
    records=[]
    for path in paths:
        if path.name.startswith('product_'):
            rows=json.loads(path.read_text(encoding='utf-8'))['data']
            records.extend({k:r[k] for k in ['station','product_id','utc_issued','utc_issue','utc_expire','is_amendment']} for r in rows)
    if not records:
        raise ValueError('No archived product metadata')
    data=pd.DataFrame(records).drop_duplicates()
    if data.duplicated(['station','product_id']).any():
        raise ValueError('Contradictory metadata for same station and product ID')
    for field in ['utc_issued','utc_issue','utc_expire']:
        data[field]=utc_series(data[field])
    data['header_utc']=pd.to_datetime(data.product_id.str.slice(0,12),format='%Y%m%d%H%M',utc=True,errors='coerce')
    if data[['utc_issued','header_utc']].isna().any().any():
        raise ValueError('Unknown issuance or WMO timestamp')
    return data.sort_values(['station','utc_issued','product_id'])


def segment_frame(paths):
    tables=[
        pd.read_csv(path,dtype=str).fillna('') for path in paths if path.name.startswith('segment_')
    ]
    if not tables:
        raise ValueError('No archived forecast groups')
    data=pd.concat(tables,ignore_index=True).drop_duplicates()
    data['group_start']=utc_series(data.fx_valid)
    data['segment_issued']=utc_series(data.valid)
    return data


def gzip_csv(rows, fields, path):
    scratch=path.with_suffix(path.suffix+'.part')
    with scratch.open('wb') as stream, gzip.GzipFile(filename='',mode='wb',mtime=0,fileobj=stream) as compressed:
        with io.TextIOWrapper(compressed,encoding='utf-8',newline='') as wrapped:
            def value(x):
                if isinstance(x,pd.Timestamp):
                    return x.strftime('%Y-%m-%dT%H:%M:%SZ')
                if x is pd.NaT:
                    return ''
                return x
            writer=csv.DictWriter(wrapped,fieldnames=fields,lineterminator='\n')
            writer.writeheader()
            for row in rows:
                writer.writerow({k:value(row[k]) for k in fields})
    scratch.replace(path)


def normalize(raw, out, allow_partial):
    manifest,paths=manifest_paths(raw,allow_partial)
    products=product_frame(paths)
    segments=segment_frame(paths)
    grouped=defaultdict(list)
    for record in segments.itertuples(index=False):
        grouped[(record.station,record.product_id)].append(record)
    product_rows,segment_rows=[],[]
    diagnostics=Counter()
    for row in products.itertuples(index=False):
        key=(row.station,row.product_id)
        groups=grouped.pop(key,None)
        segment_issued=row.utc_issued
        if groups is not None and any(
            pd.isna(item.segment_issued) or item.segment_issued!=row.utc_issued for item in groups
        ):
            diagnostics['product_vs_group_issuance_different']+=1
            segment_issued=max((item.segment_issued for item in groups if pd.notna(item.segment_issued)),default=pd.NaT)
        available=max(row.utc_issued,row.header_utc,segment_issued) if pd.notna(segment_issued) else max(row.utc_issued,row.header_utc)
        product={'station':row.station,'product_id':row.product_id,
                 'issued_utc':row.utc_issued,'available_utc':available,
                 'product_valid_from_utc':row.utc_issue,'product_valid_to_utc':row.utc_expire,
                 'is_amendment':row.is_amendment,'product_status':'pending','has_tempo_or_prob':False}
        segment_rows.extend(segment_records(product,groups,diagnostics))
        product_rows.append(product)
    for (station, product_id), groups in grouped.items():
        if not re.match(r'^\d{12}',product_id):
            raise ValueError(f'Unpaired forecast group lacks WMO time: {station}, {product_id}')
        header_utc=pd.to_datetime(product_id[:12],format='%Y%m%d%H%M',utc=True)
        issued=max((item.segment_issued for item in groups if pd.notna(item.segment_issued)),default=pd.NaT)
        if pd.isna(issued):
            issued=header_utc
        product_rows.append({
            'station':station,'product_id':product_id,'issued_utc':issued,
            'available_utc':max(issued,header_utc),
            'product_valid_from_utc':pd.NaT,'product_valid_to_utc':pd.NaT,
            'is_amendment':any(item.is_amendment=='True' for item in groups),
            'product_status':'metadata_missing_for_parsed_groups','has_tempo_or_prob':False,
        })
    # Keep a barrier for an ambiguous latest product where source contains distinct
    # versions with the same available minute. Never guess an order from file order.
    keys=defaultdict(list)
    for row in product_rows:
        keys[(row['station'],row['available_utc'])].append(row)
    ambiguous=set()
    for rows in keys.values():
        if len(rows)>1:
            for row in rows:
                ambiguous.add((row['station'],row['product_id']))
                row['product_status']='ambiguous_same_availability_minute'
    if ambiguous:
        diagnostics['same_minute_version_barrier_products']=len(ambiguous)
        segment_rows=[row for row in segment_rows if (row['station'],row['product_id']) not in ambiguous]
    if not segment_rows:
        raise ValueError('No valid prevailing forecast segments')
    out.mkdir(exist_ok=True,parents=True)
    products_path=out/'taf_products_normalized.csv.gz'
    segments_path=out/'taf_prevailing_normalized.csv.gz'
    gzip_csv(product_rows,PRODUCT_COLS,products_path)
    gzip_csv(segment_rows,SEGMENT_COLS,segments_path)
    stats={
        'generated_utc':datetime.now(timezone.utc).isoformat(),
        'partial':len(manifest['successes'])!=manifest['planned'],
        'raw_products':len(product_rows),'prevailing_segments':len(segment_rows),
        'product_status_counts':dict(Counter(row['product_status'] for row in product_rows)),
        'stations_products':dict(Counter(row['station'] for row in product_rows)),
        'stations_segments':dict(Counter(row['station'] for row in segment_rows)),
        'group_type_counts':segments.ftype.value_counts().to_dict(),
        'source_group_only_products':len(grouped),
        'source_group_only_by_station':dict(Counter(key[0] for key in grouped)),
        'source_group_only_top_15_sample':[(key[0],key[1]) for key in list(grouped)[:15]],
        'diagnostics':dict(diagnostics),
        'normalized_sha256':{path.name:sha(path) for path in [products_path,segments_path]},
        'availability_assumption':'available_utc is the later of stored product issue, WMO header minute and parsed issuance metadata; a user-chosen availability lag is additional.',
        'join_rule':'Choose the newest product issued/available by cutoff, with any required additional lag; if unusable, expired or has no valid prevailing segment, forecast is missing. Do not fall back to superseded product. Segment interval is [valid_from_utc,valid_to_utc).',
        'forecast_scope':'Origin terminal NWS TAF, initial prevailing + FM. TEMPO/PROB not substituted for prevailing; BECMG products marked unavailable.',
    }
    (out/'taf_normalization_manifest.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(stats,indent=2),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,default=Path('taf_raw'))
    parser.add_argument('--out',type=Path,default=Path('taf_normalized'))
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    normalize(args.raw,args.out,args.allow_partial)

