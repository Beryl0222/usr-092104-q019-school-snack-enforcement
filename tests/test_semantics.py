"""语义规则正负样例：系统只提示不签字、改标题不改批次、同源不唯图片、
行为时标准+实物证据、复检留痕、交接双人、召回四阶段、儿童隐私。"""

import unittest

from src.validator import load_catalog, validate_event, validate_stream


def base(event_type: str, payload: dict, aggregate_id: str = "a-1", version: int = 1,
         occurred_at: str = "2026-09-17T10:00:00+08:00") -> dict:
    return {
        "event_id": f"evt-{event_type}-{aggregate_id}-{version}",
        "event_type": event_type,
        "aggregate_type": None,  # 由目录填充，见 setUp
        "aggregate_id": aggregate_id,
        "occurred_at": occurred_at,
        "version": version,
        "summary": "测试事件",
        "payload": payload,
    }


class SemanticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_catalog()

    def _event(self, *args, **kwargs) -> dict:
        record = base(*args, **kwargs)
        record["aggregate_type"] = self.catalog["events"][record["event_type"]]["aggregate"]
        return record

    # P4 系统提示不得代替签字
    def test_conflict_tip_cannot_carry_signature(self) -> None:
        record = self._event("CONFLICT_FLAGGED", {
            "subject_refs": ["lot-1"], "conflict_code": "TITLE_CATEGORY_MISMATCH",
            "detail": "x", "evidence_refs": [{"ref_type": "t", "ref_id": "x"}],
            "severity": "medium", "signed_by": "系统",
        })
        self.assertTrue(any("signed_by" in e for e in validate_event(record, self.catalog)))

    # P4 执法决定必须人工签字
    def test_signed_decision_requires_human(self) -> None:
        payload = {
            "decision_no": "D1", "scope": "link", "scope_targets": [{"kind": "link", "id": "lst-1"}],
            "result": "delisting_order", "legal_basis": ["食品安全法"],
            "evidence_chain_refs": ["rpt-1"], "signed_at": "2026-09-26T10:00:00+08:00",
            "decision_doc_hash": "a" * 64,
        }
        missing_signer = self._event("DECISION_SIGNED", dict(payload))
        self.assertTrue(any("signed_by" in e for e in validate_event(missing_signer, self.catalog)))

        payload["signed_by"] = "赵建国(执法证号010000ZZ)"
        self.assertEqual(validate_event(self._event("DECISION_SIGNED", payload), self.catalog), [])

    def test_system_signed_decision_rejected(self) -> None:
        record = self._event("DECISION_SIGNED", {
            "decision_no": "D1", "scope": "store", "scope_targets": [{"kind": "store", "id": "s-1"}],
            "result": "fine", "legal_basis": ["x"], "evidence_chain_refs": ["r-1"],
            "signed_by": "系统自动", "signed_at": "2026-09-26T10:00:00+08:00",
            "system_signed": True, "decision_doc_hash": "b" * 64,
        })
        self.assertTrue(any("系统不得代替" in e for e in validate_event(record, self.catalog)))

    # P7 处置必须精确到对象
    def test_decision_requires_scope_and_targets(self) -> None:
        record = self._event("DECISION_DRAFTED", {
            "decision_no": "D2", "scope": "by_title", "scope_targets": [],
            "proposed_result": "delisting_order", "basis_refs": [],
            "drafted_by": "王敏", "drafted_at": "2026-09-25T10:00:00+08:00",
        })
        errors = validate_event(record, self.catalog)
        self.assertTrue(any("scope" in e for e in errors))
        self.assertTrue(any("scope_targets" in e for e in errors))

    # P5 同源关联不得仅凭图片自动合并
    def test_confirmed_linkage_image_only_rejected(self) -> None:
        payload = {
            "linkage_no": "L1", "listing_refs": ["lst-1", "lst-2"],
            "match_basis": ["image_only"], "evidence_refs": [{"ref_type": "t", "ref_id": "x"}],
            "linkage_status": "confirmed",
        }
        self.assertTrue(validate_event(self._event("LISTING_LINKED", payload), self.catalog))

    def test_proposed_image_only_linkage_allowed(self) -> None:
        payload = {
            "linkage_no": "L1", "listing_refs": ["lst-1", "lst-2"],
            "match_basis": ["image_only"], "evidence_refs": [{"ref_type": "t", "ref_id": "x"}],
            "linkage_status": "proposed", "image_similarity_score": 0.91,
        }
        self.assertEqual(validate_event(self._event("LISTING_LINKED", payload), self.catalog), [])

    def test_manual_confirmation_keeps_confirmer(self) -> None:
        payload = {
            "linkage_no": "L1", "listing_refs": ["lst-1", "lst-2"],
            "match_basis": ["manual_confirmation"], "evidence_refs": [{"ref_type": "t", "ref_id": "x"}],
            "linkage_status": "confirmed",
        }
        self.assertTrue(any("confirmed_by" in e for e in validate_event(self._event("LISTING_LINKED", payload), self.catalog)))

    # P3 分类按行为时有效标准
    def test_classification_requires_effective_standard_version(self) -> None:
        record = self._event("LOT_CLASSIFIED", {
            "lot_ref": "lot-1", "claimed_category": "starch_product", "assessed_category": "candy",
            "effective_standards": [{"standard_no": "GB 2760"}],  # 缺 version/effective_at
            "physical_evidence_refs": [{"ref_type": "test_report", "ref_id": "r-1"}],
        })
        errors = validate_event(record, self.catalog)
        self.assertTrue(any("版本" in e for e in errors))
        self.assertTrue(any("effective_at" in e for e in errors))

    def test_future_standard_cannot_judge_past_behavior(self) -> None:
        record = self._event("LOT_CLASSIFIED", {
            "lot_ref": "lot-1", "claimed_category": "candy", "assessed_category": "candy",
            "effective_standards": [{"standard_no": "GB 2760", "version": "2027新版",
                                     "effective_at": "2027-01-01T00:00:00+08:00"}],
            "physical_evidence_refs": [{"ref_type": "test_report", "ref_id": "r-1"}],
        })
        self.assertTrue(any("行为时有效标准" in e for e in validate_event(record, self.catalog)))

    def test_unresolved_allowed_with_insufficient_evidence(self) -> None:
        # 证据不足时结论只能是 unresolved；已有的薄弱证据如实留存
        record = self._event("LOT_CLASSIFIED", {
            "lot_ref": "lot-1", "claimed_category": "candy", "assessed_category": "unresolved",
            "effective_standards": [{"standard_no": "GB 2760", "version": "2014",
                                     "effective_at": "2015-05-24T00:00:00+08:00"}],
            "physical_evidence_refs": [{"ref_type": "listing_snapshot", "ref_id": "snp-1"}],
            "reasoning": "仅有页面截图、无实物，不能定性",
        })
        self.assertEqual(validate_event(record, self.catalog), [])

    # P3 添加剂：超限不得判合规
    def test_additive_out_of_range_cannot_be_compliant(self) -> None:
        record = self._event("INGREDIENT_RULE_EVALUATED", {
            "lot_ref": "lot-1",
            "rule_basis": [{"standard_no": "GB 2760", "version": "2014",
                            "effective_at": "2015-05-24T00:00:00+08:00"}],
            "declared_ingredients": ["白砂糖"],
            "additives": [{"name": "诱惑红", "verdict": "out_of_range"}],
            "physical_evidence_refs": [{"ref_type": "test_report", "ref_id": "r-1"}],
            "overall_verdict": "compliant",
        })
        self.assertTrue(any("overall_verdict" in e for e in validate_event(record, self.catalog)))

    # P6 购样双人
    def test_purchase_requires_two_buyers(self) -> None:
        record = self._event("SAMPLE_PURCHASED", {
            "sample_no": "S1", "lot_ref": "lot-1", "purchased_from_ref": "s-1",
            "purchased_at": "2026-09-10T10:00:00+08:00", "buyers": ["王敏"],
            "quantity": "2袋", "purchase_evidence_refs": [{"ref_type": "t", "ref_id": "x"}],
        })
        self.assertTrue(any("两名" in e for e in validate_event(record, self.catalog)))

    # P6 交接双方签字、封条完好
    def test_transfer_requires_dual_signature(self) -> None:
        record = self._event("SAMPLE_TRANSFERRED", {
            "sample_ref": "spl-1", "from_party": "局", "to_party": "所",
            "transferred_at": "2026-09-12T09:30:00+08:00", "seal_intact": True,
            "handover_doc_ref": {"ref_type": "t", "ref_id": "h"}, "both_parties_signed": False,
        })
        self.assertTrue(any("双方签字" in e for e in validate_event(record, self.catalog)))

    # P6 复检必须回溯初检与异议
    def test_retest_requires_lineage(self) -> None:
        record = self._event("TEST_REPORT_ISSUED", {
            "sample_ref": "spl-1", "report_no": "R2", "testing_org": "市院",
            "issued_at": "2026-09-23T16:00:00+08:00", "test_round": "retest",
            "test_items": [], "overall_conclusion": "不合格", "report_hash": "c" * 64,
        })
        errors = validate_event(record, self.catalog)
        self.assertTrue(any("original_report_ref" in e for e in errors))
        self.assertTrue(any("dispute_ref" in e for e in errors))

    # P9 召回四阶段
    def test_recall_update_stage_enumerated(self) -> None:
        record = self._event("RECALL_UPDATED", {
            "recall_no": "R1", "stage": "已删除", "quantity": 10,
            "recorded_at": "2026-09-28T10:00:00+08:00",
        })
        self.assertTrue(any("stage" in e for e in validate_event(record, self.catalog)))

    def test_recall_close_requires_four_totals(self) -> None:
        record = self._event("RECALL_CLOSED", {
            "recall_no": "R1", "closed_at": "2026-10-03T09:00:00+08:00",
            "totals": {"notified": 100, "delisted": 80, "returned": 50},
        })
        self.assertTrue(any("四阶段" in e for e in validate_event(record, self.catalog)))

    # P8 儿童隐私
    def test_parent_notice_must_protect_child_identity(self) -> None:
        record = self._event("NOTICE_PUBLISHED", {
            "notice_no": "N1", "audience": "parent", "channel": "家委会",
            "title": "提示", "content_hash": "d" * 64,
            "published_at": "2026-09-27T10:00:00+08:00",
            "child_identity_protected": False,
        })
        self.assertTrue(any("child_identity_protected" in e for e in validate_event(record, self.catalog)))

    def test_notice_cannot_contain_child_identity_fields(self) -> None:
        record = self._event("NOTICE_PUBLISHED", {
            "notice_no": "N1", "audience": "school", "channel": "教育局",
            "title": "提示", "content_hash": "d" * 64,
            "published_at": "2026-09-27T10:00:00+08:00",
            "child_identity_protected": True, "child_name": "某某",
        })
        self.assertTrue(any("儿童身份字段" in e for e in validate_event(record, self.catalog)))

    # P2 改标题不改批次身份（跨事件）
    def test_revision_cannot_change_lot_identity(self) -> None:
        captured = self._event("LISTING_CAPTURED", {
            "platform": "platform_a", "platform_listing_id": "A1", "seller_ref": "s-1",
            "snapshot_ref": "snp-1", "title_at_capture": "糖果", "claimed_category": "candy",
            "lot_ref": "lot-1",
        }, aggregate_id="lst-1", version=1)
        revised = self._event("LISTING_REVISED", {
            "lot_ref": "lot-2", "revision_no": 2, "changed_fields": ["title"],
            "previous_snapshot_ref": "snp-1", "current_snapshot_ref": "snp-2",
        }, aggregate_id="lst-1", version=2)
        errors = validate_stream([captured, revised], self.catalog)
        self.assertTrue(any("批次身份" in e for e in errors))

    def test_stream_versions_must_be_sequential(self) -> None:
        first = self._event("CONFLICT_FLAGGED", {
            "subject_refs": ["x"], "conflict_code": "TITLE_CATEGORY_MISMATCH",
            "detail": "x", "evidence_refs": [{"ref_type": "t", "ref_id": "x"}], "severity": "low",
        }, aggregate_id="cnf-1", version=1)
        second = self._event("CONFLICT_FLAGGED", {
            "subject_refs": ["x"], "conflict_code": "TITLE_CATEGORY_MISMATCH",
            "detail": "x2", "evidence_refs": [{"ref_type": "t", "ref_id": "x2"}], "severity": "low",
        }, aggregate_id="cnf-1", version=3)
        self.assertTrue(any("版本号" in e for e in validate_stream([first, second], self.catalog)))

    # P6 流向序号连续（跨事件）
    def test_flow_seq_must_be_continuous(self) -> None:
        def node(seq: int) -> dict:
            return self._event("FLOW_NODE_RECORDED", {
                "trace_no": "T1", "lot_ref": "lot-1", "seq": seq, "node_type": "warehouse",
                "party_ref": "p-1", "quantity": "10袋",
                "occurred_at": "2026-08-21T10:00:00+08:00",
                "evidence_ref": {"ref_type": "t", "ref_id": f"e-{seq}"},
            }, aggregate_id="flw-1", version=seq)
        self.assertTrue(any("seq" in e for e in validate_stream([node(1), node(3)], self.catalog)))
        self.assertEqual(validate_stream([node(1), node(2)], self.catalog), [])

    # 信封底线仍在
    def test_missing_envelope_field_reported(self) -> None:
        record = {"event_id": "x"}
        self.assertTrue(validate_event(record, self.catalog))


if __name__ == "__main__":
    unittest.main()
