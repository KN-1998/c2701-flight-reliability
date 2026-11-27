"""Two linked formula implementation plus direct joint comparator.
All caps/regularization/defaults are experimental engineering choices, not paper-derived constants.
"""
from __future__ import annotations
import hashlib,json,warnings
from numbers import Integral
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit,logit
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score,brier_score_loss,log_loss,roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder,StandardScaler

from audit import KEY
from forecast_protocol import parse_forecast_protocol
CATS=['Origin','Dest','Reporting_Airline','month','weekday','time_bin']
NUMS=['dep_minutes','arr_minutes','Distance','CRSElapsedTime']
BRANCHES=['cancel','divert_given_not_cancel','long_given_completed']
FIT_CAP=200000

def combine(q):
    # P2 (2014), PDF p5 Definition 2 unnumbered path product; provenance D1.
    f,v,l=np.asarray(q).T
    return np.column_stack([f,(1-f)*v,(1-f)*(1-v)*l,(1-f)*(1-v)*(1-l)])
def features(df):
    x=df[CATS+NUMS].copy()
    for c in CATS:x[c]=x[c].astype('string').fillna('MISSING').astype(str)
    return x

def branch_masks(df):
    return [np.ones(len(df),dtype=bool),df.state.ne('cancelled').to_numpy(),df.completed.to_numpy()]
def branch_targets(df,threshold=60):
    return [df.state.eq('cancelled').to_numpy().astype(int),df.state.eq('diverted').to_numpy().astype(int),df.ArrDelay.ge(threshold).to_numpy().astype(int)]
def joint_target(df,threshold=60):
    return (df.state.isin(['cancelled','diverted']) | (df.completed & df.ArrDelay.ge(threshold))).to_numpy().astype(int)
def estimator(C):
    prep=ColumnTransformer([('cat',OneHotEncoder(handle_unknown='infrequent_if_exist',min_frequency=100,dtype=np.float64),CATS),('num',Pipeline([('impute',SimpleImputer(strategy='median')),('scale',StandardScaler())]),NUMS)])
    return Pipeline([('features',prep),('logit',LogisticRegression(C=C,solver='lbfgs',max_iter=250,tol=1e-5))])
def fit_binary(x,y,C):
    if len(y)==0:raise ValueError('empty binary training set')
    if len(np.unique(y))<2:return float(np.mean(y)),[]
    m=estimator(C)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always');m.fit(x,y)
    return m,[str(w.message) for w in caught]
def prob(m,x):
    return np.full(len(x),m) if isinstance(m,float) else m.predict_proba(x)[:,1]
def fit_sigmoid(p,y):
    if len(np.unique(y))<2:return None
    m=LogisticRegression(C=1e6,solver='lbfgs',max_iter=250)
    m.fit(logit(np.clip(p,1e-6,1-1e-6)).reshape(-1,1),y)
    return m
def apply_sigmoid(p,m):
    return p if m is None else m.predict_proba(logit(np.clip(p,1e-6,1-1e-6)).reshape(-1,1))[:,1]

class SequentialModel:
    def __init__(self,C=1,threshold=60,fit_cap=FIT_CAP,*,seed=2701):
        self.C=C;self.threshold=threshold;self.fit_cap=fit_cap;self.seed=seed
        self.models=[];self.calibrators=[];self.training_counts=[];self.fit_warnings=[];self.calibration_counts=[]
    def fit(self,df):
        self.models=[];self.training_counts=[];self.fit_warnings=[];self.calibrators=[]
        rng=np.random.default_rng(self.seed)
        for mask,y in zip(branch_masks(df),branch_targets(df,self.threshold)):
            idx=np.flatnonzero(mask)
            if len(idx)>self.fit_cap:idx=np.sort(rng.choice(idx,self.fit_cap,replace=False))
            model,w=fit_binary(features(df.iloc[idx]),y[idx],self.C)
            self.models.append(model);self.fit_warnings.append(w)
            self.training_counts.append({'available':int(mask.sum()),'fitted':len(idx),'events':int(y[idx].sum())})
        return self
    def raw(self,df):
        x = features(df)
        return np.column_stack([prob(model,x) for model in self.models])
    def calibrate(self,df):
        q=self.raw(df);self.calibrators=[];self.calibration_counts=[]
        for j,(mask,y) in enumerate(zip(branch_masks(df),branch_targets(df,self.threshold))):
            self.calibrators.append(fit_sigmoid(q[mask,j],y[mask]))
            self.calibration_counts.append({'n':int(mask.sum()),'events':int(y[mask].sum()),'applied':self.calibrators[-1] is not None})
        return self
    def predict(self,df):
        q=self.raw(df)
        for j,m in enumerate(self.calibrators):q[:,j]=apply_sigmoid(q[:,j],m)
        return q

