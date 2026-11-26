"""Two linked formula implementation plus direct joint comparator.
All caps/regularization/defaults are experimental engineering choices, not paper-derived constants.
"""
from __future__ import annotations
import hashlib,json,warnings
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
    def __init__(self,C=1,threshold=60,fit_cap=FIT_CAP):
        self.C=C;self.threshold=threshold;self.fit_cap=fit_cap
        self.models=[];self.calibrators=[];self.training_counts=[];self.fit_warnings=[];self.calibration_counts=[]
    def fit(self,df):
        self.models=[];self.training_counts=[];self.fit_warnings=[];self.calibrators=[]
        x=features(df);rng=np.random.default_rng(2701)
        for mask,y in zip(branch_masks(df),branch_targets(df,self.threshold)):
            idx=np.flatnonzero(mask)
            if len(idx)>self.fit_cap:idx=np.sort(rng.choice(idx,self.fit_cap,replace=False))
            model,w=fit_binary(x.iloc[idx],y[idx],self.C)
            self.models.append(model);self.fit_warnings.append(w)
            self.training_counts.append({'available':int(mask.sum()),'fitted':len(idx),'events':int(y[idx].sum())})
        return self
    def raw(self,df):return np.column_stack([prob(m,features(df)) for m in self.models])
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
    def __init__(self,C=1,threshold=60,fit_cap=FIT_CAP):
        self.C=C;self.threshold=threshold;self.fit_cap=fit_cap;self.calibrator=None
    def fit(self,df):
        idx=np.arange(len(df));rng=np.random.default_rng(2701)
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

