"""Exercise the evidence review against inconsistent saved inversion inventories."""
from pathlib import Path
import json
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from review_v6_evidence import ROOT, inspect_evidence
from threshold_coherence import DEFAULT_ATOL

SAVED = ROOT / 'results/implementation_v6'
SUMMARY = Path('threshold_coherence/threshold_coherence.csv')
DETAIL = Path('threshold_coherence/threshold_coherence_examples.csv')
PAIRING_STATUS = Path('threshold_coherence/threshold_coherence_status.json')


class InversionInventoryTests(unittest.TestCase):
    def copy_results(self, temporary_directory):
        results = Path(temporary_directory) / 'results'
        shutil.copytree(SAVED, results)
        return results

    def test_same_flight_can_have_inversions_in_multiple_methods(self):
        report = inspect_evidence(SAVED)
        records = pd.DataFrame(report['inversion_records'])
        self.assertFalse(records.duplicated(['method', 'flight_key']).any())
        methods_per_flight = records.groupby('flight_key')['method'].nunique()
        self.assertGreater(methods_per_flight.max(), 1)
        self.assertEqual(
            report['inversions_by_method'],
            {
                'conditional_tree': 1,
                'direct_joint': 2,
                'historical_baseline': 0,
                'selected_direct_low_tree_high': 1,
            },
        )

    def test_accept_empty_inventory_including_below_tolerance_margin(self):
        with TemporaryDirectory() as temp:
            results = self.copy_results(temp)
            summary = pd.read_csv(results / SUMMARY)
            summary[['violations', 'violation_rate', 'max_upper_minus_lower', 'max_positive_excess']] = 0
            below_tolerance = summary.period.isin(['2025-08', 'ALL']) & summary.method.eq('direct_joint')
            summary = summary.astype({'max_upper_minus_lower': float, 'max_positive_excess': float})
            summary.loc[below_tolerance, ['max_upper_minus_lower', 'max_positive_excess']] = DEFAULT_ATOL / 2
            summary.to_csv(results / SUMMARY, index=False)
            pd.read_csv(results / DETAIL).iloc[:0].to_csv(results / DETAIL, index=False)

            pairing_path = results / PAIRING_STATUS
            pairing = json.loads(pairing_path.read_text(encoding='utf-8'))
            for gate in pairing['joint_display_by_method'].values():
                gate.update(violations=0, nested_threshold_check='NO_VIOLATIONS_ABOVE_TOLERANCE',
                            joint_display_authorized=False,
                            reason='SHARED_DISTRIBUTION_AND_LATER_VALIDATION_NOT_CERTIFIED')
            pairing_path.write_text(json.dumps(pairing), encoding='utf-8')
            delivery_path = results / 'delivery_status.json'
            delivery = json.loads(delivery_path.read_text(encoding='utf-8'))
            delivery['paired_thresholds'] = pairing
            delivery_path.write_text(json.dumps(delivery), encoding='utf-8')

            report = inspect_evidence(results)
            self.assertEqual(report['inversion_records'], [])
            self.assertEqual(report['inversions_by_method'], dict.fromkeys(pairing['joint_display_by_method'], 0))

    def test_reject_same_method_and_flight_duplicate_with_unchanged_counts(self):
        with TemporaryDirectory() as temp:
            results = self.copy_results(temp)
            records = pd.read_csv(results / DETAIL)
            first, second = records.index[records.method.eq('direct_joint')]
            # Both rows remain in the same method/month and retain the larger gap.
            records.loc[first] = records.loc[second].copy()
            records.to_csv(results / DETAIL, index=False)
            with self.assertRaises(ValueError):
                inspect_evidence(results)

    def test_reject_monthly_and_pooled_count_changes(self):
        for period in ('2025-08', 'ALL'):
            with self.subTest(period=period), TemporaryDirectory() as temp:
                results = self.copy_results(temp)
                summary = pd.read_csv(results / SUMMARY)
                direct = summary.period.eq(period) & summary.method.eq('direct_joint')
                tree = summary.period.eq(period) & summary.method.eq('conditional_tree')
                # Redistribute one inversion without changing the total count.
                summary.loc[direct, 'violations'] -= 1
                summary.loc[tree, 'violations'] += 1
                summary.loc[direct | tree, 'violation_rate'] = (
                    summary.loc[direct | tree, 'violations'] / summary.loc[direct | tree, 'n']
                )
                summary.to_csv(results / SUMMARY, index=False)
                with self.assertRaises(ValueError):
                    inspect_evidence(results)

    def test_reject_record_date_differing_from_flight_key_in_same_month(self):
        with TemporaryDirectory() as temp:
            results = self.copy_results(temp)
            records = pd.read_csv(results / DETAIL)
            records.loc[0, 'date'] = '2025-08-23'
            records.to_csv(results / DETAIL, index=False)
            with self.assertRaises(ValueError):
                inspect_evidence(results)

    def test_reject_illegal_or_inconsistent_probability_differences(self):
        variants = (
            ('upper_minus_lower', float('nan')),
            ('upper_minus_lower', float('inf')),
            ('upper_minus_lower', 0.0),
            ('upper_minus_lower', -0.01),
            ('upper_minus_lower', 0.025),
            ('lower_probability', -0.1),
            ('upper_probability', 1.1),
        )
        for field, value in variants:
            with self.subTest(field=field, value=value), TemporaryDirectory() as temp:
                results = self.copy_results(temp)
                records = pd.read_csv(results / DETAIL)
                records.loc[0, field] = value
                records.to_csv(results / DETAIL, index=False)
                with self.assertRaises(ValueError):
                    inspect_evidence(results)


    def test_round_trip_preserves_the_strict_decision_boundary(self):
        for lower, upper, is_inversion in (
            (0.31, 0.31000000000100003, True),
            (0.0, 1e-12, False),
        ):
            with self.subTest(lower=lower, upper=upper), TemporaryDirectory() as temp:
                results = self.copy_results(temp)
                detail = pd.read_csv(results / DETAIL, float_precision='round_trip')
                # Change the smaller of the two direct-model gaps so the maximum stays fixed.
                position = detail.loc[detail.method.eq('direct_joint'), 'upper_minus_lower'].idxmin()
                detail.loc[position, ['lower_probability', 'upper_probability', 'upper_minus_lower']] = (
                    lower, upper, upper - lower
                )
                detail.to_csv(results / DETAIL, index=False)
                if is_inversion:
                    self.assertEqual(inspect_evidence(results)['inversions_by_method']['direct_joint'], 2)
                else:
                    with self.assertRaisesRegex(ValueError, 'decision tolerance'):
                        inspect_evidence(results)


if __name__ == '__main__':
    unittest.main()
