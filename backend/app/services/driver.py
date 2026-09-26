"""司机管理业务规则：状态流转、字段校验与筛选口径都收在这里。

可派车判断不在本文件重复实现：列表与详情统一引用
app.services.driver_availability，调度派车校验用的也是同一份。
"""
from __future__ import annotations

from typing import Any

from app.services.driver_availability import attach_conclusion
from app.store import store

MODULE = "driver"
REQUIRED_FIELDS = ["驾驶员编号", "驾驶员姓名", "驾驶证号"]
ARCHIVE_FIELDS = ["驾驶员编号", "驾驶员姓名", "驾驶证号", "准驾车型", "从业资格", "联系电话", "所属车队", "出勤状态"]
STATUS_ORDER = ["空闲", "出车中", "休假", "已离职"]
ACTION_RULES = {"派车出勤": "出车中", "登记休假": "休假", "办理离职": "已离职"}
NEGATIVE_ACTIONS = []


class DriverService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("驾驶员编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [attach_conclusion(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return attach_conclusion(row)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values[field] for field in ARCHIVE_FIELDS if values.get(field) is not None})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"驾驶员 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于司机管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"驾驶员已{action}"
