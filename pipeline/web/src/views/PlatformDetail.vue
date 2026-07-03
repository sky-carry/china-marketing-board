<template>
  <div class="page">
    <div class="card" style="margin-bottom:10px">
      <!-- 维度 tabs -->
      <el-tabs v-model="level" @tab-change="reload">
        <el-tab-pane v-for="lv in levels" :key="lv" :label="lv" :name="lv" />
      </el-tabs>
      <!-- 筛选行 -->
      <div class="controls" style="margin-top:2px">
        <div>
          <div class="lbl">账号</div>
          <el-select v-model="login" size="small" style="width:200px" @change="reload" clearable placeholder="全部账号">
            <el-option label="全部账号" value="" />
            <el-option v-for="lg in logins" :key="lg" :label="lg" :value="lg" />
          </el-select>
        </div>
        <div>
          <div class="lbl">日期范围</div>
          <el-date-picker v-model="range" type="daterange" size="small" value-format="YYYY-MM-DD"
            :shortcuts="shortcuts" start-placeholder="开始" end-placeholder="结束" style="width:240px" @change="reload" />
        </div>
        <div>
          <div class="lbl">搜索名称/ID</div>
          <el-input v-model="search" size="small" style="width:200px" clearable placeholder="回车搜索"
            @keyup.enter="reload" @clear="reload" />
        </div>
        <el-button size="small" type="primary" @click="reload">查询</el-button>
      </div>
    </div>

    <div class="card grow">
      <div class="table-wrap">
        <el-table :data="tableData" size="small" border v-loading="loading" height="100%"
          :row-class-name="rowClass" @sort-change="onSort">
          <el-table-column v-for="col in columns" :key="col.key" :prop="col.key" :label="col.label"
            :width="col.width" :min-width="col.minWidth" :fixed="col.fixed" :sortable="col.sortable?'custom':false"
            :align="col.align||'right'" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.__total && col.key===firstCol">总计</span>
              <span v-else>{{ fmt(row[col.key], col.type) }}</span>
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
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const platform = ref(route.params.name)
const levels = ref([]); const logins = ref([])
const level = ref(''); const login = ref(''); const range = ref(null); const search = ref('')
const rows = ref([]); const totals = ref({}); const total = ref(0)
const page = ref(1); const pageSize = ref(50); const sort = ref('cost'); const loading = ref(false)

const columns = [
  { key:'entity_name', label:'名称', minWidth:240, fixed:'left', align:'left' },
  { key:'entity_id', label:'ID', width:150, align:'left' },
  { key:'account_name', label:'所属账户', width:170, align:'left' },
  { key:'parent_name', label:'上级', width:150, align:'left' },
  { key:'cost', label:'总消费(元)', width:120, type:'money', sortable:true },
  { key:'impressions', label:'展示量', width:100, type:'int', sortable:true },
  { key:'clicks', label:'点击量', width:90, type:'int', sortable:true },
  { key:'ctr', label:'点击率(%)', width:100, type:'rate' },
  { key:'cpm', label:'CPM(元)', width:100, type:'money' },
  { key:'cpc', label:'CPC(元)', width:90, type:'money' },
  { key:'pay_amount', label:'付款金额(元)', width:120, type:'money', sortable:true },
  { key:'orders', label:'订单数', width:90, type:'int', sortable:true },
  { key:'roi', label:'ROI', width:80, type:'roi', sortable:true },
  { key:'real_pay_amount', label:'真实付款(元)', width:120, type:'money', sortable:true },
  { key:'real_orders', label:'真实订单', width:90, type:'int' },
  { key:'real_roi', label:'真实ROI', width:90, type:'roi' },
  { key:'conversions', label:'转化数', width:90, type:'int' },
  { key:'conversion_cost', label:'转化成本(元)', width:110, type:'money' },
  { key:'refund_rate', label:'退款率(%)', width:100, type:'rate' },
]
const firstCol = 'entity_name'
const shortcuts = [
  { text:'今天', value:()=>{const d=new Date();return [d,d]} },
  { text:'昨天', value:()=>{const d=new Date(Date.now()-864e5);return [d,d]} },
  { text:'近7天', value:()=>[new Date(Date.now()-6*864e5), new Date()] },
  { text:'近30天', value:()=>[new Date(Date.now()-29*864e5), new Date()] },
  { text:'本月', value:()=>{const n=new Date();return [new Date(n.getFullYear(),n.getMonth(),1), n]} },
]

function fmt(v, type) {
  if (v === null || v === undefined || v === '') return type ? '0' : ''
  if (type === 'money') return Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})
  if (type === 'int') return Math.round(Number(v)).toLocaleString()
  if (type === 'rate') return Number(v).toFixed(2) + '%'
  if (type === 'roi') return Number(v).toFixed(2)
  return v
}
const tableData = computed(() => (totals.value && total.value ? [{ __total:true, ...totals.value }, ...rows.value] : rows.value))
function rowClass({ row }) { return row.__total ? 'total-row' : '' }

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/detail', { params: {
      platform: platform.value, level: level.value, login: login.value || undefined,
      start: range.value?.[0], end: range.value?.[1], search: search.value || undefined,
      sort: sort.value, limit: pageSize.value, offset: (page.value-1)*pageSize.value }})
    rows.value = data.rows; totals.value = data.totals; total.value = data.total
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }
function onSort({ prop, order }) { if (order) { sort.value = prop; reload() } }

async function initMeta() {
  const { data } = await api.get('/meta')
  levels.value = data.levels[platform.value] || []
  logins.value = data.logins?.[platform.value] || []
  level.value = levels.value[0] || ''
  const t = new Date(); const today = `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`
  range.value = [today, today]        // 默认当天，用户无需每次手动选日期
}

watch(() => route.params.name, async (nv) => { if (nv) { platform.value = nv; await initMeta(); reload() } })
onMounted(async () => { await initMeta(); load() })
</script>

<style>
.total-row { background: #eef4ff !important; font-weight: 700; }
.total-row td { background: #eef4ff !important; }
</style>
