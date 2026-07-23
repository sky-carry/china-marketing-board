<template>
  <div class="dr-wrap">
    <!-- 标题栏（与系统风格一致；左=展示商品，右=复制图片/刷新） -->
    <div class="dr-title">
      <span class="dr-left">
        <el-button v-if="isAdmin" size="small" text style="color:#fff" @click="openPick">
          <el-icon><Grid /></el-icon>展示商品
        </el-button>
      </span>
      <span class="dr-heading">站外 CID 投放日报<span class="dr-date"> 【{{ dateText }}】</span></span>
      <span class="dr-right">
        <span class="dr-note">GSV实时更新退款数据，近7日数据因退款退货，存在小幅波动</span>
        <el-button size="small" text style="color:#fff" :loading="imging" @click="copyImg">
          <el-icon><Picture /></el-icon>复制为图片
        </el-button>
        <el-button size="small" text style="color:#fff" :loading="loading" @click="load">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </span>
    </div>

    <div class="dr-scroll" v-loading="loading">
      <div ref="captureEl" class="cap-wrap" :class="{ capturing }">
        <!-- 复制为图片时才显示的标题(与看板一致，无按钮)，随图片一起导出 -->
        <div v-if="capturing" class="cap-head">
          <div class="cap-title">站外 CID 投放日报 【{{ dateText }}】</div>
          <div class="cap-note">GSV实时更新退款数据，近7日数据因退款退货，存在小幅波动</div>
        </div>
        <table ref="tableEl" class="dr-table" :style="{ '--sub-top': subTop + 'px' }">
        <thead>
          <tr>
            <th class="dim" rowspan="2" style="min-width:64px">类目</th>
            <th class="dim" rowspan="2" style="min-width:96px">产品</th>
            <th v-for="q in quarters" :key="q.key" class="grp qgrp" colspan="2">{{ q.label }}</th>
            <th v-for="m in months" :key="m.key" class="grp mgrp" colspan="2">{{ m.label }}</th>
            <th class="grp dgrp" :colspan="days.length">当天GSV</th>
            <th class="grp sgrp" rowspan="2" style="min-width:70px">近7日<br>GSV变化</th>
            <th class="grp rgrp" :colspan="days.length">当天退后ROI</th>
            <th class="grp sgrp" rowspan="2" style="min-width:70px">近7日<br>ROI变化</th>
          </tr>
          <tr>
            <template v-for="q in quarters" :key="q.key+'2'">
              <th class="sub qgrp">GSV达成</th>
              <th class="sub qgrp">退后ROI</th>
            </template>
            <template v-for="m in months" :key="m.key+'2'">
              <th class="sub mgrp">GSV达成</th>
              <th class="sub mgrp">退后ROI</th>
            </template>
            <th v-for="d in days" :key="d.key+'g'" class="sub dgrp">{{ d.label }}</th>
            <th v-for="d in days" :key="d.key+'r'" class="sub rgrp">{{ d.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r,i) in displayRows" :key="i" :class="'dr-'+r.row_type">
            <!-- 维度：合计/电商=跨两列标签；类目=纵向合并单元格(可折叠)；产品=右列 -->
            <template v-if="r.kind==='label2'">
              <td class="dim label" colspan="2">{{ r.label }}</td>
            </template>
            <template v-else>
              <td v-if="r.catSpan>0" class="dim cat merged" :rowspan="r.catSpan>1 ? r.catSpan : null">{{ r.catName||'未分类' }}</td>
              <td class="dim prod">{{ r.product }}</td>
            </template>
            <!-- 季度：GSV达成 / 退后ROI -->
            <template v-for="q in quarters" :key="q.key">
              <td class="num">{{ gsvFull(r.q[q.key]?.gsv) }}</td>
              <td class="num strong">{{ roiFmt(r.q[q.key]?.roi) }}</td>
            </template>
            <!-- 分月：GSV达成 / ROI -->
            <template v-for="m in months" :key="m.key">
              <td class="num">{{ gsvFull(r.m[m.key]?.gsv) }}</td>
              <td class="num strong">{{ roiFmt(r.m[m.key]?.roi) }}</td>
            </template>
            <!-- 近7天 当天GSV -->
            <td v-for="(d,j) in days" :key="d.key+'g'" class="num">{{ gsvWan(r.dg[j]) }}</td>
            <!-- 近7日 GSV 柱状梯度条 -->
            <td class="spark"><svg :width="sparkW" height="24"><rect v-for="(b,j) in bars(r.dg)" :key="j" :x="b.x" :y="24-b.h" :width="b.w" :height="b.h" rx="1" fill="#5b8ff9"/></svg></td>
            <!-- 近7天 当天退后ROI -->
            <td v-for="(d,j) in days" :key="d.key+'r'" class="num">{{ roiFmt(r.dr[j]) }}</td>
            <!-- 近7日 退后ROI 折线图 -->
            <td class="spark"><svg :width="sparkW" height="24"><polyline :points="linePts(r.dr)" fill="none" stroke="#5b8ff9" stroke-width="1.4"/><circle v-for="(p,j) in lineDots(r.dr)" :key="j" :cx="p.x" :cy="p.y" r="1.6" fill="#5b8ff9"/></svg></td>
          </tr>
        </tbody>
      </table>
      </div>
      <div v-if="!displayRows.length && !loading" class="dr-empty">暂无数据</div>
    </div>

    <!-- 展示商品选择（管理员）：勾选不影响合计/京东天猫小计，仅影响产品明细行显隐 -->
    <el-dialog v-model="pickShow" title="展示商品（不影响合计与京东/天猫小计）" width="640px" top="8vh">
      <div class="pick-bar">
        <el-button size="small" @click="pickAll(true)">全选</el-button>
        <el-button size="small" @click="pickAll(false)">全不选</el-button>
        <span class="pick-tip">未勾选的产品明细行将被隐藏；类目/小计/合计始终按全量计算</span>
      </div>
      <div class="pick-body">
        <div v-for="(prods,cat) in prodByCat" :key="cat" class="pick-cat">
          <div class="pick-cat-h">{{ cat }}</div>
          <el-checkbox v-for="p in prods" :key="p" v-model="pickSel[p]" class="pick-item">{{ p }}</el-checkbox>
        </div>
      </div>
      <template #footer>
        <el-button @click="pickShow=false">取消</el-button>
        <el-button type="primary" :loading="picking" @click="savePick">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import api from '../api'
import { Refresh, Picture, Grid } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { toBlob } from 'html-to-image'

const isAdmin = localStorage.getItem('authAdmin') === '1'
const data = ref({ rows: [], quarters: [], months: [], days: [], products: [], visible_products: null, date: '' })
const loading = ref(false)

const quarters = computed(() => data.value.quarters || [])
const months = computed(() => data.value.months || [])
const days = computed(() => data.value.days || [])
const sparkW = computed(() => days.value.length * 11)   // 每天 8px 柱 + 3px 间隔

const dateText = computed(() => {
  const d = data.value.date; if (!d) return ''
  const [y, m, dd] = d.split('-'); return `${y}/${m}/${dd}`
})

// —— 格式化 ——
const roiFmt  = v => v == null ? '/' : Number(v).toFixed(2)
const gsvFull = v => v == null ? '/' : Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const gsvWan  = v => v == null ? '/' : (Number(v) / 10000).toFixed(1) + '万'

// —— 迷你图 ——
function bars(arr) {
  const vals = (arr || []).map(v => Number(v) || 0)
  const mx = Math.max(...vals, 1), W = 8, G = 3, H = 22
  return vals.map((v, i) => ({ x: i * (W + G), w: W, h: Math.max(1, Math.round(v / mx * H)) }))
}
function lineGeom(arr) {
  const vals = (arr || []).map(v => v == null ? null : Number(v))
  const nn = vals.filter(v => v != null)
  if (!nn.length) return []
  const mn = Math.min(...nn), mx = Math.max(...nn), span = (mx - mn) || 1
  const W = sparkW.value - 4, H = 20, n = vals.length
  return vals.map((v, i) => v == null ? null : { x: 2 + (n > 1 ? i / (n - 1) * W : W / 2), y: 2 + (H - (v - mn) / span * H) })
}
const linePts = arr => lineGeom(arr).filter(Boolean).map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
const lineDots = arr => lineGeom(arr).filter(Boolean)

// 维度渲染：合计/电商=整行标签(label2)；类目→产品用「类目纵向合并单元格 + 产品行」(图二 Excel 风)。
// 无产品的类目不展示；后端已按展示商品过滤产品行；合计/电商小计恒全量。
const displayRows = computed(() => {
  const src = data.value.rows || []
  const out = []
  for (let i = 0; i < src.length; i++) {
    const r = src[i]
    if (r.row_type === 'total' || r.row_type === 'ecom') { out.push({ ...r, kind: 'label2' }); continue }
    if (r.row_type === 'category') {
      const cat = r.category
      const prods = []
      let j = i + 1
      while (j < src.length && src[j].row_type === 'product' && src[j].category === cat) { prods.push(src[j]); j++ }
      i = j - 1
      if (prods.length === 0) continue   // 无产品的类目不展示
      prods.forEach((p, idx) => out.push({ ...p, kind: 'prod', catName: cat, catSpan: idx === 0 ? prods.length : 0 }))
    }
  }
  return out
})

// —— 展示商品选择（管理员）——
const pickShow = ref(false); const picking = ref(false)
const pickSel = reactive({})
const prodByCat = computed(() => {
  const g = {}
  for (const p of (data.value.products || [])) (g[p.category || '未分类'] ||= []).push(p.product)
  return g
})
function openPick() {
  const vis = data.value.visible_products   // null=全部
  for (const p of (data.value.products || [])) pickSel[p.product] = vis == null ? true : vis.includes(p.product)
  pickShow.value = true
}
function pickAll(v) { for (const p of (data.value.products || [])) pickSel[p.product] = v }
async function savePick() {
  const all = (data.value.products || []).map(p => p.product)
  const chosen = all.filter(p => pickSel[p])
  // 全选 => 传 null（展示全部）
  const products = chosen.length === all.length ? null : chosen
  picking.value = true
  try { await api.post('/daily_report/products', { products }); pickShow.value = false; await load() }
  catch (e) { ElMessage.error(e.response?.data?.detail || '保存失败') }
  finally { picking.value = false }
}

// —— 复制为图片：优先剪贴板，失败自动下载。导出含标题(cap-head)，并临时关掉吸顶表头 ——
const tableEl = ref(null); const captureEl = ref(null); const imging = ref(false); const capturing = ref(false)
async function copyImg() {
  if (!captureEl.value) return
  imging.value = true; capturing.value = true
  try {
    await nextTick()
    const blob = await toBlob(captureEl.value, { backgroundColor: '#ffffff', pixelRatio: 2 })
    if (!blob) throw new Error('生成图片失败')
    try {
      if (window.isSecureContext && navigator.clipboard && window.ClipboardItem) {
        await navigator.clipboard.write([new window.ClipboardItem({ 'image/png': blob })])
        ElMessage.success('日报已复制到剪贴板'); return
      }
      throw new Error('insecure')
    } catch {
      const url = URL.createObjectURL(blob), a = document.createElement('a')
      a.href = url; a.download = `站外CID投放日报_${data.value.date}.png`; a.click(); URL.revokeObjectURL(url)
      ElMessage.success('已下载为图片（当前非 https，无法直接写剪贴板）')
    }
  } catch (e) { ElMessage.error('生成图片失败：' + (e.message || e)) }
  finally { capturing.value = false; imging.value = false }
}

// 双层吸顶表头：第二行 top 必须等于第一行实测高度，否则两行之间会露出滚动内容(白缝)。
// 实测第一行高度并减 1px 让两行轻微重叠，彻底消除缝隙。
const subTop = ref(27)
function measureHeader() {
  const tr = tableEl.value?.querySelector('thead tr')
  if (tr) subTop.value = Math.max(0, Math.round(tr.getBoundingClientRect().height) - 1)
}

let timer = null
async function load() {
  loading.value = true
  try { const { data: d } = await api.get('/daily_report'); data.value = d; await nextTick(); measureHeader() }
  finally { loading.value = false }
}
onMounted(() => { load(); timer = setInterval(load, 300000); window.addEventListener('resize', measureHeader) })   // 每5分钟自动刷新
onBeforeUnmount(() => { if (timer) clearInterval(timer); window.removeEventListener('resize', measureHeader) })
defineExpose({ load })
</script>

<style scoped>
.dr-wrap { display: flex; flex-direction: column; height: 100%; min-height: 0; background: #fff; }
.dr-title { background: #20222a; color: #fff; padding: 8px 14px; display: flex; align-items: center;
  justify-content: center; flex: none; position: relative; min-height: 32px; }
.dr-heading { font-size: 18px; font-weight: 700; text-align: center; }
.dr-date { font-weight: 400; opacity: .92; }
.dr-left { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); display: flex; }
.dr-right { position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
  display: flex; align-items: center; gap: 6px; }
.dr-note { font-size: 12px; opacity: .78; max-width: 400px; }
.dr-scroll { flex: 1 1 auto; min-height: 0; overflow: auto; }
/* 截图容器：宽度随表格(比视口宽时也完整导出)；标题随图片一起 */
.cap-wrap { width: fit-content; min-width: 100%; }
.cap-head { background: #20222a; color: #fff; padding: 10px 16px; text-align: center; }
.cap-title { font-size: 18px; font-weight: 700; }
.cap-note { font-size: 12px; opacity: .82; margin-top: 4px; }
/* 截图时关掉吸顶，避免表头浮动错位 */
.cap-wrap.capturing .dr-table thead th { position: static !important; }

.dr-table { border-collapse: collapse; font-size: 12px; white-space: nowrap; background: #fff; }
.dr-table th, .dr-table td { border: 1px solid #c6cad2; padding: 4px 8px; text-align: center; }
.dr-table thead th { position: sticky; top: 0; z-index: 2; font-weight: 600; color: #303133; }
.dr-table thead th.grp { top: 0; }
.dr-table thead th.sub { top: var(--sub-top, 27px); }
th.qgrp { background: #eef0f7; }
th.mgrp { background: #eaf3ff; }
th.dgrp { background: #fff7e8; }
th.sgrp { background: #eef7f0; }
th.rgrp { background: #eef7f0; }
th.dim  { background: #f5f7fa; }

.dr-table td.dim { text-align: left; color: #303133; }
.dr-table td.dim.label { text-align: center; font-weight: 700; }
.dr-table td.dim.cat { text-align: center; vertical-align: middle; font-weight: 600; background: #f2f5e9; }
.dr-table td.dim.prod { text-align: left; color: #606266; }
.dr-table td.num { color: #303133; font-variant-numeric: tabular-nums; }
.dr-table td.strong { font-weight: 600; }
.dr-table td.spark { padding: 2px 4px; }

/* 行类型底色 */
.dr-total td { background: #dbe6f3; font-weight: 700; }
.dr-ecom td  { background: #eef1f6; font-weight: 600; }
.dr-category td { background: #f2f5e9; font-weight: 600; }
.dr-product:hover td { background: #f5f7fa; }
.dr-product:hover td.dim.cat { background: #eaeedd; }
.dr-empty { padding: 40px; text-align: center; color: #909399; }

.pick-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.pick-tip { font-size: 12px; color: #909399; }
.pick-body { max-height: 52vh; overflow: auto; }
.pick-cat { margin-bottom: 10px; }
.pick-cat-h { font-weight: 700; color: #303133; margin: 4px 0 6px; border-left: 3px solid #5b8ff9; padding-left: 6px; }
.pick-item { width: 30%; margin-right: 0 !important; }
</style>
