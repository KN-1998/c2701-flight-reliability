"""Regression checks for the weather composition and matched comparison contracts."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from weather_joint_v8 import (
    JAN_AUG, LATER, SEPTEMBER, WEATHER, apply_fallback, compare_reference, fit_pair, study_months,
)


class JointWeatherV8Tests(unittest.TestCase):
    def test_branch_samples_are_paired_and_probabilities_nested(self):
        count = 80
        record = pd.DataFrame({
            'Origin': ['ATL'] * count, 'Dest': ['ORD'] * count,
            'Reporting_Airline': ['DL'] * count,
            'month': [1] * count, 'weekday': np.arange(count) % 7,
            'time_bin': ['06-11'] * count, 'dep_minutes': np.arange(count) + 400,
            'arr_minutes': np.arange(count) + 540, 'Distance': [601] * count,
            'CRSElapsedTime': [140] * count,
            'state': ['cancelled', 'diverted', 'late', 'late', 'on_time'] * (count // 5),
            'completed': [False, False, True, True, True] * (count // 5),
            'ArrDelay': [np.nan, np.nan, 70, 20, 3] * (count // 5),
            'visibility_sm': np.linspace(1, 7, count), 'ceiling_ft_agl': np.linspace(550, 4900, count),
            'wind_speed_kt': np.arange(count) % 15, 'gust_kt': [np.nan, 12] * (count // 2),
            'clear_ceiling': [0] * count, 'adverse_forecast': (np.arange(count) < 25).astype(int),
        })
        pair = fit_pair(record.iloc[:55], record.iloc[55:], {'C': .1, 'fit_cap': 20, 'random_seed': 2701})
        for model in pair:
            leaves, p15, p60 = model.predict(record.iloc[55:])
            self.assertTrue((leaves >= 0).all())
            np.testing.assert_allclose(leaves.sum(axis=1), 1, atol=1e-12, rtol=0)
            np.testing.assert_allclose(leaves[:, :4].sum(axis=1), p15, atol=1e-12, rtol=0)
            np.testing.assert_allclose(leaves[:, :3].sum(axis=1), p60, atol=1e-12, rtol=0)
            self.assertTrue((p60 <= p15).all())
        for counts_a, counts_b in zip(pair[0].risk_counts, pair[1].risk_counts, strict=True):
            for field in ('training_n', 'training_events', 'calibration_n', 'calibration_events'):
                self.assertEqual(counts_a[field], counts_b[field])

    def test_schedule_fallback_replaces_only_corresponding_matched_rows(self):
        index = pd.Index([0, 3, 6, 9])
        matches = pd.Index([9, 3])
        schedule = (np.zeros((4, 5)), np.zeros(4), np.zeros(4))
        weather = (np.tile([0, 1, 2, 3, 4], (2, 1)),
                   np.array([.9, .3]), np.array([.8, .2]))
        leaves, p15, p60 = apply_fallback(index, matches, schedule, weather)
        np.testing.assert_allclose(p15, [0, .3, 0, .9])
        np.testing.assert_allclose(p60, [0, .2, 0, .8])
        np.testing.assert_array_equal(leaves[[0, 2]], 0)
        np.testing.assert_array_equal(schedule[1], 0)
        with self.assertRaisesRegex(ValueError, 'belong'):
            apply_fallback(index, pd.Index([10, 11]), schedule, weather)
        with self.assertRaisesRegex(ValueError, 'unique'):
            apply_fallback(index, pd.Index([9, 9]), schedule, weather)

    def test_binary_reference_must_preserve_exact_identities_and_scope(self):
        candidate = pd.DataFrame({
            'period': ['2026-01', '2026-09'], 'scope': [JAN_AUG, SEPTEMBER],
            'threshold_minutes': [15, 15], 'method': [WEATHER, WEATHER],
            'n': [5, 7], 'events': [2, 4], 'identity_sha256': ['abc', 'def'],
        })
        parts = [candidate.assign(method=method, scope=['frozen_followup', 'previously_reviewed'])
                 for method in ('schedule_proxy_only', 'schedule_plus_origin_taf')]
        with TemporaryDirectory() as temp:
            path = Path(temp) / 'binary.csv'
            pd.concat(parts).to_csv(path, index=False)
            reference = compare_reference(candidate, path, 'archived_binary')
            self.assertEqual(set(reference.scope), {JAN_AUG, SEPTEMBER})
            parts[0].loc[1, 'identity_sha256'] = 'not-same'
            pd.concat(parts).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'Unpaired'):
                compare_reference(candidate, path, 'archived_binary')
            parts[0].loc[1, 'identity_sha256'] = 'def'
            parts[0].loc[1, 'scope'] = 'frozen_followup'
            pd.concat(parts).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'Incorrect source month'):
                compare_reference(candidate, path, 'archived_binary')

    def test_later_readout_excludes_reviewed_months_and_repeats(self):
        original = {'holdout_months': ['2026-08'], 'previously_inspected_months': ['2026-09']}
        registered = {'retrospective_score_months': ['2026-08'], 'retrospective_reference_months': ['2026-09'],
                      'prospective_months': ['2026-10', '2026-11', '2026-12']}
        _, historical = study_months(original, registered, [])
        self.assertEqual(historical, {'2026-08': JAN_AUG, '2026-09': SEPTEMBER})
        later_protocol, later = study_months(original, registered, ['2026-11', '2026-10'])
        self.assertEqual(later_protocol['holdout_months'], ['2026-10', '2026-11'])
        self.assertEqual(later_protocol['previously_inspected_months'], [])
        self.assertEqual(later, {'2026-10': LATER, '2026-11': LATER})
        for invalid in (['2026-09'], ['2026-11', '2026-11'], ['2027-01']):
            with self.assertRaisesRegex(ValueError, 'distinct registered'):
                study_months(original, registered, invalid)


if __name__ == '__main__':
    unittest.main()
