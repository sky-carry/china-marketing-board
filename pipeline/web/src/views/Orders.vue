<template>
  <div class="page">
    <div class="card" style="margin-bottom:10px">
      <div class="controls">
        <div>
          <div class="lbl">平台</div>
          <el-select v-model="platform" size="small" style="width:110px" clearable placeholder="全部平台" @change="onPlat">
            <el-option label="全部平台" value="" />
            <el-option v-for="p in platforms" :key="p" :label="p" :value="p" />
          </el-select>
        </div>
        <div>
          <div class="lbl">订单类型</div>
          <el-select v-model="orderType" size="small" style="width:150px" clearable placeholder="全部类型" @change="reload">
            <el-option label="全部类型" value="" />
            <el-option v-for="t in typeOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </div>
        <div>
          <div class="lbl">登录账号</div>
          <el-select v-model="login" size="small" style="width:180px" clearable filterable placeholder="全部账号" @change="reload">
            <el-option label="全部账号" value="" />
            <el-option v-for="l in loginOptions" :key="l" :label="l" :value="l" />
          </el-select>
        </div>
        <div>
          <div class="lbl">广告账户名称</div>
          <el-select v-model="accountFilter" size="small" style="width:200px" multiple filterable clearable
            collapse-tags collapse-tags-tooltip placeholder="全部账户" @change="reload">
            <el-option v-for="a in accountOptions" :key="a" :label="a" :value="a" />
          </el-select>
        </div>
        <div>
          <div class="lbl">日期范围</div>
          <el-date-picker v-model="range" type="daterange" size="small" value-format="YYYY-MM-DD"
            :shortcuts="shortcuts" start-placeholder="开始" end-placeholder="结束" style="width:230px" @change="reload" />
        </div>
        <div>
          <div class="lbl">搜索 订单号/账户/商品</div>
          <el-input v-model="search" size="small" style="width:180px" clearable placeholder="回车搜索"
            @keyup.enter="reload" @clear="reload" />
        </div>
        <div v-for="f in metaFields" :key="f.key">
          <div class="lbl">{{ f.label }}</div>
          <el-select v-model="metaFilter[f.key]" size="small" style="width:130px" multiple filterable clearable
            collapse-tags collapse-tags-tooltip :placeholder="'全部'+f.label" @change="reload">
            <el-option v-for="o in (metaOptions[f.key]||[])" :key="o" :label="o" :value="o" />
          </el-select>
        </div>
        <el-button size="small" type="primary" @click="reload">查询</el-button>
        <el-button size="small" @click="openColDlg"><el-icon style="margin-right:4px"><Operation /></el-icon>自定义列</el-button>
        <el-button size="small" type="success" plain @click="exportXlsx" :loading="exporting"><el-icon style="margin-right:4px"><Download /></el-icon>导出数据</el-button>
        <span style="color:#909399;font-size:12px">共 {{ total.toLocaleString() }} 单 · 付款合计 ¥{{ money(sumPay) }}</span>
      </div>
    </div>

    <div class="card grow">
      <div class="table-wrap">
        <el-table :data="rows" size="small" border v-loading="loading" height="100%" @sort-change="onSort"
          @header-dragend="onColResize">
          <el-table-column type="index" label="#" :width="colWidths['#'] || 46" :index="i=>i+1+(page-1)*pageSize" fixed="left" />
          <el-table-column v-for="col in visibleColumns" :key="col.key" :prop="col.key" :label="col.label"
            :width="col.width" :min-width="col.minWidth" :fixed="col.fixed"
            :sortable="col.sortable ? 'custom' : false"
            :align="col.type==='money' ? 'right' : 'left'"
            :show-overflow-tooltip="col.type!=='money' && col.type!=='calc'">
            <template #header>
              <span>{{ col.label }}</span>
              <el-tooltip v-if="col.tip" :content="col.tip" placement="top" effect="dark" :show-after="60">
                <el-icon class="tip-q"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span v-if="col.type==='money'">{{ row[col.key]==null?'—':money(row[col.key]) }}</span>
              <span v-else :class="{ 'bg-empty': col.bg && !row[col.key] }">{{ row[col.key]==null||row[col.key]===''?(col.bg?'—':''):row[col.key] }}</span>
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
      <div style="color:#909399;font-size:12px;margin-bottom:10px">勾选控制显示/隐藏，勾「固定」把列固定到左侧（可固定多列），拖动 <b>⣿</b> 调整列顺序。B-G列在账户看板按广告账号配置后自动带出。</div>
      <div class="col-list">
        <div v-for="(c,i) in draft" :key="c.key" class="col-item" :class="{dragging:dragIdx===i}"
          draggable="true" @dragstart="dragStart(i)" @dragover.prevent="dragOver(i)" @drop.prevent @dragend="dragEnd">
          <span class="drag-handle" title="拖动排序">⣿</span>
          <el-checkbox v-model="c.visible" style="flex:1">{{ colLabel(c.key) }}<el-tag v-if="COLMAP[c.key]?.bg" size="small" type="warning" effect="plain" style="margin-left:6px">人工</el-tag></el-checkbox>
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
import { ref, reactive, computed, onMounted } from 'vue'
import api from '../api'
import shortcuts from '../shortcuts'
import { Operation, Download, QuestionFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const meta = ref({ platforms: [], types: {}, logins: {} })
const platforms = computed(() => meta.value.platforms || [])
const platform = ref(''); const orderType = ref(''); const login = ref(''); const range = ref(null); const search = ref('')
const accountFilter = ref([])                       // 广告账户名称(多选)
const accountOptions = computed(() => meta.value.accounts || [])
// 6 个投放属性筛选（类目/投放产品/电商平台/投放渠道/店铺/代理商，值来自 account_meta），均多选
const metaFilter = reactive({ category: [], product: [], ecom_platform: [], ad_channel: [], store: [], agency: [] })
const metaFields = computed(() => meta.value.meta_fields || [])
const metaOptions = computed(() => meta.value.meta_options || {})
// 组装筛选参数：账户名称 + 6 属性，均为多选数组，空则不传（axios 已配置数组序列化为 key=a&key=b）
function metaParams() {
  const p = {}
  if (accountFilter.value.length) p.account = accountFilter.value
  for (const k in metaFilter) if (metaFilter[k]?.length) p[k] = metaFilter[k]
  return p
}
const rows = ref([]); const total = ref(0); const sumPay = ref(0)
const page = ref(1); const pageSize = ref(50); const sort = ref('pay_time'); const loading = ref(false)

const typeOptions = computed(() => {
  const t = meta.value.types || {}
  return platform.value ? (t[platform.value] || []) : [...new Set(Object.values(t).flat())]
})
const loginOptions = computed(() => {
  const l = meta.value.logins || {}
  return platform.value ? (l[platform.value] || []) : [...new Set(Object.values(l).flat())]
})
const money = v => v==null?'0.00':Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})

