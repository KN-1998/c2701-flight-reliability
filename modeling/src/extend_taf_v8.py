"""Prepare a combined TAF archive for the registered post-September scoring window."""
from datetime import date
from pathlib import Path
import argparse
import gzip
import io
import json

import pandas as pd

from predeparture_v7 import ORIGIN_STATION, read_taf
from run_study_v7 import ROOT, new_directory, sha


MAIN_SEGMENTS = ROOT / 'data/taf_v8/extended_exact/taf_prevailing_corrected.csv.gz'
MAIN_PRODUCTS = ROOT / 'data/taf_v7/taf_products_normalized.csv.gz'
PRODUCTS = 'taf_products_normalized.csv.gz'
SEGMENTS = 'taf_prevailing_normalized.csv.gz'
KEY = ['station','product_id']


def read(path):
    return pd.read_csv(path,dtype=str,keep_default_na=False)


def write_csv(frame, path):
    with path.open('wb') as stream, gzip.GzipFile(fileobj=stream,mode='wb',filename='',mtime=0) as archive:
        with io.TextIOWrapper(archive,encoding='utf-8',newline='') as text:
            frame.to_csv(text,index=False,lineterminator='\n')


def combine(first_segments, first_products, extension, cutover, out):
    old, new = read(first_products), read(extension/PRODUCTS)
    start = pd.Timestamp(cutover,tz='UTC')
    old_times = pd.to_datetime(old.available_utc,utc=True,errors='raise',format='mixed')
    new_times = pd.to_datetime(new.available_utc,utc=True,errors='raise',format='mixed')
    before = old.loc[old_times.lt(start)].copy()
    after = new.loc[new_times.ge(start)].copy()
    station_set = set(ORIGIN_STATION.values())
    if set(before.station) != station_set or set(after.station) != station_set:
        raise ValueError('Both archives must cover every origin station around the cutover')
    old_end = old_times.loc[before.index].groupby(before.station).max()
    new_begin = new_times.loc[after.index].groupby(after.station).min()
    if not (new_begin-old_end).le(pd.Timedelta(days=1)).all():
        raise ValueError('The latest older and earliest new issuances must be within a day at each station')
    products = pd.concat([before,after],ignore_index=True)
    if products.duplicated(KEY).any():
        raise ValueError('Conflicting original product crosses the archive cutover')
    if products.duplicated(['station','available_utc'],keep=False).any():
        ambiguous = products.loc[products.duplicated(['station','available_utc'],keep=False)]
        if not ambiguous.product_status.eq('ambiguous_same_availability_minute').all():
            raise ValueError('Duplicate release times were not normalized as ambiguous')
    segments = pd.concat([
        read(first_segments).merge(before[KEY],on=KEY,validate='many_to_one'),
        read(extension/SEGMENTS).merge(after[KEY],on=KEY,validate='many_to_one')
    ],ignore_index=True)
    new_directory(out)
    write_csv(products,out/PRODUCTS)
    write_csv(segments,out/SEGMENTS)
    checked = read_taf(out/SEGMENTS,out/PRODUCTS)
    if checked.valid_from_utc.notna().sum() != len(segments):
        raise ValueError('A segment was lost while validating the combined archive')
    manifest = {'cutover_utc':start.isoformat(),'old_products_retained':len(before),
                'extension_products_added':len(after),'prevailing_segments':len(segments),
                'older_archive_sha256':{PRODUCTS:sha(first_products),SEGMENTS:sha(first_segments)},
                'extension_sha256':{p:sha(extension/p) for p in (PRODUCTS,SEGMENTS)},
                'combined_sha256':{p:sha(out/p) for p in (PRODUCTS,SEGMENTS)},
                'note':'Archive assembled before official BTS outcomes were available; cadence, '
                       'station coverage and timing do not certify full original-text semantics.'}
    (out/'taf_extension_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest,indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--taf',type=Path,default=MAIN_SEGMENTS)
    parser.add_argument('--taf-products',type=Path,default=MAIN_PRODUCTS)
    parser.add_argument('--extension',type=Path,required=True)
    parser.add_argument('--cutover',type=date.fromisoformat,default=date(2026,10,2))
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    combine(args.taf,args.taf_products,args.extension,args.cutover,args.out)


if __name__ == '__main__':
    main()
