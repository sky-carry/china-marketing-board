<template>
  <div class="page">
    <div class="card" style="margin-bottom:10px">
      <div class="controls">
        <div>
          <div class="lbl">平台</div>
          <el-select v-model="platform" size="small" style="width:120px" clearable placeholder="全部平台" @change="reload">
            <el-option label="全部平台" value="" />
            <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
          </el-select>
        </div>
        <div>
          <div class="lbl">日期范围</div>
          <el-date-picker v-model="range" type="daterange" size="small" value-format="YYYY-MM-DD"
            :shortcuts="shortcuts" start-placeholder="开始" end-placeholder="结束" style="width:240px" @change="reload" />
        </div>
        <div>
          <div class="lbl">统计方式</div>
          <el-radio-group v-model="mode" size="small" @change="reload">
            <el-radio-button value="summary">日汇总</el-radio-button>
            <el-radio-button value="daily">分日</el-radio-button>
          </el-radio-group>
        </div>
        <div>
          <div class="lbl">搜索账户名/ID</div>
          <el-input v-model="search" size="small" style="width:200px" clearable placeholder="回车搜索"
            @keyup.enter="reload" @clear="reload" />
        </div>
        <el-button size="small" type="primary" @click="reload">查询</el-button>
        <el-button size="small" @click="openColDlg"><el-icon style="margin-right:4px"><Operation /></el-icon>自定义列</el-button>
        <el-button size="small" type="success" plain :loading="exporting" @click="exportCsv"><el-icon style="margin-right:4px"><Download /></el-icon>导出数据</el-button>
        <span style="color:#909399;font-size:12px">共 {{ total }} {{ mode==='daily'?'条(账户·日)':'个账户' }} · {{ mode==='daily'?'分日展示':'区间汇总' }} · 末列可给账户打标签</span>
      </div>
    </div>

    <div class="card grow">
      <div class="table-wrap">
      <el-table :data="tableData" size="small" border v-loading="loading" height="100%" @sort-change="onSort"
        :row-class-name="({row})=>row.__total?'total-row':''">
        <el-table-column label="#" width="48" fixed="left">
          <template #default="{ row }">
            <span v-if="row.__total">合计</span>
            <span v-else>{{ row.__idx }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180" fixed="left">
          <template #default="{ row }">{{ timeCell(row) }}</template>
        </el-table-column>
        <el-table-column v-for="col in visibleColumns" :key="col.key" :prop="col.key" :label="col.label"
          :width="col.width" :min-width="col.minWidth" :fixed="col.fixed"
          :sortable="col.sortable ? 'custom' : false"
          :align="col.type==='text'||col.type==='tags' ? 'left' : 'right'"
          :show-overflow-tooltip="col.type==='text'">
          <template #header>
            <span>{{ col.label }}</span>
            <el-tooltip v-if="TIPS[col.key]" :content="TIPS[col.key]" placement="top" effect="dark" :show-after="80">
              <el-icon class="tip-q" @click.stop><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <!-- 标签列 -->
            <template v-if="col.type==='tags'">
              <template v-if="!row.__total">
                <el-tag v-for="(t,i) in row.tags" :key="i" size="small" closable style="margin:2px"
                  @close="removeTag(row,i)">{{ t }}</el-tag>
                <el-input v-if="row._editing" v-model="row._newtag" size="small" style="width:100px"
                  @keyup.enter="confirmTag(row)" @blur="confirmTag(row)" />
                <el-button v-else size="small" text type="primary" @click="startTag(row)">+ 添加标签</el-button>
              </template>
            </template>
            <!-- 普通列 -->
            <span v-else>{{ fmtCell(row[col.key], col.type) }}</span>
          </template>
        </el-table-column>
      </el-table>
      </div>
      <div class="pager">
        <el-pagination background layout="total, sizes, prev, pager, next" :total="total"
          :page-size="pageSize" :current-page="page" :page-sizes="[20,50,100,200]"
          @current-change="p=>{page=p;load()}" @size-change="s=>{pageSize=s;page=1;load()}" />
      </div>
    </div>

    <!-- 自定义列 弹窗 -->
    <el-dialog v-model="colDlg" title="自定义列" width="400">
      <div style="color:#909399;font-size:12px;margin-bottom:10px">勾选控制显示/隐藏，勾「固定」把列固定到左侧（可固定多列），拖动 <b>⣿</b> 调整列顺序</div>
      <div class="col-list">
        <div v-for="(c,i) in draft" :key="c.key" class="col-item" :class="{dragging:dragIdx===i}"
          draggable="true" @dragstart="dragStart(i)" @dragover.prevent="dragOver(i)" @drop.prevent @dragend="dragEnd">
          <span class="drag-handle" title="拖动排序">⣿</span>
          <el-checkbox v-model="c.visible" style="flex:1">{{ colLabel(c.key) }}</el-checkbox>
          <el-checkbox v-model="c.pinned" size="small" class="pin-cb" title="固定到左侧">📌固定</el-checkbox>
        </div>
      </div>
      <template #footer>
        <el-button size="small" @click="resetCols">恢复默认</el-button>
        <span style="flex:1"></span>
        <el-button size="small" @click="colDlg=false">取消</el-button>
        <el-button size="small" type="primary" @click="applyCols">应用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import { Operation, Download, QuestionFilled } from '@element-plus/icons-vue'

const platforms = ref(['小飞机','沸点','微橙','麦斯'])
const platform = ref(''); const range = ref(null); const search = ref('')
const mode = ref('summary')          // summary=区间汇总 / daily=分日
const rows = ref([]); const total = ref(0); const totalRow = ref(null)
const tableData = computed(() => totalRow.value ? [totalRow.value, ...rows.value] : rows.value)
const page = ref(1); const pageSize = ref(50); const sort = ref('cost'); const sortDesc = ref(true); const loading = ref(false)
const exporting = ref(false)

// 时间列：合计行与汇总模式显示日期范围，分日模式显示当天日期
const rangeText = computed(() => {
  const s = range.value?.[0], e = range.value?.[1]
  if (!s && !e) return '全部'
  return s === e ? s : `${s} ~ ${e}`
})
function timeCell(row) {
  if (row.__total) return rangeText.value
  return mode.value === 'daily' ? row.date : rangeText.value
}

import shortcuts from '../shortcuts'
const money = v => v==null?'0.00':Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})
const int = v => v==null?'0':Math.round(Number(v)).toLocaleString()
const rate = v => v==null?'0%':Number(v).toFixed(2)+'%'
const roiv = v => v==null?'0':Number(v).toFixed(2)
function fmtCell(v, type) {
  if (type==='money') return money(v)
  if (type==='int') return int(v)
  if (type==='rate') return rate(v)
  if (type==='roi') return roiv(v)
  return v==null ? '' : v
}

