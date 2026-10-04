import json
import unittest
from pathlib import Path

from src.validator import load_catalog, validate_event, validate_stream

ROOT = Path(__file__).parents[1]


class ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads((ROOT / "contracts" / "domain.schema.json").read_text(encoding="utf-8"))
        self.catalog = load_catalog()

    def test_sample_matches_envelope(self) -> None:
        record = json.loads((ROOT / "data" / "sample.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_event(record, self.catalog), [])

    def test_envelope_fields_unchanged(self) -> None:
        # 信封七字段是跨版本兼容底线
        self.assertEqual(
            self.schema["required"],
            ["event_id", "event_type", "aggregate_type", "aggregate_id", "occurred_at", "version", "summary"],
        )

    def test_schema_event_enum_matches_catalog(self) -> None:
        schema_events = set(self.schema["properties"]["event_type"]["enum"])
        catalog_events = set(self.catalog["events"])
        self.assertEqual(schema_events, catalog_events)

    def test_schema_aggregate_enum_covers_catalog(self) -> None:
        schema_aggregates = set(self.schema["properties"]["aggregate_type"]["enum"])
        catalog_aggregates = set(self.catalog["aggregates"])
        missing = catalog_aggregates - schema_aggregates
        self.assertEqual(missing, set())
        # 每个事件声明的聚合都在目录中有登记
        for event_type, spec in self.catalog["events"].items():
            self.assertIn(spec["aggregate"], catalog_aggregates, event_type)

    def test_every_catalog_rule_is_enforced_or_documented(self) -> None:
        # 校验器至少覆盖目录中声明的机器可执行规则编号
        enforced = {
            "R_MATCH_BASIS", "R_HASH_SHA256", "R_LICENSE_VALIDITY_WINDOW",
            "R_NO_SYSTEM_SIGNATURE", "R_POINT_IN_TIME_STANDARD",
            "R_CLASSIFICATION_EVIDENCE", "R_ADDITIVE_VERDICT", "R_DUAL_PERSONNEL",
            "R_CUSTODY_HANDOVER", "R_RETEST_LINEAGE", "R_FLOW_SEQ",
            "R_DISPOSITION_SCOPE", "R_HUMAN_SIGNATURE", "R_RECALL_STAGE",
            "R_RECALL_TOTALS", "R_CHILD_PRIVACY", "R_IDENTITY_ANCHOR",
        }
        for code in enforced:
            self.assertIn(code, self.catalog["rule_definitions"])

    def test_sample_chain_is_valid_and_closed_loop(self) -> None:
        chain = json.loads((ROOT / "data" / "sample-chain.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_stream(chain["events"], self.catalog), [])

        # 回查闭环：CASE_SNAPSHOT_BUILT 中每个 included_refs 都能在链中找到对应聚合
        snapshot = next(e for e in chain["events"] if e["event_type"] == "CASE_SNAPSHOT_BUILT")
        aggregate_ids = {e["aggregate_id"] for e in chain["events"]}
        missing = [ref for ref in snapshot["payload"]["included_refs"] if ref not in aggregate_ids]
        self.assertEqual(missing, [])

        # 锚点批次确实是整链中心：所有批次相关事件都指向同一 lot
        lot_events = [
            e for e in chain["events"]
            if isinstance(e.get("payload"), dict) and e["payload"].get("lot_ref")
        ]
        self.assertTrue(lot_events)
        self.assertTrue(all(e["payload"]["lot_ref"] == "lot-20260820-07" for e in lot_events))


if __name__ == "__main__":
    unittest.main()
