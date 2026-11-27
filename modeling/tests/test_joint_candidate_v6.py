import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from joint_candidate_v6 import BRANCHES, LEAVES, observed_leaves, path_probabilities, run_joint_candidate


def flights(period):
    date = pd.Timestamp(f'{period}-01')
    delays = [np.nan, np.nan, -1, 14.999, 15, 59.999, 60, 75]
    return pd.DataFrame({
        'date': [date] * 8, 'FlightDate': [date.date().isoformat()] * 8,
        'Origin': ['LGA'] * 8, 'Dest': ['DEN'] * 8, 'Reporting_Airline': ['UA'] * 8,
        'Flight_Number_Reporting_Airline': list(range(1001, 1009)),
        'CRSDepTime': list(range(1010, 1018)),
        'month': [date.month] * 8, 'weekday': [date.dayofweek] * 8, 'time_bin': [1] * 8,
        'dep_minutes': list(range(610, 618)), 'arr_minutes': list(range(830, 838)),
        'Distance': [1600.] * 8, 'CRSElapsedTime': [220.] * 8,
        'completed': [False, False] + [True] * 6, 'ArrDelay': delays,
        'state': ['cancelled', 'diverted', 'on_time', 'on_time'] + ['late'] * 4,
    })


class SharedFiveLeafTests(unittest.TestCase):
    def test_composition_endpoints_and_nested_probabilities(self):
        q = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1], [0, 0, 0, 0],
                      [.2, .1, .25, .4]])
        leaves, p15, p60 = path_probabilities(q)
        np.testing.assert_array_equal(leaves[:5], np.eye(5))
        np.testing.assert_allclose(leaves[-1], [.2, .08, .18, .216, .324])
        self.assertTrue((p60 <= p15).all())
        np.testing.assert_allclose(leaves.sum(axis=1), 1.)
        np.testing.assert_allclose(p15, leaves[:, :4].sum(axis=1))
        np.testing.assert_allclose(p60, leaves[:, :3].sum(axis=1))
        with self.assertRaises(ValueError):
            path_probabilities([[0, 0, np.nan, 0]])

    def test_observed_boundaries(self):
        observed = observed_leaves(flights('2024-01'))
        np.testing.assert_array_equal(observed.sum(axis=1), 1)
        np.testing.assert_array_equal(observed.argmax(axis=1), [0, 1, 4, 4, 3, 3, 2, 2])

    def test_candidate_uses_both_thresholds_and_exact_risk_sets(self):
        periods = ['2023-12', '2024-01', '2024-02', '2024-03', '2024-04', '2024-05']
        frame = pd.concat([flights(month) for month in periods], ignore_index=True)
        protocol = {
            'fit_start': '2024-01-01', 'fit_end': '2024-01-31',
            'tune_months': ['2024-02'], 'refit_end': '2024-02-29',
            'calibration_months': ['2024-03'], 'previously_scored_months': ['2024-04'],
            'new_core_months': [], 'late_months': ['2024-05'],
            'thresholds_minutes': [15, 60], 'fit_cap': 1000, 'seed': 7, 'C_grid': [.1, 1],
            'baseline_strength': 20,
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'candidate'
            metrics = run_joint_candidate(frame, protocol, out)
            self.assertFalse(metrics['actual_flight_prediction_authorized'])
            self.assertEqual(metrics['seed'], 7)
            self.assertEqual(metrics['threshold_violations'], 0)
            self.assertEqual(metrics['holdout_row_count'], 16)
            risk = pd.read_csv(out / 'candidate_risk_sets.csv')
            self.assertEqual(list(risk.branch), list(BRANCHES))
            self.assertEqual(list(risk.training_n), [16, 14, 12, 8])
            self.assertEqual(list(risk.training_events), [2, 2, 4, 4])
            self.assertEqual(list(risk.calibration_n), [8, 7, 6, 4])
            self.assertEqual(list(risk.calibration_events), [1, 1, 2, 2])
            scored = pd.read_csv(out / 'candidate_joint_monthly.csv')
            self.assertEqual(scored.events.tolist(), [6, 4, 6, 4])
            self.assertEqual(scored.n.tolist(), [8, 8, 8, 8])
            self.assertEqual(list(scored.threshold_minutes), [15, 60, 15, 60])
            self.assertTrue(scored.groupby('period').test_row_hash.nunique().eq(1).all())
            sample = pd.read_csv(out / 'candidate_probability_examples.csv')
            np.testing.assert_allclose(sample[list(LEAVES)].sum(axis=1), 1.)
            self.assertEqual(sample.Flight_Number_Reporting_Airline.tolist(), [1001, 1001])
            self.assertLessEqual(json.loads((out / 'candidate_status.json').read_text())['max_leaf_sum_error'], 1e-12)
            with self.assertRaisesRegex(ValueError, 'fresh output'):
                run_joint_candidate(frame, protocol, out)
            with self.assertRaisesRegex(ValueError, 'Missing five-leaf'):
                run_joint_candidate(frame.loc[frame.date.dt.month.ne(5)], protocol, Path(tmp) / 'missing')
            self.assertFalse((Path(tmp) / 'missing').exists())


if __name__ == '__main__':
    unittest.main()
