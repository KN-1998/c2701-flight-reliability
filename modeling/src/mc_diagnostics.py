"""Pair Monte-Carlo interval runs; precision/sensitivity check, NOT a coverage proof."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
KEYS=['a','b','mode','threshold_minutes','block_days']
REQUIRED=KEYS+['ci_lower','ci_upper']

def quantile_changes(first,second):
    for label,frame in [('first',first),('second',second)]:
        if not set(REQUIRED)<=set(frame):raise ValueError(label+': missing columns')
        if frame[KEYS].isna().any().any() or frame.duplicated(KEYS).any():raise ValueError(label+': duplicate or missing keys')
        if np.isinf(frame[['ci_lower','ci_upper']].to_numpy(dtype=float)).any():raise ValueError(label+': infinite interval')
        present=frame[['ci_lower','ci_upper']].notna()
        if (present.ci_lower!=present.ci_upper).any():raise ValueError(label+': half-missing interval')
        if (frame.ci_lower>frame.ci_upper).any():raise ValueError(label+': reversed interval')
    z=first[REQUIRED].merge(second[REQUIRED],on=KEYS,how='outer',validate='one_to_one',indicator=True,suffixes=('_1000_s2701','_2000_s2702'))
    if not z['_merge'].eq('both').all():raise ValueError('Different comparison keys; no silent row loss allowed')
    z=z.drop(columns='_merge');z['lower_quantile_change']=z.ci_lower_2000_s2702-z.ci_lower_1000_s2701;z['upper_quantile_change']=z.ci_upper_2000_s2702-z.ci_upper_1000_s2701
    def classification(lo,hi):
        return np.where(lo.isna()|hi.isna(),'SUPPRESSED',np.where(lo>0,'POSITIVE',np.where(hi<0,'NEGATIVE','CROSSES_OR_TOUCHES_ZERO')))
    z['class_1000_s2701']=classification(z.ci_lower_1000_s2701,z.ci_upper_1000_s2701)
    z['class_2000_s2702']=classification(z.ci_lower_2000_s2702,z.ci_upper_2000_s2702)
    z['classification_changed']=z.class_1000_s2701.ne(z.class_2000_s2702)
    return z.sort_values(KEYS).reset_index(drop=True)

def write_changes(first,second,out):
    out=Path(out)
    if out.exists():raise ValueError('Fresh MC output file required')
    z=quantile_changes(pd.read_csv(first),pd.read_csv(second));out.parent.mkdir(parents=True,exist_ok=True);z.to_csv(out,index=False)
    return {'rows':len(z),'classification_changes':int(z.classification_changed.sum()),'interpretation':'Monte Carlo and seed sensitivity only; not interval validity or model improvement'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('first',type=Path);p.add_argument('second',type=Path);p.add_argument('out',type=Path);a=p.parse_args();print(write_changes(a.first,a.second,a.out))
if __name__=='__main__':main()