class DirectJointModel:
    def __init__(self,C=1,threshold=60,fit_cap=FIT_CAP,*,seed=2701):
        self.C=C;self.threshold=threshold;self.fit_cap=fit_cap;self.seed=seed;self.calibrator=None
    def fit(self,df):
        idx=np.arange(len(df));rng=np.random.default_rng(self.seed)
        if len(idx)>self.fit_cap:idx=np.sort(rng.choice(idx,self.fit_cap,replace=False))
        y=joint_target(df,self.threshold)
        self.model,self.fit_warnings=fit_binary(features(df.iloc[idx]),y[idx],self.C)
        self.training_counts={'available':len(df),'fitted':len(idx),'events':int(y[idx].sum())}
        return self
    def calibrate(self,df):
        y=joint_target(df,self.threshold);self.calibrator=fit_sigmoid(prob(self.model,features(df)),y)
        self.calibration_counts={'n':len(df),'events':int(y.sum()),'applied':self.calibrator is not None};return self
    def predict(self,df):return apply_sigmoid(prob(self.model,features(df)),self.calibrator)

class HistoricalBaseline:
    def __init__(self,strength=20,threshold=60):self.strength=strength;self.threshold=threshold;self.rates=[];self.tables=[]
    def fit(self,df):
        self.rates=[];self.tables=[]
        for mask,y in zip(branch_masks(df),branch_targets(df,self.threshold)):
            sub=df.loc[mask,['Origin','quarter','time_bin']].copy();sub['y']=y[mask]
            if sub.empty:raise ValueError('empty baseline branch')
            rate=float(sub.y.mean());self.rates.append(rate)
            g=sub.groupby(['Origin','quarter','time_bin'],observed=True).y.agg(['sum','count'])
            self.tables.append((g['sum']+self.strength*rate)/(g['count']+self.strength))
        return self
    def predict(self,df):
        keys=pd.MultiIndex.from_frame(df[['Origin','quarter','time_bin']])
        return np.column_stack([t.reindex(keys).fillna(r).to_numpy() for t,r in zip(self.tables,self.rates)])

def evaluate(y,p):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=float)
    if len(y)==0:return {'n':0,'events':0,'observed':None,'predicted':None,'brier':None,'log_loss':None,'oe_ratio':None,'roc_auc':None,'pr_auc':None,'ece_10_fixed_bins':None}
    if not np.isfinite(p).all() or ((p<0)|(p>1)).any():raise ValueError('invalid probabilities')
    out={'n':len(y),'events':int(y.sum()),'observed':float(y.mean()),'predicted':float(p.mean()),'brier':float(brier_score_loss(y,p)),'log_loss':float(log_loss(y,np.clip(p,1e-8,1-1e-8),labels=[0,1])),'oe_ratio':float(y.mean()/p.mean()) if p.mean()>0 else None}
    out['roc_auc']=float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None
    out['pr_auc']=float(average_precision_score(y,p)) if len(np.unique(y))==2 else None
    bins=np.minimum((p*10).astype(int),9)
    out['ece_10_fixed_bins']=float(sum(np.abs(y[bins==b].mean()-p[bins==b].mean())*(bins==b).mean() for b in range(10) if (bins==b).any()))
    return out

