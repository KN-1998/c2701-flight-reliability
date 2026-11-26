"""Verified HTTP byte-range acquisition; bounded workers, no partial artifact publication."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,time,zipfile
import pandas as pd
import requests
from fetch_bts import ROOT,AIRPORTS,FIELDS

def fetch_ranges(year,month,workers=12,chunk_bytes=131072):
    folder=ROOT/'data';out=folder/f'bts_{year}_{month:02}.csv.gz';meta=folder/f'bts_{year}_{month:02}.json'
    if out.exists() and meta.exists():return json.loads(meta.read_text(encoding='utf-8'))
    u=f'https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip'
    with requests.get(u,headers={'Range':'bytes=0-0'},timeout=(15,40)) as r:
        r.raise_for_status()
        if r.status_code!=206 or not r.headers.get('Content-Range','').startswith('bytes 0-0/'):raise ValueError('Range unsupported')
        total=int(r.headers['Content-Range'].split('/')[-1]);etag=r.headers.get('ETag')
    parts=[(i,min(i+chunk_bytes,total)-1) for i in range(0,total,chunk_bytes)]
    def part(pair):
        a,b=pair;err=None
        for attempt in range(3):
            try:
                with requests.get(u,headers={'Range':f'bytes={a}-{b}'},timeout=(15,45)) as r:
                    r.raise_for_status();data=r.content
                    if r.status_code!=206 or r.headers.get('Content-Range')!=f'bytes {a}-{b}/{total}' or len(data)!=b-a+1:raise ValueError('Invalid range response')
                    if etag and r.headers.get('ETag')!=etag:raise ValueError('ETag changed')
                    return data
            except Exception as e:err=e;time.sleep(attempt+1)
        raise err
    t=time.time()
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:payload=b''.join(pool.map(part,parts))
    if len(payload)!=total:raise ValueError('Invalid assembled byte count')
    cache=ROOT/'.cache/range_downloads';cache.mkdir(parents=True,exist_ok=True);raw=cache/f'bts_{year}_{month:02}.zip';raw.write_bytes(payload)
    pieces=[];n=0
    with zipfile.ZipFile(raw) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        member=next(k for k in z.namelist() if k.lower().endswith('.csv'))
        with z.open(member) as s:
            for x in pd.read_csv(s,usecols=lambda c:c in FIELDS,chunksize=100000,low_memory=False):
                n+=len(x);pieces.append(x.loc[x.Origin.isin(AIRPORTS)].copy())
    frame=pd.concat(pieces,ignore_index=True);temp=out.with_name(out.name+'.part');frame.to_csv(temp,index=False,compression='gzip');temp.replace(out)
    record={'source':'BTS Reporting Carrier On-Time Performance','source_url':u,'downloaded_at_utc':pd.Timestamp.now(tz='UTC').isoformat(),'sha256_zip':hashlib.sha256(payload).hexdigest(),'compressed_bytes':total,'national_rows':n,'selected_origin_rows':len(frame),'airports':AIRPORTS,'fields':list(frame.columns),'period':f'{year}-{month:02}','filtered_file':out.name,'sha256_filtered':hashlib.sha256(out.read_bytes()).hexdigest(),'transfer':'HTTP ranges validated against Content-Range/ETag/length; assembled ZIP CRC verified','range_chunk_bytes':chunk_bytes,'range_workers':workers,'duration_seconds':round(time.time()-t,2)}
    meta.write_text(json.dumps(record,indent=2),encoding='utf-8');return record
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--periods',nargs='+',required=True);p.add_argument('--workers',type=int,default=12);a=p.parse_args();log=[]
    for period in a.periods:
        y,m=map(int,period.split('-'))
        try:r=fetch_ranges(y,m,a.workers);row={'period':period,'status':'OK','record':r}
        except Exception as e:row={'period':period,'status':'FAILED','error':repr(e)}
        log.append(row);print(json.dumps(row),flush=True)
        (ROOT/'data/REVIEW_V3_ACQUISITION_RANGES.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