// ============ 派生字段计算（点击/付款/退款时间 + 状态） ============
// 视为「真实付款」的订单状态：已付款/已完成(小飞机) 支付(麦斯) 订单付款(微橙) 已结算(沸点) 成交(通用)
const PAID_STATUSES = ['已付款', '已完成', '订单付款', '支付', '成交', '已结算']
function parseDt(s) { return s ? new Date(String(s).replace(' ', 'T')) : null }
function fmtDur(ms) {   // 毫秒 -> 可读时长
  if (ms == null || ms < 0) return ''
  const s = Math.floor(ms / 1000), d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  if (d) return `${d}天${h}时`
  if (h) return `${h}时${m}分`
  return `${m}分`
}
function dayDiff(a, b) {   // date(a) - date(b) 自然日差
  const da = new Date(a.getFullYear(), a.getMonth(), a.getDate())
  const db = new Date(b.getFullYear(), b.getMonth(), b.getDate())
  return Math.round((da - db) / 86400000)
}
function enrich(r) {
  const ct = parseDt(r.click_time), pt = parseDt(r.pay_time), rt = parseDt(r.refund_time)
  r.click_to_pay = (ct && pt) ? fmtDur(pt - ct) : ''
  r.pay_to_refund = (pt && rt) ? fmtDur(rt - pt) : ''
  r.reflow_days = (ct && pt) ? dayDiff(pt, ct) : null
  const paid = PAID_STATUSES.some(s => String(r.order_status || '').includes(s))
  r.same_day_real_pay = (ct && pt) ? ((dayDiff(pt, ct) === 0 && paid) ? '是' : '否') : ''
  return r
}

