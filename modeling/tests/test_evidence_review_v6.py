"""Regression tests for saved-table evidence checks, not model adequacy tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

import pandas as pd
from review_v6_evidence import ROOT, inspect_evidence, compare_csv_trees

SAVED = ROOT / 'results/implementation_v6'


class EvidenceReviewTests(unittest.TestCase):
    def copy_saved(self, directory):
        target = Path(directory) / 'saved'
        shutil.copytree(SAVED, target)
        return target

    def test_saved_evidence_scope_and_tradeoff(self):
        report = inspect_evidence(SAVED)
        self.assertEqual(report['holdout_rows'], 3287437)
        self.assertEqual(report['inversions_by_method']['selected_direct_low_tree_high'], 1)
        for row in report['candidate_tradeoffs']:
            if row['threshold_minutes'] == 15:
                self.assertGreater(row['candidate_minus_selected'], 0)

    def test_reject_duplicate_audit_month(self):
        with TemporaryDirectory() as temp:
            root = self.copy_saved(temp)
            path = root / 'audit_by_month.csv'
            table = pd.read_csv(path)
            pd.concat([table, table.iloc[:1]], ignore_index=True).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'Duplicate audit month'):
                inspect_evidence(root)

    def test_reject_structure_fingerprint_mismatch(self):
        with TemporaryDirectory() as temp:
            root = self.copy_saved(temp)
            path = root / 'joint_candidate/candidate_structure_monthly.csv'
            table = pd.read_csv(path)
            table.loc[0, 'test_row_hash'] = 'not-the-scored-records'
            table.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'structure identity'):
                inspect_evidence(root)

    def test_reject_nonclosing_leaf_report(self):
        with TemporaryDirectory() as temp:
            root = self.copy_saved(temp)
            path = root / 'joint_candidate/candidate_structure_monthly.csv'
            table = pd.read_csv(path)
            table.loc[0, 'max_leaf_sum_error'] = .01
            table.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'leaves do not close'):
                inspect_evidence(root)

    def test_reject_upgraded_future_gate(self):
        with TemporaryDirectory() as temp:
            root = self.copy_saved(temp)
            path = root / 'delivery_status.json'
            status = json.loads(path.read_text(encoding='utf-8'))
            status['new_unseen_validation'] = True
            path.write_text(json.dumps(status), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Retrospective gate'):
                inspect_evidence(root)

    def test_all_csv_reports_measured_float_difference(self):
        with TemporaryDirectory() as temp:
            a, b = Path(temp)/'a', Path(temp)/'b'
            a.mkdir(); b.mkdir()
            table = pd.DataFrame({'n':[10,20], 'key':['first','second'], 'score':[.1,.2], 'flag':[True,False]})
            table.to_csv(b/'x.csv', index=False)
            table.loc[0,'score'] += 1e-12
            table.to_csv(a/'x.csv', index=False)
            value = compare_csv_trees(a,b)
            self.assertEqual(value['tables_compared'],1)
            self.assertGreater(value['maximum_observed_abs_difference'],0)
            self.assertLess(value['maximum_observed_abs_difference'],value['absolute_tolerance'])

    def test_all_csv_rejects_integer_boolean_and_identity_changes(self):
        for col, value in [('n',11), ('flag',False), ('key','different'), ('score',.3)]:
            with self.subTest(column=col), TemporaryDirectory() as temp:
                a,b = Path(temp)/'a',Path(temp)/'b'
                a.mkdir();b.mkdir()
                table = pd.DataFrame({'n':[10], 'flag':[True], 'key':['a'], 'score':[.1]})
                table.to_csv(b/'x.csv',index=False)
                table.loc[0,col] = value
                table.to_csv(a/'x.csv',index=False)
                with self.assertRaises(ValueError):
                    compare_csv_trees(a,b)

    def test_all_csv_rejects_inventory_or_missingness_change(self):
        with TemporaryDirectory() as temp:
            a,b = Path(temp)/'a',Path(temp)/'b'
            a.mkdir();b.mkdir()
            pd.DataFrame({'score':[.1,.2]}).to_csv(b/'x.csv',index=False)
            with self.assertRaisesRegex(ValueError,'inventory'):
                compare_csv_trees(a,b)
            pd.DataFrame({'score':[.1,None]}).to_csv(a/'x.csv',index=False)
            with self.assertRaisesRegex(ValueError,'missingness'):
                compare_csv_trees(a,b)
