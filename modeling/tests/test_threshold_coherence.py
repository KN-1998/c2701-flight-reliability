"""Program contracts for the follow-up audit, NOT the reported v5 41-test suite."""
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from threshold_coherence import coherence_tables, write_diagnostics
from reproduce_threshold_followup import attach_verified_keys

class ThresholdCoherenceTests(unittest.TestCase):
    def frames(self):
        base = pd.DataFrame(dict(flight_key=['a','b','c','d','e'],date=['2025-01-01']*3+['2025-02-01']*2,
            Origin=['EWR']*5,Dest=['DEN']*5,Reporting_Airline=['UA']*5,
            state=['cancelled','diverted','late','late','on_time'],completed=[False,False,True,True,True],
            ArrDelay=[np.nan,np.nan,15.,60.,-2.],bad=[1,1,1,1,0],target_threshold_minutes=[15]*5,
            model_p=[.4]*5,direct_p=[.35]*5,baseline_p=[.3]*5))
        high=base.copy();high['target_threshold_minutes']=60;high['bad']=[1,1,0,1,0]
        high['model_p']=.2;high['direct_p']=.18;high['baseline_p']=.1
        return base,high
    def test_nested_events_and_counts(self):
        a,b=self.frames();s,e=coherence_tables(a,b);z=s.query('period=="ALL"')
        self.assertEqual(len(s),12);self.assertTrue(z.violations.eq(0).all());self.assertTrue(e.empty)
        self.assertTrue(z.observed_low_events.eq(4).all());self.assertTrue(z.observed_high_events.eq(3).all())
        self.assertTrue(z.observed_between_events.eq(1).all())
    def test_align_by_key_not_order(self):
        a,b=self.frames();s,_=coherence_tables(a,b);q,_=coherence_tables(a,b.iloc[::-1]);pd.testing.assert_frame_equal(s,q)
    def test_each_method_and_mixed_violation(self):
        a,b=self.frames();b.loc[0,'model_p']=.8;b.loc[1,'direct_p']=.9;b.loc[2,'baseline_p']=.7
        s,e=coherence_tables(a,b);z=s.query('period=="ALL"').set_index('method')
        for method in ['conditional_tree','direct_joint','historical_baseline','selected_direct_low_tree_high']:
            self.assertEqual(z.loc[method,'violations'],1)
        self.assertEqual(len(e),4);self.assertAlmostEqual(z.loc['conditional_tree','max_positive_excess'],.4)
    def test_duplicate_missing_and_empty_keys_fail(self):
        a,b=self.frames()
        for value in ['a',None,' ',1]:
            q=b.copy();q['flight_key']=q.flight_key.astype(object);q.loc[1,'flight_key']=value
            with self.subTest(key=value),self.assertRaises(ValueError):coherence_tables(a,q)
    def test_key_sets_must_match_without_dropping(self):
        a,b=self.frames()
        with self.assertRaises(ValueError):coherence_tables(a,b.iloc[:-1])
        b.loc[0,'flight_key']='other'
        with self.assertRaises(ValueError):coherence_tables(a,b)
    def test_changed_metadata_fail(self):
        a,b=self.frames()
        for col,val in [('date','2025-01-02'),('Origin','LGA'),('Dest','SEA'),('Reporting_Airline','DL'),('ArrDelay',25.)]:
            q=b.copy();q.loc[2,col]=val
            with self.subTest(column=col),self.assertRaises(ValueError):coherence_tables(a,q)
    def test_threshold_and_label_contracts(self):
        a,b=self.frames();q=b.copy();q['target_threshold_minutes']=15
        with self.assertRaises(ValueError):coherence_tables(a,q)
        q=b.copy();q.loc[2,'bad']=1
        with self.assertRaises(ValueError):coherence_tables(a,q)
        for lo,hi,tol in [(60,15,1e-12),(0,60,1e-12),(15.5,60,1e-12),(15,60,-1),(15,60,np.nan)]:
            with self.subTest(lower=lo,upper=hi,tol=tol),self.assertRaises(ValueError):coherence_tables(a,b,lower=lo,upper=hi,atol=tol)
    def test_invalid_probability_and_unknown_fail(self):
        a,b=self.frames()
        for col,val in [('direct_p',np.nan),('baseline_p',1.01),('model_p',-.1),('state','unknown')]:
            q=b.copy();q.loc[0,col]=val
            with self.subTest(column=col),self.assertRaises(ValueError):coherence_tables(a,q)
    def test_missing_method_or_metadata_fail(self):
        a,b=self.frames()
        for col in ['flight_key','direct_p','Origin']:
            with self.subTest(column=col),self.assertRaises(ValueError):coherence_tables(a,b.drop(columns=col))
    def test_tolerance_does_not_change_forecasts(self):
        a,b=self.frames();b['model_p']=a.model_p+5e-13;original=b.copy(deep=True)
        s,_=coherence_tables(a,b);q,_=coherence_tables(a,b,atol=0)
        self.assertEqual(s.query('period=="ALL" and method=="conditional_tree"').violations.iloc[0],0)
        self.assertEqual(q.query('period=="ALL" and method=="conditional_tree"').violations.iloc[0],5)
        pd.testing.assert_frame_equal(b,original)
    def test_fresh_output_and_failed_validation(self):
        a,b=self.frames()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'new';r=write_diagnostics(a,b,out)
            self.assertFalse(r['v5_reproduced']);self.assertFalse(r['forecasts_modified'])
            self.assertEqual(json.loads((out/'threshold_coherence_status.json').read_text())['paired_rows'],5)
            with self.assertRaises(ValueError):write_diagnostics(a,b,out)
            bad=Path(td)/'bad'
            with self.assertRaises(ValueError):write_diagnostics(a,b.iloc[:-1],bad)
            self.assertFalse(bad.exists())
    def test_csv_roundtrip(self):
        a,b=self.frames()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);a.to_csv(p/'a.csv',index=False);b.to_csv(p/'b.csv',index=False)
            s,e=coherence_tables(pd.read_csv(p/'a.csv'),pd.read_csv(p/'b.csv'))
            self.assertEqual(s.query('period=="ALL"').n.tolist(),[5]*4)


