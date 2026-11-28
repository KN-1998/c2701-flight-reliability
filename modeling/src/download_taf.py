"""Download issuance metadata and parsed TAF groups from public Iowa State IEM archives."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from hashlib import file_digest
import json
from pathlib import Path
import random
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

STATIONS = ['KATL','KDEN','KDFW','KEWR','PHNL','KLGA','KMCO','KORD','KSEA','KSFO']
HOST = 'https://mesonet.agron.iastate.edu'
PRODUCT = HOST + '/api/1/nws/taf_overview.json'
SEGMENT = HOST + '/cgi-bin/request/taf.py'
PRODUCT_FIELDS = {'station','product_id','is_amendment','utc_issued','utc_issue','utc_expire'}
SEGMENT_FIELDS = {'station','product_id','is_amendment','valid','fx_valid','raw','ftype',
                  'visibility','gust','skyc','skyl','presentwx'}
PERIODS = [('2022-12-30','2024-07-03'),('2025-12-30','2026-10-03')]
PRODUCT_SPANS = [('2022-12-30','2023-12-29'),('2023-12-29','2024-07-03'),
                 ('2025-12-30','2026-10-03')]


def sha(path):
    with path.open('rb') as stream:
        return file_digest(stream,'sha256').hexdigest()


def describe(path, kind, station, start, stop):
    if kind == 'product':
        data = json.loads(path.read_text(encoding='utf-8'))['data']
        assert data and PRODUCT_FIELDS.issubset(data[0]), (path, 'empty or bad product schema')
        times = [row['utc_issued'] for row in data]
    else:
        with path.open(encoding='utf-8-sig',newline='') as stream:
            reader = csv.DictReader(stream)
            assert SEGMENT_FIELDS.issubset(reader.fieldnames), (path,'segment schema')
            data = list(reader)
        times = [row['valid'] for row in data]
        assert data, (path, 'empty')
    found = {row['station'] for row in data}
    expected = set(station.split(','))
    assert found == expected, (path, sorted(found), sorted(expected))
    lo, hi = min(times)[:10], max(times)[:10]
    assert start<=lo<=hi<=stop, (path, lo, hi)
    assert (date.fromisoformat(stop)-date.fromisoformat(hi)).days<=2, (path, 'early truncation', hi)
    assert (date.fromisoformat(lo)-date.fromisoformat(start)).days<=1, (path,'late start',lo)
    return {'rows':len(data),'stations':sorted(found),'first_issued_utc':min(times),
            'last_issued_utc':max(times)}


def segment_spans():
    for start,end in PERIODS:
        begin = date.fromisoformat(start)
        finish = date.fromisoformat(end)
        while begin<finish:
            month_boundary = date(begin.year + (begin.month==12), 1 if begin.month==12 else begin.month+1, 1)
            stop = min(month_boundary,finish)
            if (stop-begin).days<4 and stop!=finish:
                stop = min(date(stop.year+(stop.month==12),1 if stop.month==12 else stop.month+1,1),finish)
            yield (str(begin),str(stop))
            begin = stop


def jobs():
    # Metadata accepts one station and at most one year. CSV supports multiple stations.
    # Interleave segments with metadata; keep the serving site at two requests at once.
    products = [(station,a,b) for (a,b) in PRODUCT_SPANS for station in STATIONS]
    segments = [(','.join(STATIONS),a,b) for a,b in segment_spans()]
    for j in range(max(len(products),len(segments))):
        if j<len(products):
            yield ('product',*products[j])
        if j<len(segments):
            yield ('segment',*segments[j])


def fetch(root, item):
    kind, station, start, stop = item
    params = {'station':station,'sts':start,'ets':stop}
    if kind == 'segment':
        params.update(sts=start+'T00:00Z',ets=stop+'T00:00Z',fmt='csv',tz='UTC')
    url = (PRODUCT if kind=='product' else SEGMENT)+'?'+urlencode(params)
    name = f'{kind}_{station if kind=="product" else "10station"}_{start}_{stop}.{"json" if kind=="product" else "csv"}'
    path = root/name
    if path.exists():
        evidence=describe(path,*item)
        return {'file':name,'url':url,'http_status':200,'reused_local':True,'bytes':path.stat().st_size,
                'sha256':sha(path),**evidence}
    error = None
    for attempt in range(1,5):
        scratch = path.with_suffix(path.suffix+'.part')
        try:
            request = Request(url,headers={'User-Agent':'C2701 academic TAF archive evidence / once per range'})
            with urlopen(request,timeout=90) as response:
                data = response.read()
                size = response.getheader('Content-Length')
                kind_header = response.getheader('Content-Type','')
                assert response.status==200 and (size is None or int(size)==len(data))
                expected_type = 'json' if kind=='product' else 'csv'
                assert expected_type in kind_header or 'octet-stream' in kind_header, kind_header
                headers={k:response.getheader(k) for k in ['ETag','Last-Modified','Content-Type','Content-Length']}
            scratch.write_bytes(data)
            evidence = describe(scratch,*item)
            scratch.replace(path)
            record={'file':name,'url':url,'http_status':200,'response_headers':headers,
                    'fetched_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(data),
                    'reused_local':False,'sha256':sha(path),**evidence}
            time.sleep(.5)
            return record
        except Exception as exc:
            scratch.unlink(missing_ok=True)
            error=exc
            time.sleep(min(attempt*3,10)+random.random())
    raise RuntimeError(f'{name} failed: {error}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('taf_raw'))
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    manifest_path=args.out/'download_manifest.json'
    previous={}
    if manifest_path.exists():
        previous={i['file']:i for i in json.loads(manifest_path.read_text(encoding='utf-8'))['successes']}
    pending=list(jobs())
    records,errors=[],[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(fetch,args.out,item):item for item in pending}
        for work in as_completed(futures):
            try:
                record=work.result()
                cached=previous.get(record['file'])
                if cached and cached['sha256']==record['sha256']:
                    record=cached
                records.append(record)
                print(f'OK {len(records):02}/{len(pending)} {record["file"]}: {record["rows"]:,} rows',flush=True)
            except Exception as exc:
                errors.append({'job':futures[work],'error':str(exc)})
                print('ERROR',exc,flush=True)
            stage=manifest_path.with_suffix('.json.part')
            stage.write_text(json.dumps({'stations':STATIONS,'planned':len(pending),'successes':sorted(records,key=lambda r:r['file']),
                                         'errors':errors},indent=2)+'\n',encoding='utf-8')
            stage.replace(manifest_path)
    if errors:
        raise SystemExit(f'{len(errors)} failed archive requests; see {manifest_path}')


if __name__ == '__main__':
    main()

