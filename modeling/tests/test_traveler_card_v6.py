from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from traveler_card_v6 import build_traveler_card


def segment(day, airport, state='on_time', delay=0, carrier='AA'):
    return {
        'date':pd.Timestamp(day), 'Origin':airport, 'Dest':'DEN',
        'Reporting_Airline':carrier, 'season':'winter', 'time_bin':1,
        'state':state, 'completed':state in {'on_time','late'}, 'ArrDelay':delay,
    }


class TravelerCardTests(unittest.TestCase):
    def test_shared_partition_keeps_boundary_labels_and_both_denominators(self):
        frame = pd.DataFrame([
            segment('2023-01-01','EWR','cancelled',None),
            segment('2023-01-01','EWR','diverted',None),
            segment('2023-01-01','EWR','late',60),
            segment('2023-01-01','EWR','late',15),
            segment('2023-01-01','EWR','unknown',None),
            segment('2023-01-01','LGA','on_time',14),
            segment('2023-01-01','LGA','late',59),
            segment('2026-09-01','EWR','cancelled',None),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'card'
            status = build_traveler_card(frame,out,min_known=1,reps=4)
            self.assertEqual(status['n'],7)
            self.assertEqual(status['coverage_status'],'INCOMPLETE_CORE_MONTHS')
            rates = pd.read_csv(out/'route_rates.csv',dtype={'period':str})
            ewr = rates.loc[rates.period.eq('2023-2025') & rates.airport.eq('EWR')].iloc[0]
            self.assertEqual(ewr.n_planned,5)
            self.assertEqual(ewr.n_completed,2)
            self.assertEqual(ewr.completed_15_to_under_60,1)
            self.assertEqual(ewr.completed_at_least_60,1)
            self.assertAlmostEqual(ewr.long_delay_60_per_scheduled,.2)
            self.assertAlmostEqual(ewr.long_delay_60_given_completed,.5)
            self.assertAlmostEqual(ewr.long_delay_60_given_completed_identified_low,1/3)
            self.assertAlmostEqual(ewr.long_delay_60_given_completed_identified_high,2/3)
            self.assertAlmostEqual(ewr.joint_bad_15,.8)
            self.assertAlmostEqual(ewr.joint_bad_60,.6)
            matched = pd.read_csv(out/'matched_comparisons.csv')
            point = matched.loc[matched.period.eq('2023-2025') & matched.block_days.eq(7)].set_index('target')
            self.assertGreaterEqual(point.at['joint_bad_15','EWR_adjusted_rate'],point.at['joint_bad_60','EWR_adjusted_rate'])
            self.assertAlmostEqual(point.at['joint_bad_60','identified_difference_high'],.8)
            with self.assertRaisesRegex(ValueError,'fresh or empty'):
                build_traveler_card(frame,out,min_known=1,reps=4)

    def test_annual_comparisons_keep_a_fixed_common_mix(self):
        frame = pd.DataFrame([
            segment(f'{year}-01-01',airport,carrier=carrier)
            for year in (2023,2024) for airport in ('EWR','LGA')
            for carrier in (('AA','UA') if year == 2023 else ('AA',))
        ])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            status = build_traveler_card(frame,out,min_known=1,reps=4)
            self.assertEqual(status['shared_cells'],2)
            self.assertEqual(status['shared_fixed_annual_cells'],1)
            coverage = pd.read_csv(out/'support_coverage.csv',dtype={'period':str})
            self.assertTrue(coverage.loc[coverage.period.eq('2023'),'coverage'].eq(.5).all())
            weights = pd.read_csv(out/'reference_weights.csv')
            annual = weights.loc[weights.reference_scope.eq('fixed_cross_year_common_support')]
            self.assertEqual(annual.cell.tolist(),['AA|winter|1'])
            self.assertEqual(annual.weight.tolist(),[1])

    def test_absent_routes_produce_a_readable_empty_card(self):
        frame = pd.DataFrame([segment('2023-01-01','MCO')])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = build_traveler_card(frame,out,reps=2)
            self.assertEqual(result['status'],'no_route_rows')
            self.assertEqual(result['periods'],['2023-01'])
            self.assertTrue(pd.read_csv(out/'route_rates.csv').n_planned.eq(0).all())
            self.assertTrue(pd.read_csv(out/'matched_comparisons.csv').empty)

    def test_missing_support_and_missing_completion_are_reported_separately(self):
        frame = pd.DataFrame([
            segment('2023-01-01','EWR','cancelled',None),
            segment('2023-01-01','LGA','cancelled',None),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            good, no_support = Path(tmp)/'good', Path(tmp)/'no_support'
            result = build_traveler_card(frame,good,min_known=1,reps=4)
            self.assertEqual(result['status'],'computed')
            matched = pd.read_csv(good/'matched_comparisons.csv')
            unavailable = matched.target.eq('long_delay_60_given_completed')
            self.assertTrue(matched.loc[unavailable,'experimental_95_low'].isna().all())
            self.assertTrue(matched.loc[unavailable,'invalid_reps'].eq(4).all())
            self.assertTrue(matched.loc[~unavailable,'invalid_reps'].eq(0).all())
            result = build_traveler_card(frame,no_support,min_known=2,reps=4)
            self.assertEqual(result['status'],'no_common_support')
            self.assertTrue(pd.read_csv(no_support/'matched_comparisons.csv').empty)


if __name__ == '__main__':
    unittest.main()

