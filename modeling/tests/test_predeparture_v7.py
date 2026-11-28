"""Focused checks for time-safe archived-weather matching."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from predeparture_v7 import match_origin_taf, read_taf, scheduled_utc
from run_study_v7 import date_blocks


def forecast(product, issued, start, end, visibility):
    return {'station':'KATL','product_id':product,'issued_utc':issued,'valid_from_utc':start,
            'valid_to_utc':end,'visibility_sm':visibility,'ceiling_ft_agl':9000,'gust_kt':20,'wind_speed_kt':10,'weather_codes':'','ceiling_status':'present'}


class AsOfForecastTests(unittest.TestCase):
    def match(self, rows):
        dep = pd.DataFrame({'Origin':['ATL'],'date':pd.to_datetime(['2026-01-15']),
                            'CRSDepTime':[800],'dep_minutes':[480]},index=[42])
        with TemporaryDirectory() as folder:
            path=Path(folder)/'segment.csv'
            pd.DataFrame(rows).to_csv(path,index=False)
            return match_origin_taf(dep,read_taf(path),lead_minutes=120,availability_lag_minutes=30)

    def test_issue_cutoff_validity_and_adverse_indicator(self):
        out=self.match([
            forecast('valid','2026-01-15T10:30Z','2026-01-15T12:00Z','2026-01-15T14:00Z',2.5),
            forecast('late','2026-01-15T10:31Z','2026-01-15T12:00Z','2026-01-15T14:00Z',6.0),
        ])
        self.assertEqual(out.index.tolist(),[42])
        self.assertEqual(out.product_id.tolist(),['valid'])
        self.assertEqual(out.adverse_forecast.tolist(),[1])

    def test_latest_product_can_remove_existing_coverage(self):
        out=self.match([
            forecast('previous','2026-01-15T08:29Z','2026-01-15T12:00Z','2026-01-15T14:00Z',2.5),
            forecast('cancelled','2026-01-15T09:45Z',None,None,6.0),
        ])
        self.assertTrue(out.empty)

    def test_valid_to_is_exclusive(self):
        self.assertTrue(self.match([
            forecast('expired','2026-01-15T08:29Z','2026-01-15T12:00Z','2026-01-15T13:00Z',2.5),
        ]).empty)

    def test_unknown_local_clock_values_stay_unmatched(self):
        frame=pd.DataFrame({'date':pd.to_datetime(['2026-03-08','2026-11-01','2026-09-15','2026-09-15']),
                            'CRSDepTime':[230,130,2400,1230],'dep_minutes':[150,90,0,750]})
        times=scheduled_utc(frame,'ATL')
        self.assertTrue(times.iloc[:3].isna().all())
        self.assertEqual(times.iloc[3],pd.Timestamp('2026-09-15T16:30Z'))


    def test_product_availability_cannot_reintroduce_an_older_bulletin(self):
        dep = pd.DataFrame({'Origin':['ATL'],'date':pd.to_datetime(['2026-01-15']),
                            'CRSDepTime':[800],'dep_minutes':[480]},index=[42])
        older = forecast('old','2026-01-15T09:30Z','2026-01-15T12:00Z','2026-01-15T14:00Z',2.5)
        latest = forecast('new','2026-01-15T10:00Z','2026-01-15T12:00Z','2026-01-15T14:00Z',6.0)
        later_duplicate = dict(latest,product_id='duplicate')
        with TemporaryDirectory() as folder:
            root=Path(folder)
            segments=root/'segments.csv'
            products=root/'products.csv'
            pd.DataFrame([older,latest,later_duplicate]).to_csv(segments,index=False)
            pd.DataFrame([
                {**x,'available_utc':available,'product_status':'usable'}
                for x,available in [(older,'2026-01-15T10:25Z'),
                                    (latest,'2026-01-15T10:10Z'),
                                    (later_duplicate,'2026-01-15T10:40Z')]
            ]).to_csv(products,index=False)
            result = match_origin_taf(dep,read_taf(segments,products),lead_minutes=120,
                                      availability_lag_minutes=30)
        self.assertEqual(result.product_id.tolist(),['new'])


    def test_date_block_inputs_can_be_sparse_and_accept_csv_dates(self):
        daily = pd.DataFrame({'date':['2026-01-01','2026-01-15','2026-09-01'],
                              'threshold_minutes':60,'contrast':'adverse_group',
                              'n':[2,2,100],'sum_delta':[.2,.4,10]})
        out = date_blocks(daily,{'holdout_months':['2026-01'],'fit_scope':{'random_seed':2701}})
        self.assertEqual(set(out.block_days),{1,7,14})
        self.assertTrue(out.n.eq(4).all())
        self.assertAlmostEqual(out.estimate.iloc[0],.15)


if __name__ == '__main__':
    unittest.main()

