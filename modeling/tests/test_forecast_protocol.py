"""Regression tests for configured execution and traceable holdout output."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from audit import audit
from forecast_protocol import parse_forecast_protocol
from prediction import HistoricalBaseline, combine, joint_target, run_prediction, stable_flight_key
from test_contract import example


def fixture_protocol():
    return {
        'label':'integration_fixture',
        'fit_start':'2024-01-01',
        'fit_end':'2024-01-31',
        'tune_months':['2024-02'],
        'refit_end':'2024-02-29',
        'calibration_months':['2024-03'],
        'previously_scored_months':[],
        'new_core_months':['2024-05'],
        'late_months':[],
        'thresholds_minutes':[15, 60],
        'fit_cap':7,
        'seed':913,
        'C_grid':[.2],
        'baseline_strength':0,
    }


def fixture_flights():
    # There are distractor observations before fit_start and between calibration
    # and the holdout. Neither can enter any fitted model or any holdout table.
    frames = []
    for period in pd.period_range('2023-12', '2024-05', freq='M'):
        for origin, indices in [('ATL',[0,1,2,3,4,5]), ('LGA',[0,1,2,3,5])]:
            rows = example().iloc[indices].copy()
            rows['Origin'] = origin
            rows['FlightDate'] = f'{period}-03'
            rows['CRSDepTime'] = [2400, *[900]*(len(rows)-1)]
            frames.append(rows)
    return audit(pd.concat(frames, ignore_index=True))[0]


class ForecastProtocolTests(unittest.TestCase):
    def test_existing_protocol_matches_frozen_calendar(self):
        path = Path(__file__).resolve().parents[1] / 'docs/VALIDATION_V5.json'
        protocol = parse_forecast_protocol(json.loads(path.read_text(encoding='utf-8-sig')))
        self.assertEqual(protocol.fit_start, '2023-01-01')
        self.assertEqual(protocol.calibration_end, '2024-06-30')
        self.assertEqual(len(protocol.required_months), 18)
        self.assertEqual(len(protocol.holdout_months), 19)
        self.assertEqual(protocol.holdout_months[0], '2024-07')
        self.assertEqual(protocol.holdout_months[-1], '2026-09')

    def test_impossible_or_unsupported_settings_are_rejected(self):
        for invalid in [
            {'refit_end':'2024-03-31'},
            {'fit_start':'2024-01-03'},
            {'calibration_months':['2024-04']},
            {'new_core_months':['2024-03']},
            {'late_months':['2024-05']},
            {'seed':True},
            {'thresholds_minutes':[15,15]},
            {'fit_cap':0},
            {'C_grid':[.1,float('nan')]},
            {'baseline_strength':-1},
            {'primary_loss':'log loss'},
        ]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_forecast_protocol(fixture_protocol() | invalid)

    def test_protocol_controls_parameters_windows_and_audit_outputs(self):
        case = fixture_protocol()
        df = fixture_flights()
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            first = run_prediction(df, directory/'first', protocol=case, threshold=15,
                                   save_flight_identity=True)
            shifted = case | {'tune_months':['2024-02','2024-03'], 'refit_end':'2024-03-31',
                              'calibration_months':['2024-04'], 'seed':914,
                              'baseline_strength':50}
            second = run_prediction(df, directory/'second', protocol=shifted, threshold=15)
            for result, out, protocol in [(first, directory/'first', case), (second, directory/'second', shifted)]:
                fitted = df.loc[df.date.between(protocol['fit_start'],protocol['refit_end'])]
                testing = df.loc[df.date.dt.to_period('M').eq('2024-05')]
                sampled = np.sort(np.random.default_rng(protocol['seed']).choice(
                    np.arange(len(fitted)), protocol['fit_cap'], replace=False))
                self.assertEqual(result['direct_training']['available'], len(fitted))
                self.assertEqual(result['direct_training']['events'], int(joint_target(fitted,15)[sampled].sum()))
                self.assertEqual(result['calibration_start'], protocol['calibration_months'][0]+'-01')
                self.assertEqual(result['baseline_strength'], protocol['baseline_strength'])
                self.assertEqual(result['seed'], protocol['seed'])
                self.assertEqual(result['chosen_C'], {'conditional_tree':.2,'direct_joint':.2})
                self.assertEqual([item['period'] for item in result['holdout_months']], ['2024-05'])
                pred = pd.read_pickle(out/'predictions.pkl')
                expected_base = 1 - combine(HistoricalBaseline(protocol['baseline_strength'],15).fit(fitted)
                                            .predict(testing))[:,3]
                np.testing.assert_allclose(pred.baseline_p, expected_base)
                paired = pd.read_csv(out/'paired_prediction_loss.csv').set_index('contrast')
                daily = pd.read_csv(out/'paired_prediction_loss_by_day.csv')
                for method, group in daily.groupby('contrast'):
                    self.assertEqual(group.n.sum(), paired.at[method, 'n'])
                    self.assertAlmostEqual(group.loss_difference_sum.sum()/group.n.sum(),
                                           paired.at[method, 'brier_difference'])
            pred = pd.read_pickle(directory/'first/predictions.pkl')
            keys = pred.flight_key.to_list()
            self.assertEqual(keys[0], '2024-05-03|XX|0|ATL|ORD|2400')
            self.assertEqual(first['holdout_months'][0]['flight_identity_sha256'],
                             hashlib.sha256(('\n'.join(sorted(keys))+'\n').encode()).hexdigest())
            self.assertEqual(first['holdout_months'][0]['row_hash'], second['holdout_months'][0]['row_hash'])
            with self.assertRaisesRegex(ValueError, 'fit_cap'):
                run_prediction(df, directory/'contradiction', protocol=case, fit_cap=12)

    def test_flight_keys_survive_numeric_csv_types_and_refuse_invalid_rows(self):
        df = fixture_flights()
        float_identifiers = df.astype({'Flight_Number_Reporting_Airline':'float64','CRSDepTime':'float64'})
        self.assertEqual(stable_flight_key(df).to_list(), stable_flight_key(float_identifiers).to_list())
        alphanumeric = df.iloc[:1].assign(Flight_Number_Reporting_Airline='120A')
        self.assertIn('|120A|', stable_flight_key(alphanumeric).iat[0])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            stable_flight_key(pd.concat([df,df.iloc[:1]], ignore_index=True))
        bad = df.iloc[:1].assign(Reporting_Airline='X|X')
        with self.assertRaisesRegex(ValueError, 'Invalid'):
            stable_flight_key(bad)


if __name__ == '__main__':
    unittest.main()
