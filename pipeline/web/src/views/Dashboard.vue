<template>
  <div class="page">
    <div class="card">
      <div class="controls">
        <div>
          <div class="lbl">平台</div>
          <el-checkbox-group v-model="sel.platforms" size="small" @change="onPlatform">
            <el-checkbox-button v-for="p in meta.platforms" :key="p" :value="p">{{ p }}</el-checkbox-button>
          </el-checkbox-group>
        </div>
        <div>
          <div class="lbl">层级</div>
          <el-select v-model="sel.level" size="small" style="width:170px" @change="reload">
            <el-option v-for="o in levelOptions" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <div>
          <div class="lbl">指标</div>
          <el-select v-model="sel.metric" size="small" style="width:150px" @change="loadTrend">
            <el-option v-for="m in meta.metrics" :key="m.key" :label="m.label" :value="m.key" />
          </el-select>
        </div>
        <div>
          <div class="lbl">粒度</div>
          <el-radio-group v-model="sel.gran" size="small" @change="loadTrend">
            <el-radio-button value="day">日</el-radio-button>
            <el-radio-button value="week">周</el-radio-button>
            <el-radio-button value="month">月</el-radio-button>
          </el-radio-group>
        </div>
        <div>
          <div class="lbl">分组</div>
          <el-radio-group v-model="sel.group" size="small" @change="loadTrend">
            <el-radio-button value="platform">按平台</el-radio-button>
            <el-radio-button value="login">按登录账号</el-radio-button>
            <el-radio-button value="account">按投放账户Top10</el-radio-button>
            <el-radio-button value="total">总计</el-radio-button>
          </el-radio-group>
        </div>
        <div>
          <div class="lbl">日期范围</div>
          <el-date-picker v-model="sel.range" type="daterange" size="small" value-format="YYYY-MM-DD"
            start-placeholder="开始" end-placeholder="结束" style="width:230px" @change="reload" />
        </div>
      </div>
    </div>

    <div class="kpis">
      <div class="kpi"><div class="t">总消费</div><div class="v">¥{{ fmt(kpi.cost) }}</div></div>
      <div class="kpi"><div class="t">真实付款(GSV)</div><div class="v">¥{{ fmt(kpi.real_pay_amount) }}</div></div>
      <div class="kpi"><div class="t">整体真实ROI</div><div class="v">{{ kpi.real_roi ?? '-' }}</div></div>
      <div class="kpi"><div class="t">真实订单数</div><div class="v">{{ fmt(kpi.real_orders) }}</div></div>
      <div class="kpi"><div class="t">加权退款率</div><div class="v">{{ kpi.refund_rate ?? '-' }}%</div></div>
    </div>

    <div class="card grow">
      <div style="font-weight:600;margin-bottom:8px;flex:none">{{ trendLabel }} · 趋势</div>
      <div ref="chartEl" class="chart-fill" style="min-height:260px"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, computed } from 'vue'
import api from '../api'
import * as echarts from 'echarts'

const meta = reactive({ platforms: [], levels: {}, metrics: [], date_min: null, date_max: null })
const sel = reactive({ platforms: [], level: '', metric: 'cost', gran: 'day', group: 'platform', range: null })
const kpi = reactive({ cost: 0, real_pay_amount: 0, real_roi: 0, real_orders: 0, refund_rate: 0 })
const chartEl = ref(null)
let chart = null
const trendLabel = ref('消费(元)')

const ACCOUNT_LEVELS = ['推广账号', '账户维度', '账户']
const levelOptions = computed(() => {
  const plats = sel.platforms.length ? sel.platforms : meta.platforms
  const opts = []
  const acct = []
  for (const p of plats) (meta.levels[p] || []).forEach(l => { if (ACCOUNT_LEVELS.includes(l) && !acct.includes(l)) acct.push(l) })
  if (acct.length) opts.push({ label: '账户(全平台)', value: acct.join(',') })
  for (const p of plats) (meta.levels[p] || []).forEach(l => { if (!ACCOUNT_LEVELS.includes(l)) opts.push({ label: `${p}·${l}`, value: `${p}|${l}` }) })
  return opts
})
const fmt = (v) => (v == null ? '-' : Math.round(v).toLocaleString())

function levelParam() {
  // 账户(全平台): 逗号分隔的层级名; 深层: "平台|层级" -> 只取层级名(平台已由平台筛选限定)
  if (!sel.level) return { levels: '', platforms: sel.platforms.join(',') }
  if (sel.level.includes('|')) {
    const [p, l] = sel.level.split('|')
    return { levels: l, platforms: p }   // 深层下钻时锁定到该平台
  }
  return { levels: sel.level, platforms: sel.platforms.join(',') }
}
function onPlatform() {
  const vals = levelOptions.value.map(o => o.value)
  if (!vals.includes(sel.level)) sel.level = vals[0] || ''
  reload()
}
async function loadMeta() {
  const { data } = await api.get('/meta')
  Object.assign(meta, data)
  sel.platforms = [...data.platforms]
  sel.range = [data.date_min, data.date_max]
  sel.level = levelOptions.value[0]?.value || ''   // 默认「账户(全平台)」
}
function params() {
  const lp = levelParam()
  return { ...lp, start: sel.range?.[0], end: sel.range?.[1] }
}
async function loadKpi() {
  const { data } = await api.get('/summary', { params: params() })
  Object.assign(kpi, data)
}
async function loadTrend() {
  const { data } = await api.get('/trend', { params: { ...params(), metric: sel.metric, gran: sel.gran, group: sel.group } })
  trendLabel.value = data.label
  const colors = { '小飞机': '#5b8cff', '沸点': '#27c498', '微橙': '#ffb454', '麦斯': '#e05fae' }
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', top: 0 },
    grid: { left: 60, right: 24, top: 34, bottom: 44 },
    xAxis: { type: 'category', data: data.times },
    yAxis: { type: 'value' },
    dataZoom: [{ type: 'inside' }, { type: 'slider', height: 16, bottom: 8 }],
    series: data.series.map(s => ({ name: s.name, type: 'line', smooth: true, showSymbol: false,
      itemStyle: colors[s.name] ? { color: colors[s.name] } : undefined, data: s.data }))
  }, true)
}
async function reload() { await Promise.all([loadKpi(), loadTrend()]) }

let ro = null
const onResize = () => chart && chart.resize()
onMounted(async () => {
  chart = echarts.init(chartEl.value)
  window.addEventListener('resize', onResize)
  ro = new ResizeObserver(onResize); ro.observe(chartEl.value)   // 跟随 flex 高度变化自适应
  await loadMeta()
  await reload()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (ro) ro.disconnect()
  chart && chart.dispose()
})
</script>