// ================= 列定义 & 自定义列 =================
const COLS = [
  { key:'platform',        label:'平台',        width:80,  type:'text' },
  { key:'login_account',   label:'登录账号',    width:170, type:'text' },
  { key:'entity_name',     label:'账户名称',    minWidth:220, type:'text' },
  { key:'entity_id',       label:'账户ID',      width:150, type:'text' },
  { key:'cost',            label:'消费(元)',    width:115, type:'money', sortable:true },
  { key:'impressions',     label:'展示量',      width:100, type:'int',   sortable:true },
  { key:'clicks',          label:'点击量',      width:90,  type:'int',   sortable:true },
  { key:'ctr',             label:'点击率(%)',   width:95,  type:'rate' },
  { key:'cpm',             label:'CPM(元)',     width:95,  type:'money' },
  { key:'cpc',             label:'CPC(元)',     width:90,  type:'money' },
  { key:'conversions',     label:'转化数',      width:85,  type:'int' },
  { key:'conversion_cost', label:'转化成本(元)', width:110, type:'money' },
  { key:'orders',          label:'订单数',      width:85,  type:'int',   sortable:true },
  { key:'pay_amount',      label:'付款金额(元)', width:120, type:'money', sortable:true },
  { key:'roi',             label:'ROI',         width:75,  type:'roi',   sortable:true },
  { key:'real_pay_amount', label:'真实付款(元)', width:120, type:'money', sortable:true },
  { key:'real_orders',     label:'真实订单',    width:85,  type:'int' },
  { key:'real_roi',        label:'真实ROI',     width:85,  type:'roi',   sortable:true },
  { key:'rt_real_pay',     label:'实时真实付款(元)', width:140, type:'money' },
  { key:'rt_real_roi',     label:'实时真实ROI', width:115, type:'roi' },
  { key:'refund_rate',     label:'退款率(%)',   width:95,  type:'rate' },
  { key:'direct_pay_amount',      label:'直投下单金额(元)', width:130, type:'money', sortable:true },
  { key:'direct_orders',          label:'直投下单量',      width:100, type:'int',   sortable:true },
  { key:'direct_roi',             label:'直投下单ROI',     width:105, type:'roi',   sortable:true },
  { key:'direct_real_pay_amount', label:'直投成交金额(元)', width:130, type:'money', sortable:true },
  { key:'direct_real_orders',     label:'直投成交量',      width:100, type:'int',   sortable:true },
  { key:'direct_real_roi',        label:'直投成交ROI',     width:105, type:'roi',   sortable:true },
  // 投放账户自定义属性（在「账号管理→投放账户管理」编辑），默认隐藏，可在自定义列勾选展示
  { key:'category',      label:'类目',      width:90,  type:'text', hidden:true },
  { key:'product',       label:'投放产品',  width:120, type:'text', hidden:true },
  { key:'ecom_platform', label:'电商平台',  width:90,  type:'text', hidden:true },
  { key:'ad_channel',    label:'投放渠道',  width:100, type:'text', hidden:true },
  { key:'store',         label:'店铺',      width:90,  type:'text', hidden:true },
  { key:'agency',        label:'代理商',    width:120, type:'text', hidden:true },
  { key:'tags',            label:'标签',        minWidth:160, type:'tags', pin:'right' },
]
const COLMAP = Object.fromEntries(COLS.map(c => [c.key, c]))
// 计算类/难懂字段的表头说明（悬浮 ? 显示计算口径）
const TIPS = {
  ctr: '点击率 = 点击量 / 展示量 × 100%',
  cpm: 'CPM = 总消费 / 展示量 × 1000（每千次展示成本）',
  cpc: 'CPC = 总消费 / 点击量（每次点击成本）',
  conversion_cost: '转化成本 = 总消费 / 转化数',
  roi: 'ROI = 付款金额 / 消费',
  real_roi: '真实ROI = 真实付款 / 消费',
  rt_real_pay: '实时真实付款：当天该账户「当天真实付款」订单的付款金额之和（点击与付款为同一日期、且订单状态为已付款/已完成/订单付款/支付/已结算等付款态），数据来自订单明细',
  rt_real_roi: '实时真实ROI = 实时真实付款 / 消费',
  refund_rate: '退款率：汇总口径 =（付款金额 − 真实付款）/ 付款金额 × 100%',
  pay_amount: '下单支付金额（含后续可能退款的部分）',
  real_pay_amount: '扣除退款后的真实成交金额',
  direct_orders: '直投归因下单量（小飞机=直推 / 沸点=直接 / 微橙=单品 / 麦斯=主投品）',
  direct_pay_amount: '直投归因下单金额（小飞机=直推 / 沸点=直接 / 微橙=单品 / 麦斯=主投品）',
  direct_roi: '直投下单ROI = 直投下单金额 / 消费',
  direct_real_orders: '直投归因成交量（扣退款后）',
  direct_real_pay_amount: '直投归因成交金额（扣退款后）',
  direct_real_roi: '直投成交ROI = 直投成交金额 / 消费',
}
const colLabel = k => COLMAP[k]?.label || k
const STORAGE = 'accountBoardCols.v1'

