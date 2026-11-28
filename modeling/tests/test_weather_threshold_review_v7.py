"""Regressions for post-v7 paired weather-threshold review."""
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from audit_weather_thresholds_v7 import METHODS, threshold_tables


class WeatherThresholdReviewTests(unittest.TestCase):
    def fixture(self):
        frame = pd.DataFrame({'FlightDate':['2026-01-15','2026-01-15'],
                              'date':pd.to_datetime(['2026-01-15','2026-01-15']),
                              'Reporting_Airline':['DL','DL'],
                              'Flight_Number_Reporting_Airline':[101,102],
                              'Origin':['ATL','ATL'], 'Dest':['BOS','BOS'],
                              'CRSDepTime':[800,900], 'state':['completed','completed'],
                              'completed':[True,True], 'ArrDelay':[15.,60.]}, index=[42,8])
        predictions = {name:{15:np.array([.2,.5]),60:np.array([.1,.4])} for name in METHODS}
        return frame,predictions

    def test_nested_probabilities_do_not_authorize_card(self):
        frame,p = self.fixture()
        summary, detail = threshold_tables(frame,p,'2026-01','frozen_followup')
        self.assertEqual(summary.violations.tolist(),[0,0])
        self.assertTrue(detail.empty)
        self.assertTrue(summary.identity_sha256.eq(summary.identity_sha256.iloc[0]).all())
        self.assertEqual(summary.lower_events.tolist(),[2,2])
        self.assertEqual(summary.upper_events.tolist(),[1,1])

    def test_retains_every_method_flight_counterexample(self):
        frame,p = self.fixture()
        for method in METHODS:
            p[method][60]=np.array([.3,.6])
        summary,detail=threshold_tables(frame,p,'2026-01','frozen_followup')
        self.assertEqual(summary.violations.tolist(),[2,2])
        self.assertEqual(len(detail),4)
        self.assertFalse(detail.duplicated(['flight_key','method']).any())
        np.testing.assert_allclose(detail.upper_minus_lower,.1,rtol=0,atol=1e-15)

    def test_strict_tolerance_boundary_is_not_rounding(self):
        frame,p = self.fixture()
        for method in METHODS:
            p[method][15]=np.array([0.,0.])
            p[method][60]=np.array([1e-12,np.nextafter(1e-12,np.inf)])
        summary,detail=threshold_tables(frame,p,'2026-01','frozen_followup')
        self.assertEqual(summary.violations.tolist(),[1,1])
        self.assertEqual(len(detail),2)

    def test_never_modifies_inputs_or_clips_inversions(self):
        frame,p = self.fixture()
        p[METHODS[1]][60][0]=.7
        old_frame=frame.copy(deep=True)
        arrays={m:{t:x.copy() for t,x in values.items()} for m,values in p.items()}
        threshold_tables(frame,p,'2026-01','frozen_followup')
        pd.testing.assert_frame_equal(frame,old_frame)
        for m in METHODS:
            for t in (15,60):np.testing.assert_array_equal(p[m][t],arrays[m][t])

    def test_rejects_duplicate_flight_identity(self):
        frame,p = self.fixture()
        frame.iloc[1]=frame.iloc[0]
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            threshold_tables(frame,p,'2026-01','frozen_followup')

    def test_rejects_missing_method_or_threshold(self):
        for mode in ('method','threshold'):
            frame,p=self.fixture()
            if mode=='method':del p[METHODS[0]]
            else:del p[METHODS[0]][60]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                threshold_tables(frame,p,'2026-01','frozen_followup')

    def test_rejects_invalid_probabilities_shape_or_tolerance(self):
        for value in ([np.nan,.2],[-.1,.2],[.2,1.1],[.2],[[.2,.3]]):
            frame,p=self.fixture();p[METHODS[0]][60]=np.array(value)
            with self.subTest(value=value),self.assertRaises(ValueError):
                threshold_tables(frame,p,'2026-01','frozen_followup')
        frame,p=self.fixture()
        for tolerance in (-1,np.nan,np.inf):
            with self.subTest(tolerance=tolerance),self.assertRaises(ValueError):
                threshold_tables(frame,p,'2026-01','frozen_followup',atol=tolerance)

    def test_rejects_wrong_declared_month_and_empty_inputs(self):
        frame,p=self.fixture()
        with self.assertRaisesRegex(ValueError,'month'):
            threshold_tables(frame,p,'2026-02','frozen_followup')
        with self.assertRaises(ValueError):
            threshold_tables(frame.iloc[:0],p,'2026-01','frozen_followup')


if __name__=='__main__':unittest.main()
