<template>
  <section class="page" data-module="dispatch3">
    <header class="page-head">
      <div>
        <h2>运力调度管理</h2>
        <p class="page-desc">维护调度任务，围绕调度编号、关联委托、指派车辆、指派司机做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记调度任务</button>
        <button class="btn" type="button" @click="exportRows">导出运力调度清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDispatchCheck(row)">派车校验</button>
            <button class="link" type="button" @click="openDispatchAssign(row)">指派调度</button>
            <button
              v-for="action in flowActions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无运力调度数据，可先登记调度任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条运力调度记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="dispatchModal.open" class="modal-mask" @click.self="closeDispatchModal">
      <div class="modal">
        <div class="modal-head">
          <h3>{{ dispatchModal.mode === 'assign' ? '指派调度 · 派车' : '派车校验' }} · {{ dispatchModal.row?.调度编号 ?? '' }}</h3>
          <button class="link" type="button" @click="closeDispatchModal">关闭</button>
        </div>
        <div class="modal-body">
          <p class="modal-tip">
            按驾驶证号取司机档案，统一核对准驾车型、从业资格与出勤状态；
            校验口径与司机列表、司机详情完全一致。
          </p>
          <label class="filter-item">
            <span>驾驶证号（必填）</span>
            <input v-model="dispatchModal.licenseNo" placeholder="请输入司机驾驶证号" />
          </label>
          <label class="filter-item">
            <span>要求准驾车型（可选，如 A2、B2）</span>
            <input v-model="dispatchModal.requiredType" placeholder="本车/本任务要求的准驾车型" />
          </label>
          <div v-if="dispatchModal.verdict" class="verdict-box">
            <div class="verdict-head">
              <span>可派车结论</span>
              <span class="tag" :class="dispatchModal.verdict.dispatchable ? 'ok' : 'bad'">
                {{ dispatchModal.verdict.label }}
              </span>
            </div>
            <ul v-if="dispatchModal.verdict.reasons.length" class="verdict-reasons">
              <li v-for="reason in dispatchModal.verdict.reasons" :key="reason">{{ reason }}</li>
            </ul>
            <p v-else class="verdict-reasons empty">准驾车型、从业资格、出勤状态均满足派车要求</p>
          </div>
          <div class="modal-actions">
            <button class="btn" type="button" :disabled="dispatchModal.busy" @click="submitDispatchCheck">
              {{ dispatchModal.mode === 'assign' ? '校验并指派' : '执行校验' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import type { DispatchVerdict } from '@/api/dispatchVerdict'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/dispatch3'
const columns = ["调度编号", "关联委托", "指派车辆", "指派司机", "计划发出", "预计到达", "调度人员", "调度状态"]
// 「指派调度」必须先过统一的可派车校验，单独走弹窗，不与其余状态流转并列直点。
const flowActions = ["确认发出", "确认抵达"]
const statuses = ["待调度", "已调度", "运输中", "已抵达"]
const stats = [{"label": "待调度任务", "value": 0}, {"label": "运输中任务", "value": 0}, {"label": "已抵达任务", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const dispatchModal = ref<{
  open: boolean
  mode: 'check' | 'assign'
  row: Row | null
  licenseNo: string
  requiredType: string
  busy: boolean
  verdict: DispatchVerdict | null
}>({ open: false, mode: 'check', row: null, licenseNo: '', requiredType: '', busy: false, verdict: null })

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '调度任务登记入口尚未接入审批流'
}

function openDispatchCheck(row: Row) {
  dispatchModal.value = {
    open: true,
    mode: 'check',
    row,
    licenseNo: String(row['指派司机驾驶证号'] ?? ''),
    requiredType: '',
    busy: false,
    verdict: null,
  }
}

function openDispatchAssign(row: Row) {
  dispatchModal.value = {
    open: true,
    mode: 'assign',
    row,
    licenseNo: String(row['指派司机驾驶证号'] ?? ''),
    requiredType: '',
    busy: false,
    verdict: null,
  }
}

function closeDispatchModal() {
  dispatchModal.value.open = false
  dispatchModal.value.verdict = null
}

function checkPayload(): { 驾驶证号: string; 要求车型?: string } | null {
  const licenseNo = dispatchModal.value.licenseNo.trim()
  if (!licenseNo) {
    errorMessage.value = '请先填写驾驶证号，按驾驶证号核对司机可派车状态'
    return null
  }
  const requiredType = dispatchModal.value.requiredType.trim()
  return requiredType
    ? { 驾驶证号: licenseNo, 要求车型: requiredType }
    : { 驾驶证号: licenseNo }
}

async function submitDispatchCheck() {
  errorMessage.value = ''
  const payload = checkPayload()
  if (!payload) {
    return
  }
  dispatchModal.value.busy = true
  try {
    if (dispatchModal.value.mode === 'check') {
      const response = await request(`${ENDPOINT}/dispatch-check`, {
        method: 'POST',
        body: JSON.stringify({ values: payload }),
      })
      if (!response.ok) {
        throw new Error('派车校验未完成，请稍后重试')
      }
      dispatchModal.value.verdict = (await response.json()) as DispatchVerdict
      return
    }

    // 指派模式：校验与状态流转在后端同一个动作里完成，校验不过任务状态不变。
    const row = dispatchModal.value.row
    const response = await request(`${ENDPOINT}/${row?.id ?? ''}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '指派调度', ...payload } }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      dispatchModal.value.verdict = (result?.entry ?? null) as DispatchVerdict | null
      throw new Error(result?.message || '指派调度未生效')
    }
    dispatchModal.value.open = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '派车校验失败'
  } finally {
    dispatchModal.value.busy = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('运力调度动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '运力调度操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('调度任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '运力调度列表读取失败'
  }
}

onMounted(reload)
</script>