def run_prediction(df,outdir,*,threshold=60,fit_cap=FIT_CAP,plan='primary',C_grid=(.1,1,10)):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    if threshold<=0 or fit_cap<1:raise ValueError('positive threshold/cap required')
    periods=set(df.loc[df.date.notna(),'date'].dt.strftime('%Y-%m'))
    if plan=='primary':
        fit_end='2023-12-31';tune_start='2024-01-01';tune_end='2024-03-31';cal_start='2024-04-01';cal_end='2024-06-30'
        required=[f'2023-{m:02}' for m in range(1,13)]+[f'2024-{m:02}' for m in range(1,7)]
        holds=[(f'2024-{m:02}',f'2024-{m:02}') for m in range(7,13)]+[(f'2025-{m:02}',f'2025-{m:02}') for m in range(1,13)]+[('2026-09','2026-09')]
    elif plan=='development2023':
        fit_end='2023-08-31';tune_start='2023-09-01';tune_end='2023-09-30';cal_start='2023-10-01';cal_end='2023-10-31'
        required=[f'2023-{m:02}' for m in range(1,11)];holds=[('2023-11','2023-11'),('2023-12','2023-12')]
    else:raise ValueError('unknown prediction plan')
    missing=sorted(set(required)-periods)
    if missing:return {'status':'insufficient_period_coverage','plan':plan,'missing_training_or_calibration_months':missing}
    known=df[df.state.ne('unknown') & df.date.notna()].copy()
    fit=known[known.date.le(fit_end)];tune=known[known.date.between(tune_start,tune_end)];cal=known[known.date.between(cal_start,cal_end)];train=known[known.date.le(tune_end)]
    if min(len(fit),len(tune),len(cal))==0:return {'status':'empty_training_tuning_or_calibration','plan':plan}
    candidates=[];chosen={}
    for name,cls in [('conditional_tree',SequentialModel),('direct_joint',DirectJointModel)]:
        for C in C_grid:
            m=cls(C=C,threshold=threshold,fit_cap=fit_cap).fit(fit)
            p=1-combine(m.predict(tune))[:,3] if name=='conditional_tree' else m.predict(tune)
            rec={'method':name,'C':C,**evaluate(joint_target(tune,threshold),p),'fit_warnings':json.dumps(m.fit_warnings)};candidates.append(rec)
            print(f'{plan} {name} C={C} tuning Brier={rec["brier"]:.6f}',flush=True)
        chosen[name]=min([r for r in candidates if r['method']==name],key=lambda v:v['brier'])['C']
    tree=SequentialModel(chosen['conditional_tree'],threshold,fit_cap).fit(train).calibrate(cal)
    direct=DirectJointModel(chosen['direct_joint'],threshold,fit_cap).fit(train).calibrate(cal)
    baseline=HistoricalBaseline(20,threshold).fit(train)
    pd.DataFrame(candidates).to_csv(outdir/'tuning.csv',index=False)
    output=[];allpred=[];reliability=[];evaluated=[]
    for label,period in holds:
        test=known[known.date.dt.strftime('%Y-%m').eq(period)]
        if test.empty:continue
        print(f'{plan} predicting {label} n={len(test)}',flush=True)
        q=tree.predict(test);qb=baseline.predict(test);p=1-combine(q)[:,3];pb=1-combine(qb)[:,3];pdirect=direct.predict(test);y=joint_target(test,threshold)
        row_hash=hashlib.sha256(pd.util.hash_pandas_object(test[['date','Origin','Dest','Reporting_Airline','dep_minutes']],index=True).values.tobytes()).hexdigest()
        for name,risk,branches in [('conditional_tree',p,q),('historical_baseline',pb,qb),('direct_joint',pdirect,None)]:
            output.append({'period':label,'method':name,'threshold_minutes':threshold,'test_row_hash':row_hash,'target':'joint',**evaluate(y,risk)})
            if branches is not None:
                for j,(bm,by) in enumerate(zip(branch_masks(test),branch_targets(test,threshold))):
                    output.append({'period':label,'method':name,'threshold_minutes':threshold,'test_row_hash':row_hash,'target':BRANCHES[j],**evaluate(by[bm],branches[bm,j])})
            bins=np.minimum((risk*10).astype(int),9)
            for b in range(10):
                ix=bins==b
                if ix.any():reliability.append({'period':label,'method':name,'bin_left':b/10,'bin_right':(b+1)/10,'n':int(ix.sum()),'predicted':float(risk[ix].mean()),'observed':float(y[ix].mean())})
        keep=test[['date','Origin','Dest','Reporting_Airline','time_bin','quarter','weekday','bad','completed','ArrDelay','state']].copy()
        keep['bad']=y;keep['target_threshold_minutes']=threshold;keep['model_p']=p;keep['baseline_p']=pb;keep['direct_p']=pdirect
        keep['cancel_p']=q[:,0];keep['diversion_p']=(1-q[:,0])*q[:,1];keep['long_p']=combine(q)[:,2]
        allpred.append(keep);evaluated.append({'period':label,'n':len(test),'row_hash':row_hash})
    pd.DataFrame(output).to_csv(outdir/'prediction_metrics.csv',index=False);pd.DataFrame(reliability).to_csv(outdir/'calibration_bins.csv',index=False)
    if allpred:
        pred=pd.concat(allpred,ignore_index=True);pred.to_pickle(outdir/'predictions.pkl')
        # paired loss differences on the identical held-out rows; day variation, not a formal coverage claim
        rows=[]
        for period,sub in pred.groupby(pred.date.dt.strftime('%Y-%m')):
            for other,col in [('historical_baseline','baseline_p'),('direct_joint','direct_p')]:
                delta=(sub.model_p-sub.bad)**2-(sub[col]-sub.bad)**2
                daily=pd.DataFrame({'date':sub.date,'delta':delta}).groupby('date').delta.mean()
                rows.append({'period':period,'contrast':'conditional_tree_minus_'+other,'n':len(sub),'brier_difference':float(delta.mean()),'daily_difference_min':float(daily.min()),'daily_difference_max':float(daily.max()),'uncertainty':'descriptive paired loss; no CI/coverage guarantee'})
        pd.DataFrame(rows).to_csv(outdir/'paired_prediction_loss.csv',index=False)
    result={'status':'fitted' if allpred else 'fitted_no_holdout','plan':plan,'threshold_minutes':threshold,'chosen_C':chosen,'training_end':tune_end,'fit_end':fit_end,'tuning_start':tune_start,'calibration_start':cal_start,'calibration_end':cal_end,'holdout_months':evaluated,'features':CATS+NUMS,'coverage_basis':'Caller must supply complete audited monthly artifacts; internal eligibility checks month presence. run.py verifies monthly hashes/row counts.', 'fit_cap_per_binary':fit_cap,'seed':2701,'tree_training':tree.training_counts,'tree_calibration':tree.calibration_counts,'tree_warnings':tree.fit_warnings,'direct_training':direct.training_counts,'direct_calibration':direct.calibration_counts,'direct_warnings':direct.fit_warnings,'baseline_strength':20,'limitations':['Experimental defaults and sampling cap not justified for final use','Conditional branch fitting does not make categories independent','Same raw features/time windows, but tree has three fits and is not matched for parameter budget','Unknown excluded; historical schedules are not verified booking-time snapshots','2023 development plan cannot establish 2025 generalization; monthly test results not used for model choice']}
    (outdir/'prediction_status.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