// ============ 列定义 & 自定义列 ============
const COLS = [
  { key:'platform',        label:'平台',        width:70,  fixed:'left' },
  { key:'order_type',      label:'订单类型',    width:110, fixed:'left' },
  { key:'ad_account_name', label:'广告账户名称', minWidth:180 },
  { key:'ad_account_id',   label:'广告账户ID',  width:150 },
  { key:'ad_name',         label:'广告名称',    minWidth:180 },
  { key:'material_name',   label:'视频素材名称', minWidth:160 },
  { key:'main_order_no',   label:'主订单号',    width:170 },
  { key:'order_no',        label:'订单号',      width:200 },
  { key:'product_id',      label:'商品ID',      width:150 },
  { key:'product_info',    label:'商品信息',    minWidth:240 },
  { key:'product_price',   label:'商品单价',    width:95,  type:'money' },
  { key:'pay_amount',      label:'付款金额',    width:100, type:'money', sortable:true },
  { key:'order_status',    label:'订单状态',    width:90 },
  { key:'callback_status', label:'回传',        width:80 },
  { key:'click_time',      label:'点击时间',    width:150, sortable:true },
  { key:'pay_time',        label:'付款时间',    width:150, sortable:true },
  { key:'refund_time',     label:'退款时间',    width:150 },
  // 派生字段（前端按时间/状态计算）
  { key:'click_to_pay',    label:'点击到付款时间', width:120, type:'calc', tip:'付款时间 − 点击时间：用户点击广告后多久下单付款' },
  { key:'pay_to_refund',   label:'付款到退款时间', width:120, type:'calc', tip:'退款时间 − 付款时间：付款后多久发生退款（无退款则为空）' },
  { key:'reflow_days',     label:'回流天数',    width:90, type:'calc', tip:'付款日期 − 点击日期（自然日）：0=当天付款，>0=隔天回流' },
  { key:'same_day_real_pay', label:'是否当天真实付款', width:130, type:'calc', tip:'点击与付款为同一日期，且订单状态为已付款/已完成/支付等付款态 → 是' },
  { key:'attribution',     label:'归因',        width:70 },
  { key:'ad_position',     label:'广告投放位置', width:120 },
  // B-G 人工列（账户看板配置 → 按广告账号ID绑定）
  { key:'category',        label:'类目',        width:100, bg:true },
  { key:'product',         label:'投放产品',    width:110, bg:true },
  { key:'ecom_platform',   label:'电商平台',    width:100, bg:true },
  { key:'ad_channel',      label:'投放渠道',    width:100, bg:true },
  { key:'store',           label:'店铺',        width:120, bg:true },
  { key:'agency',          label:'代理商',      width:100, bg:true },
]
const COLMAP = Object.fromEntries(COLS.map(c => [c.key, c]))
const colLabel = k => COLMAP[k]?.label || k
const STORAGE = 'ordersCols.v1'
// pinned: 是否固定到左侧；默认沿用 COLS 里 fixed:'left' 的列
function defaultState() { return COLS.map(c => ({ key: c.key, visible: true, pinned: c.fixed === 'left' })) }
function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(STORAGE))
    if (Array.isArray(s) && s.length) {
      const seen = new Set(s.map(x => x.key))
      const merged = s.filter(x => COLMAP[x.key])
        .map(x => ({ ...x, pinned: x.pinned ?? (COLMAP[x.key].fixed === 'left') }))   // 老数据补 pinned
      for (const c of COLS) if (!seen.has(c.key)) merged.push({ key: c.key, visible: true, pinned: c.fixed === 'left' })
      return merged
    }
  } catch {}
  return defaultState()
}
const colState = ref(loadState())
function saveState() { localStorage.setItem(STORAGE, JSON.stringify(colState.value)) }

