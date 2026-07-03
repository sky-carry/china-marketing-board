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
          <div class="lbl">搜索账户名/ID</div>
          <el-input v-model="search" size="small" style="width:200px" clearable placeholder="回车搜索"
            @keyup.enter="reload" @clear="reload" />
        </div>
        <el-button size="small" type="primary" @click="reload">查询</el-button>
        <span style="color:#909399;font-size:12px">共 {{ total }} 个账户 · 末列可给账户打标签</span>
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
        <el-table-column prop="platform" label="平台" width="80" fixed="left" />
        <el-table-column prop="login_account" label="登录账号" width="170" fixed="left" show-overflow-tooltip />
        <el-table-column prop="entity_name" label="账户名称" min-width="220" fixed="left" show-overflow-tooltip />
        <el-table-column prop="entity_id" label="账户ID" width="150" />
        <el-table-column prop="cost" label="消费(元)" width="115" align="right" sortable="custom">
          <template #default="{row}">{{ money(row.cost) }}</template></el-table-column>
        <el-table-column prop="impressions" label="展示量" width="100" align="right" sortable="custom">
          <template #default="{row}">{{ int(row.impressions) }}</template></el-table-column>
        <el-table-column prop="clicks" label="点击量" width="90" align="right" sortable="custom">
          <template #default="{row}">{{ int(row.clicks) }}</template></el-table-column>
        <el-table-column prop="ctr" label="点击率(%)" width="95" align="right">
          <template #default="{row}">{{ rate(row.ctr) }}</template></el-table-column>
        <el-table-column prop="cpc" label="CPC(元)" width="90" align="right">
          <template #default="{row}">{{ money(row.cpc) }}</template></el-table-column>
        <el-table-column prop="orders" label="订单数" width="85" align="right" sortable="custom">
          <template #default="{row}">{{ int(row.orders) }}</template></el-table-column>
        <el-table-column prop="pay_amount" label="付款金额(元)" width="120" align="right" sortable="custom">
          <template #default="{row}">{{ money(row.pay_amount) }}</template></el-table-column>
        <el-table-column prop="roi" label="ROI" width="75" align="right" sortable="custom">
          <template #default="{row}">{{ roiv(row.roi) }}</template></el-table-column>
        <el-table-column prop="real_pay_amount" label="真实付款(元)" width="120" align="right" sortable="custom">
          <template #default="{row}">{{ money(row.real_pay_amount) }}</template></el-table-column>
        <el-table-column prop="real_orders" label="真实订单" width="85" align="right">
          <template #default="{row}">{{ int(row.real_orders) }}</template></el-table-column>
        <el-table-column prop="real_roi" label="真实ROI" width="85" align="right" sortable="custom">
          <template #default="{row}">{{ roiv(row.real_roi) }}</template></el-table-column>
        <el-table-column prop="refund_rate" label="退款率(%)" width="95" align="right">
          <template #default="{row}">{{ rate(row.refund_rate) }}</template></el-table-column>
        <!-- 标签列 -->
        <el-table-column label="标签" min-width="240" fixed="right">
          <template #default="{ row }">
            <template v-if="!row.__total">
              <el-tag v-for="(t,i) in row.tags" :key="i" size="small" closable style="margin:2px"
                @close="removeTag(row,i)">{{ t }}</el-tag>
              <el-input v-if="row._editing" ref="tagInput" v-model="row._newtag" size="small" style="width:100px"
                @keyup.enter="confirmTag(row)" @blur="confirmTag(row)" />
              <el-button v-else size="small" text type="primary" @click="startTag(row)">+ 添加标签</el-button>
            </template>
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
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const platforms = ref(['小飞机','沸点','微橙','麦斯'])
const platform = ref(''); const range = ref(null); const search = ref('')
const rows = ref([]); const total = ref(0); const totalRow = ref(null)
// 汇总行(__total) 置顶，其余为真实账户行；分开保存以免破坏标签编辑时的行对象引用
const tableData = computed(() => totalRow.value ? [totalRow.value, ...rows.value] : rows.value)
const page = ref(1); const pageSize = ref(50); const sort = ref('cost'); const loading = ref(false)

const shortcuts = [
  { text:'今天', value:()=>{const d=new Date();return [d,d]} },
  { text:'近7天', value:()=>[new Date(Date.now()-6*864e5), new Date()] },
  { text:'近30天', value:()=>[new Date(Date.now()-29*864e5), new Date()] },
  { text:'本月', value:()=>{const n=new Date();return [new Date(n.getFullYear(),n.getMonth(),1), n]} },
]
const money = v => v==null?'0.00':Number(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})
const int = v => v==null?'0':Math.round(Number(v)).toLocaleString()
const rate = v => v==null?'0%':Number(v).toFixed(2)+'%'
const roiv = v => v==null?'0':Number(v).toFixed(2)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/account_board', { params: {
      platform: platform.value||undefined, start: range.value?.[0], end: range.value?.[1],
      search: search.value||undefined, sort: sort.value, limit: pageSize.value, offset:(page.value-1)*pageSize.value }})
    const base = (page.value-1)*pageSize.value
    rows.value = data.rows.map((r,i) => ({ ...r, _editing:false, _newtag:'', __idx: base+i+1 }))
    totalRow.value = data.totals ? { ...data.totals, __total:true, entity_name:'合计' } : null
    total.value = data.total
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }
function onSort({ prop, order }) { if (order) { sort.value = prop; reload() } }

async function saveTags(row) {
  await api.post('/account_tags', { platform: row.platform, entity_id: row.entity_id, tags: row.tags })
}
function startTag(row) { row._editing = true; row._newtag=''; nextTick(()=>{}) }
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
  range.value = [today, today]        // 默认当天，用户无需每次手动选日期
  load()
})
</script>

<style scoped>
/* 汇总行置顶高亮，字体加粗 */
:deep(.total-row) td { background: #f0f6ff !important; font-weight: 700; }
:deep(.total-row):hover td { background: #e6f0ff !important; }
</style>
