"""Reviewer regression checks; passing these does not prove empirical assumptions."""
from pathlib import Path
import sys,tempfile,json,unittest
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from comparison import block_weights,calendar_episodes,compare
from prediction import DirectJointModel,branch_targets,joint_target,features,run_prediction,evaluate
from audit import audit
from run import execute_tasks
from test_contract import example
import test_integration as integration

class ReviewRegressionTests(unittest.TestCase):
    def test_full_calendar_preserves_each_year_season_episode(self):
        dates=pd.date_range('2023-01-01','2024-03-31');w=block_weights(dates,reps=200,block=14)
        self.assertEqual(len(calendar_episodes(dates)),7)
        self.assertGreater(np.var(w),0)
        for ix in calendar_episodes(dates):np.testing.assert_array_equal(w[:,ix].sum(axis=1),len(ix))
        for months in [(12,1,2),(3,4,5),(6,7,8),(9,10,11)]:
            ix=np.flatnonzero(dates.month.isin(months));self.assertTrue((w[:,ix].sum(axis=1)>0).all())
    def test_missing_dates_never_joined(self):
        dates=pd.date_range('2023-01-01','2023-01-10').append(pd.date_range('2023-03-01','2023-03-08'))
        episodes=calendar_episodes(dates);self.assertEqual(list(map(len,episodes)),[10,8])
        w=block_weights(dates,reps=40,block=14);np.testing.assert_array_equal(w[:,:10].sum(axis=1),10);np.testing.assert_array_equal(w[:,10:].sum(axis=1),8)
    def test_empty_rare_cell_is_diagnosed_not_redrawn(self):
        df=integration.IntegrationTests().training();rare=df[df.date.eq('2023-01-01')].copy();rare['distance_bin']='rare'
        df=pd.concat([df,rare],ignore_index=True)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);r=compare(df,out,reps=100,min_known=1,blocks=(1,))
            diag=pd.read_csv(out/'bootstrap_diagnostics.csv');self.assertGreater(diag.invalid_reps.sum(),0);self.assertEqual(diag.redraws.sum(),0);self.assertEqual(diag.dropped_reps.sum(),0)
            z=pd.read_csv(out/'rank_intervals.csv');self.assertTrue(z.loc[z['mode'].eq('standardized'),'ci_lower'].isna().all());self.assertTrue(z.loc[z['mode'].eq('raw'),'ci_lower'].notna().all())
            self.assertIn('suppressed',r['status'])
    def test_invalid_date_order_rejected(self):
        with self.assertRaises(ValueError):block_weights(pd.to_datetime(['2023-01-02','2023-01-01']))
    def test_comparison_failure_does_not_block_prediction(self):
        def fail():raise RuntimeError('injected comparison failure')
        with tempfile.TemporaryDirectory() as td:
            summary={};errors=execute_tasks([('comparison',fail),('prediction',lambda:{'status':'sentinel_ran'})],summary,Path(td))
            self.assertEqual(errors,['comparison']);self.assertEqual(summary['prediction']['status'],'sentinel_ran')
    def test_prediction_requires_own_windows_not_all_36_months(self):
        df=integration.IntegrationTests().training()
        with tempfile.TemporaryDirectory() as td:
            r=run_prediction(df,Path(td));self.assertEqual(r['status'],'insufficient_period_coverage');self.assertIn('2024-04',r['missing_training_or_calibration_months']);self.assertNotIn('2025-12',r['missing_training_or_calibration_months'])
    def test_threshold_is_parameterized(self):
        df=integration.IntegrationTests().training()
        self.assertTrue((joint_target(df,15)>=joint_target(df,60)).all());self.assertTrue((branch_targets(df,15)[2]>=branch_targets(df,60)[2]).all())
    def test_direct_joint_and_empty_metrics(self):
        df=integration.IntegrationTests().training();df=df[df.state.ne('unknown')]
        m=DirectJointModel(.1,15,100).fit(df).calibrate(df)
        p=m.predict(df);self.assertTrue(np.isfinite(p).all());self.assertEqual(m.training_counts['fitted'],100);self.assertEqual(evaluate([],[])['n'],0)
    def test_2400_source_token_preserved_without_date_shift(self):
        raw=example();raw.loc[0,'CRSDepTime']=2400;x,c=audit(raw)
        self.assertTrue(x.loc[0,'scheduled_dep_2400']);self.assertEqual(x.loc[0,'dep_minutes'],0);self.assertEqual(x.loc[0,'date'],pd.Timestamp(raw.loc[0,'FlightDate']))
    def test_diversion_fields_not_normal_arrival(self):
        raw=example();raw['DivReachedDest']=np.nan;raw['DivArrDelay']=np.nan
        ix=raw.Diverted.eq(1);raw.loc[ix,'DivReachedDest']=1;raw.loc[ix,'DivArrDelay']=180
        x,c=audit(raw);self.assertEqual(c['diverted_reached_destination'],int(x.state.eq('diverted').sum()));self.assertFalse(x.loc[x.state.eq('diverted'),'completed'].any())
    def test_selection_counts_exclude_unused_categories(self):
        from case_study import airport_rationale
        df=integration.IntegrationTests().training()
        df['Reporting_Airline']=pd.Categorical(df.Reporting_Airline,categories=list(df.Reporting_Airline.unique())+['UNUSED'])
        df['Dest']=pd.Categorical(df.Dest,categories=list(df.Dest.unique())+['ZZZ'])
        with tempfile.TemporaryDirectory() as td:
            rows=airport_rationale(df,Path(td))
            for row in rows:
                sub=df[df.Origin.eq(row['airport'])]
                self.assertEqual(row['carrier_count'],sub.Reporting_Airline.nunique())
                self.assertEqual(row['destination_count'],sub.Dest.nunique())
if __name__=='__main__':unittest.main(verbosity=2)
