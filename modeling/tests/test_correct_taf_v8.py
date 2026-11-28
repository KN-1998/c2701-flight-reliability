"""Regression cases for raw TAF group pairing and bounded wind recovery."""
from pathlib import Path
import unittest

from correct_taf_v8 import parse_values, raw_groups, vrb_candidate


RAW = Path(__file__).resolve().parents[1] / "data/taf_v8/original_products"


class ExactTafRepairTests(unittest.TestCase):
    def test_prob30_conditions_do_not_enter_prevailing_group(self):
        product_id = "202406182320-KLOT-FTUS43-TAFORD"
        raw = (RAW / (product_id + ".txt")).read_bytes()
        metadata = {
            "station": "KORD",
            "issued_utc": "2024-06-18T23:20:00Z",
            "product_valid_from_utc": "2024-06-19T00:00:00Z",
            "product_valid_to_utc": "2024-06-20T06:00:00Z",
        }
        groups = raw_groups(product_id, metadata, raw)
        self.assertEqual(set(groups), {"initial", "FM200100", "FM200300"})
        self.assertIn(b"-TSRA BKN050CB", raw)
        initial = parse_values(groups["initial"])
        self.assertEqual(initial["ceiling_ft_agl"], "25000")
        self.assertEqual(initial["weather_codes"], "")
        self.assertEqual(initial["visibility_relation"], "greater_than")

    def test_exact_fm_preserves_its_own_variable_wind(self):
        product_id = "202601071258-KFFC-FTUS42-TAFATL-AAA"
        raw = (RAW / (product_id + ".txt")).read_bytes()
        metadata = {
            "station": "KATL",
            "issued_utc": "2026-01-07T12:58:00Z",
            "product_valid_from_utc": "2026-01-07T13:00:00Z",
            "product_valid_to_utc": "2026-01-08T18:00:00Z",
        }
        groups = raw_groups(product_id, metadata, raw)
        last = parse_values(groups["FM080700"])
        self.assertEqual(last["ceiling_ft_agl"], "1500")
        self.assertEqual(last["wind_speed_kt"], "3")
        self.assertEqual(last["gust_kt"], "0")
        self.assertEqual(last["visibility_sm"], "4.0")

    def test_raw_receipt_must_match_amendment_identity(self):
        product_id = "202601071258-KFFC-FTUS42-TAFATL-AAA"
        raw = (RAW / (product_id + ".txt")).read_bytes()
        wrong_revision = raw.replace(b"071258 AAA", b"071258 AAB")
        with self.assertRaisesRegex(ValueError, "Wrong WMO/AWIPS"):
            raw_groups(product_id, {}, wrong_revision)

    def test_vrb_sensitivity_refuses_ambiguous_or_disagreeing_text(self):
        text = "FM080700 VRB03G10KT 4SM BR SCT004 BKN015"
        values = parse_values(text)
        row = {
            **values,
            "wind_speed_kt": "",
            "gust_kt": "",
            "segment_kind": "FM",
            "valid_from_utc": "2026-01-08T07:00:00Z",
        }
        recovered, disposition = vrb_candidate(row, True)
        self.assertEqual(recovered, {"wind_speed_kt": "3", "gust_kt": "10"})
        self.assertEqual(disposition, "text_supported_vrb_repair")
        self.assertEqual(vrb_candidate(row, False), (None, "repeated_group_text"))
        self.assertEqual(
            vrb_candidate({**row, "valid_from_utc": "2026-01-08T08:00:00Z"}, True),
            (None, "unverified_group_identity"),
        )
        self.assertEqual(
            vrb_candidate({**row, "ceiling_ft_agl": "3000.0"}, True),
            (None, "nonwind_field_disagrees"),
        )


if __name__ == "__main__":
    unittest.main()
