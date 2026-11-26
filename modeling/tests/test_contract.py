from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from audit import audit,metrics,valid_hhmm


def example():
    n=9
    return pd.DataFrame(dict(FlightDate=['2025-01-01']*n,Reporting_Airline=['XX']*n,
        Flight_Number_Reporting_Airline=list(range(n)),Origin=['ATL']*n,Dest=['ORD']*n,
        CRSDepTime=[900]*n,CRSArrTime=[1100]*n,ArrTime=[1100,1114,1115,1200,np.nan,np.nan,np.nan,1200,1100],
        ArrDelay=[0,14,15,60,np.nan,np.nan,np.nan,60,0],
        Cancelled=[0,0,0,0,1,0,0,1,1],Diverted=[0,0,0,0,0,1,0,1,0],
        CancellationCode=[None]*n,Distance=[500]*n,CRSElapsedTime=[120]*n))


class ContractTests(unittest.TestCase):
    def test_boundary_and_partition(self):
        df,a=audit(example())
        self.assertEqual(list(df.state),['on_time','on_time','late','late','cancelled','diverted','unknown','unknown','unknown'])
        self.assertEqual(a['retained_rows'],9)
        self.assertEqual(sum(a[s] for s in ['on_time','late','cancelled','diverted','unknown']),9)
        m=metrics(df).iloc[0]
        self.assertAlmostEqual(m.reliability_15_lower,2/9)
        self.assertAlmostEqual(m.reliability_15_upper,5/9)
        self.assertAlmostEqual(m.conditional_long_delay,1/4)
    def test_hhmm(self):
        self.assertEqual(list(valid_hhmm(pd.Series([0,59,100,2359,2400,1260,2401,-1,np.nan,1230.5]))),[True]*5+[False]*5)
    def test_duplicates(self):
        x=example()
        df,a=audit(pd.concat([x,x.iloc[[0]]],ignore_index=True))
        self.assertEqual(a['exact_duplicates_removed'],1)
        self.assertEqual(len(df),9)
        y=x.iloc[[0]].copy(); y['ArrDelay']=10
        df,a=audit(pd.concat([x,y],ignore_index=True))
        self.assertEqual(a['conflicting_key_rows'],2)
        self.assertTrue(df.iloc[[0,-1]].state.eq('unknown').all())
    def test_no_completed(self):
        df,a=audit(example().iloc[[4,5]])
        m=metrics(df).iloc[0]
        self.assertTrue(np.isnan(m.conditional_on_time))
        self.assertEqual(m.reliability_15_lower,0)
    def test_probability_chain(self):
        from prediction import combine
        rng=np.random.default_rng(2026)
        for _ in range(100):
            q=rng.uniform(size=(20,3)); out=combine(q)
            np.testing.assert_allclose(out.sum(axis=1),1,atol=1e-12)
            self.assertTrue(((out>=0)&(out<=1)).all())
        np.testing.assert_allclose(combine(np.zeros((1,3))),[[0,0,0,1]])
        np.testing.assert_allclose(combine(np.ones((1,3))),[[1,0,0,0]])

if __name__=='__main__':
    unittest.main(verbosity=2)