def stable_flight_key(frame):
    """Encode the audited BTS identity without using a row index or shifting 2400."""
    missing = sorted(set(KEY) - set(frame.columns))
    if missing:
        raise ValueError('Flight identity is missing fields: ' + ', '.join(missing))
    parts = frame[KEY].astype('string')
    numeric_columns = ['CRSDepTime']
    flight_number = 'Flight_Number_Reporting_Airline'
    if pd.api.types.is_numeric_dtype(frame[flight_number]):
        numeric_columns.append(flight_number)
    for name in numeric_columns:
        # CSV parsing may promote integral values to floats when another row is missing.
        number = pd.to_numeric(parts[name], errors='coerce')
        if number.isna().any() or not np.isfinite(number).all() or number.mod(1).ne(0).any():
            raise ValueError(f'Non-integral value in the audited flight identity: {name}')
        parts[name] = number.astype('int64').astype('string')
    for name in KEY:
        part = parts[name]
        if part.isna().any() or part.str.strip().eq('').any() or part.str.contains(r'[|\r\n]').any():
            raise ValueError(f'Invalid value in the audited flight identity: {name}')
    key = parts[KEY[0]].str.cat([parts[name] for name in KEY[1:]], sep='|')
    if not key.is_unique:
        raise ValueError('Duplicate audited flight identity in held-out rows')
    return key


