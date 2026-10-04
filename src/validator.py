"""校验领域事件信封的基础字段。"""

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).parents[1] / "contracts" / "domain.schema.json"

_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

REQUIRED = tuple(_SCHEMA["required"])
EVENT_TYPES = tuple(_SCHEMA["properties"]["event_type"]["enum"])
AGGREGATE_TYPES = tuple(_SCHEMA["properties"]["aggregate_type"]["enum"])


def validate_event(record: dict) -> list[str]:
    errors = [f"缺少字段：{name}" for name in REQUIRED if name not in record]
    if "version" in record and (not isinstance(record["version"], int) or record["version"] < 1):
        errors.append("version 必须是正整数")
    if "event_type" in record and record["event_type"] not in EVENT_TYPES:
        errors.append("event_type 未在领域事件登记表中")
    if "aggregate_type" in record and record["aggregate_type"] not in AGGREGATE_TYPES:
        errors.append("aggregate_type 未在领域对象登记表中")
    return errors
