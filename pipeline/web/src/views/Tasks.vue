<template>
  <div class="page">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-weight:600">定时任务</span>
        <span style="color:#909399;font-size:13px">滚动任务：每 5 分钟重抓「近15天」并覆盖更新；15 天前的历史不动。</span>
      </div>
      <el-table :data="tasks" size="small" border v-loading="loading">
        <el-table-column prop="name" label="任务" min-width="180" show-overflow-tooltip />
        <el-table-column prop="platform" label="平台" width="80"><template #default="{row}">{{ row.platform||'全部' }}</template></el-table-column>
        <el-table-column label="抓取范围" width="110">
          <template #default="{row}">近 {{ row.window_days }} 天</template>
        </el-table-column>
        <el-table-column label="调度" width="150">
          <template #default="{row}">
            <el-tag v-if="row.daily_time" type="warning" size="small">每日 {{ row.daily_time }}</el-tag>
            <el-tag v-else type="success" size="small">每 {{ row.interval_minutes }} 分钟</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="70">
          <template #default="{ row }"><el-switch v-model="row.enabled" size="small" @change="v=>toggle(row,v)" /></template>
        </el-table-column>
        <el-table-column prop="last_run_at" label="上次运行" width="180" />
        <el-table-column prop="last_status" label="状态" width="90" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }"><el-button size="small" type="primary" @click="run(row)">立即运行</el-button></template>
        </el-table-column>
      </el-table>
    </div>

    <div class="card grow">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">
        <span style="font-weight:600">最近运行记录</span>
        <el-radio-group v-model="runFilter" size="small">
          <el-radio-button value="all">全部 {{ runs.length }}</el-radio-button>
          <el-radio-button value="error">
            仅错误 <el-tag v-if="errorCount" type="danger" size="small" effect="dark" round style="margin-left:4px">{{ errorCount }}</el-tag>
            <span v-else style="margin-left:4px">0</span>
          </el-radio-button>
        </el-radio-group>
        <span v-if="runFilter==='error' && !errorCount" style="color:#67c23a;font-size:13px">近期无错误 ✓</span>
      </div>
      <div class="table-wrap">
      <el-table :data="filteredRuns" size="small" border v-loading="loading" height="100%"
        :row-class-name="({row})=>row.status==='error'?'run-error':''">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="kind" label="类型" width="100" />
        <el-table-column prop="started_at" label="开始" width="170" />
        <el-table-column prop="finished_at" label="结束" width="170" />
        <el-table-column label="状态" width="80"><template #default="{row}">
          <el-tag :type="row.status==='ok'?'success':(row.status==='error'?'danger':'warning')" size="small">{{ row.status }}</el-tag>
        </template></el-table-column>
        <el-table-column prop="rows_written" label="写入行" width="80" />
        <el-table-column label="详情" min-width="240">
          <template #default="{row}">
            <el-popover v-if="row.status==='error'" placement="top-start" width="520" trigger="click">
              <template #reference>
                <span class="err-detail">{{ row.detail }}</span>
              </template>
              <div style="max-height:300px;overflow:auto;white-space:pre-wrap;word-break:break-all;font-size:12px;line-height:1.6">{{ row.detail }}</div>
            </el-popover>
            <span v-else style="color:#909399">{{ row.detail }}</span>
          </template>
        </el-table-column>
      </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const tasks = ref([]); const runs = ref([]); const loading = ref(false)
const runFilter = ref('all')   // all | error
const errorCount = computed(() => runs.value.filter(r => r.status === 'error').length)
const filteredRuns = computed(() => runFilter.value === 'error' ? runs.value.filter(r => r.status === 'error') : runs.value)
let timer = null
async function load() {
  loading.value = true
  tasks.value = (await api.get('/tasks')).data
  runs.value = (await api.get('/runs')).data
  loading.value = false
}
async function toggle(row, v) { await api.put(`/tasks/${row.id}`, { enabled: v }) }
async function run(row) { await api.post(`/tasks/${row.id}/run`); ElMessage.success('已触发'); setTimeout(load, 1500) }
onMounted(() => { load(); timer = setInterval(load, 10000) })
onBeforeUnmount(() => clearInterval(timer))
</script>

<style scoped>
/* 错误行整行淡红底，一眼可辨 */
:deep(.run-error) { background: #fef0f0 !important; }
:deep(.run-error:hover > td) { background: #fde2e2 !important; }
/* 错误详情：红字 + 单行省略 + 可点击展开 */
.err-detail { color: #f56c6c; cursor: pointer; display: block; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; text-decoration: underline dotted; }
.err-detail:hover { color: #dd5b5b; }
</style>
