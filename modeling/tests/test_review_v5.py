import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from calibration_diagnostics import saved_prediction_targets
from run_validation_v5 import summarize_holdouts
from stress import stress_tests


class ValidationV5Tests(unittest.TestCase):
    def test_carrier_scoped_event_and_origin_matching(self):
        days = pd.to_datetime(['2024-07-19','2024-07-19','2024-07-12','2024-07-12','2024-07-12'])
        sample = pd.DataFrame({
            'date':days,'Origin':['ATL','ATL','ATL','LGA','ATL'],'Dest':['DEN']*5,
            'Reporting_Airline':['DL','AA','DL','DL','AA'],'time_bin':[1]*5,'weekday':[4]*5,
            'state':['cancelled','diverted','on_time','on_time','on_time'],
            'bad':[1,1,0,0,0],'model_p':[.1]*5,'baseline_p':[.1]*5,'direct_p':[.1]*5,
            'target_threshold_minutes':[60]*5,
        })
        training = pd.DataFrame({'date':[pd.Timestamp('2023-01-01')],
                                 'state':['on_time'],'completed':[True],'ArrDelay':[0]})
        config = {'events':[{'id':'DL','reporting_airline':'DL','start':'2024-07-19','end':'2024-07-19',
                             'calendar_control_dates':['2024-07-12'],'source_id':'fixture',
                             'source_location':'fixture','definition':'fixture',
                             'matching_fields':['Origin','Dest','time_bin','weekday']}]}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            path=out/'events.json'
            path.write_text(json.dumps(config), encoding='utf-8')
            sample.to_pickle(out/'predictions.pkl')
            stress_tests(training,out,events_config=path)
            scores=pd.read_csv(out/'external_event_scores.csv')
            status=json.loads((out/'external_event_status.json').read_text())
            matched=pd.read_csv(out/'external_event_matched.csv')
            self.assertEqual(len(scores),6)
            self.assertEqual(status[0]['cancelled'],1)
            self.assertEqual(status[0]['holdout_event_rows'],1)
            self.assertEqual(status[0]['holdout_control_rows'],2)
            self.assertTrue(matched.n.eq(1).all())

    def test_baseline_conditional_risk_sets(self):
        sample=pd.DataFrame({
            'bad':[1,1,0],'model_p':[.25]*3,'target_threshold_minutes':[60]*3,
            'state':['cancelled','diverted','on_time'],'completed':[False,False,True],
            'ArrDelay':[None,None,0],'baseline_cancel_p':[.1]*3,
            'baseline_divert_given_not_cancel_p':[.02]*3,
            'baseline_long_given_completed_p':[.08]*3,
        })
        targets={target:(y.tolist(),p.tolist()) for method,target,y,p in saved_prediction_targets(sample)
                 if method=='historical_baseline'}
        self.assertEqual(targets['cancel'],([True,False,False],[.1]*3))
        self.assertEqual(targets['divert_given_not_cancel'],([True,False],[.02]*2))
        self.assertEqual(targets['long_given_completed'],([False],[.08]))

    def test_unseen_periods_and_late_period_are_scored_separately(self):
        protocol={'new_core_months':['2025-02','2025-03'],
                  'previously_scored_months':['2025-01'],'late_months':['2026-09']}
        rows=[]
        for month in protocol['new_core_months']+protocol['late_months']:
            for method,brier in [('historical_baseline',.2),('conditional_tree',.1),('direct_joint',.3)]:
                if month=='2026-09' and method=='conditional_tree':
                    brier=.8
                rows.append(dict(period=month,method=method,target='joint',threshold_minutes=60,n=100,
                                 events=5,test_row_hash=month,brier=brier,log_loss=.5,predicted=.1))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            scores=pd.DataFrame(rows)
            self.assertEqual(summarize_holdouts(scores,protocol,out)['selection'],'conditional_tree')
            partial=scores.loc[scores.period.ne('2025-03')]
            self.assertEqual(summarize_holdouts(partial,protocol,out)['selection'],'historical_baseline')


if __name__=='__main__':
    unittest.main()
