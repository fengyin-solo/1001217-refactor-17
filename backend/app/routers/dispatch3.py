"""运力调度接口：维护调度任务，覆盖指派调度、确认发出、确认抵达等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.dispatch3 import Dispatch3Service

router = APIRouter(prefix="/api/dispatch3", tags=["运力调度"])

service = Dispatch3Service()

LIST_FIELDS = ["调度编号", "关联委托", "指派车辆", "指派司机", "计划发出", "预计到达", "调度人员", "调度状态"]
STATUSES = ["待调度", "已调度", "运输中", "已抵达"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按调度编号检索"),
    status: str | None = Query(default=None, description="待调度、已调度、运输中、已抵达"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按调度编号与状态过滤运力调度列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出运力调度清单：返回当前过滤条件下的全量数据。

    注意：本静态路由必须排在 ``/{entry_id}`` 之前，否则会被当成 id 解析。
    """
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "dispatch3", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条调度任务明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"调度任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条调度任务，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="调度任务已登记", entry=entry)


@router.post("/dispatch-check")
def check_dispatch(payload: EntryPayload) -> dict[str, Any]:
    """派车前的司机校验：按驾驶证号 + 本次要求车型，回统一的可派车结论。

    与司机列表、司机详情用的是同一份 driver_eligibility 结论，
    这里只负责取数与透传，不另写任何判断。
    """
    license_no = str(payload.values.get("驾驶证号") or payload.values.get("指派司机驾驶证号") or "").strip()
    required_vehicle_type = payload.values.get("要求车型") or payload.values.get("准驾车型")
    return service.check_driver_dispatch(
        license_no, required_vehicle_type=required_vehicle_type
    )


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条调度任务执行指派调度、确认发出、确认抵达；不允许的动作会被拦下并说明原因。

    「指派调度」必须携带驾驶证号（可选要求车型），先走统一的可派车校验；
    校验不过时任务状态不变，并把统一结论里的原因原样带回页面。
    """
    action = str(payload.values.get("action") or "").strip()
    license_no = payload.values.get("驾驶证号") or payload.values.get("指派司机驾驶证号")
    required_vehicle_type = payload.values.get("要求车型") or payload.values.get("准驾车型")
    entry, message, verdict = service.run_action(
        entry_id,
        action,
        license_no=str(license_no) if license_no is not None else None,
        required_vehicle_type=str(required_vehicle_type)
        if required_vehicle_type is not None else None,
    )
    if entry is None:
        return ActionResult(ok=False, message=message, entry=verdict)
    return ActionResult(ok=True, message=message, entry=entry)
