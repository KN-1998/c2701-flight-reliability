"""Descriptive calibration diagnostics, never a recalibration of released forecasts.
Primary method: Dimitriadis et al., arXiv:2008.03033v1, PDF pp5,8-10.
Flight dependence/exchangeability not established: no confidence bands are issued.
"""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

FINE_EDGES=np.array([0,.001,.0025,.005,.01,.02,.05,.1,.2,.4,.6,.8,1.])

def validated(y,p):
    y=np.asarray(y,dtype=float);p=np.asarray(p,dtype=float)
    if y.ndim!=1 or p.ndim!=1 or len(y)!=len(p):raise ValueError('One-dimensional matched vectors required')
    if not np.isfinite(y).all() or not np.isin(y,[0,1]).all():raise ValueError('Binary finite outcomes required')
    if not np.isfinite(p).all() or ((p<0)|(p>1)).any():raise ValueError('Finite probabilities in [0,1] required')
    return y,p

def diagnostics(y,p,*,period='',method='',target='',quantile_bins=10):
    y,p=validated(y,p)
    if quantile_bins<1:raise ValueError('Positive bin count required')
    meta=dict(period=period,method=method,target=target)
    if not len(y):return [],[],{**meta,'n':0,'events':0,'status':'EMPTY_RISK_SET'}
    schemes={'coarse_10':np.linspace(0,1,11),'fine_low_risk':FINE_EDGES,
             'quantile_ties_kept':np.unique(np.r_[0,np.quantile(p,np.linspace(0,1,quantile_bins+1))[1:-1],1])}
    bins=[]
    for scheme,edges in schemes.items():
        labels=np.searchsorted(edges[1:-1],p,side='right')
        for b in range(len(edges)-1):
            ix=labels==b;n=int(ix.sum());events=int(y[ix].sum())
            bins.append({**meta,'scheme':scheme,'bin':b,'left':float(edges[b]),'right':float(edges[b+1]),
                         'right_closed':b==len(edges)-2,'n':n,'events':events,'non_events':n-events,
                         'predicted':float(p[ix].mean()) if n else np.nan,'observed':float(y[ix].mean()) if n else np.nan,
                         'uncertainty':'DESCRIPTIVE_ONLY_no_independent_flight_CI'})
    # On the same outcomes ONLY to describe conditional frequencies. Never export as future forecasts.
    iso=IsotonicRegression(increasing=True,out_of_bounds='raise'); fitted=iso.fit_transform(p,y)
    z=pd.DataFrame({'p':p,'y':y,'cep':fitted})
    points=z.groupby('p',sort=True).agg(n=('y','size'),events=('y','sum'),cep=('cep','first')).reset_index()
    points['observed_at_exact_p']=points.events/points.n
    for k,v in meta.items():points[k]=v
    sx=float(np.mean((p-y)**2));sc=float(np.mean((fitted-y)**2));sr=float(np.mean((y.mean()-y)**2))
    summary={**meta,'n':len(y),'events':int(y.sum()),'unique_p':len(points),'pav_plateaus':int(points.cep.nunique()),
             'brier_original':sx,'brier_pav_same_sample_diagnostic':sc,'MCB':sx-sc,'DSC':sr-sc,'UNC':sr,
             'identity_residual':sx-((sx-sc)-(sr-sc)+sr),'status':'DESCRIPTIVE_ONLY',
             'monotone_CEP':'diagnostic_regularization_not_verified_population_truth',
             'reuse_warning':'PAV uses evaluation outcomes; NOT a new forecast model or out-of-sample skill gain'}
    return bins,points.to_dict('records'),summary

def saved_prediction_targets(sub):
    # Saved v3 predictions contain tree marginal branches only; do NOT fabricate baseline branches.
    yield 'conditional_tree','joint',sub.bad.to_numpy(),sub.model_p.to_numpy()
    for method,col in [('historical_baseline','baseline_p'),('direct_joint','direct_p')]:
        if col in sub:yield method,'joint',sub.bad.to_numpy(),sub[col].to_numpy()
    if 'cancel_p' in sub:
        f=sub.cancel_p.to_numpy();yield 'conditional_tree','cancel',sub.state.eq('cancelled').to_numpy(),f
    if 'diversion_p' in sub:
        yield 'conditional_tree','diversion_marginal',sub.state.eq('diverted').to_numpy(),sub.diversion_p.to_numpy()
        noncancel=sub.state.ne('cancelled').to_numpy();den=1-sub.cancel_p.to_numpy()
        if (den[noncancel]<=0).any():raise ValueError('Undefined conditional diversion risk')
        yield 'conditional_tree','divert_given_not_cancel',sub.loc[noncancel,'state'].eq('diverted').to_numpy(),sub.diversion_p.to_numpy()[noncancel]/den[noncancel]
    if 'long_p' in sub:
        completed=sub.completed.to_numpy(dtype=bool);den=1-sub.cancel_p.to_numpy()-sub.diversion_p.to_numpy()
        if (den[completed]<=0).any():raise ValueError('Undefined conditional long-delay risk')
        t=int(sub.target_threshold_minutes.iloc[0]);yield 'conditional_tree','long_given_completed',sub.loc[completed,'ArrDelay'].ge(t).to_numpy(),sub.long_p.to_numpy()[completed]/den[completed]
    threshold = int(sub.target_threshold_minutes.iloc[0])
    branch_labels = [
        ('cancel', np.ones(len(sub), dtype=bool), sub.state.eq('cancelled').to_numpy()),
        ('divert_given_not_cancel', sub.state.ne('cancelled').to_numpy(), sub.state.eq('diverted').to_numpy()),
        ('long_given_completed', sub.completed.to_numpy(dtype=bool), sub.ArrDelay.ge(threshold).to_numpy()),
    ]
    for target, mask, labels in branch_labels:
        column = f'baseline_{target}_p'
        if column in sub:
            yield 'historical_baseline', target, labels[mask], sub[column].to_numpy()[mask]

