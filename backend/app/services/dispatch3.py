"""运力调度业务规则：状态流转、字段校验与筛选口径都收在这里。

派车校验不在这里另写判断：指派调度时统一调用
app.services.driver_availability 的可派车结论，与司机列表、司机详情同口径。
"""
from __future__ import annotations

from typing import Any

from app.services.driver_availability import assess_driver, find_driver
from app.store import store

MODULE = "dispatch3"
FLEET_MODULE = "fleet"
REQUIRED_FIELDS = ["调度编号", "关联委托", "指派车辆"]
ARCHIVE_FIELDS = ["调度编号", "关联委托", "指派车辆", "指派司机", "计划发出", "预计到达", "调度人员", "调度状态"]
STATUS_ORDER = ["待调度", "已调度", "运输中", "已抵达"]
ACTION_RULES = {"指派调度": "已调度", "确认发出": "运输中", "确认抵达": "已抵达"}
NEGATIVE_ACTIONS = []
DISPATCH_ACTION = "指派调度"


class Dispatch3Service:
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
            rows = [row for row in rows if keyword in str(row.get("调度编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

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
            return None, f"调度任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于运力调度可执行范围"
        if action == DISPATCH_ACTION:
            block = self._dispatch_block_message(entry)
            if block:
                return None, block
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"调度任务已{action}"

    def _dispatch_block_message(self, entry: dict[str, Any]) -> str | None:
        """调度派车校验：与司机列表、司机详情同一份可派车判断，不可派车就拦下。"""
        vehicle_class, block = _assigned_vehicle_class(entry)
        if block:
            return f"调度派车校验未通过：{block}"
        driver_key = str(entry.get("指派司机") or "").strip()
        if not driver_key:
            return "调度派车校验未通过：未填写指派司机"
        driver = find_driver(driver_key)
        verdict = assess_driver(driver, required_class=vehicle_class)
        if verdict["可派车"]:
            return None
        name = str((driver or {}).get("驾驶员姓名") or driver_key)
        return f"调度派车校验未通过：司机「{name}」{verdict['结论']}（{'；'.join(verdict['原因'])}）"


def _assigned_vehicle_class(entry: dict[str, Any]) -> tuple[str, str | None]:
    """按指派车辆取车型类别，供准驾车型核验；查不到档案时给出拦下原因。"""
    vehicle_key = str(entry.get("指派车辆") or "").strip()
    if not vehicle_key:
        return "", "未填写指派车辆"
    for row in store.rows(FLEET_MODULE):
        keys = {str(row.get("车辆编号") or "").strip(), str(row.get("车牌号码") or "").strip()}
        if vehicle_key in keys:
            return str(row.get("车型类别") or "").strip(), None
    return "", f"指派车辆「{vehicle_key}」未登记车辆档案，无法核验准驾车型"
