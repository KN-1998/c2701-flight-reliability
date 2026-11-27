"""Synthetic regression of USER-REPORTED rounded values, not the actual v5 flight.
No unknown airline/flight number/outcome is reconstructed from the report.
"""
from pathlib import Path
import json
import tempfile
import unittest
import pandas as pd
from threshold_coherence import coherence_tables, write_diagnostics

class CounterexampleDisplayTests(unittest.TestCase):
    def frames(self):
        # Every identity/outcome field below is a synthetic test fixture.
        low=pd.DataFrame(dict(flight_key=['synthetic-rounded-counterexample'],
            date=['2025-08-24'],Origin=['EWR'],Dest=['BOS'],Reporting_Airline=['SYNTHETIC'],
            state=['on_time'],completed=[True],ArrDelay=[0.],bad=[0],
            target_threshold_minutes=[15],model_p=[.1],direct_p=[.09021],baseline_p=[.09]))
        high=low.copy();high['target_threshold_minutes']=60
        high['model_p']=.09177;high['direct_p']=.08;high['baseline_p']=.07
        return low,high
    def run_output(self,a,b):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'audit'
            status=write_diagnostics(a,b,out)
            saved=json.loads((out/'threshold_coherence_status.json').read_text(encoding='utf-8'))
            self.assertEqual(status,saved)
            return status
    def test_reported_rounded_values_detect_negative_interval_mass(self):
        a,b=self.frames();s,e=coherence_tables(a,b)
        row=s.query('period=="ALL" and method=="selected_direct_low_tree_high"').iloc[0]
        self.assertEqual(row.violations,1)
        self.assertAlmostEqual(row.max_positive_excess,.00156)
        self.assertAlmostEqual(row.mean_implied_between_probability,-.00156)
        self.assertEqual(len(e),1)
    def test_gate_blocks_only_the_affected_combination(self):
        a,b=self.frames();status=self.run_output(a,b)
        gate=status['joint_display_by_method']
        self.assertEqual(gate['selected_direct_low_tree_high']['reason'],'BLOCKED_THRESHOLD_INVERSION')
        for method in ['conditional_tree','direct_joint','historical_baseline']:
            self.assertEqual(gate[method]['violations'],0)
            self.assertNotEqual(gate[method]['reason'],'BLOCKED_THRESHOLD_INVERSION')
    def test_no_inversion_does_not_authorize_joint_display(self):
        a,b=self.frames();b['model_p']=.08;status=self.run_output(a,b)
        for gate in status['joint_display_by_method'].values():
            self.assertFalse(gate['joint_display_authorized'])
            self.assertEqual(gate['reason'],'SHARED_DISTRIBUTION_AND_LATER_VALIDATION_NOT_CERTIFIED')
    def test_gate_uses_total_not_sum_of_month_and_total(self):
        a,b=self.frames();status=self.run_output(a,b)
        self.assertEqual(status['joint_display_by_method']['selected_direct_low_tree_high']['violations'],1)
        self.assertEqual(status['paired_rows'],1)
    def test_display_gate_never_rewrites_forecasts_or_marginal_scores(self):
        a,b=self.frames();old_a=a.copy(deep=True);old_b=b.copy(deep=True)
        status=self.run_output(a,b)
        pd.testing.assert_frame_equal(a,old_a);pd.testing.assert_frame_equal(b,old_b)
        self.assertFalse(status['forecasts_modified'])
        self.assertFalse(status['historical_marginal_scoring_changed'])
        self.assertFalse(status['v5_reproduced'])
    def test_sub_tolerance_difference_is_not_display_approval(self):
        a,b=self.frames();b['model_p']=a.direct_p+5e-13
        status=self.run_output(a,b)
        gate=status['joint_display_by_method']['selected_direct_low_tree_high']
        self.assertEqual(gate['violations'],0)
        self.assertFalse(gate['joint_display_authorized'])

if __name__=='__main__':unittest.main()
