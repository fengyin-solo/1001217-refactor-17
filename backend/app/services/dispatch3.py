"""运力调度业务规则：状态流转、字段校验与筛选口径都收在这里。

调度派车对司机的校验不在这里另写规则，统一调用司机域的
``DriverService.eligibility_verdict``（底层为 driver_eligibility），
与司机列表、司机详情共用同一份可派车口径。
"""
from __future__ import annotations

from typing import Any

from app.services.driver import DriverService
from app.store import store

MODULE = "dispatch3"
REQUIRED_FIELDS = ["调度编号", "关联委托", "指派车辆"]
STATUS_ORDER = ["待调度", "已调度", "运输中", "已抵达"]
ACTION_RULES = {"指派调度": "已调度", "确认发出": "运输中", "确认抵达": "已抵达"}
NEGATIVE_ACTIONS = []


class Dispatch3Service:
    def __init__(self) -> None:
        self._drivers = DriverService()

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
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def check_driver_dispatch(
        self,
        license_no: str | None,
        *,
        required_vehicle_type: str | None = None,
    ) -> dict[str, Any]:
        """派车前的司机校验：按驾驶证号取司机，套用统一可派车口径。

        返回统一结论（``dispatchable`` / ``label`` / ``reasons`` 等），
        调度页面与其他入口一样只展示、不改写结论。
        """
        driver = self._drivers.find_by_license(str(license_no or "").strip())
        return self._drivers.eligibility_verdict(
            driver,
            license_no=str(license_no or "").strip(),
            required_vehicle_type=required_vehicle_type,
        )

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        license_no: str | None = None,
        required_vehicle_type: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, dict[str, Any] | None]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"调度任务 {entry_id} 不存在或已归档", None
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于运力调度可执行范围", None
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里", None

        # 「指派调度」即派车动作：必须通过统一的可派车校验，
        # 不允许列表说不符、调度却照样派得出去。
        verdict: dict[str, Any] | None = None
        if action == "指派调度":
            normalized_license = str(license_no or entry.get("指派司机驾驶证号") or "").strip()
            verdict = self.check_driver_dispatch(
                normalized_license, required_vehicle_type=required_vehicle_type
            )
            if not verdict["dispatchable"]:
                return None, "派车校验未通过：" + "；".join(verdict["reasons"]), verdict
            entry["指派司机驾驶证号"] = normalized_license

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"调度任务已{action}", verdict
