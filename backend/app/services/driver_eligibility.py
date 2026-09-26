"""司机可派车判断：全平台唯一一份判定口径。

司机列表、司机详情、调度派车校验三处都必须走这里的
``evaluate_driver`` / ``evaluate_by_license``，不得在页面或
其他服务里再各写一遍判断；以后调整可派车条件，只改这一处。

判定依据（均以司机档案为基准，按驾驶证号定位）：
1. 驾驶证号对应的司机档案必须存在；
2. 准驾车型必须能识别，且派车要求车型时必须覆盖该车型；
3. 从业资格必须在有效期内（未过期 / 未失效 / 未吊销 / 未注销）；
4. 出勤状态必须为「空闲」（休假、出车中、已离职等一律不可派）。

判定结果是纯数据：``dispatchable`` + 面向页面的中文结论
（``label`` / ``reasons``）以及取到的三项依据原值，三处消费方
直接展示即可，不允许再在前端补充或改写结论。
"""
from __future__ import annotations

import re
from typing import Any, Callable

# 中国驾驶证准驾车型（含牵引车、冷链常用大型货车与客车）。
KNOWN_VEHICLE_TYPES = {
    "A1", "A2", "A3",
    "B1", "B2",
    "C1", "C2", "C3", "C4", "C5",
    "D", "E", "F", "M", "N", "P",
}

# 从业资格失效类措辞，命中任一即视为资格不可用。
INVALID_QUALIFICATION_TOKENS = ("过期", "失效", "吊销", "注销", "未取得", "无")

# 出勤状态归一化：键为规范状态，值为可识别的同义措辞。
ATTENDANCE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "空闲": ("空闲", "待命", "在岗空闲", "可派车", "可出勤"),
    "出车中": ("出车中", "运输中", "已派车", "执行任务", "任务中"),
    "休假": ("休假", "请假", "休息", "轮休"),
    "已离职": ("已离职", "离职", "离岗"),
}

# 只有「空闲」可以派车，其余出勤状态统一不可派。
AVAILABLE_ATTENDANCE = "空闲"

ELIGIBLE_LABEL = "可派车"
INELIGIBLE_LABEL = "不可派车"


def normalize_vehicle_types(value: Any) -> list[str]:
    """把「准驾车型」字段拆成规范的车型代码列表，识别不出来的内容丢弃。

    兼容 ``A2、B2`` / ``A2,B2`` / ``A2/B2`` / ``a2 b2`` 等写法。
    """
    if not value:
        return []
    tokens = re.split(r"[、,，/／\s;；]+", str(value).upper())
    result: list[str] = []
    for token in tokens:
        token = token.strip()
        if token in KNOWN_VEHICLE_TYPES and token not in result:
            result.append(token)
    return result


def normalize_attendance(value: Any) -> str | None:
    """把出勤状态归一到规范状态；无法识别时返回 ``None``。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("状态"):
        text = text[:-2]
    for canonical, synonyms in ATTENDANCE_SYNONYMS.items():
        if text == canonical or any(token in text for token in synonyms):
            return canonical
    return None


def is_qualification_valid(value: Any) -> bool:
    """从业资格是否有效：有值且不含失效类措辞。"""
    text = str(value or "").strip()
    if not text:
        return False
    return not any(token in text for token in INVALID_QUALIFICATION_TOKENS)


def evaluate_driver(
    driver: dict[str, Any] | None,
    *,
    license_no: str | None = None,
    required_vehicle_type: str | None = None,
) -> dict[str, Any]:
    """对一条司机档案给出可派车结论。

    ``driver`` 为 ``None`` 表示按驾驶证号查无此人。
    ``required_vehicle_type`` 为本次派车要求的准驾车型（调度派车时传），
    列表 / 详情不传，只核对档案车型本身是否可识别。
    """
    raw_types = driver.get("准驾车型") if driver else None
    raw_qualification = driver.get("从业资格") if driver else None
    raw_attendance = driver.get("出勤状态") if driver else None

    held_types = normalize_vehicle_types(raw_types)
    attendance = normalize_attendance(raw_attendance)
    required = (str(required_vehicle_type).strip().upper()
                if required_vehicle_type and str(required_vehicle_type).strip() else None)

    reasons: list[str] = []
    if driver is None:
        reasons.append(f"驾驶证号「{str(license_no).strip() or '—'}」查不到司机档案")
    if driver is not None and not held_types:
        reasons.append("准驾车型缺失或无法识别，无法匹配车辆")
    if driver is not None and held_types and required and required not in held_types:
        reasons.append(f"准驾车型不符：该任务要求 {required}，司机准驾为 {'、'.join(held_types)}")
    if driver is not None and not is_qualification_valid(raw_qualification):
        reasons.append("从业资格缺失或已失效")
    if driver is not None and attendance is None:
        reasons.append(f"出勤状态「{raw_attendance or '—'}」无法确认")
    if driver is not None and attendance not in (None, AVAILABLE_ATTENDANCE):
        reasons.append(f"当前出勤状态为「{attendance}」，非空闲不可派车")

    dispatchable = not reasons
    return {
        "dispatchable": dispatchable,
        "label": ELIGIBLE_LABEL if dispatchable else INELIGIBLE_LABEL,
        "reasons": reasons,
        "驾驶证号": driver.get("驾驶证号") if driver else license_no,
        "准驾车型": raw_types,
        "从业资格": raw_qualification,
        "出勤状态": raw_attendance,
        "要求车型": required_vehicle_type or None,
    }


def evaluate_by_license(
    license_no: str | None,
    lookup_driver: Callable[[str], dict[str, Any] | None],
    *,
    required_vehicle_type: str | None = None,
) -> dict[str, Any]:
    """按驾驶证号取司机档案后给结论——三个入口共用的取数方式。

    ``lookup_driver`` 由调用方的数据层提供（如 ``store.find`` 的封装），
    保证列表、详情、调度派车都按同一键（驾驶证号）定位同一份档案。
    """
    normalized = str(license_no or "").strip()
    if not normalized:
        return evaluate_driver(None, license_no=license_no,
                               required_vehicle_type=required_vehicle_type)
    return evaluate_driver(
        lookup_driver(normalized),
        license_no=normalized,
        required_vehicle_type=required_vehicle_type,
    )
