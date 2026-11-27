"""Independent external event windows and explicitly outcome-selected tail diagnostics."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import expit,logit
from comparison import block_weights
from prediction import evaluate,joint_target
ROOT=Path(__file__).resolve().parents[1]

def stress_tests(df,outdir,*,allow_unverified_scenarios=False,events_config=None, fitted_dates=None):
    outdir=Path(outdir);path=outdir/'predictions.pkl'
    if not path.exists():return {'status':'no_predictions'}
    pred=pd.read_pickle(path)
    methods=[('conditional_tree','model_p'),('historical_baseline','baseline_p')]
    if 'direct_p' in pred:methods.append(('direct_joint','direct_p'))
    config=json.loads(Path(events_config or ROOT/'docs/EXTERNAL_EVENTS.json').read_text(encoding='utf-8-sig'))
    scores=[];matched=[];event_status=[]
    for e in config['events']:
        if 'origin' not in e and 'reporting_airline' not in e:
            raise ValueError(f"Event {e['id']} needs an origin or reporting carrier")
        scope = pred
        if 'origin' in e:
            scope = scope[scope.Origin.eq(e['origin'])]
        if 'reporting_airline' in e:
            scope = scope[scope.Reporting_Airline.eq(e['reporting_airline'])]
        event = scope[scope.date.between(e['start'], e['end'])]
        controls = scope[scope.date.isin(pd.to_datetime(e['calendar_control_dates']))]
        status = 'observed_holdout' if len(event) else 'NO_HELDOUT_EVENT_ROWS'
        if len(event) and event.date.nunique() < len(pd.date_range(e['start'], e['end'])):
            status = 'PARTIAL_EVENT_DAYS'
        entry = {'event':e['id'],'holdout_event_rows':len(event),'holdout_control_rows':len(controls),
                 'status':status,'source':e['source_id'],'definition':e['definition']}
        if events_config is not None:
            entry.update(event_days=event.date.nunique(), control_days=controls.date.nunique(),
                         cancelled=int(event.state.eq('cancelled').sum()))
        event_status.append(entry)
        if event.empty:continue
        for label,sub in [('external_event',event),('calendar_controls_not_verified_calm',controls)]:
            if sub.empty:continue
            for method,col in methods:
                row = {'event':e['id'],'window':label,'origin':e.get('origin','ALL_SELECTED'),
                       'method':method,'days':sub.date.nunique(),'source_id':e['source_id'],
                       'source_location':e['source_location'],
                       'selection':e.get('selection','external administrative window, not chosen using flight outcomes'),
                       'uncertainty':'DESCRIPTIVE_ONLY; too few event days; no causal attribution',
                       **evaluate(sub.bad,sub[col])}
                if events_config is not None:
                    row.update(reporting_airline=e.get('reporting_airline','ALL_REPORTED'),
                               cancelled=int(sub.state.eq('cancelled').sum()))
                scores.append(row)
        if controls.empty:continue
        strata=e.get('matching_fields',['Dest','Reporting_Airline','time_bin','weekday'])
        def cells(sub):
            temp=sub[strata].astype('string').fillna('MISSING');keys=temp.iloc[:,0]
            for col in temp.columns[1:]:keys=keys+'|'+temp[col]
            z=sub.copy();z['cell']=keys;return z
        ev=cells(event);ct=cells(controls);common=set(ev.cell)&set(ct.cell)
        es=ev[ev.cell.isin(common)];cs=ct[ct.cell.isin(common)]
        if es.empty:continue
        w=es.groupby('cell').size()/len(es)
        for method,col in methods:
            for label,sub,total in [('external_event',es,len(ev)),('calendar_controls_not_verified_calm',cs,len(ct))]:
                g=sub.groupby('cell').agg(n=('bad','size'),observed=('bad','mean'),predicted=(col,'mean')).reindex(w.index)
                matched.append({'event':e['id'],'window':label,'method':method,'common_cells':len(common),'n':len(sub),'coverage':len(sub)/total,'observed':float(w@g.observed),'predicted':float(w@g.predicted),'residual':float(w@(g.observed-g.predicted)),'target_mix':('event flights restricted to shared '+'/'.join(strata)+' cells' if events_config is not None else 'event flights restricted to shared destination/carrier/time/weekday cells'),'causal_claim':False,'uncertainty':'DESCRIPTIVE_ONLY; calendar controls not proven exchangeable'})
    pd.DataFrame(scores,columns=list(scores[0]) if scores else ['event','window','method','n']).to_csv(outdir/'external_event_scores.csv',index=False)
    pd.DataFrame(matched,columns=list(matched[0]) if matched else ['event','window','method','n']).to_csv(outdir/'external_event_matched.csv',index=False)
    (outdir/'external_event_status.json').write_text(json.dumps(event_status,indent=2),encoding='utf-8')
    target=int(pred.target_threshold_minutes.iloc[0]) if 'target_threshold_minutes' in pred else 60
    fitting_days = df.date.le('2024-03-31') if fitted_dates is None else df.date.between(*fitted_dates)
    train=df[fitting_days & df.state.ne('unknown')].copy()
    train['bad_target']=joint_target(train,target)
    threshold=float(train.groupby('date',observed=True).bad_target.mean().quantile(.95))
    test=pred[pred.date.dt.year.eq(2025)].copy();daily_rate=test.groupby('date',observed=True).bad.mean()
    difficult_dates=daily_rate.index[daily_rate>threshold];test['difficult']=test.date.isin(difficult_dates)
    rows=[]
    for flag,sub in test.groupby('difficult',observed=True):
        for method,col in methods:rows.append({'difficult':bool(flag),'training_daily_threshold':threshold,'days':sub.date.nunique(),'method':method,'selection':'RETROSPECTIVE_OUTCOME_SELECTED; cannot establish independent difficult-day underprediction',**evaluate(sub.bad,sub[col])})
    pd.DataFrame(rows,columns=list(rows[0]) if rows else ['difficult','method','n','selection']).to_csv(outdir/'tail_day_diagnostics_2025.csv',index=False)
    # Gate A33/A34: no empirical justification for the old odds multipliers.
    # An explicit opt-in is retained only for numerical sensitivity/integration tests.
    if not allow_unverified_scenarios:
        if (outdir/'scenarios_2027_assumed.csv').exists():
            raise RuntimeError('Legacy unverified scenario output exists; use a fresh result directory to avoid stale scientific claims.')
        return {'status':'historical_diagnostics_only','tail_day_threshold':threshold,
                'difficult_days_2025':len(difficult_dates),
                'scenario_status':'DISABLED: A33/A34 require externally supported scenario intensity',
                'assumption_audit':'SOURCE_AUDIT_INCOMPLETE; calendar windows are not verified event attribution'}
    # Scenario baseline uses 2025 reference flight mix, NOT actual 2027 schedules.
    scenario=[]
    dates=pd.DatetimeIndex(sorted(test.date.unique())); weights=block_weights(dates,reps=500,block=7)
    f=np.clip(test.cancel_p.to_numpy(),1e-8,1-1e-8)
    v=np.clip(test.diversion_p.to_numpy()/(1-f),1e-8,1-1e-8)
    l=np.clip(test.long_p.to_numpy()/np.maximum(1-f-test.diversion_p.to_numpy(),1e-8),1e-8,1-1e-8)
    for kind in ['cancel_concentration','long_delay_pressure','mixed_disruption']:
        for multiplier in [1,1.5,2,3]:
            fs=expit(logit(f)+(np.log(multiplier) if kind!='long_delay_pressure' else 0))
            ls=expit(logit(l)+(np.log(multiplier) if kind!='cancel_concentration' else 0))
            ps=1-(1-fs)*(1-v)*(1-ls)
            temp=test[['date','Origin']].copy();temp['ps']=ps
            for a,sub in temp.groupby('Origin',observed=True):
                daily=sub.groupby('date',observed=True).ps.agg(['sum','count']).reindex(dates).fillna(0)
                boot=(weights@daily['sum'].to_numpy())/(weights@daily['count'].to_numpy())
                scenario.append({'reference_year':2025,'target_label':2027,'airport':a,'scenario':kind,'odds_multiplier':multiplier,'mean_bad_risk':float(sub.ps.mean()),'conditional_sampling_ci_low':np.quantile(boot,.025),'conditional_sampling_ci_high':np.quantile(boot,.975),'evidence':'ASSUMED_STRESS; not verified historical interpolation; does not include parameter or structural uncertainty'})
    pd.DataFrame(scenario).to_csv(outdir/'scenarios_2027_assumed.csv',index=False)
    return {'status':'computed','tail_day_threshold':threshold,'difficult_days_2025':len(difficult_dates),'scenario_status':'ASSUMED_STRESS; 2025 flight mix; not actual 2027 predictions'}

