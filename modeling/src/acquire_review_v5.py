"""Resume official TranStats ZIP ranges and publish validated monthly extracts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
import argparse
import hashlib
import json
import re
import threading
import time
import zipfile

import pandas as pd
import requests

from fetch_bts import AIRPORTS, FIELDS

HOST = 'https://www.transtats.bts.gov/PREZIP/'
MISSING = ['2026-09','2024-08','2024-09','2024-11','2024-12'] + [
    f'2025-{m:02}' for m in range(2, 13)
]
SINGLE_RANGE = re.compile(r'bytes (\d+)-(\d+)/(\d+)')
LOCAL = threading.local()


def fetch_range(url, start, end, total=None, etag=None):
    session = getattr(LOCAL, 'session', None)
    if session is None:
        session = requests.Session()
        LOCAL.session = session
    for attempt in range(4):
        headers = {'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}
        try:
            with session.get(url, headers=headers, timeout=(12, 20)) as response:
                response.raise_for_status()
                match = SINGLE_RANGE.fullmatch(response.headers.get('Content-Range', ''))
                if response.status_code != 206 or match is None:
                    raise ValueError('Server did not return a verified range')
                lo, hi, length = map(int, match.groups())
                version = response.headers.get('ETag')
                if (lo, hi) != (start, end) or (total is not None and length != total):
                    raise ValueError('Unexpected range or full object size')
                if etag is not None and version != etag:
                    raise ValueError('Source ETag changed during download')
                data = response.content
                if len(data) != hi - lo + 1:
                    raise ValueError('Incomplete range data')
                return data, length, version
        except (requests.RequestException, ValueError) as error:
            if attempt == 3:
                raise error
            time.sleep(attempt + 1)


def monthly_spec(period):
    year, month = period.split('-')
    url = f'{HOST}On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{int(month)}.zip'
    _, size, etag = fetch_range(url, 0, 0)
    if not etag:
        raise ValueError('Cannot verify source version without an ETag')
    return url, size, etag


def part_file(path, url, start, end, size, etag):
    if path.is_file() and path.stat().st_size == end - start + 1:
        return path
    data, _, _ = fetch_range(url, start, end, size, etag)
    scratch = path.with_suffix('.part')
    scratch.write_bytes(data)
    scratch.replace(path)
    return path


def publish(period, spec, parts, data_dir, cache):
    url, size, etag = spec
    raw = cache / f'bts_{period}.zip'
    scratch = raw.with_suffix('.part')
    digest = hashlib.sha256()
    with scratch.open('wb') as stream:
        for part in parts:
            chunk = part.read_bytes()
            digest.update(chunk)
            stream.write(chunk)
    if scratch.stat().st_size != size:
        raise ValueError(f'Unexpected assembled length for {period}')
    pieces = []
    national = 0
    with zipfile.ZipFile(scratch) as archive:
        if archive.testzip() is not None:
            raise ValueError(f'ZIP CRC failure for {period}')
        members = [name for name in archive.namelist() if name.lower().endswith('.csv')]
        if len(members) != 1:
            raise ValueError(f'Unexpected CSV member count for {period}')
        with archive.open(members[0]) as stream:
            for chunk in pd.read_csv(stream, usecols=FIELDS, chunksize=100000, low_memory=False):
                dates = pd.to_datetime(chunk.FlightDate, errors='raise')
                if not dates.dt.strftime('%Y-%m').eq(period).all():
                    raise ValueError(f'Out-of-month records in {period}')
                national += len(chunk)
                pieces.append(chunk.loc[chunk.Origin.isin(AIRPORTS)].copy())
    frame = pd.concat(pieces, ignore_index=True)
    days = pd.DatetimeIndex(pd.to_datetime(frame.FlightDate).unique()).sort_values()
    expected_days = pd.date_range(f'{period}-01', pd.Period(period).end_time.normalize())
    if not days.equals(expected_days) or set(frame.Origin.unique()) != set(AIRPORTS):
        raise ValueError(f'Incomplete days or selected airports in {period}')
    raw = scratch.replace(raw)
    stem = 'bts_' + period.replace('-', '_')
    filtered = data_dir / f'{stem}.csv.gz'
    meta = data_dir / f'{stem}.json'
    tmp_data = filtered.with_suffix('.part')
    tmp_meta = meta.with_suffix('.part')
    frame.to_csv(tmp_data, index=False, compression={'method':'gzip','mtime':0})
    record = dict(
        source='BTS Reporting Carrier On-Time Performance', source_url=url, period=period,
        downloaded_at_utc=datetime.now(UTC).isoformat(), etag=etag, sha256_zip=digest.hexdigest(),
        compressed_bytes=size, national_rows=national, selected_origin_rows=len(frame),
        airports=AIRPORTS, fields=list(frame.columns), filtered_file=filtered.name,
        sha256_filtered=hashlib.sha256(tmp_data.read_bytes()).hexdigest(), valid_days=len(days),
        raw_zip_filename=raw.name, reporting_carriers=sorted(frame.Reporting_Airline.unique()),
        transfer='Official HTTP ranges validated by Content-Range and ETag; ZIP CRC and month coverage verified',
    )
    tmp_meta.write_text(json.dumps(record, indent=2), encoding='utf-8')
    tmp_data.replace(filtered)
    tmp_meta.replace(meta)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=20)
    parser.add_argument('--periods', nargs='+', default=MISSING)
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    args.cache.mkdir(parents=True, exist_ok=True)
    periods = [
        period for period in args.periods
        if not all((args.data / ('bts_'+period.replace('-', '_')+ext)).exists()
                   for ext in ('.csv.gz', '.json'))
    ]
    specs, plans, failures = {}, {}, {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        headers = {pool.submit(monthly_spec, period):period for period in periods}
        for job in as_completed(headers):
            period = headers[job]
            try:
                specs[period] = job.result()
            except (ValueError, requests.RequestException) as exc:
                failures[period] = repr(exc)
                print(period, 'metadata failed', failures[period], flush=True)
        for period in periods:
            if period not in specs:
                continue
            url, size, etag = specs[period]
            saved = args.cache / ('ranges_'+period+'_'+hashlib.sha256(etag.encode()).hexdigest()[:12])
            saved.mkdir(exist_ok=True)
            chunk_size = 2**20
            plans[period] = [
                (saved / f'{start:09}.range', start, min(start+chunk_size, size)-1)
                for start in range(0, size, chunk_size)
            ]
        jobs = {}
        for period, plan in plans.items():
            url, size, etag = specs[period]
            for path, start, end in plan:
                jobs[pool.submit(part_file,path,url,start,end,size,etag)] = period
        done = dict.fromkeys(plans,0)
        for job in as_completed(jobs):
            period = jobs[job]
            try:
                job.result()
                done[period] += 1
                if done[period] % 8 == 0:
                    print(period, done[period], 'of', len(plans[period]), 'ranges', flush=True)
                if done[period] == len(plans[period]):
                    rec = publish(period,specs[period],[entry[0] for entry in plans[period]],args.data,args.cache)
                    print(period, 'VERIFIED', rec['selected_origin_rows'], 'selected rows', flush=True)
            except (ValueError, OSError, requests.RequestException, zipfile.BadZipFile) as exc:
                failures[period] = repr(exc)
                print(period, 'failed', failures[period], flush=True)
    (args.cache/'acquisition_attempt.json').write_text(json.dumps(failures,indent=2),encoding='utf-8')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

