from pathlib import Path
import argparse, concurrent.futures, hashlib, json, time, zipfile
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
AIRPORTS = ['ATL','ORD','DFW','DEN','LGA','EWR','SFO','SEA','MCO','HNL']
FIELDS = ['FlightDate','Reporting_Airline','DOT_ID_Reporting_Airline','Flight_Number_Reporting_Airline',
          'OriginAirportID','Origin','DestAirportID','Dest','CRSDepTime','CRSArrTime',
          'DepTime','ArrTime','DepDelay','ArrDelay','ArrDel15','Cancelled','CancellationCode',
          'Diverted','CRSElapsedTime','Distance','DivReachedDest','DivArrDelay']

def fetch(year, month, force=False):
    folder = ROOT / 'data'
    folder.mkdir(exist_ok=True)
    stem = f'{year}_{month:02d}'
    out = folder / f'bts_{stem}.csv.gz'
    meta = folder / f'bts_{stem}.json'
    if not force and out.exists() and meta.exists():
        return json.loads(meta.read_text(encoding='utf-8'))
    url = f'https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip'
    raw = folder / f'bts_{stem}.zip'
    for attempt in range(3):
        try:
            with requests.get(url, timeout=(20, 60), stream=True) as response:
                response.raise_for_status()
                with raw.open('wb') as stream:
                    for block in response.iter_content(1024 * 1024):
                        stream.write(block)
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2)
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    pieces, total = [], 0
    with zipfile.ZipFile(raw) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith('.csv'))
        with archive.open(name) as stream:
            for chunk in pd.read_csv(stream, usecols=lambda c: c in FIELDS, chunksize=100000, low_memory=False):
                total += len(chunk)
                pieces.append(chunk.loc[chunk.Origin.isin(AIRPORTS)].copy())
    data = pd.concat(pieces, ignore_index=True)
    data.to_csv(out, index=False, compression='gzip')
    record = dict(source='BTS Reporting Carrier On-Time Performance', source_url=url,
                  downloaded_at_utc=pd.Timestamp.now(tz='UTC').isoformat(), sha256_zip=digest,
                  compressed_bytes=raw.stat().st_size, national_rows=total,
                  selected_origin_rows=len(data), airports=AIRPORTS, fields=list(data.columns),
                  period=f'{year}-{month:02d}', filtered_file=out.name, sha256_filtered=hashlib.sha256(out.read_bytes()).hexdigest())
    meta.write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ['period','national_rows','selected_origin_rows']}), flush=True)
    return record

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pilot', action='store_true')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--force',action='store_true',help='Redownload even when a filtered cache exists')
    parser.add_argument('--periods',nargs='+',help='Explicit YYYY-MM months; overrides default/pilot list')
    args = parser.parse_args()
    periods = [(2025,1)] if args.pilot else [(y,m) for y in [2023,2024,2025] for m in range(1,13)] + [(2026,9)]
    if args.periods:
        periods = [tuple(map(int,p.replace('_','-').split('-'))) for p in args.periods]
        if any(len(p)!=2 or not 1<=p[1]<=12 for p in periods):
            parser.error('Each period must be YYYY-MM with month 01..12')
    records, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(fetch,y,m,args.force):(y,m) for y,m in periods}
        for job in concurrent.futures.as_completed(jobs):
            try:
                records.append(job.result())
            except Exception as exc:
                errors.append({'period':jobs[job], 'error':str(exc)})
                print(str(errors[-1]), flush=True)
    (ROOT/'data'/'manifest.json').write_text(json.dumps({'records':sorted(records,key=lambda r:r['period']), 'errors':errors},indent=2), encoding='utf-8')
    if errors:
        raise SystemExit(1)


