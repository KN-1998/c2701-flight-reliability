"""Independent eligibility/error boundaries for descriptive, comparison and prediction work."""
from pathlib import Path
import argparse,json,traceback,hashlib
import pandas as pd
from audit import audit,metrics
from comparison import compare
from prediction import run_prediction
from stress import stress_tests
ROOT=Path(__file__).resolve().parents[1]
def dump(value,path):path.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')
def execute_tasks(tasks,summary,out):
    errors=[]
    for name,task in tasks:
        try:summary[name]=task()
        except Exception as e:
            summary[name]={'status':'ERROR','error':repr(e),'traceback':traceback.format_exc()};errors.append(name)
        dump(summary,out/'run_summary.json')
    return errors

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pilot',action='store_true');parser.add_argument('--skip-model',action='store_true');parser.add_argument('--skip-comparison',action='store_true')
    parser.add_argument('--out',type=Path);parser.add_argument('--allow-existing',action='store_true')
    parser.add_argument('--prediction-plan',choices=['primary','development2023'],default='primary')
    parser.add_argument('--prediction-threshold',type=float,default=60);parser.add_argument('--comparison-threshold',type=float,default=15)
    parser.add_argument('--fit-cap',type=int,default=200000);parser.add_argument('--reps',type=int,default=500)
    args=parser.parse_args();out=args.out or ROOT/'results'/('pilot_v3' if args.pilot else 'core_v3')
    if out.exists() and any(out.iterdir()) and not args.allow_existing:raise SystemExit('Use a fresh --out folder. Existing scientific outputs are not overwritten by default.')
    out.mkdir(parents=True,exist_ok=True)
    files=sorted((ROOT/'data').glob('bts_*.csv.gz'))
    if args.pilot:files=[p for p in files if '2025_01' in p.name]
    if not files:raise SystemExit('No BTS files available.')
    frames=[];audits=[];exceptions=[];periods=[]
    keep=['date','year','month','quarter','weekday','season','Origin','Dest','Reporting_Airline','Flight_Number_Reporting_Airline','state','completed','bad','ArrDelay','dep_minutes','arr_minutes','time_bin','distance_bin','Distance','CRSElapsedTime','DivReachedDest','DivArrDelay','scheduled_dep_2400','scheduled_arr_2400']
    for f in files:
        metadata=f.with_name(f.name.replace('.csv.gz','.json'))
        if not metadata.exists():raise ValueError('Monthly source metadata missing: '+f.name)
        record=json.loads(metadata.read_text(encoding='utf-8'))
        if hashlib.sha256(f.read_bytes()).hexdigest()!=record['sha256_filtered']:raise ValueError('Monthly hash mismatch: '+f.name)
        raw=pd.read_csv(f,low_memory=False)
        if len(raw)!=record['selected_origin_rows']:raise ValueError('Monthly row count mismatch: '+f.name)
        frame,c=audit(raw);c['file']=f.name;audits.append(c)
        unknown=frame[frame.state.eq('unknown')]
        if len(unknown):exceptions.append(unknown[['FlightDate','Reporting_Airline','Flight_Number_Reporting_Airline','Origin','Dest','CRSDepTime','audit_reason']])
        frames.append(frame[keep]);periods.append(f.name[4:11].replace('_','-'))
        print(f'audited {f.name} n={len(frame)}',flush=True)
    pd.DataFrame(audits).to_csv(out/'audit_by_month.csv',index=False)
    if exceptions:pd.concat(exceptions).to_csv(out/'unknown_records.csv',index=False)
    data=pd.concat(frames,ignore_index=True);del frames
    for c in ['season','Origin','Dest','Reporting_Airline','state','distance_bin']:data[c]=data[c].astype('category')
    core=data[data.year.between(2023,2025)]
    required={f'{y}-{m:02}' for y in [2023,2024,2025] for m in range(1,13)}
    missing=sorted(required-set(periods))
    summary={'status':'PARTIAL_CORE' if missing else 'FULL_CORE_DATA_ONLY','retained_rows':len(data),'core_rows':len(core),'periods':periods,'missing_core_months':missing,'unknown':int(data.state.eq('unknown').sum()),'provenance_status':'SOURCE_AUDIT_INCOMPLETE','date_context':'2026-11-26 Asia/Shanghai','comparative_ranking_is_not_causal':True,'eligibility':'Each task uses its own observed period requirements; a comparison failure does not prevent prediction.'}
    tasks=[]
    def describe():
        metrics(data,('year','Origin')).to_csv(out/'metrics_by_year_airport.csv',index=False);metrics(core).to_csv(out/'metrics_core_airport.csv',index=False)
        for cols,name in [(('Origin','season'),'season'),(('Origin','time_bin'),'time_bin'),(('Origin','Reporting_Airline'),'airline'),(('Origin','distance_bin'),'distance')]:metrics(core,cols).to_csv(out/f'metrics_by_{name}.csv',index=False)
        return {'status':'computed','months':periods}
    tasks.append(('descriptive',describe))
    if not args.skip_comparison:
        tasks.append(('comparison',lambda:compare(core,out/'comparison_observed',reps=args.reps,threshold=args.comparison_threshold)))
    if not args.skip_model:
        tasks.append(('prediction',lambda:run_prediction(data,out/'prediction',threshold=args.prediction_threshold,fit_cap=args.fit_cap,plan=args.prediction_plan)))
        tasks.append(('stress',lambda:stress_tests(data,out/'prediction')))
    errors=execute_tasks(tasks,summary,out)
    summary['task_errors']=errors;dump(summary,out/'run_summary.json');print(json.dumps(summary,indent=2),flush=True)
    if errors:raise SystemExit(1)
if __name__=='__main__':main()