// pinned: 用户勾选的左固定；默认沿用 COLS 里 pin:'left' 的列
function defaultState() { return COLS.map(c => ({ key: c.key, visible: !c.hidden, pinned: c.pin === 'left' })) }
function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(STORAGE))
    if (Array.isArray(s) && s.length) {
      const seen = new Set(s.map(x => x.key))
      const merged = s.filter(x => COLMAP[x.key])            // 丢弃已删除的列
        .map(x => ({ ...x, pinned: x.pinned ?? (COLMAP[x.key].pin === 'left') }))   // 老数据补 pinned
      for (const c of COLS) if (!seen.has(c.key)) merged.push({ key: c.key, visible: !c.hidden, pinned: c.pin === 'left' })
      return merged
    }
  } catch {}
  return defaultState()
}
const colState = ref(loadState())
function saveState() { localStorage.setItem(STORAGE, JSON.stringify(colState.value)) }

// 可见列：用户固定(pinned)的列排最前并固定左；标签(pin:'right')排最后固定右；中间列保持自定义顺序。
const visibleColumns = computed(() => {
  const vis = colState.value.filter(c => c.visible)
    .map(c => COLMAP[c.key] ? { ...COLMAP[c.key], _pinned: c.pinned } : null).filter(Boolean)
  const left = vis.filter(c => c._pinned)
  const right = vis.filter(c => !c._pinned && c.pin === 'right')
  const mid = vis.filter(c => !c._pinned && c.pin !== 'right')
  return [...left, ...mid, ...right].map(c => ({
    ...c, fixed: c._pinned ? 'left' : (c.pin === 'right' ? 'right' : undefined)
  }))
})

// 弹窗 + 拖拽
const colDlg = ref(false); const draft = ref([]); const dragIdx = ref(-1)
function openColDlg() { draft.value = colState.value.map(x => ({ ...x })); colDlg.value = true }
function dragStart(i) { dragIdx.value = i }
function dragOver(i) {
  if (dragIdx.value === -1 || dragIdx.value === i) return
  const arr = draft.value
  const [moved] = arr.splice(dragIdx.value, 1)
  arr.splice(i, 0, moved)
  dragIdx.value = i
}
function dragEnd() { dragIdx.value = -1 }
function applyCols() { colState.value = draft.value.map(x => ({ ...x })); saveState(); colDlg.value = false }
function resetCols() { draft.value = defaultState() }

