"""Reproduce v3 from portable monthly CSV.GZ files, never from hidden pickle caches."""
from pathlib import Path
import argparse,hashlib,json
import pandas as pd
from audit import audit,metrics
from comparison import compare
from prediction import run_prediction
from mc_diagnostics import write_changes
from calibration_diagnostics import analyze_saved
from stress import stress_tests
from case_study import airport_rationale,traveler_case
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--predict',action='store_true');p.add_argument('--development',action='store_true');p.add_argument('--cap',type=int,default=50000);p.add_argument('--reps',type=int,default=1000);p.add_argument('--mc-check',action='store_true');p.add_argument('--snapshot',type=Path);a=p.parse_args()
    if a.mc_check and a.reps!=1000:raise ValueError('--mc-check requires --reps 1000 (run labels are literal)')
    if a.out.exists() and any(a.out.iterdir()):raise SystemExit('Fresh output folder required')
    a.out.mkdir(parents=True,exist_ok=True);frames=[];records=[];counts=[]
    keep=['date','year','month','quarter','weekday','season','Origin','Dest','Reporting_Airline','Flight_Number_Reporting_Airline','state','completed','bad','ArrDelay','dep_minutes','arr_minutes','time_bin','distance_bin','Distance','CRSElapsedTime','DivReachedDest','DivArrDelay','scheduled_dep_2400','scheduled_arr_2400']
    expected={}
    if a.snapshot:
        snapshot=json.loads(a.snapshot.read_text(encoding='utf-8'));expected={r['filtered_file']:r for r in snapshot['records']}
    files=sorted((ROOT/'data').glob('bts_*.csv.gz'))
    if expected:
        files=[ROOT/'data'/name for name in sorted(expected)]
    for f in files:
        meta=json.loads(f.with_name(f.name.replace('.csv.gz','.json')).read_text(encoding='utf-8'))
        if expected and meta['sha256_filtered']!=expected[f.name]['sha256_filtered']:raise ValueError('Snapshot changed '+f.name)
        if hashlib.sha256(f.read_bytes()).hexdigest()!=meta['sha256_filtered']:raise ValueError('Source hash mismatch '+f.name)
        raw=pd.read_csv(f,low_memory=False)
        if len(raw)!=meta['selected_origin_rows']:raise ValueError('Source row count mismatch '+f.name)
        x,c=audit(raw);frames.append(x[keep]);records.append(meta);counts.append({'file':f.name,**c})
    df=pd.concat(frames,ignore_index=True)
    for c in ['season','Origin','Dest','Reporting_Airline','state','distance_bin']:df[c]=df[c].astype('category')
    pd.DataFrame(counts).to_csv(a.out/'audit_by_month.csv',index=False)
    (a.out/'data_snapshot.json').write_text(json.dumps({'records':records,'n':len(df)},indent=2),encoding='utf-8')
    metrics(df,('year','Origin')).to_csv(a.out/'metrics_by_year_airport.csv',index=False)
    y=df[df.year.eq(2023)];d=a.out/'descriptive';airport_rationale(y,d);traveler_case(y,d/'EWR_LGA_to_DEN_2023',reps=a.reps)
    traveler_case(df[df.year.between(2024,2025)],d/'EWR_LGA_to_DEN_later_observed',reps=a.reps)
    status={}
    for name,strata,min_n in [('base',('season','time_bin','distance_bin'),30),('season_time',('season','time_bin'),30),('season_distance',('season','distance_bin'),30),('support_min100',('season','time_bin','distance_bin'),100)]:
        status[name]=compare(y,a.out/'comparison_2023'/name,reps=a.reps,strata=strata,min_known=min_n)
    if a.mc_check:
        status['mc_2000_seed2702']=compare(y,a.out/'comparison_2023/mc_2000_seed2702',reps=2000,seed=2702)
        status['monte_carlo_quantile_changes']=write_changes(a.out/'comparison_2023/base/pairwise_comparisons.csv',a.out/'comparison_2023/mc_2000_seed2702/pairwise_comparisons.csv',a.out/'comparison_2023/monte_carlo_quantile_changes.csv')
    if a.predict:
        for plan in (['development2023','primary'] if a.development else ['primary']):
            for t in [15,60]:
                o=a.out/f'prediction_{plan}_t{t}';status[f'{plan}_t{t}']=run_prediction(df,o,threshold=t,fit_cap=a.cap,plan=plan)
                status[f'events_{plan}_t{t}']=stress_tests(df,o)
                if (o/'predictions.pkl').exists():status[f'calibration_v4_{plan}_t{t}']=analyze_saved(pd.read_pickle(o/'predictions.pkl'),o/'calibration_v4')
    (a.out/'review_reproduction_status.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
if __name__=='__main__':main()
