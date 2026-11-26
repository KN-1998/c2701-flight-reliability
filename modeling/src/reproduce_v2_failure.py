"""Reproduce the archived v2 empty-common-cell failure (intentional negative run)."""
from pathlib import Path
import json
import pandas as pd
from audit import audit
from legacy_v2_comparison import compare
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    out=ROOT/'results/v2_failure_reproduction'
    if out.exists() and any(out.iterdir()):raise SystemExit('Fresh output folder required')
    out.mkdir(parents=True,exist_ok=True);frames=[]
    for f in sorted((ROOT/'data').glob('bts_2023_*.csv.gz')):
        x,_=audit(pd.read_csv(f,low_memory=False));frames.append(x[['date','year','season','Origin','state','completed','ArrDelay','time_bin','distance_bin']])
    df=pd.concat(frames,ignore_index=True)
    try:
        compare(df,out,reps=500);result={'status':'EXPECTED_FAILURE_NOT_REPRODUCED'}
    except ValueError as e:
        result={'status':'REPRODUCED_FAILURE','error':repr(e),'scope':'2023; archived v2 snapshot, seed2701, reps500, blocks1/7/14'}
    (out/'v2_reproduction.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    if result['status']!='REPRODUCED_FAILURE':raise SystemExit(1)
