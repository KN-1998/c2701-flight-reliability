"""Regression coverage for pooled streaming diagnostics in the delivery entry point."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from run_delivery_v6 import audit_threshold_pairs
from threshold_coherence import coherence_tables


def inputs():
    dates = pd.to_datetime(['2025-01-15'] * 8 + ['2025-02-14'] * 3)
    low = pd.DataFrame({
        'date': dates, 'flight_key': [f'key{i}' for i in range(len(dates))],
        'Origin': 'EWR', 'Dest': 'DEN', 'Reporting_Airline': 'UA',
        'state': 'late', 'completed': True, 'ArrDelay': 45,
        'bad': 1, 'target_threshold_minutes': 15,
        'model_p': .4, 'direct_p': .25, 'baseline_p': .3,
    })
    high = low.assign(bad=0, target_threshold_minutes=60, baseline_p=.2)
    high = high.assign(model_p=[.6] * 8 + [.5, .15, .1])
    return low, high


class DeliveryThresholdTests(unittest.TestCase):
    def test_partitioned_recheck_matches_full_reference_and_retains_all_inversions(self):
        low, high = inputs()
        expected, examples = coherence_tables(low, high, example_limit=None)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            a, b, out = root/'low.pkl', root/'high.pkl', root/'result'
            low.to_pickle(a)
            high.iloc[::-1].to_pickle(b)
            status = audit_threshold_pairs(a, b, out)
            actual = pd.read_csv(out/'threshold_coherence.csv').sort_values(['method','period'])
            expected = expected.sort_values(['method','period'])
            pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected.reset_index(drop=True))
            actual_examples = pd.read_csv(out/'threshold_coherence_examples.csv')
            self.assertEqual(len(actual_examples), len(examples))
            self.assertEqual(status['paired_rows'], len(low))
            self.assertEqual(status['months'], 2)
            self.assertTrue(status['inversions_are_exhaustive'])
            self.assertEqual(status['joint_display_by_method']['selected_direct_low_tree_high']['violations'], 9)

    def test_rejects_missing_month_without_creating_outputs(self):
        low, high = inputs()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            a, b, out = root/'low.pkl', root/'high.pkl', root/'result'
            low.to_pickle(a)
            high.iloc[:8].to_pickle(b)
            with self.assertRaisesRegex(ValueError, 'same nonempty set of months'):
                audit_threshold_pairs(a, b, out)
            self.assertFalse(out.exists())

