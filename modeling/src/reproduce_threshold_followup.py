"""Reproduce a descriptive follow-up from TRUSTED, locally generated v3 pickle files.
Never run on downloaded or untrusted pickle files: pickle can execute arbitrary code.
Use threshold_coherence.py CSV inputs for interchange. No forecasts are refitted here.
"""
from pathlib import Path
import argparse
import hashlib
import json
import pandas as pd
from threshold_coherence import write_diagnostics

IDENTITY = ['date','Origin','Dest','Reporting_Airline','Flight_Number_Reporting_Airline','dep_minutes','scheduled_dep_2400']
CHECK_COLUMNS = ['date','Origin','Dest','Reporting_Airline','time_bin','quarter','weekday','completed','ArrDelay','state']


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def attach_verified_keys(pred, status, audited):
    if status.get('status') != 'fitted':raise ValueError('Fitted v3 status required')
    if not set(IDENTITY+CHECK_COLUMNS).issubset(audited.columns):raise ValueError('Full audited identity and metadata required')
    known=audited[audited.state.ne('unknown') & audited.date.notna()]
    months=[];seen=set()
    for item in status['holdout_months']:
        period=item['period']
        if period in seen:raise ValueError('Duplicate holdout period')
        seen.add(period)
        sub=known[known.date.dt.strftime('%Y-%m').eq(period)]
        row_hash=hashlib.sha256(pd.util.hash_pandas_object(sub[['date','Origin','Dest','Reporting_Airline','dep_minutes']],index=True).values.tobytes()).hexdigest()
        if len(sub)!=item['n'] or row_hash!=item['row_hash']:raise ValueError('Cached source differs from original holdout fingerprint')
        months.append(sub)
    if not months:raise ValueError('No holdout periods')
    raw=pd.concat(months,ignore_index=True)
    if len(raw)!=len(pred):raise ValueError('Prediction/source counts differ')
    if raw[IDENTITY].isna().any().any() or raw.duplicated(IDENTITY).any():raise ValueError('Invalid or duplicate source flight identity')
    x=pred.reset_index(drop=True).copy()
    for col in CHECK_COLUMNS:
        if col not in x:raise ValueError('Missing saved metadata '+col)
        a,b=raw[col],x[col]
        same=(a==b)|(a.isna()&b.isna())
        if not same.fillna(False).all():raise ValueError('Source order/outcome mismatch: '+col)
    if not x.target_threshold_minutes.eq(status['threshold_minutes']).all():raise ValueError('Source threshold mismatch')
    # A full identity, not a row number. Check uniqueness after hashing too.
    canonical=raw[IDENTITY].astype('string');canonical['date']=pd.to_datetime(raw.date).dt.strftime('%Y-%m-%d')
    x['flight_key']=[hashlib.sha256(json.dumps(list(row),ensure_ascii=True,separators=(',',':')).encode()).hexdigest()
                     for row in canonical.itertuples(index=False,name=None)]
    if not x.flight_key.is_unique:raise ValueError('Duplicate generated key')
    proof=dict(holdout_months=status['holdout_months'],source_order_and_outcome_checked=True,
               identity_columns=IDENTITY,paired_key_list_sha256=hashlib.sha256(('\n'.join(x.flight_key)+'\n').encode()).hexdigest())
    return x,proof


def reproduce(data, predictions_root, out):
    out=Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Fresh output directory required')
    audited=pd.read_pickle(data) # Explicit trusted-local CLI contract, never an automatic download.
    pairs=[];proofs=[];inputs=[dict(role='audited_v3_cache',name=Path(data).name,sha256=sha256(data))]
    for threshold in [15,60]:
        folder=Path(predictions_root)/f'prediction_primary_t{threshold}'
        pred_path=folder/'predictions.pkl';status_path=folder/'prediction_status.json'
        status=json.loads(status_path.read_text(encoding='utf-8'))
        if status['threshold_minutes']!=threshold:raise ValueError('Unexpected threshold in status')
        keyed,proof=attach_verified_keys(pd.read_pickle(pred_path),status,audited)
        pairs.append(keyed);proofs.append(proof)
        for role,path in [('predictions',pred_path),('prediction_status',status_path)]:
            inputs.append(dict(role=role,threshold=threshold,name=folder.name+'/'+path.name,sha256=sha256(path)))
    if proofs[0]!=proofs[1]:raise ValueError('Two thresholds do not share the exact original ordered holdout source')
    result=write_diagnostics(*pairs,out)
    manifest=dict(kind='REANALYSIS_OF_PREVIOUSLY_SEEN_V3_PREDICTIONS_NOT_V5_VALIDATION',inputs=inputs,
                  pairing_proof=proofs[0],new_data=False,new_training=False,v5_artifacts_available=False)
    (out/'diagnostic_inputs.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trusted-local-data',type=Path,required=True)
    parser.add_argument('--trusted-local-predictions-root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(reproduce(args.trusted_local_data,args.trusted_local_predictions_root,args.out),indent=2))

if __name__=='__main__':main()