def validate_saved_predictions(pred):
    """Reject ambiguous risk sets before creating output or describing calibration."""
    required={'date','state','completed','bad','ArrDelay','target_threshold_minutes','model_p'}
    if not pred.columns.is_unique:raise ValueError('Duplicate prediction columns')
    missing=required-set(pred.columns)
    if missing:raise ValueError('Missing prediction columns: '+','.join(sorted(missing)))
    if pred.empty:raise ValueError('Empty saved predictions')
    dates=pd.to_datetime(pred.date,errors='raise')
    if dates.isna().any():raise ValueError('Missing prediction date')
    if pred.state.isna().any() or not pred.state.isin(['on_time','late','cancelled','diverted']).all():
        raise ValueError('Only known outcome states may enter calibration risk sets')
    threshold=pred.target_threshold_minutes.to_numpy(dtype=float)
    if not np.isfinite(threshold).all() or not (threshold==threshold[0]).all() or threshold[0]<=0 or threshold[0]!=int(threshold[0]):
        raise ValueError('Single positive integer target threshold required')
    completed,_=validated(pred.completed,pred.model_p)
    if not np.array_equal(completed.astype(bool),pred.state.isin(['on_time','late']).to_numpy()):
        raise ValueError('completed disagrees with outcome state')
    delay=pred.ArrDelay.to_numpy(dtype=float)
    if not np.isfinite(delay[completed.astype(bool)]).all():raise ValueError('Completed outcomes need finite arrival delays')
    expected=(completed==0)|(delay>=threshold[0])
    bad,_=validated(pred.bad,pred.model_p)
    if not np.array_equal(bad.astype(bool),expected):raise ValueError('bad disagrees with states/threshold')
    probability_columns=['model_p','baseline_p','direct_p','cancel_p','diversion_p','long_p']
    probability_columns.extend(
        f'baseline_{branch}_p' for branch in ('cancel','divert_given_not_cancel','long_given_completed')
    )
    for col in probability_columns:
        if col in pred:validated(pred.bad,pred[col])
    if 'diversion_p' in pred and 'cancel_p' not in pred:raise ValueError('diversion_p needs cancel_p')
    if 'long_p' in pred and not {'cancel_p','diversion_p'}.issubset(pred.columns):
        raise ValueError('long_p needs both preceding branch marginals')
    marginals=[c for c in ['cancel_p','diversion_p','long_p'] if c in pred]
    if marginals and (pred[marginals].sum(axis=1)>1+1e-10).any():raise ValueError('Branch marginal mass exceeds one')
    if len(marginals)==3 and not np.allclose(pred[marginals].sum(axis=1),pred.model_p,atol=1e-10,rtol=0):
        raise ValueError('Joint risk disagrees with branch marginal sum')

def analyze_saved(pred,out):
    validate_saved_predictions(pred)
    out=Path(out)
    if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Fresh output folder required')
    out.mkdir(parents=True, exist_ok=True)
    bins, plateaus, summaries = [], [], []
    keys = ['period','method','target','cep']
    for period, sub in pred.groupby(pd.to_datetime(pred.date).dt.to_period('M'), sort=True):
        for method, target, y, p in saved_prediction_targets(sub):
            b, points, summary = diagnostics(y, p, period=str(period), method=method, target=target)
            bins.extend(b)
            summaries.append(summary)
            if points:
                plateaus.append(pd.DataFrame(points).groupby(keys).agg(
                    p_min=('p','min'), p_max=('p','max'), n=('n','sum'),
                    events=('events','sum'), unique_p=('p','size')
                ).reset_index())
    pd.DataFrame(bins).to_csv(out/'calibration_bins_v4.csv',index=False)
    if plateaus:
        table = pd.concat(plateaus, ignore_index=True).sort_values(keys)
        table.to_csv(out/'calibration_pav_plateaus_v4.csv',index=False)
    pd.DataFrame(summaries).to_csv(out/'calibration_summary_v4.csv',index=False)
    missing = ('v3 saved file has no baseline conditional branch predictions'
               if 'baseline_cancel_p' not in pred else '')
    return {'status':'DESCRIPTIVE_ONLY','groups':len(summaries),'pav_used_for_forecasts':False,
            'uncertainty_bands_issued':False,'missing_saved_outputs':missing}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trusted-local-predictions',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists() and any(a.out.iterdir()):raise SystemExit('Fresh output folder required')
    # Pickle must be produced locally by this project; never load untrusted downloaded files.
    result=analyze_saved(pd.read_pickle(a.trusted_local_predictions),a.out)
    (a.out/'calibration_status_v4.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
if __name__=='__main__':main()
