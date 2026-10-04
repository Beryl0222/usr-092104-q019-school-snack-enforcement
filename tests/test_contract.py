import json
import unittest
from pathlib import Path

from src.validator import AGGREGATE_TYPES, EVENT_TYPES, validate_event

ROOT = Path(__file__).parents[1]


class ContractTest(unittest.TestCase):
    def test_sample_matches_envelope(self) -> None:
        path = ROOT / "data" / "sample.json"
        self.assertEqual(validate_event(json.loads(path.read_text(encoding="utf-8"))), [])

    def test_chain_events_match_envelope(self) -> None:
        events = json.loads((ROOT / "data" / "sample_chain.json").read_text(encoding="utf-8"))
        for event in events:
            with self.subTest(event_id=event["event_id"]):
                self.assertEqual(validate_event(event), [])

    def test_unknown_event_type_rejected(self) -> None:
        record = json.loads((ROOT / "data" / "sample.json").read_text(encoding="utf-8"))
        record["event_type"] = "TITLE_AUTO_SIGNED"
        self.assertIn("event_type 未在领域事件登记表中", validate_event(record))

    def test_unknown_aggregate_type_rejected(self) -> None:
        record = json.loads((ROOT / "data" / "sample.json").read_text(encoding="utf-8"))
        record["aggregate_type"] = "shopping_cart"
        self.assertIn("aggregate_type 未在领域对象登记表中", validate_event(record))

    def test_original_vocabulary_kept(self) -> None:
        for event_type in ("LISTING_CAPTURED", "LOT_CLASSIFIED", "SAMPLE_TRANSFERRED", "DECISION_SIGNED", "RECALL_UPDATED"):
            self.assertIn(event_type, EVENT_TYPES)
        for aggregate_type in ("product_listing", "physical_lot", "inspection_sample", "enforcement_action"):
            self.assertIn(aggregate_type, AGGREGATE_TYPES)


if __name__ == "__main__":
    unittest.main()