class LegacyPairingTests(unittest.TestCase):
    frames = ThresholdCoherenceTests.frames
    def source_fixture(self):
        pred,_=self.frames();pred['date']=pd.to_datetime(pred.date)
        pred['time_bin']=2;pred['quarter']=1;pred['weekday']=2
        raw=pred.copy();raw['Flight_Number_Reporting_Airline']=range(100,105)
        raw['dep_minutes']=600.;raw['scheduled_dep_2400']=False
        months=[]
        for period,sub in raw.groupby(raw.date.dt.strftime('%Y-%m')):
            digest=hashlib.sha256(pd.util.hash_pandas_object(sub[['date','Origin','Dest','Reporting_Airline','dep_minutes']],index=True).values.tobytes()).hexdigest()
            months.append(dict(period=period,n=len(sub),row_hash=digest))
        return pred,raw,dict(status='fitted',threshold_minutes=15,holdout_months=months)
    def test_adapter_preserves_verified_identity(self):
        x,raw,status=self.source_fixture();a,p=attach_verified_keys(x,status,raw);b,q=attach_verified_keys(x,status,raw)
        self.assertEqual(p,q);self.assertTrue(a.flight_key.is_unique);self.assertEqual(a.flight_key.tolist(),b.flight_key.tolist())
    def test_adapter_bad_fingerprint_and_count_fail(self):
        x,raw,status=self.source_fixture();bad=raw.copy();bad['dep_minutes']+=1
        with self.assertRaises(ValueError):attach_verified_keys(x,status,bad)
        status['holdout_months'][0]['n']+=1
        with self.assertRaises(ValueError):attach_verified_keys(x,status,raw)
    def test_adapter_prediction_order_not_guessed(self):
        x,raw,status=self.source_fixture()
        with self.assertRaises(ValueError):attach_verified_keys(x.iloc[::-1],status,raw)
    def test_adapter_duplicate_identity_fail(self):
        x,raw,status=self.source_fixture();raw.loc[1,'Flight_Number_Reporting_Airline']=raw.loc[0,'Flight_Number_Reporting_Airline']
        with self.assertRaises(ValueError):attach_verified_keys(x,status,raw)
    def test_adapter_threshold_and_prediction_count_fail(self):
        x,raw,status=self.source_fixture();bad=x.copy();bad['target_threshold_minutes']=60
        with self.assertRaises(ValueError):attach_verified_keys(bad,status,raw)
        with self.assertRaises(ValueError):attach_verified_keys(x.iloc[:-1],status,raw)
    def test_adapter_empty_or_duplicate_period_fail(self):
        x,raw,status=self.source_fixture();status['holdout_months'].append(status['holdout_months'][0].copy())
        with self.assertRaises(ValueError):attach_verified_keys(x,status,raw)
        status['holdout_months']=[]
        with self.assertRaises(ValueError):attach_verified_keys(x,status,raw)
    def test_adapter_missing_identity_fail(self):
        x,raw,status=self.source_fixture()
        with self.assertRaises(ValueError):attach_verified_keys(x,status,raw.drop(columns='Flight_Number_Reporting_Airline'))

if __name__ == '__main__':unittest.main()
