<template>
  <section class="page" data-module="driver">
    <header class="page-head">
      <div>
        <h2>司机管理管理</h2>
        <p class="page-desc">维护驾驶员，围绕驾驶员编号、驾驶员姓名、驾驶证号、准驾车型做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记驾驶员</button>
        <button class="btn" type="button" @click="exportRows">导出司机管理清单</button>
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
          <th>可派车</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span
              class="tag"
              :class="rowVerdict(row)?.dispatchable ? 'ok' : 'bad'"
              :title="(verdictReasons(rowVerdict(row)).join('；') || '准驾车型、从业资格、出勤状态均满足派车要求')"
            >
              {{ verdictLabel(rowVerdict(row)) }}
            </span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
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
          <td :colspan="columns.length + 2" class="empty-state">暂无司机管理数据，可先登记驾驶员</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条司机管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detailRow" class="modal-mask" @click.self="closeDetail">
      <div class="modal">
        <div class="modal-head">
          <h3>司机详情 · {{ detailRow.驾驶员姓名 ?? '' }}</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </div>
        <div v-if="detailLoading" class="modal-body">详情读取中…</div>
        <div v-else-if="detailVerdict" class="modal-body">
          <dl class="detail-grid">
            <template v-for="column in columns" :key="column">
              <dt>{{ column }}</dt>
              <dd>{{ detailRow[column] ?? '—' }}</dd>
            </template>
          </dl>
          <div class="verdict-box">
            <div class="verdict-head">
              <span>可派车结论</span>
              <span class="tag" :class="detailVerdict.dispatchable ? 'ok' : 'bad'">{{ detailVerdict.label }}</span>
            </div>
            <ul v-if="detailVerdict.reasons.length" class="verdict-reasons">
              <li v-for="reason in detailVerdict.reasons" :key="reason">{{ reason }}</li>
            </ul>
            <p v-else class="verdict-reasons empty">准驾车型、从业资格、出勤状态均满足派车要求</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { resolveVerdict, verdictLabel, verdictReasons, type DispatchVerdict } from '@/api/dispatchVerdict'

type Row = Record<string, string | number | null>
type DetailRow = Record<string, string | number | DispatchVerdict | null>

const ENDPOINT = '/api/driver'
const columns = ["驾驶员编号", "驾驶员姓名", "驾驶证号", "准驾车型", "从业资格", "联系电话", "所属车队", "出勤状态"]
const actions = ["派车出勤", "登记休假", "办理离职"]
const statuses = ["空闲", "出车中", "休假", "已离职"]
const stats = [{"label": "空闲驾驶员", "value": 0}, {"label": "出车中驾驶员", "value": 0}, {"label": "休假驾驶员", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// 列表行与详情弹窗都只读取后端挂在「可派车」上的统一结论，前端不再自行判断。
const detailRow = ref<DetailRow | null>(null)
const detailVerdict = ref<DispatchVerdict | null>(null)
const detailLoading = ref(false)

function rowVerdict(row: Row): DispatchVerdict | null {
  return resolveVerdict(row as unknown as { 可派车?: DispatchVerdict | null })
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '驾驶员登记入口尚未接入审批流'
}

async function openDetail(row: Row) {
  detailRow.value = { ...row }
  detailVerdict.value = rowVerdict(row)
  detailLoading.value = true
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('司机详情读取失败')
    }
    const payload = (await response.json()) as DetailRow
    detailRow.value = payload
    detailVerdict.value = resolveVerdict(payload as { 可派车?: DispatchVerdict | null })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '司机详情读取失败'
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  detailRow.value = null
  detailVerdict.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('司机管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '司机管理操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('驾驶员列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '司机管理列表读取失败'
  }
}

onMounted(reload)
</script>
