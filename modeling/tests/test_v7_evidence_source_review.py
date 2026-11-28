"""Evidence corruption and text-audit regressions; never edits frozen inputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import sys
import unittest

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from audit_taf_text_v7 import raw_text_flags
from review_v7_evidence import inspect_evidence
from run_study_v7 import pooled


class V7EvidenceSourceReviewTests(unittest.TestCase):
    def test_saved_pairing_and_arithmetic(self):
        self.assertEqual(inspect_evidence(ROOT/'results/v7_20261128')['status'],
                         'V7_SAVED_ARITHMETIC_AND_PAIRING_PASS')

    def test_rejects_changed_identity_with_unchanged_counts(self):
        with TemporaryDirectory() as tmp:
            dest=Path(tmp)/'evidence';shutil.copytree(ROOT/'results/v7_20261128',dest)
            file=dest/'weather/taf_monthly.csv';frame=pd.read_csv(file)
            frame.loc[0,'identity_sha256']='0'*64;frame.to_csv(file,index=False)
            with self.assertRaisesRegex(ValueError,'identity'):
                inspect_evidence(dest)

    def test_rejects_consistently_relabelled_previously_reviewed_month(self):
        with TemporaryDirectory() as tmp:
            dest=Path(tmp)/'evidence'
            shutil.copytree(ROOT/'results/v7_20261128',dest)
            for folder,prefix in [('followup','followup'),('weather','taf')]:
                base=dest/folder
                for table in ('monthly','calibration'):
                    file=base/f'{prefix}_{table}.csv'
                    frame=pd.read_csv(file)
                    frame.loc[frame.period.eq('2026-09'),'scope']='frozen_followup'
                    frame.to_csv(file,index=False)
                    if table=='monthly':
                        pooled(frame).to_csv(base/f'{prefix}_pooled.csv',index=False)
            file=dest/'weather/taf_stress_monthly.csv'
            stress=pd.read_csv(file)
            stress.loc[stress.period.eq('2026-09'),'scope']='frozen_followup'
            stress.to_csv(file,index=False)
            pooled(stress,extras=('group',)).to_csv(dest/'weather/taf_stress_pooled.csv',index=False)
            with self.assertRaisesRegex(ValueError,'scope differs from frozen protocol'):
                inspect_evidence(dest)

    def test_rejects_missing_or_unexpected_score_month(self):
        for replacement in (None,'2026-10'):
            with self.subTest(replacement=replacement),TemporaryDirectory() as tmp:
                dest=Path(tmp)/'evidence'
                shutil.copytree(ROOT/'results/v7_20261128',dest)
                file=dest/'followup/followup_monthly.csv'
                frame=pd.read_csv(file)
                inspected=frame.period.eq('2026-09')
                if replacement is None:
                    frame=frame.loc[~inspected]
                else:
                    frame.loc[inspected,'period']=replacement
                frame.to_csv(file,index=False)
                with self.assertRaisesRegex(ValueError,'month inventory differs from frozen protocol'):
                    inspect_evidence(dest)

    def test_rejects_invalid_decile_bounds_or_mean_with_unchanged_aggregation(self):
        for bounds,error in [((2.,3.),'Invalid calibration decile bounds'),
                             ((.9,1.),'Mean prediction lies outside its calibration decile')]:
            with self.subTest(bounds=bounds),TemporaryDirectory() as tmp:
                dest=Path(tmp)/'evidence'
                shutil.copytree(ROOT/'results/v7_20261128',dest)
                file=dest/'weather/taf_calibration.csv'
                frame=pd.read_csv(file)
                frame.loc[0,['lower','upper']]=bounds
                frame.to_csv(file,index=False)
                with self.assertRaisesRegex(ValueError,error):
                    inspect_evidence(dest)

    def test_rejects_fractional_calibration_counts(self):
        with TemporaryDirectory() as tmp:
            dest=Path(tmp)/'evidence'
            shutil.copytree(ROOT/'results/v7_20261128',dest)
            file=dest/'weather/taf_calibration.csv'
            frame=pd.read_csv(file)
            frame['n']=frame.n.astype(float)
            frame.loc[0,'n']+=.5
            frame.to_csv(file,index=False)
            with self.assertRaisesRegex(ValueError,'Invalid calibration count'):
                inspect_evidence(dest)

    def test_rejects_corrupted_pooled_daily_or_stress_evidence(self):
        for relative,column in [('weather/taf_pooled.csv','brier'),
                                ('weather/taf_daily_losses.csv','sum_delta'),
                                ('weather/taf_stress_monthly.csv','events')]:
            with self.subTest(relative=relative),TemporaryDirectory() as tmp:
                dest=Path(tmp)/'evidence';shutil.copytree(ROOT/'results/v7_20261128',dest)
                file=dest/relative;frame=pd.read_csv(file);frame.loc[0,column]+=.01 if column=='brier' else 10
                frame.to_csv(file,index=False)
                with self.assertRaises(ValueError):inspect_evidence(dest)

    def test_cloud_cb_tcu_and_vertical_visibility_are_not_false_flags(self):
        frame=pd.DataFrame({'source_forecast_text':['P6SM TSRA OVC009CB','P6SM BKN020TCU','1SM BR VV003','P6SM SKC'],
                            'weather_codes':['TSRA','','BR',''],'ceiling_ft_agl':[900.,2000.,300.,float('nan')]})
        self.assertTrue(raw_text_flags(frame).empty)

    def test_flags_text_disagreements_without_changing_input(self):
        frame=pd.DataFrame({'source_forecast_text':['P6SM OVC020','P6SM FEW050 SCT100','P6SM BKN003'],
                            'weather_codes':['','-TSRA',''],'ceiling_ft_agl':[1200.,4500.,300.]})
        before=frame.copy(deep=True);result=raw_text_flags(frame)
        self.assertEqual(result.index.tolist(),[0,1])
        self.assertEqual(result.ceiling_text_mismatch.tolist(),[True,True])
        self.assertEqual(result.adverse_code_absent_in_visible_text.tolist(),[False,True])
        pd.testing.assert_frame_equal(frame,before)

    def test_missing_text_is_a_candidate_not_automatic_correction(self):
        frame=pd.DataFrame({'source_forecast_text':[None,'P6SM SKC'],'weather_codes':['FZRA',''],
                            'ceiling_ft_agl':[float('nan'),float('nan')]})
        result=raw_text_flags(frame)
        self.assertEqual(result.index.tolist(),[0])
        self.assertTrue(result.adverse_code_absent_in_visible_text.iloc[0])
        self.assertTrue(pd.isna(result.ceiling_ft_agl.iloc[0]))


if __name__=='__main__':unittest.main()
