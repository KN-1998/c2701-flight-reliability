"""Plots and auditable binned tables; no performance superiority inferred here."""
from pathlib import Path
import argparse,json,os
import numpy as np
import pandas as pd
cache=Path(__file__).resolve().parents[1]/'.cache/matplotlib_review'
cache.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR',str(cache))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prediction import evaluate
METHODS=[('conditional_tree','model_p'),('historical_baseline','baseline_p'),('direct_joint','direct_p')]

def render_prediction(folder):
    folder=Path(folder);path=folder/'predictions.pkl'
    if not path.exists():return
    df=pd.read_pickle(path);t=int(df.target_threshold_minutes.iloc[0]);bins=[];groups=[]
    for period,x in df.groupby(df.date.dt.strftime('%Y-%m')):
        fig,axes=plt.subplots(2,2,figsize=(10,9))
        targets=[('joint',np.ones(len(x),bool),x.bad.to_numpy(),None),('cancel',np.ones(len(x),bool),x.state.eq('cancelled').to_numpy(),x.cancel_p.to_numpy()),('divert_given_not_cancel',x.state.ne('cancelled').to_numpy(),x.state.eq('diverted').to_numpy(),x.diversion_p.to_numpy()/np.maximum(1-x.cancel_p.to_numpy(),1e-12)),('long_given_completed',x.completed.to_numpy(),x.ArrDelay.ge(t).to_numpy(),x.long_p.to_numpy()/np.maximum(1-x.cancel_p.to_numpy()-x.diversion_p.to_numpy(),1e-12))]
        for ax,(target,mask,y,pbranch) in zip(axes.ravel(),targets):
            models=[(name,x[col].to_numpy()) for name,col in METHODS] if target=='joint' else [('conditional_tree',pbranch)]
            for name,p in models:
                p=np.clip(p[mask],0,1);obs=y[mask];idx=np.minimum((p*10).astype(int),9);px=[];oy=[]
                for b in range(10):
                    ix=idx==b
                    if not ix.any():continue
                    row={'period':period,'threshold_minutes':t,'target':target,'method':name,'bin_left':b/10,'bin_right':(b+1)/10,'n':int(ix.sum()),'predicted':float(p[ix].mean()),'observed':float(obs[ix].mean())};bins.append(row);px.append(row['predicted']);oy.append(row['observed'])
                ax.plot(px,oy,'o-',label=name,markersize=4)
            ax.plot([0,1],[0,1],'k--',alpha=.3);ax.set(xlabel='Mean predicted probability',ylabel='Observed fraction',title=target,xlim=(0,1),ylim=(0,1));ax.legend(fontsize=7);ax.grid(alpha=.2)
        fig.suptitle(f'{period}, threshold={t} min; conditional branch bins, descriptive calibration');fig.tight_layout();fig.savefig(folder/f'calibration_{period}.png',dpi=140);plt.close(fig)
        for c in ['Origin','time_bin','Reporting_Airline']:
            for v,g in x.groupby(c,observed=True):
                for name,col in METHODS:groups.append({'period':period,'group':c,'value':str(v),'method':name,**evaluate(g.bad,g[col])})
    pd.DataFrame(bins).to_csv(folder/'branch_and_joint_calibration_bins.csv',index=False);pd.DataFrame(groups).to_csv(folder/'holdout_subgroups_by_month.csv',index=False)
    scores=pd.read_csv(folder/'prediction_metrics.csv');joint=scores[scores.target.eq('joint')]
    for _,g in joint.groupby('period'):
        assert g.n.nunique()==g.events.nunique()==g.test_row_hash.nunique()==1
    # Observe all airport groups, not just the largest residuals.
    for period,g in pd.DataFrame(groups).query("group == 'Origin'").groupby('period'):
        fig,ax=plt.subplots(figsize=(9,4))
        for method,m in g.groupby('method'):
            z=m.sort_values('value');ax.plot(z.value,z.predicted-z.observed,'o-',label=method)
        ax.axhline(0,color='k',ls='--',alpha=.3);ax.set(ylabel='Predicted - observed risk',title=f'{period}: airport residuals (all groups)');ax.legend(fontsize=8);fig.tight_layout();fig.savefig(folder/f'airport_residuals_{period}.png',dpi=140);plt.close(fig)

def render_comparison(root):
    root=Path(root);b=root/'comparison_2023/base'
    if not b.exists():return
    cov=pd.read_csv(b/'common_support_coverage.csv');fig,ax=plt.subplots(figsize=(9,4));ax.bar(cov.airport,100*cov.coverage);ax.set(ylabel='Retained records (%)',ylim=(0,105),title='2023 common support: season x time x distance; not full-population fairness');fig.tight_layout();fig.savefig(root/'common_support_coverage_2023.png',dpi=150);plt.close(fig)
    z=pd.read_csv(b/'rank_intervals.csv');z=z[z.block_days.eq(7)]
    fig,ax=plt.subplots(figsize=(10,5))
    for mode,offset in [('raw',-.16),('raw_common_support',0),('standardized',.16)]:
        g=z[z['mode'].eq(mode)].sort_values('airport');x=np.arange(len(g))+offset;ax.errorbar(x,g.rate,yerr=[g.rate-g.ci_lower,g.ci_upper-g.rate],fmt='o',capsize=2,label=mode)
    ax.set(xticks=np.arange(len(g)),xticklabels=g.airport,ylabel='Normal completion and arrival delay <15 / all scheduled',title='2023 point estimates and EXPERIMENTAL paired 7-day block intervals');ax.legend(fontsize=8);fig.tight_layout();fig.savefig(root/'comparison_estimands_2023.png',dpi=150);plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);a=p.parse_args()
    render_comparison(a.results)
    for f in a.results.glob('prediction_*'):render_prediction(f)
if __name__=='__main__':main()
