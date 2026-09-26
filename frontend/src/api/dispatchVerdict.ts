/**
 * 司机可派车结论的前端共享定义。
 *
 * 结论一律由后端 app/services/driver_eligibility.py 统一给出，
 * 司机列表、司机详情弹窗、调度派车校验三处共用这里的取值函数，
 * 前端只负责展示，绝不重新判断准驾车型 / 从业资格 / 出勤状态。
 */

/** 后端统一结论结构，字段与 driver_eligibility.evaluate_driver 对齐。 */
export interface DispatchVerdict {
  dispatchable: boolean
  label: string
  reasons: string[]
  驾驶证号?: string | null
  准驾车型?: string | null
  从业资格?: string | null
  出勤状态?: string | null
  要求车型?: string | null
}

type MaybeVerdict = { 可派车?: DispatchVerdict | null }

/** 从列表行 / 详情对象上取统一结论，缺省时给一个不会渲染出错的空壳。 */
export function resolveVerdict(source: MaybeVerdict | null | undefined): DispatchVerdict | null {
  return source?.可派车 ?? null
}

export function verdictLabel(verdict: DispatchVerdict | null): string {
  return verdict?.label ?? '—'
}

export function verdictReasons(verdict: DispatchVerdict | null): string[] {
  return verdict?.reasons ?? []
}