def run_prediction(df, outdir, *, threshold=60, fit_cap=None, plan='primary', C_grid=None,
                   save_baseline_branches=False, protocol=None, save_flight_identity=False):
    """Fit and score one threshold, with the archived plan as the default.

    A provided forecast protocol supplies all execution settings and requires
    explicit, nonoverlapping calendar windows. Holdouts can be absent when this
    function is called directly. Full-run coverage is checked by its caller.
    """
    fit_start = None
    seed = 2701
    baseline_strength = 20
    configured = protocol is not None
    if configured:
        protocol = parse_forecast_protocol(protocol)
        if plan != 'primary':
            raise ValueError('The explicit forecast protocol requires the primary plan')
        if isinstance(threshold, bool) or not isinstance(threshold, Integral) or threshold not in protocol.thresholds_minutes:
            raise ValueError('Threshold is not registered in the forecast protocol')
        threshold = int(threshold)
        if ((fit_cap is not None and fit_cap != protocol.fit_cap)
                or (C_grid is not None and tuple(C_grid) != protocol.C_grid)):
            raise ValueError('Use the forecast protocol to set fit_cap and C_grid')
        fit_start, fit_end = protocol.fit_start, protocol.fit_end
        tune_start, tune_end = protocol.tune_start, protocol.refit_end
        cal_start, cal_end = protocol.calibration_start, protocol.calibration_end
        required = protocol.required_months
        holds = protocol.holdout_months
        seed, baseline_strength = protocol.seed, protocol.baseline_strength
        fit_cap, C_grid = protocol.fit_cap, protocol.C_grid
    else:
        fit_cap = FIT_CAP if fit_cap is None else fit_cap
        C_grid = (.1, 1, 10) if C_grid is None else tuple(C_grid)
        if plan == 'primary':
            fit_end, tune_start, tune_end = '2023-12-31', '2024-01-01', '2024-03-31'
            cal_start, cal_end = '2024-04-01', '2024-06-30'
            required = [f'2023-{m:02}' for m in range(1, 13)] + [f'2024-{m:02}' for m in range(1, 7)]
            holds = ([f'2024-{m:02}' for m in range(7, 13)]
                     + [f'2025-{m:02}' for m in range(1, 13)] + ['2026-09'])
        elif plan == 'development2023':
            fit_end, tune_start, tune_end = '2023-08-31', '2023-09-01', '2023-09-30'
            cal_start, cal_end = '2023-10-01', '2023-10-31'
            required = [f'2023-{m:02}' for m in range(1, 11)]
            holds = ['2023-11', '2023-12']
        else:
            raise ValueError('unknown prediction plan')
    if threshold <= 0 or fit_cap < 1:
        raise ValueError('positive threshold/cap required')
    if save_flight_identity and not set(KEY).issubset(df.columns):
        raise ValueError('Full audited BTS identity is required to save flight keys')

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    month_index = df.date.dt.to_period('M')
    periods = set(month_index.dropna().unique().astype(str))
    missing = sorted(set(required) - periods)
    if missing:
        return {'status':'insufficient_period_coverage','plan':plan,
                'missing_training_or_calibration_months':missing}
    known = df.loc[df.state.ne('unknown') & month_index.notna()]
    # Apply the lower bound only for an explicit protocol. The legacy plans keep
    # the previous behavior when the caller supplies pre-2023 observations.
    training_source = known.loc[known.date.ge(fit_start)] if fit_start else known
    fit = training_source.loc[training_source.date.le(fit_end)]
    train = training_source.loc[training_source.date.le(tune_end)]
    tune = known.loc[known.date.between(tune_start, tune_end)]
    cal = known.loc[known.date.between(cal_start, cal_end)]
    if min(len(fit), len(tune), len(cal)) == 0:
        return {'status':'empty_training_tuning_or_calibration','plan':plan}

    candidates, chosen = [], {}
    settings = {'threshold':threshold, 'fit_cap':fit_cap, 'seed':seed}
    tune_target = joint_target(tune, threshold)
    for name, cls in [('conditional_tree', SequentialModel), ('direct_joint', DirectJointModel)]:
        model_rows = []
        for C in C_grid:
            model = cls(C=C, **settings).fit(fit)
            p_tune = model.predict(tune)
            if name == 'conditional_tree':
                p_tune = 1 - combine(p_tune)[:,3]
            rec = {'method':name, 'C':C, **evaluate(tune_target, p_tune),
                   'fit_warnings':json.dumps(model.fit_warnings)}
            model_rows.append(rec)
            print(f'{plan} {name} C={C} tuning Brier={rec["brier"]:.6f}', flush=True)
        chosen[name] = min(model_rows, key=lambda row:row['brier'])['C']
        candidates.extend(model_rows)
    tree = SequentialModel(C=chosen['conditional_tree'], **settings).fit(train).calibrate(cal)
    direct = DirectJointModel(C=chosen['direct_joint'], **settings).fit(train).calibrate(cal)
    baseline = HistoricalBaseline(baseline_strength, threshold).fit(train)
    pd.DataFrame(candidates).to_csv(outdir/'tuning.csv', index=False)

    output, allpred, reliability, evaluated = [], [], [], []
    paired_losses, daily_losses = [], []
    known_months = known.date.dt.to_period('M')
    for period in holds:
        test = known.loc[known_months.eq(period)]
        if test.empty:
            continue
        print(f'{plan} predicting {period} n={len(test)}', flush=True)
        q, qb = tree.predict(test), baseline.predict(test)
        leaf_probabilities = combine(q)
        p = 1 - leaf_probabilities[:,3]
        pb = 1 - combine(qb)[:,3]
        pdirect = direct.predict(test)
        y = joint_target(test, threshold)
        row_hash = hashlib.sha256(pd.util.hash_pandas_object(
            test[['date','Origin','Dest','Reporting_Airline','dep_minutes']], index=True
        ).values.tobytes()).hexdigest()
        row = {'period':period, 'n':len(test), 'row_hash':row_hash}
        if save_flight_identity:
            keys = stable_flight_key(test)
            row['flight_identity_sha256'] = hashlib.sha256(
                ('\n'.join(sorted(keys))+'\n').encode()
            ).hexdigest()
        masks = branch_masks(test)
        targets = branch_targets(test, threshold)
        for name, risk, branches in [
            ('conditional_tree',p,q), ('historical_baseline',pb,qb), ('direct_joint',pdirect,None),
        ]:
            common = {'period':period, 'method':name, 'threshold_minutes':threshold, 'test_row_hash':row_hash}
            if save_flight_identity:
                common['flight_identity_sha256'] = row['flight_identity_sha256']
            output.append({**common, 'target':'joint', **evaluate(y, risk)})
            if branches is not None:
                for j, (mask, target) in enumerate(zip(masks, targets)):
                    output.append({**common, 'target':BRANCHES[j], **evaluate(target[mask], branches[mask,j])})
            bins = np.minimum((risk*10).astype(int), 9)
            for b in np.unique(bins):
                ix = bins == b
                reliability.append({'period':period, 'method':name, 'bin_left':b/10,
                                    'bin_right':(b+1)/10, 'n':int(ix.sum()),
                                    'predicted':float(risk[ix].mean()), 'observed':float(y[ix].mean())})
        keep = test[['date','Origin','Dest','Reporting_Airline','time_bin','quarter','weekday',
                     'bad','completed','ArrDelay','state']].copy()
        keep['bad'] = y
        keep['target_threshold_minutes'] = threshold
        keep['model_p'], keep['baseline_p'], keep['direct_p'] = p, pb, pdirect
        keep['cancel_p'], keep['diversion_p'], keep['long_p'] = q[:,0], leaf_probabilities[:,1], leaf_probabilities[:,2]
        if save_baseline_branches:
            for j, branch in enumerate(BRANCHES):
                keep[f'baseline_{branch}_p'] = qb[:,j]
        if save_flight_identity:
            keep['flight_key'] = keys
        allpred.append(keep)
        evaluated.append(row)

        tree_loss = (p-y)**2
        for other, alternate_p in [('historical_baseline',pb), ('direct_joint',pdirect)]:
            contrast = 'conditional_tree_minus_' + other
            delta = tree_loss - (alternate_p-y)**2
            daily = pd.DataFrame({'date':test.date, 'delta':delta}).groupby('date').delta.agg(['sum','size','mean'])
            paired_losses.append({
                'period':period, 'contrast':contrast, 'n':len(test), 'brier_difference':float(delta.mean()),
                'daily_difference_min':float(daily['mean'].min()), 'daily_difference_max':float(daily['mean'].max()),
                'uncertainty':'descriptive paired loss; no CI/coverage guarantee',
            })
            if configured:
                for day, total, count, mean in daily.itertuples():
                    daily_losses.append({'period':period, 'date':day, 'contrast':contrast, 'n':count,
                                         'loss_difference_sum':total, 'brier_difference':mean})

    pd.DataFrame(output).to_csv(outdir/'prediction_metrics.csv', index=False)
    pd.DataFrame(reliability).to_csv(outdir/'calibration_bins.csv', index=False)
    if allpred:
        pd.concat(allpred, ignore_index=True).to_pickle(outdir/'predictions.pkl')
        pd.DataFrame(paired_losses).to_csv(outdir/'paired_prediction_loss.csv', index=False)
        if configured:
            pd.DataFrame(daily_losses).to_csv(outdir/'paired_prediction_loss_by_day.csv', index=False)
    result = {
        'status':'fitted' if allpred else 'fitted_no_holdout', 'plan':plan, 'threshold_minutes':threshold,
        'chosen_C':chosen, 'training_end':tune_end, 'fit_end':fit_end, 'tuning_start':tune_start,
        'calibration_start':cal_start, 'calibration_end':cal_end, 'holdout_months':evaluated,
        'features':CATS+NUMS,
        'coverage_basis':'Caller must supply complete audited monthly artifacts; internal eligibility checks month presence. run.py verifies monthly hashes/row counts.',
        'fit_cap_per_binary':fit_cap, 'seed':seed,
        'tree_training':tree.training_counts, 'tree_calibration':tree.calibration_counts, 'tree_warnings':tree.fit_warnings,
        'direct_training':direct.training_counts, 'direct_calibration':direct.calibration_counts,
        'direct_warnings':direct.fit_warnings, 'baseline_strength':baseline_strength,
        'limitations':[
            'Experimental defaults and sampling cap not justified for final use',
            'Conditional branch fitting does not make categories independent',
            'Same raw features/time windows, but tree has three fits and is not matched for parameter budget',
            'Unknown excluded; historical schedules are not verified booking-time snapshots',
            '2023 development plan cannot establish 2025 generalization; monthly test results not used to fit or tune each method'
            if configured else
            '2023 development plan cannot establish 2025 generalization; monthly test results not used for model choice',
        ],
    }
    if configured:
        result.update(
            protocol_label=protocol.label, fit_start=fit_start, tuning_end=tune_end,
            tune_months=list(protocol.tune_months), calibration_months=list(protocol.calibration_months),
            required_months=list(required), planned_holdout_months=list(holds), C_grid=list(C_grid),
        )
    if save_flight_identity:
        result['flight_identity_columns'] = KEY
        result['flight_identity_digest'] = 'SHA-256 of sorted flight keys, each followed by LF'
    (outdir/'prediction_status.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result

