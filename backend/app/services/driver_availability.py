"""司机可派车判断：司机列表、司机详情与调度派车共用的同一份实现。

判断口径：按驾驶证号取到司机档案，核对其准驾车型、从业资格与出勤状态，
统一给出「可派车 / 不可派车（原因）」的结论。三处消费方都从这里拿结果，
以后调整条件只改这一个文件，不要再各写一遍。
"""
from __future__ import annotations

from typing import Any

from app.store import store

DRIVER_MODULE = "driver"

# 从业资格出现这些取值时不可派车；未登记（空值）同样不可派车
QUALIFICATION_BLOCK = {"无效", "已过期", "过期", "注销", "未办理"}
# 出勤状态出现这些取值时不可派车；未登记（空值）同样不可派车
ATTENDANCE_BLOCK = {"休假", "停工", "停职", "缺勤", "离职", "已离职"}


def find_driver(key: str) -> dict[str, Any] | None:
    """按驾驶证号取司机档案；兼容驾驶员编号与姓名，三处共用一个查找入口。"""
    key = key.strip()
    if not key:
        return None
    rows = store.rows(DRIVER_MODULE)
    for field in ("驾驶证号", "驾驶员编号", "驾驶员姓名"):
        for row in rows:
            if str(row.get(field) or "").strip() == key:
                return row
    return None


def assess_driver(
    driver: dict[str, Any] | None,
    *,
    required_class: str = "",
) -> dict[str, Any]:
    """按驾驶证号取到的准驾车型、从业资格与出勤状态给出统一结论。

    返回 {"可派车": bool, "结论": str, "原因": [str, ...]}。
    调度派车传入指派车辆的车型类别（required_class）时，顺带核验准驾车型是否覆盖。
    """
    if driver is None:
        return _verdict(["按驾驶证号未取到司机档案"])
    reasons: list[str] = []
    license_no = str(driver.get("驾驶证号") or "").strip()
    vehicle_class = str(driver.get("准驾车型") or "").strip()
    if not license_no:
        reasons.append("驾驶证号缺失，无法核验准驾车型")
    elif not vehicle_class:
        reasons.append(f"驾驶证号「{license_no}」未登记准驾车型")
    required_class = required_class.strip()
    if vehicle_class and required_class and required_class not in vehicle_class:
        reasons.append(f"准驾车型「{vehicle_class}」不含「{required_class}」")
    qualification = str(driver.get("从业资格") or "").strip()
    if not qualification:
        reasons.append("从业资格未登记")
    elif qualification in QUALIFICATION_BLOCK:
        reasons.append(f"从业资格为「{qualification}」")
    attendance = str(driver.get("出勤状态") or "").strip()
    if not attendance:
        reasons.append("出勤状态未登记")
    elif attendance in ATTENDANCE_BLOCK:
        reasons.append(f"出勤状态为「{attendance}」")
    return _verdict(reasons)


def attach_conclusion(row: dict[str, Any], *, required_class: str = "") -> dict[str, Any]:
    """给一条司机档案附上统一结论后返回副本；不改库里的原始档案与出勤记录。"""
    verdict = assess_driver(row, required_class=required_class)
    enriched = dict(row)
    enriched["可派车"] = verdict["可派车"]
    enriched["可派车原因"] = verdict["原因"]
    if verdict["可派车"]:
        enriched["可派车结论"] = verdict["结论"]
    else:
        enriched["可派车结论"] = f"{verdict['结论']}：{'；'.join(verdict['原因'])}"
    return enriched


def _verdict(reasons: list[str]) -> dict[str, Any]:
    ok = not reasons
    return {"可派车": ok, "结论": "可派车" if ok else "不可派车", "原因": reasons}
