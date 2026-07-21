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
            <el-radio-button value="summary">汇总</el-radio-button>
            <el-radio-button value="daily">分日</el-radio-button>
            <el-radio-button value="weekly">分周</el-radio-button>
            <el-radio-button value="monthly">分月</el-radio-button>
          </el-radio-group>
        </div>
        <!-- 6 个投放属性筛选，两两一组、用底色分成三组 -->
        <div v-for="g in metaGroups" :key="g.cls" class="meta-group" :class="g.cls">
          <div v-for="f in g.fields" :key="f.key">
            <div class="lbl">{{ f.label }}</div>
            <el-select v-model="metaFilter[f.key]" size="small" style="width:120px" multiple filterable clearable
              collapse-tags collapse-tags-tooltip :placeholder="'全部'+f.label" @change="reload">
              <el-option v-for="o in (metaOptions[f.key]||[])" :key="o" :label="o" :value="o" />
            </el-select>
          </div>
        </div>
        <div>
          <div class="lbl">账户名称</div>
          <el-select v-model="accountFilter" size="small" style="width:200px" multiple filterable clearable
            collapse-tags collapse-tags-tooltip placeholder="全部账户" @change="reload">
            <el-option v-for="a in accountOptions" :key="a" :label="a" :value="a" />
          </el-select>
        </div>
        <div>
          <div class="lbl">搜索账户名/ID</div>
          <el-input v-model="search" size="small" style="width:200px" clearable placeholder="回车搜索"
            @keyup.enter="reload" @clear="reload" />
        </div>
        <el-button size="small" type="primary" @click="reload">查询</el-button>
        <ColumnCustomizer :model-value="colState" @update:model-value="onColsApply"
          :columns="COLS" :groups="COL_GROUPS" page="account_board" :admin="isAdmin" :default-state="defaultState" />
        <el-button size="small" type="success" plain :loading="exporting" @click="exportCsv"><el-icon style="margin-right:4px"><Download /></el-icon>导出数据</el-button>
        <span style="color:#909399;font-size:12px">共 {{ total }} {{ MODE_UNIT[mode] }} · {{ MODE_DESC[mode] }} · 末列可给账户打标签</span>
      </div>
    </div>

    <div class="card grow">
      <div class="table-wrap">
      <el-table :data="tableData" size="small" border v-loading="loading" height="100%" @sort-change="onSort"
        @header-dragend="onColResize" :row-class-name="({row})=>row.__total?'total-row':''">
        <el-table-column label="#" :width="colWidths['#'] || 48" fixed="left">
          <template #default="{ row }">
            <span v-if="row.__total">合计</span>
            <span v-else>{{ row.__idx }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" :width="colWidths['时间'] || 180" fixed="left" show-overflow-tooltip>
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

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'
import { Download, QuestionFilled } from '@element-plus/icons-vue'
import ColumnCustomizer from '../components/ColumnCustomizer.vue'

const platforms = ref(['小飞机','沸点','微橙','麦斯'])
const platform = ref(''); const range = ref(null); const search = ref('')
const mode = ref('summary')          // summary=区间汇总 / daily=分日 / weekly=分周(周一起) / monthly=分月
const MODE_UNIT = { summary:'个账户', daily:'条(账户·日)', weekly:'条(账户·周)', monthly:'条(账户·月)' }
const MODE_DESC = { summary:'区间汇总', daily:'分日展示', weekly:'分周展示(周一~周日)', monthly:'分月展示' }
// 账户名称(多选) + 6 投放属性(多选)筛选；选项来自 /account_board_meta；刷新页面即清空(不做持久化)
const boardMeta = ref({ accounts: [], meta_options: {}, meta_fields: [] })
const accountFilter = ref([])
const accountOptions = computed(() => boardMeta.value.accounts || [])
const metaFields = computed(() => boardMeta.value.meta_fields || [])
const metaOptions = computed(() => boardMeta.value.meta_options || {})
const metaFilter = reactive({ category: [], product: [], ecom_platform: [], ad_channel: [], store: [], agency: [] })
// 6 个投放属性两两分 3 组(各一底色)：类目/产品、电商平台/店铺、投放渠道/代理商
const META_GROUPS = [
  { cls: 'mg-a', keys: ['category', 'product'] },
  { cls: 'mg-b', keys: ['ecom_platform', 'store'] },
  { cls: 'mg-c', keys: ['ad_channel', 'agency'] },
]
const metaGroups = computed(() => {
  const byKey = Object.fromEntries(metaFields.value.map(f => [f.key, f]))
  return META_GROUPS.map(g => ({ cls: g.cls, fields: g.keys.map(k => byKey[k]).filter(Boolean) }))
    .filter(g => g.fields.length)
})
function filterParams() {
  const p = {}
  if (accountFilter.value.length) p.account = accountFilter.value
  for (const k in metaFilter) if (metaFilter[k]?.length) p[k] = metaFilter[k]
  return p
}
const rows = ref([]); const total = ref(0); const totalRow = ref(null)
const tableData = computed(() => totalRow.value ? [totalRow.value, ...rows.value] : rows.value)
const page = ref(1); const pageSize = ref(50); const sort = ref('cost'); const sortDesc = ref(true); const loading = ref(false)
const exporting = ref(false)

// 时间列：合计行与汇总模式显示日期范围；分日/周/月显示对应分期
const rangeText = computed(() => {
  const s = range.value?.[0], e = range.value?.[1]
  if (!s && !e) return '全部'
  return s === e ? s : `${s} ~ ${e}`
})
function addDays(ds, n) {           // ds='YYYY-MM-DD' + n 天（本地解析，避开时区偏移）
  const d = new Date(ds.replace(/-/g, '/')); d.setDate(d.getDate() + n)
  const p = x => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
// 后端返回的 row.date 是分期起始日：周=周一，月=1号；据 mode 格式化展示
function periodText(ds) {
  if (!ds) return ''
  if (mode.value === 'weekly') return `${ds} ~ ${addDays(ds, 6)}`   // 周一 ~ 周日
  if (mode.value === 'monthly') return ds.slice(0, 7)               // YYYY-MM
  return ds                                                         // daily
}
function timeCell(row) {
  if (row.__total) return rangeText.value
  return mode.value === 'summary' ? rangeText.value : periodText(row.date)
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
// group: info=账户信息 / front=前端数据 / back=后端产出（自定义列按此三类分组）
const COL_GROUPS = [
  { key:'info',  label:'账户信息' },
  { key:'front', label:'前端数据' },
  { key:'back',  label:'后端产出' },
]
const COLS = [
  { key:'platform',        label:'平台',        width:80,  type:'text', group:'info' },
  { key:'login_account',   label:'登录账号',    width:170, type:'text', group:'info' },
  { key:'entity_name',     label:'账户名称',    minWidth:220, type:'text', group:'info' },
  { key:'entity_id',       label:'账户ID',      width:150, type:'text', group:'info' },
  { key:'category',      label:'类目',      width:90,  type:'text', group:'info' },
  { key:'product',       label:'投放产品',  width:120, type:'text', group:'info' },
  { key:'ecom_platform', label:'电商平台',  width:90,  type:'text', group:'info' },
  { key:'ad_channel',    label:'投放渠道',  width:100, type:'text', group:'info' },
  { key:'store',         label:'店铺',      width:90,  type:'text', group:'info' },
  { key:'agency',        label:'代理商',    width:120, type:'text', group:'info' },
  { key:'tags',            label:'标签',        minWidth:160, type:'tags', pin:'right', group:'info' },
  { key:'cost',            label:'消费(元)',    width:115, type:'money', sortable:true, group:'front' },
  { key:'impressions',     label:'展示量',      width:100, type:'int',   sortable:true, group:'front' },
  { key:'clicks',          label:'点击量',      width:90,  type:'int',   sortable:true, group:'front' },
  { key:'ctr',             label:'点击率(%)',   width:95,  type:'rate', group:'front' },
  { key:'cpm',             label:'CPM(元)',     width:95,  type:'money', group:'front' },
  { key:'cpc',             label:'CPC(元)',     width:90,  type:'money', group:'front' },
  { key:'conversions',     label:'转化数',      width:85,  type:'int', group:'front' },
  { key:'conversion_cost', label:'转化成本(元)', width:110, type:'money', group:'front' },
  { key:'orders',          label:'订单数',      width:85,  type:'int',   sortable:true, group:'back' },
  { key:'pay_amount',      label:'付款金额(元)', width:120, type:'money', sortable:true, group:'back' },
  { key:'roi',             label:'ROI',         width:75,  type:'roi',   sortable:true, group:'back' },
  { key:'real_pay_amount', label:'真实付款(元)', width:120, type:'money', sortable:true, group:'back' },
  { key:'real_orders',     label:'真实订单',    width:85,  type:'int', group:'back' },
  { key:'real_roi',        label:'真实ROI',     width:85,  type:'roi',   sortable:true, group:'back' },
  { key:'rt_real_pay',     label:'实时真实付款(元)', width:140, type:'money', group:'back' },
  { key:'rt_real_roi',     label:'实时真实ROI', width:115, type:'roi', group:'back' },
  { key:'refund_rate',     label:'退款率(%)',   width:95,  type:'rate', group:'back' },
  { key:'direct_pay_amount',      label:'直投下单金额(元)', width:130, type:'money', sortable:true, group:'back' },
  { key:'direct_orders',          label:'直投下单量',      width:100, type:'int',   sortable:true, group:'back' },
  { key:'direct_roi',             label:'直投下单ROI',     width:105, type:'roi',   sortable:true, group:'back' },
  { key:'direct_real_pay_amount', label:'直投成交金额(元)', width:130, type:'money', sortable:true, group:'back' },
  { key:'direct_real_orders',     label:'直投成交量',      width:100, type:'int',   sortable:true, group:'back' },
  { key:'direct_real_roi',        label:'直投成交ROI',     width:105, type:'roi',   sortable:true, group:'back' },
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
const STORAGE = 'accountBoardCols.v2'   // v2：默认全部列可见 + 自定义列改版(分类/常用列)

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

// 列宽持久化：拖拽表头边框后按列 key(数据列)或列名(#/时间)记住，刷新不失效
const WIDTH_KEY = 'accountBoardColW.v1'
const colWidths = ref((() => { try { return JSON.parse(localStorage.getItem(WIDTH_KEY)) || {} } catch { return {} } })())
function onColResize(newW, oldW, column) {
  const k = column.property || column.label
  if (!k) return
  colWidths.value = { ...colWidths.value, [k]: Math.round(newW) }
  localStorage.setItem(WIDTH_KEY, JSON.stringify(colWidths.value))
}

// 可见列：用户固定(pinned)的列排最前并固定左；标签(pin:'right')排最后但不固定；中间列保持自定义顺序。
const visibleColumns = computed(() => {
  const vis = colState.value.filter(c => c.visible)
    .map(c => COLMAP[c.key] ? { ...COLMAP[c.key], _pinned: c.pinned } : null).filter(Boolean)
  const left = vis.filter(c => c._pinned)
  const right = vis.filter(c => !c._pinned && c.pin === 'right')
  const mid = vis.filter(c => !c._pinned && c.pin !== 'right')
  return [...left, ...mid, ...right].map(c => ({
    ...c,
    width: colWidths.value[c.key] ?? c.width,     // 应用持久化列宽(拖拽后记住)
    fixed: c._pinned ? 'left' : undefined         // 标签(pin:right)仍排最后，但不再固定右
  }))
})

// 自定义列（复用 ColumnCustomizer 组件：自带按钮+下拉模板+配置弹窗）
const isAdmin = ref(localStorage.getItem('authAdmin') === '1')
function onColsApply(newState) { colState.value = newState; saveState() }

// ================= 数据加载 =================
async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/account_board', { params: {
      platform: platform.value||undefined, start: range.value?.[0], end: range.value?.[1],
      search: search.value||undefined, sort: sort.value, desc: sortDesc.value, mode: mode.value,
      limit: pageSize.value, offset:(page.value-1)*pageSize.value, ...filterParams() }})
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
  if (col.type === 'tags') return (Array.isArray(row.tags) ? row.tags : []).join(' ')
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
      search: search.value||undefined, sort: sort.value, desc: sortDesc.value, mode: mode.value,
      limit: 100000, offset: 0, ...filterParams() }})
    const cols = visibleColumns.value
    const lines = [['时间', ...cols.map(c => c.label)]]
    if (data.totals) {                                        // 合计行置顶
      const t = { ...data.totals, entity_name: '合计' }
      lines.push([rangeText.value, ...cols.map(c => c.type==='tags' ? '' : cellForExport(t, c))])
    }
    for (const r of data.rows) {
      const timev = mode.value === 'summary' ? rangeText.value : periodText(r.date)
      lines.push([timev, ...cols.map(c => cellForExport(r, c))])
    }
    const csv = '﻿' + lines.map(row => row.map(csvEscape).join(',')).join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `账户看板_${MODE_DESC[mode.value]}_${range.value?.[0]||''}_${range.value?.[1]||''}.csv`
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
  try { const { data } = await api.get('/account_board_meta'); boardMeta.value = data } catch {}
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
/* 投放属性筛选：两两一组，用底色分成三组 */
.meta-group { display: flex; gap: 12px; align-items: flex-end; padding: 6px 10px; border-radius: 8px; border: 1px solid transparent; }
.mg-a { background: #ecf5ff; border-color: #d3e9ff; }   /* 蓝：类目/产品 */
.mg-b { background: #f0f9eb; border-color: #e1f0d6; }   /* 绿：电商平台/店铺 */
.mg-c { background: #fdf6ec; border-color: #f7e6c8; }   /* 橙：投放渠道/代理商 */
</style>
