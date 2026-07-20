<template>
  <div class="rt-wrap">
    <!-- 标题栏（深紫，随当天日期/更新时间） -->
    <div class="rt-title">
      <span>SKG 站外投放 {{ dateText }}<span class="rt-time"> {{ timeText }}</span></span>
      <span class="rt-actions">
        <span class="rt-meta">当日在投 {{ data.active_accounts || 0 }} 个账户 · 每5分钟自动刷新</span>
        <el-button size="small" text @click="load" :loading="loading" style="color:#fff">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </span>
    </div>

    <div class="rt-scroll" v-loading="loading">
      <table class="rt-table">
        <thead>
          <tr>
            <th v-for="c in COLS" :key="c.key" :class="c.dim?'dim':'num'" :style="{minWidth:c.w+'px'}">{{ c.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r,i) in renderRows" :key="i" :class="'rt-'+r.row_type">
            <!-- 明细：6 个维度列，相同值合并单元格(rowspan) -->
            <template v-if="r.row_type==='detail'">
              <td v-for="cell in r._cells" :key="cell.j" :rowspan="cell.span>1 ? cell.span : null"
                class="dim" :class="{ cat: cell.j===0, prod: cell.j===1, merged: cell.span>1 }">{{ cell.val }}</td>
            </template>
            <!-- 产品小计：类目列被上方合并覆盖，「X-小计」跨 产品~代理商 5 列居中 -->
            <template v-else-if="r.row_type==='subtotal'">
              <td v-if="r._subCat" :rowspan="r._subCat.span>1 ? r._subCat.span : null" class="dim cat merged">{{ r._subCat.val }}</td>
              <td class="dim sub-label" colspan="5">{{ r.product }}</td>
            </template>
            <!-- 总计 / 电商平台汇总：首列跨 6 列显示标签 -->
            <template v-else>
              <td class="dim label" colspan="6">{{ r.label }}</td>
            </template>
            <td class="num">{{ money(r.cost) }}</td>
            <td class="num">{{ int(r.real_orders) }}</td>
            <td class="num">{{ money(r.real_pay) }}</td>
            <td class="num strong">{{ roi(r.real_roi) }}</td>
            <td class="num" :class="deltaCls(r.roi_vs_yesterday)">{{ delta(r.roi_vs_yesterday) }}</td>
            <td class="num" :class="{ warn: r.refund_rate>=30 }">{{ pct(r.refund_rate) }}</td>
            <td class="num">{{ int(r.direct_real_orders) }}</td>
            <td class="num">{{ money(r.direct_real_pay) }}</td>
            <td class="num">{{ roi(r.direct_real_roi) }}</td>
            <td class="num muted">—</td>
            <td class="num">{{ money(r.y_cost) }}</td>
            <td class="num">{{ roi(r.y_real_roi) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!renderRows.length && !loading" class="rt-empty">当日暂无在投账户数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import api from '../api'
import { Refresh } from '@element-plus/icons-vue'

// 列定义：6 维度 + 12 指标（顺序与飞书「实时数据」sheet 一致）
const COLS = [
  { key:'category',    label:'类目',   dim:true, w:70 },
  { key:'product',     label:'产品',   dim:true, w:96 },
  { key:'ecom_platform', label:'渠道', dim:true, w:60 },
  { key:'store',       label:'店铺',   dim:true, w:64 },
  { key:'ad_channel',  label:'投放渠道', dim:true, w:84 },
  { key:'agency',      label:'代理商', dim:true, w:90 },
  { key:'cost',        label:'消耗',   w:96 },
  { key:'real_orders', label:'真实订单', w:78 },
  { key:'real_pay',    label:'真实付款', w:100 },
  { key:'real_roi',    label:'真实ROI', w:78 },
  { key:'roi_vs_yesterday', label:'对比昨日ROI', w:96 },
  { key:'refund_rate', label:'退款率', w:72 },
  { key:'direct_real_orders', label:'直投成交量', w:86 },
  { key:'direct_real_pay', label:'直投成交金额', w:104 },
  { key:'direct_real_roi', label:'直投成交ROI', w:96 },
  { key:'last_hour_cost', label:'上一个小时消耗', w:110 },
  { key:'y_cost',      label:'昨日总消耗', w:100 },
  { key:'y_real_roi',  label:'昨日真实ROI', w:96 },
]

const data = ref({ rows: [], date: '', updated_at: '', active_accounts: 0 })
const loading = ref(false)

const money = v => v==null?'—':Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})
const int   = v => v==null?'—':Math.round(Number(v)).toLocaleString()
const roi   = v => v==null?'—':Number(v).toFixed(2)
const pct   = v => v==null?'—':Number(v).toFixed(2)+'%'
const delta = v => v==null?'—':(v>=0?'+':'')+Number(v).toFixed(2)
const deltaCls = v => v==null?'':(v>=0?'up':'down')

// 标题：日期 -> 2026年7月20日；更新时间 -> 15时45分
const dateText = computed(() => {
  const d = data.value.date
  if (!d) return ''
  const [y,m,dd] = d.split('-')
  return `${y}年${+m}月${+dd}日`
})
const timeText = computed(() => {
  const u = data.value.updated_at
  if (!u) return ''
  const t = u.split(' ')[1] || ''
  const [h,mi] = t.split(':')
  return h!=null ? `${h}时${mi}分` : ''
})

// 6 维度列合并单元格：相邻行「前缀维度值全等」则纵向合并(rowspan)，层级式(Excel 风)
const DIM_KEYS = ['category', 'product', 'ecom_platform', 'store', 'ad_channel', 'agency']
function dispVal(r, j) {                          // 该行第 j 维用于合并判断/显示的值；非维度行返回 null
  if (r.row_type !== 'detail' && r.row_type !== 'subtotal') return null
  if (r.row_type === 'subtotal') return j === 0 ? (r.category || '未分类') : (j === 1 ? r.product : '')
  return j === 0 ? (r.category || '未分类') : (r[DIM_KEYS[j]] ?? '')
}
const renderRows = computed(() => {
  const rows = (data.value.rows || []).map(r => ({ ...r }))
  for (let j = 0; j < 6; j++) {                  // 逐维计算 rowspan
    let i = 0
    while (i < rows.length) {
      if (dispVal(rows[i], j) === null) { rows[i]['s' + j] = null; i++; continue }
      let k = i + 1
      while (k < rows.length && dispVal(rows[k], j) !== null &&
             Array.from({ length: j + 1 }).every((_, jj) => dispVal(rows[k], jj) === dispVal(rows[i], jj))) k++
      rows[i]['s' + j] = k - i
      for (let m = i + 1; m < k; m++) rows[m]['s' + j] = 0   // 被合并掉的行不渲染该单元格
      i = k
    }
  }
  for (const r of rows) {
    if (r.row_type === 'detail') {                 // 明细行：组装各维度合并头单元格
      r._cells = []
      for (let j = 0; j < 6; j++) if (r['s' + j]) r._cells.push({ j, val: dispVal(r, j), span: r['s' + j] })
    } else if (r.row_type === 'subtotal') {         // 小计行：类目列通常被上方合并覆盖，产品~代理商合并成一格居中
      r._subCat = r['s0'] ? { val: dispVal(r, 0), span: r['s0'] } : null
    }
  }
  return rows
})

let timer = null
async function load() {
  loading.value = true
  try { const { data: d } = await api.get('/realtime_board'); data.value = d }
  finally { loading.value = false }
}
onMounted(() => { load(); timer = setInterval(load, 300000) })   // 每 5 分钟自动刷新(对齐抓取节奏)
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
defineExpose({ load })
</script>

<style scoped>
.rt-wrap { display: flex; flex-direction: column; height: 100%; min-height: 0; background: #fff; }
.rt-title {
  background: #20222a; color: #fff; font-size: 18px; font-weight: 700;
  padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; flex: none;
}
.rt-time { font-weight: 400; opacity: .85; font-size: 15px; }
.rt-actions { display: flex; align-items: center; gap: 12px; }
.rt-meta { font-size: 12px; font-weight: 400; opacity: .8; }
.rt-scroll { flex: 1 1 auto; min-height: 0; overflow: auto; }

.rt-table { border-collapse: collapse; width: 100%; font-size: 12px; white-space: nowrap; }
.rt-table th, .rt-table td { border: 1px solid #ebeef5; padding: 5px 8px; }
.rt-table thead th {
  position: sticky; top: 0; z-index: 2; background: #f5f7fa; color: #303133;
  font-weight: 600; text-align: center; border-bottom: 1px solid #dcdfe6;
}
.rt-table td.dim { text-align: left; color: #303133; vertical-align: middle; }
.rt-table td.merged { background: #fff; text-align: center; }   /* 合并单元格白底+居中 */
.rt-table td.num { text-align: right; color: #303133; font-variant-numeric: tabular-nums; }
.rt-table td.cat { font-weight: 600; color: #303133; }
.rt-table td.prod { color: #606266; }
.rt-table td.strong { font-weight: 600; }
.rt-table td.muted { color: #c0c4cc; text-align: center; }
.rt-table td.up { color: #2e9b5b; }
.rt-table td.down { color: #d5493f; }
.rt-table td.warn { color: #d5493f; }
.rt-table td.label { font-weight: 700; text-align: center; color: #303133; }
.rt-table td.sub-label { text-align: center; font-weight: 600; }   /* 产品小计标签居中 */

/* 行类型底色（系统中性/蓝色调） */
.rt-detail:hover td { background: #f5f7fa; }
.rt-subtotal td { background: #e4e7ed; font-weight: 600; }
.rt-total td { background: #ecf5ff; font-weight: 700; font-size: 12.5px; }
.rt-platform td { background: #fafafa; }
.rt-platform_subtotal td { background: #dbe1ea; font-weight: 700; }
.rt-empty { padding: 40px; text-align: center; color: #909399; }
</style>
