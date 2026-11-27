import tempfile,unittest,subprocess,sys,os
from pathlib import Path
import numpy as np
import pandas as pd
from calibration_diagnostics import diagnostics,analyze_saved
from mc_diagnostics import quantile_changes,write_changes

class ReviewV4Tests(unittest.TestCase):
    def test_empty_and_invalid(self):
        self.assertEqual(diagnostics([],[])[2]['status'],'EMPTY_RISK_SET')
        for y,p in [([1],[1.01]),([.2],[.1]),([1],[np.nan]),([1,0],[.1])]:
            with self.assertRaises(ValueError):diagnostics(y,p)
    def test_bin_boundaries_and_event_counts(self):
        y=[0,1,0,1,0,1];p=[0,.001,.01,.1,.9,1]
        b,c,s=diagnostics(y,p)
        for scheme in ['coarse_10','fine_low_risk','quantile_ties_kept']:
            z=pd.DataFrame(b);z=z[z.scheme.eq(scheme)];self.assertEqual(z.n.sum(),6);self.assertEqual(z.events.sum(),3)
        fine=pd.DataFrame(b);fine=fine[fine.scheme.eq('fine_low_risk')];self.assertEqual(fine.iloc[-1].n,2)
        self.assertLess(abs(s['identity_residual']),1e-14)
    def test_pav_ties_not_split_or_used_as_forecast(self):
        b,c,s=diagnostics([1,0,1,0],[.02,.02,.02,.02]);self.assertEqual(len(c),1);self.assertEqual(c[0]['cep'],.5)
        z=pd.DataFrame(b);self.assertEqual(z[z.scheme.eq('quantile_ties_kept')].query('n>0').shape[0],1)
        self.assertGreaterEqual(s['MCB'],-1e-14);self.assertGreaterEqual(s['DSC'],-1e-14)
        self.assertIn('NOT a new forecast',s['reuse_warning'])
    def test_pav_reference_and_monotonicity(self):
        b,c,s=diagnostics([0,1,0,1],[.1,.2,.3,.9]);np.testing.assert_allclose([v['cep'] for v in c],[0,.5,.5,1]);self.assertTrue(np.diff([v['cep'] for v in c]).min()>=0)
    def test_zero_events_not_dropped(self):
        b,c,s=diagnostics(np.zeros(12),np.linspace(0,.02,12));self.assertEqual(s['events'],0);self.assertEqual(s['UNC'],0);self.assertEqual(s['pav_plateaus'],1)
    def frames(self):
        a=pd.DataFrame([dict(a='A',b='B',mode='raw',threshold_minutes=60,block_days=7,ci_lower=-.01,ci_upper=.02)])
        b=a.copy();b['ci_lower']=.001;return a,b
    def test_mc_pairing_and_classification(self):
        a,b=self.frames();z=quantile_changes(a,b);self.assertTrue(z.classification_changed.iloc[0]);self.assertAlmostEqual(z.lower_quantile_change.iloc[0],.011)
        with tempfile.TemporaryDirectory() as td:
            a.to_csv(Path(td)/'a.csv',index=False);b.to_csv(Path(td)/'b.csv',index=False);self.assertEqual(write_changes(Path(td)/'a.csv',Path(td)/'b.csv',Path(td)/'out.csv')['rows'],1)
    def test_mc_duplicate_and_mismatched_keys_fail(self):
        a,b=self.frames()
        with self.assertRaises(ValueError):quantile_changes(pd.concat([a,a]),b)
        b['b']='C'
        with self.assertRaises(ValueError):quantile_changes(a,b)
    def test_mc_suppression_not_called_zero_crossing(self):
        a,b=self.frames();a[['ci_lower','ci_upper']]=np.nan;z=quantile_changes(a,b);self.assertEqual(z.class_1000_s2701.iloc[0],'SUPPRESSED')
        a['ci_lower']=0
        with self.assertRaises(ValueError):quantile_changes(a,b)
    def prediction_fixture(self):
        x=pd.DataFrame({'date':['2025-01-01']*4,'state':['cancelled','diverted','late','on_time'],
                        'completed':[False,False,True,True],'bad':[1,1,1,0],
                        'ArrDelay':[np.nan,np.nan,65.,-2.],'target_threshold_minutes':[60]*4,
                        'cancel_p':[.1]*4,'diversion_p':[.09]*4,'long_p':[.162]*4,
                        'model_p':[.352]*4,'baseline_p':[.3]*4,'direct_p':[.32]*4})
        return x
    def test_saved_risk_sets_integration(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'output';status=analyze_saved(self.prediction_fixture(),out)
            self.assertFalse(status['pav_used_for_forecasts'])
            z=pd.read_csv(out/'calibration_summary_v4.csv').set_index(['method','target'])
            for target,n,events in [('joint',4,3),('cancel',4,1),('diversion_marginal',4,1),('divert_given_not_cancel',3,1),('long_given_completed',2,1)]:
                row=z.loc[('conditional_tree',target)];self.assertEqual(row.n,n);self.assertEqual(row.events,events)
    def test_saved_input_contract(self):
        base=self.prediction_fixture();cases=[]
        cases.append(base.drop(columns='date'));cases.append(base.iloc[:0])
        for col,val in [('state','unknown'),('completed',True),('bad',0),('date',None),('target_threshold_minutes',15),('model_p',.8)]:
            x=base.copy();x.loc[0,col]=val;cases.append(x)
        x=base.copy();x.loc[2,'ArrDelay']=np.nan;cases.append(x)
        cases.append(base.drop(columns='cancel_p'))
        with tempfile.TemporaryDirectory() as td:
            for i,x in enumerate(cases):
                with self.subTest(case=i):
                    out=Path(td)/str(i)
                    with self.assertRaises(ValueError):analyze_saved(x,out)
                    self.assertFalse(out.exists())
    def test_saved_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'preserve.txt';f.write_text('original')
            with self.assertRaises(ValueError):analyze_saved(self.prediction_fixture(),td)
            with self.assertRaises(ValueError):write_changes(Path(td)/'missing_a.csv',Path(td)/'missing_b.csv',f)
            self.assertEqual(f.read_text(),'original');self.assertEqual(len(list(Path(td).iterdir())),1)
    def test_probability_mass_and_branch_prerequisites(self):
        base=self.prediction_fixture()
        for x in [base.assign(diversion_p=.95),base.assign(cancel_p=np.inf),base.drop(columns='diversion_p')]:
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(ValueError):analyze_saved(x,Path(td)/'output')
    def test_mc_invalid_repetition_fails_before_output(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'must_not_be_created'
            script=Path(__file__).resolve().parents[1]/'src/reproduce_review_v3.py'
            result=subprocess.run([sys.executable,str(script),'--out',str(out),'--mc-check','--reps','20'],capture_output=True,text=True,encoding="utf-8",env={**os.environ,"PYTHONIOENCODING":"utf-8"},timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('--mc-check requires --reps 1000',result.stderr)
            self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