// ================= 数据加载 =================
async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/account_board', { params: {
      platform: platform.value||undefined, start: range.value?.[0], end: range.value?.[1],
      search: search.value||undefined, sort: sort.value, desc: sortDesc.value, mode: mode.value, limit: pageSize.value, offset:(page.value-1)*pageSize.value }})
    const base = (page.value-1)*pageSize.value
    rows.value = data.rows.map((r,i) => ({ ...r, _editing:false, _newtag:'', __idx: base+i+1 }))
    totalRow.value = data.totals ? { ...data.totals, __total:true, entity_name:'合计' } : null
    total.value = data.total
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }
function onSort({ prop, order }) {
  if (!order) return                       // 取消排序时保持原状
  sort.value = prop
  sortDesc.value = order === 'descending'  // 支持升序/降序
  reload()
}

// ================= 导出数据(所见即所得：当前可见列 + 当前筛选/统计方式的全部行) =================
function cellForExport(row, col) {
  if (col.type === 'tags') return (row.tags || []).join(' ')
  const v = row[col.key]
  if (v == null) return ''
  return ['money','int','rate','roi'].includes(col.type) ? Number(v) : v   // 数值保留原始值，Excel 可直接计算
}
function csvEscape(v) {
  const s = v == null ? '' : String(v)
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
}
async function exportCsv() {
  exporting.value = true
  try {
    // 拉取当前筛选/统计方式下的全部行（不受分页限制），与页面口径一致
    const { data } = await api.get('/account_board', { params: {
      platform: platform.value||undefined, start: range.value?.[0], end: range.value?.[1],
      search: search.value||undefined, sort: sort.value, desc: sortDesc.value, mode: mode.value, limit: 100000, offset: 0 }})
    const cols = visibleColumns.value
    const lines = [['时间', ...cols.map(c => c.label)]]
    if (data.totals) {                                        // 合计行置顶
      const t = { ...data.totals, entity_name: '合计' }
      lines.push([rangeText.value, ...cols.map(c => c.type==='tags' ? '' : cellForExport(t, c))])
    }
    for (const r of data.rows) {
      const timev = mode.value === 'daily' ? r.date : rangeText.value
      lines.push([timev, ...cols.map(c => cellForExport(r, c))])
    }
    const csv = '﻿' + lines.map(row => row.map(csvEscape).join(',')).join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `账户看板_${mode.value==='daily'?'分日':'日汇总'}_${range.value?.[0]||''}_${range.value?.[1]||''}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${data.rows.length} 行`)
  } catch (e) {
    ElMessage.error('导出失败：' + (e?.message || e))
  } finally { exporting.value = false }
}

async function saveTags(row) {
  await api.post('/account_tags', { platform: row.platform, entity_id: row.entity_id, tags: row.tags })
}
function startTag(row) { row._editing = true; row._newtag='' }
async function confirmTag(row) {
  const t = (row._newtag||'').trim()
  row._editing = false
  if (t && !row.tags.includes(t)) { row.tags = [...row.tags, t]; await saveTags(row); ElMessage.success('已添加标签') }
  row._newtag=''
}
async function removeTag(row, i) { row.tags = row.tags.filter((_,j)=>j!==i); await saveTags(row) }

onMounted(async () => {
  try { const { data } = await api.get('/meta'); if (data.platforms?.length) platforms.value = data.platforms } catch {}
  const t = new Date(); const today = `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`
  range.value = [today, today]
  load()
})
</script>

<style scoped>
:deep(.total-row) td { background: #f0f6ff !important; font-weight: 700; }
:deep(.total-row):hover td { background: #e6f0ff !important; }
/* 表头说明问号 */
.tip-q { color: #a8abb2; font-size: 13px; margin-left: 3px; vertical-align: -1px; cursor: help; }
.tip-q:hover { color: #409EFF; }
/* 自定义列 弹窗 */
.col-list { max-height: 380px; overflow-y: auto; }
.col-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid #ebeef5;
  border-radius: 6px; margin-bottom: 6px; background: #fff; cursor: default; }
.col-item.dragging { opacity: .5; border-color: #409EFF; background: #ecf5ff; }
.drag-handle { cursor: grab; color: #c0c4cc; font-size: 14px; user-select: none; letter-spacing: -2px; }
.col-item:hover .drag-handle { color: #909399; }
</style>
