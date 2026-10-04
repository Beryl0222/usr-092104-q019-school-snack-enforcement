"""校验校园跨界零食处置领域事件。

信封七字段的基础校验保持不变；在此之上，事件与聚合的合法取值、各事件
必填载荷以及语义规则均以 contracts/event-catalog.json 为单一事实源，
校验器只负责执行目录中登记的规则（见 rule_definitions）。

用法：
    validate_event(record)          # 单事件信封+载荷+语义规则
    validate_stream(records)        # 跨事件：版本递增、流向序号等链路规则
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

REQUIRED = ("event_id", "event_type", "aggregate_type", "aggregate_id", "occurred_at", "version", "summary")

_CATALOG_PATH = Path(__file__).resolve().parents[1] / "contracts" / "event-catalog.json"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$"
)
_HASH_KEY_SUFFIX = ("_hash",)
_DISPOSITION_SCOPES = {"link", "store", "lot", "manufacturer"}
_RECALL_STAGES = ("notified", "delisted", "returned", "unrecoverable")
_CHILD_FACING_AUDIENCES = {"school", "parent", "public"}
_CHILD_IDENTITY_KEYS = {"child_identity", "child_name", "buyer_child", "purchaser_child_info"}
_ADDITIVE_VERDICTS = {"permitted", "not_permitted", "out_of_range"}


def load_catalog(path: str | Path | None = None) -> dict:
    return json.loads(Path(path or _CATALOG_PATH).read_text(encoding="utf-8"))


def _parse_dt(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _check_hashes(payload: dict) -> list[str]:
    errors = []
    for key, value in payload.items():
        if key.endswith(_HASH_KEY_SUFFIX) and isinstance(value, str):
            if not _SHA256_RE.match(value):
                errors.append(f"{key} 必须是 64 位小写十六进制 SHA-256")
    return errors


def _check_standard_at_time(entries, occurred_at: datetime, field: str) -> list[str]:
    """R_POINT_IN_TIME_STANDARD：引用的标准必须给出版本与生效时间，且行为时已生效。"""
    errors = []
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return [f"{field} 必须列出标准编号、版本与生效时间"]
    for i, std in enumerate(entries):
        if not isinstance(std, dict) or "standard_no" not in std:
            continue  # 允许纯文字备注条目；结构化条目才受版本/时效约束
        label = f"{field}[{i}]({std.get('standard_no', '?')})"
        if not std.get("version"):
            errors.append(f"{label} 缺少标准版本号，无法确认行为时有效版本")
        effective_at = _parse_dt(std.get("effective_at"))
        if effective_at is None:
            errors.append(f"{label} 缺少 effective_at")
        elif effective_at > occurred_at:
            errors.append(f"{label} 生效时间晚于行为时间，不能作为行为时有效标准")
    return errors


def _check_event_semantics(event_type: str, record: dict, payload: dict) -> list[str]:
    occurred_at = _parse_dt(record.get("occurred_at"))
    errors = _check_hashes(payload)

    # R_NO_SYSTEM_SIGNATURE：冲突提示禁止携带签字字段
    if event_type in ("LICENSE_CONFLICT_FLAGGED", "CLASSIFICATION_CONFLICT_FLAGGED", "CONFLICT_FLAGGED"):
        for forbidden in ("signed_by", "system_signed"):
            if forbidden in payload:
                errors.append(f"冲突提示不得携带 {forbidden}：系统只提示，执法效力以人工签字为准")

    if event_type == "LISTING_LINKED":
        # R_MATCH_BASIS：确认同源不得仅凭图片
        status = payload.get("linkage_status")
        basis = payload.get("match_basis")
        basis_list = basis if isinstance(basis, list) else [basis]
        if status == "confirmed":
            non_image = [b for b in basis_list if b and b != "image_only"]
            if not non_image and "manual_confirmation" not in basis_list:
                errors.append("同源关联已确认，但匹配依据仅有 image_only；须补充客观依据或人工确认")
            if "manual_confirmation" in basis_list and not payload.get("confirmed_by"):
                errors.append("人工确认同源必须留存 confirmed_by")
        elif basis_list == ["image_only"] and status != "proposed":
            errors.append("仅凭图片相似度只能生成 proposed 线索，不得自动合并")

    elif event_type == "LICENSE_VERIFIED":
        # R_LICENSE_VALIDITY_WINDOW
        valid_from, valid_to = _parse_dt(payload.get("valid_from")), _parse_dt(payload.get("valid_to"))
        if valid_from and valid_to and valid_from >= valid_to:
            errors.append("许可证 valid_from 必须早于 valid_to")

    elif event_type == "LOT_CLASSIFIED":
        # R_POINT_IN_TIME_STANDARD / R_CLASSIFICATION_EVIDENCE
        if occurred_at:
            errors += _check_standard_at_time(payload.get("effective_standards"), occurred_at, "effective_standards")
        evidence = payload.get("physical_evidence_refs")
        if payload.get("assessed_category") != "unresolved" and not evidence:
            errors.append("分类判定结论非 unresolved 时必须提供 physical_evidence_refs 实物证据")

    elif event_type == "INGREDIENT_RULE_EVALUATED":
        # R_POINT_IN_TIME_STANDARD / R_ADDITIVE_VERDICT
        if occurred_at:
            errors += _check_standard_at_time(payload.get("rule_basis"), occurred_at, "rule_basis")
        additives = payload.get("additives", [])
        if not isinstance(additives, list):
            errors.append("additives 必须是列表")
            additives = []
        bad_present = False
        for i, add in enumerate(additives):
            verdict = add.get("verdict") if isinstance(add, dict) else None
            if verdict not in _ADDITIVE_VERDICTS:
                errors.append(f"additives[{i}] verdict 必须是 permitted/not_permitted/out_of_range")
            if verdict in ("not_permitted", "out_of_range"):
                bad_present = True
        if bad_present and payload.get("overall_verdict") == "compliant":
            errors.append("存在不允许或超限添加剂时 overall_verdict 不得为 compliant")

    elif event_type == "SAMPLE_PURCHASED":
        # R_DUAL_PERSONNEL
        if len(payload.get("buyers", [])) < 2:
            errors.append("购样须有两名及以上抽样人员（buyers）")

    elif event_type == "SAMPLE_SEALED":
        # R_DUAL_PERSONNEL
        if len(payload.get("sealers", [])) < 2:
            errors.append("封存须有两名及以上人员（sealers）")

    elif event_type == "SAMPLE_TRANSFERRED":
        # R_CUSTODY_HANDOVER
        if not payload.get("from_party") or not payload.get("to_party"):
            errors.append("样品移交须记录交出方与接收方")
        if payload.get("seal_intact") is not True:
            errors.append("移交时封条完好性 seal_intact 必须为 true（异常须另行立案记录）")
        if payload.get("both_parties_signed") is not True:
            errors.append("样品交接须双方签字（both_parties_signed=true）")

    elif event_type == "TEST_REPORT_ISSUED":
        # R_RETEST_LINEAGE
        if payload.get("test_round") == "retest":
            for required in ("original_report_ref", "dispute_ref"):
                if not payload.get(required):
                    errors.append(f"复检报告必须携带 {required}，以回溯初检与异议")

    elif event_type in ("DECISION_DRAFTED", "DECISION_SIGNED"):
        # R_DISPOSITION_SCOPE
        if payload.get("scope") not in _DISPOSITION_SCOPES:
            errors.append("处置 scope 必须是 link/store/lot/manufacturer 之一")
        if not payload.get("scope_targets"):
            errors.append("处置对象 scope_targets 不得为空，避免按标题误伤")
        if event_type == "DECISION_SIGNED":
            # R_HUMAN_SIGNATURE
            if not payload.get("signed_by") or not payload.get("signed_at"):
                errors.append("执法决定必须由具备资格人员 signed_by 并记录 signed_at")
            if payload.get("system_signed") is True:
                errors.append("系统不得代替执法人员签字")

    elif event_type == "RECALL_UPDATED":
        # R_RECALL_STAGE
        if payload.get("stage") not in _RECALL_STAGES:
            errors.append("召回 stage 必须是 notified/delisted/returned/unrecoverable")
        if not isinstance(payload.get("quantity"), (int, float)) or payload.get("quantity") < 0:
            errors.append("召回 quantity 必须为非负数")

    elif event_type == "RECALL_CLOSED":
        # R_RECALL_TOTALS
        totals = payload.get("totals")
        if not isinstance(totals, dict) or any(stage not in totals for stage in _RECALL_STAGES):
            errors.append("召回关闭 totals 必须同时包含四阶段数量")
        else:
            for stage in _RECALL_STAGES:
                if not isinstance(totals.get(stage), (int, float)) or totals[stage] < 0:
                    errors.append(f"totals.{stage} 必须为非负数")

    elif event_type == "NOTICE_PUBLISHED":
        # R_CHILD_PRIVACY
        if payload.get("audience") in _CHILD_FACING_AUDIENCES:
            if payload.get("child_identity_protected") is not True:
                errors.append("面向学校/家长/公众的通知必须确认 child_identity_protected=true")
        leaked = _CHILD_IDENTITY_KEYS & set(payload)
        if leaked:
            errors.append(f"通知载荷禁止出现儿童身份字段：{sorted(leaked)}")

    return errors


def validate_event(record: dict, catalog: dict | None = None) -> list[str]:
    """校验单个事件：信封 → 已知事件/聚合 → 必填载荷 → 语义规则。"""
    catalog = catalog or load_catalog()
    errors = [f"缺少字段：{name}" for name in REQUIRED if name not in record]
    if errors:
        return errors

    if not isinstance(record["version"], int) or record["version"] < 1:
        errors.append("version 必须是正整数")

    events = catalog["events"]
    event_type = record.get("event_type")
    if event_type not in events:
        errors.append(f"未知事件类型：{event_type}")
        return errors

    spec = events[event_type]
    if record.get("aggregate_type") != spec["aggregate"]:
        errors.append(
            f"{event_type} 的 aggregate_type 必须是 {spec['aggregate']}，实际为 {record.get('aggregate_type')}"
        )

    if _parse_dt(record.get("occurred_at")) is None:
        errors.append("occurred_at 必须是合法 date-time")

    payload = record.get("payload")
    if payload is None:
        payload = {}
        errors.append("缺少 payload 事件载荷")
    elif not isinstance(payload, dict):
        errors.append("payload 必须是对象")
        return errors

    for field in spec.get("payload_required", []):
        if field not in payload or payload[field] in (None, "", []):
            errors.append(f"{event_type} 缺少必填载荷字段：{field}")

    errors += _check_event_semantics(event_type, record, payload)
    return errors


def validate_stream(records: list[dict], catalog: dict | None = None) -> list[str]:
    """校验跨事件链路规则：

    1. 同一 aggregate_id 的 version 从 1 连续递增；
    2. 同一流向 trace_no 的节点 seq 从 1 连续递增；
    3. LISTING_REVISED 不得更换 lot_ref（改标题不改批次身份，P2）。
    """
    catalog = catalog or load_catalog()
    errors = []

    versions: dict[str, list[tuple[int, str]]] = {}
    flow_seq: dict[str, list[int]] = {}
    listing_lot: dict[str, object] = {}

    for idx, record in enumerate(records):
        where = f"第 {idx + 1} 条事件({record.get('event_id', '?')})"
        errors += [f"{where}：{e}" for e in validate_event(record, catalog)]

        agg_id = record.get("aggregate_id")
        version = record.get("version")
        if isinstance(agg_id, str) and isinstance(version, int):
            versions.setdefault(agg_id, []).append((version, where))

        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if record.get("event_type") == "FLOW_NODE_RECORDED":
            trace_no = payload.get("trace_no")
            seq = payload.get("seq")
            if isinstance(trace_no, str) and isinstance(seq, int):
                flow_seq.setdefault(trace_no, []).append(seq)

        if record.get("event_type") == "LISTING_CAPTURED" and payload.get("lot_ref"):
            listing_lot[agg_id] = payload["lot_ref"]
        if record.get("event_type") == "LISTING_REVISED":
            lot_ref = payload.get("lot_ref")
            anchored = listing_lot.get(agg_id)
            if anchored and lot_ref and lot_ref != anchored:
                errors.append(f"{where}：LISTING_REVISED 更换了 lot_ref，改标题不得改变批次身份")
            if anchored is None and lot_ref:
                listing_lot[agg_id] = lot_ref

    for agg_id, seen in versions.items():
        nums = [v for v, _ in seen]
        if nums != list(range(1, len(nums) + 1)):
            errors.append(f"聚合 {agg_id} 版本号须从 1 连续递增，实际为 {nums}")

    for trace_no, seqs in flow_seq.items():
        if sorted(seqs) != list(range(1, len(seqs) + 1)):
            errors.append(f"流向 {trace_no} 节点 seq 须从 1 连续递增，实际为 {sorted(seqs)}")

    return errors
