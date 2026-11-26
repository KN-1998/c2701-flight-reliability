from pathlib import Path
import tempfile,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
import pandas as pd
from audit import audit,metrics
from comparison import compare,block_weights
from prediction import features,SequentialModel,HistoricalBaseline,combine,evaluate
from test_contract import example


class IntegrationTests(unittest.TestCase):
    def training(self):
        pieces=[]
        for day in range(1,21):
            for airport in ['ATL','ORD']:
                x=example().iloc[:7].copy()
                x['Origin']=airport;x['FlightDate']=f'2023-01-{day:02d}'
                x['Flight_Number_Reporting_Airline']+=day*20
                pieces.append(x)
        return audit(pd.concat(pieces,ignore_index=True))[0]
    def test_prediction_smoke(self):
        df=self.training();known=df[df.state.ne('unknown')]
        train=known[known.date.dt.day.le(10)]
        cal=known[known.date.dt.day.between(11,15)]
        test=known[known.date.dt.day.gt(15)]
        model=SequentialModel(C=.1).fit(train).calibrate(cal)
        q=model.predict(test);p=1-combine(q)[:,3]
        self.assertTrue(np.isfinite(p).all())
        self.assertTrue(((p>=0)&(p<=1)).all())
        scores=evaluate(test.bad,p)
        self.assertEqual(scores['n'],len(test))
        base=HistoricalBaseline().fit(train).predict(test)
        self.assertEqual(base.shape,q.shape)
        forbidden={'ArrDelay','ArrTime','DepDelay','DepTime','Cancelled','Diverted','state','bad','completed'}
        self.assertFalse(set(features(test).columns)&forbidden)
    def test_comparison_smoke(self):
        df=self.training()
        with tempfile.TemporaryDirectory() as td:
            output=compare(df,Path(td),reps=30)
            self.assertEqual(output['status'],'computed')
            table=pd.read_csv(Path(td)/'rank_intervals.csv')
            self.assertTrue((table.ci_lower<=table.ci_upper).all())
            self.assertTrue((table.common_support_coverage==1).all())
            decomposition=pd.read_csv(Path(td)/'mix_decomposition.csv')
            self.assertTrue((decomposition.identity_residual.abs()<1e-12).all())
            self.assertTrue((decomposition.support_restriction_component.abs()<1e-12).all())
    def test_block_resampling(self):
        dates=pd.date_range('2023-01-01',periods=31)
        a=block_weights(dates,reps=30,block=7)
        b=block_weights(dates,reps=30,block=7)
        np.testing.assert_array_equal(a,b)
        np.testing.assert_array_equal(a.sum(axis=1),31)
    def test_threshold_monotonicity(self):
        df=self.training();row=metrics(df).iloc[0]
        xs=[row[f'reliability_{t}_lower'] for t in [0,15,30,60,120]]
        self.assertTrue(all(x<=y for x,y in zip(xs,xs[1:])))
        for t in [0,15,30,60,120]:
            self.assertLessEqual(row[f'reliability_{t}_lower'],row[f'reliability_{t}_upper'])

    def test_stress_smoke(self):
        from stress import stress_tests
        df=self.training()
        parts=[]
        for date in pd.date_range('2024-07-19','2024-07-25').append(pd.date_range('2025-01-01','2025-01-20')):
            part=df[df.date.eq('2023-01-01') & df.state.ne('unknown')].copy()
            part['date']=date
            part['quarter']=date.quarter
            part['model_p']=.25;part['baseline_p']=.24
            part['cancel_p']=.05;part['diversion_p']=.0095;part['long_p']=.1881
            parts.append(part)
        pred=pd.concat(parts,ignore_index=True)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);pred.to_pickle(out/'predictions.pkl')
            gated=stress_tests(df,out)
            self.assertEqual(gated['status'],'historical_diagnostics_only')
            self.assertFalse((out/'scenarios_2027_assumed.csv').exists())
            result=stress_tests(df,out,allow_unverified_scenarios=True)
            self.assertEqual(result['status'],'computed')
            scenarios=pd.read_csv(out/'scenarios_2027_assumed.csv')
            self.assertTrue(scenarios.evidence.str.contains('ASSUMED_STRESS').all())
            for _,g in scenarios.groupby(['airport','scenario']):
                risks=g.sort_values('odds_multiplier').mean_bad_risk.to_numpy()
                self.assertTrue((np.diff(risks)>=0).all())

if __name__=='__main__':unittest.main(verbosity=2)