// 列宽持久化：拖拽表头边框后按列 key(数据列)或列名(#)记住，刷新不失效
const WIDTH_KEY = 'ordersColW.v1'
const colWidths = ref((() => { try { return JSON.parse(localStorage.getItem(WIDTH_KEY)) || {} } catch { return {} } })())
function onColResize(newW, oldW, column) {
  const k = column.property || column.label
  if (!k) return
  colWidths.value = { ...colWidths.value, [k]: Math.round(newW) }
  localStorage.setItem(WIDTH_KEY, JSON.stringify(colWidths.value))
}

const visibleColumns = computed(() => {
  const vis = colState.value.filter(c => c.visible)
  const pinned = vis.filter(c => c.pinned), rest = vis.filter(c => !c.pinned)   // 固定列排最前, 便于 el-table 左固定连续
  return [...pinned, ...rest]
    .map(c => COLMAP[c.key] ? { ...COLMAP[c.key], width: colWidths.value[c.key] ?? COLMAP[c.key].width, fixed: c.pinned ? 'left' : undefined } : null)
    .filter(Boolean)
})
const colDlg = ref(false); const draft = ref([]); const dragIdx = ref(-1)
function openColDlg() { draft.value = colState.value.map(x => ({ ...x })); colDlg.value = true }
function dragStart(i) { dragIdx.value = i }
function dragOver(i) {
  if (dragIdx.value === -1 || dragIdx.value === i) return
  const arr = draft.value; const [m] = arr.splice(dragIdx.value, 1); arr.splice(i, 0, m); dragIdx.value = i
}
function dragEnd() { dragIdx.value = -1 }
function applyCols() { colState.value = draft.value.map(x => ({ ...x })); saveState(); colDlg.value = false }
function resetCols() { draft.value = defaultState() }

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/orders', { params: {
      platform: platform.value||undefined, order_type: orderType.value||undefined, login: login.value||undefined,
      start: range.value?.[0], end: range.value?.[1], search: search.value||undefined, ...metaParams(),
      sort: sort.value, limit: pageSize.value, offset: (page.value-1)*pageSize.value }})
    rows.value = (data.rows || []).map(enrich); total.value = data.total; sumPay.value = data.sum_pay
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }

const exporting = ref(false)
async function exportXlsx() {   // 导出当前筛选的全部订单为 xlsx(与查询同口径,不分页)
  exporting.value = true
  try {
    const res = await api.get('/orders/export', { responseType: 'blob', timeout: 300000, params: {
      platform: platform.value||undefined, order_type: orderType.value||undefined, login: login.value||undefined,
      start: range.value?.[0], end: range.value?.[1], search: search.value||undefined, ...metaParams(), sort: sort.value }})
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = '订单明细.xlsx'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) { ElMessage.error('导出失败：' + (e?.message || e)) } finally { exporting.value = false }
}
function onPlat() { orderType.value = ''; login.value = ''; reload() }
function onSort({ prop, order }) { if (order) { sort.value = prop; reload() } }

onMounted(async () => {
  try { const { data } = await api.get('/order_meta'); meta.value = data } catch {}
  const n = new Date()
  const f = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  range.value = [f(n), f(n)]   // 默认当天
  load()
})
</script>

<style scoped>
.bg-empty { color: #c0c4cc; }
.tip-q { color: #c0c4cc; font-size: 13px; margin-left: 3px; vertical-align: -1px; cursor: help; }
.tip-q:hover { color: #409EFF; }
.col-list { max-height: 400px; overflow-y: auto; }
.col-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid #ebeef5;
  border-radius: 6px; margin-bottom: 6px; background: #fff; }
.col-item.dragging { opacity: .5; border-color: #409EFF; background: #ecf5ff; }
.drag-handle { cursor: grab; color: #c0c4cc; font-size: 14px; user-select: none; letter-spacing: -2px; }
.col-item:hover .drag-handle { color: #909399; }
</style>
