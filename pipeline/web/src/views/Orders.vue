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
          <el-select v-model="login" size="small" style="width:190px" clearable filterable placeholder="全部账号" @change="reload">
            <el-option label="全部账号" value="" />
            <el-option v-for="l in loginOptions" :key="l" :label="l" :value="l" />
          </el-select>
        </div>
        <div>
          <div class="lbl">日期范围</div>
          <el-date-picker v-model="range" type="daterange" size="small" value-format="YYYY-MM-DD"
            :shortcuts="shortcuts" start-placeholder="开始" end-placeholder="结束" style="width:230px" @change="reload" />
        </div>
        <div>
          <div class="lbl">搜索 订单号/账号/商品</div>
          <el-input v-model="search" size="small" style="width:200px" clearable placeholder="回车搜索"
            @keyup.enter="reload" @clear="reload" />
        </div>
        <el-button size="small" type="primary" @click="reload">查询</el-button>
        <span style="color:#909399;font-size:12px">共 {{ total.toLocaleString() }} 单 · 付款合计 ¥{{ money(sumPay) }}</span>
      </div>
    </div>

    <div class="card grow">
      <div class="table-wrap">
        <el-table :data="rows" size="small" border v-loading="loading" height="100%" @sort-change="onSort">
          <el-table-column type="index" label="#" width="46" :index="i=>i+1+(page-1)*pageSize" fixed="left" />
          <el-table-column prop="platform" label="平台" width="70" fixed="left" />
          <el-table-column prop="order_type" label="订单类型" width="110" fixed="left" show-overflow-tooltip />
          <el-table-column prop="ad_account_name" label="广告账号名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="ad_account_id" label="广告账号ID" width="150" show-overflow-tooltip />
          <el-table-column prop="ad_name" label="广告名称" min-width="180" show-overflow-tooltip />
          <el-table-column prop="material_name" label="视频素材名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="main_order_no" label="主订单号" width="170" show-overflow-tooltip />
          <el-table-column prop="order_no" label="订单号" width="200" show-overflow-tooltip />
          <el-table-column prop="product_info" label="商品信息" min-width="240" show-overflow-tooltip />
          <el-table-column prop="product_price" label="商品单价" width="95" align="right">
            <template #default="{row}">{{ row.product_price==null?'—':money(row.product_price) }}</template></el-table-column>
          <el-table-column prop="pay_amount" label="付款金额" width="100" align="right" sortable="custom">
            <template #default="{row}">{{ row.pay_amount==null?'—':money(row.pay_amount) }}</template></el-table-column>
          <el-table-column prop="order_status" label="订单状态" width="90" />
          <el-table-column prop="callback_status" label="回传" width="80" show-overflow-tooltip />
          <el-table-column prop="click_time" label="点击时间" width="150" sortable="custom" />
          <el-table-column prop="pay_time" label="付款时间" width="150" sortable="custom" />
          <el-table-column prop="refund_time" label="退款时间" width="150" />
          <el-table-column prop="attribution" label="归因" width="70" />
          <el-table-column prop="ad_position" label="广告投放位置" width="120" show-overflow-tooltip />
          <!-- 人工列 B-G（后续填） -->
          <el-table-column prop="category" label="类目" width="90"><template #default="{row}">{{ row.category||'—' }}</template></el-table-column>
          <el-table-column prop="product" label="投放产品" width="100"><template #default="{row}">{{ row.product||'—' }}</template></el-table-column>
          <el-table-column prop="shop" label="店铺" width="110"><template #default="{row}">{{ row.shop||'—' }}</template></el-table-column>
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
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import shortcuts from '../shortcuts'

const meta = ref({ platforms: [], types: {}, logins: {}, date_min: null, date_max: null })
const platforms = computed(() => meta.value.platforms || [])
const platform = ref(''); const orderType = ref(''); const login = ref(''); const range = ref(null); const search = ref('')
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

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/orders', { params: {
      platform: platform.value||undefined, order_type: orderType.value||undefined, login: login.value||undefined,
      start: range.value?.[0], end: range.value?.[1], search: search.value||undefined,
      sort: sort.value, limit: pageSize.value, offset: (page.value-1)*pageSize.value }})
    rows.value = data.rows; total.value = data.total; sumPay.value = data.sum_pay
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }
function onPlat() { orderType.value = ''; login.value = ''; reload() }
function onSort({ prop, order }) { if (order) { sort.value = prop; reload() } }

onMounted(async () => {
  try { const { data } = await api.get('/order_meta'); meta.value = data } catch {}
  const n = new Date(); const first = new Date(n.getFullYear(), n.getMonth(), 1)
  const f = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  range.value = [f(first), f(n)]
  load()
})
</script>
