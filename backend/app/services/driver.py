"""司机管理业务规则：状态流转、字段校验与筛选口径都收在这里。

可派车结论不在本模块自行判断，统一调用
``app.services.driver_eligibility``，与司机详情、调度派车共用同一份口径。
"""
from __future__ import annotations

from typing import Any

from app.services.driver_eligibility import evaluate_driver
from app.store import store

MODULE = "driver"
REQUIRED_FIELDS = ["驾驶员编号", "驾驶员姓名", "驾驶证号"]
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
        with_eligibility: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("驾驶员编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        if with_eligibility:
            page_rows = [self._attach_eligibility(row) for row in page_rows]
        return page_rows, total

    def get_entry(
        self,
        entry_id: int,
        *,
        with_eligibility: bool = False,
    ) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._attach_eligibility(entry) if with_eligibility else entry

    def find_by_license(self, license_no: str) -> dict[str, Any] | None:
        """按驾驶证号定位唯一司机档案；列表、详情与调度派车都用这个键。"""
        normalized = str(license_no or "").strip()
        if not normalized:
            return None
        for row in store.rows(MODULE):
            if str(row.get("驾驶证号", "")).strip() == normalized:
                return row
        return None

    def eligibility_verdict(
        self,
        driver: dict[str, Any] | None,
        *,
        license_no: str | None = None,
        required_vehicle_type: str | None = None,
    ) -> dict[str, Any]:
        """对外暴露统一结论，供调度派车等其他服务调用，避免重复实现。"""
        if license_no is None and driver is not None:
            license_no = driver.get("驾驶证号")
        return evaluate_driver(
            driver,
            license_no=license_no,
            required_vehicle_type=required_vehicle_type,
        )

    @staticmethod
    def _attach_eligibility(row: dict[str, Any]) -> dict[str, Any]:
        # 复制后再挂结论，既有司机档案行本身一个字段都不动。
        entry = dict(row)
        entry["可派车"] = evaluate_driver(row)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
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
