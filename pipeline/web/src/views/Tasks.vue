<template>
  <div class="page">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-weight:600">定时任务</span>
        <span style="color:#909399;font-size:13px">滚动任务：每 5 分钟重抓「近15天」并覆盖更新；15 天前的历史不动。</span>
      </div>
      <el-table :data="tasks" size="small" border v-loading="loading">
        <el-table-column prop="name" label="任务" min-width="160" />
        <el-table-column prop="kind" label="类型" width="90" />
        <el-table-column prop="platform" label="平台" width="90"><template #default="{row}">{{ row.platform||'全部' }}</template></el-table-column>
        <el-table-column prop="window_days" label="窗口(天)" width="90" />
        <el-table-column prop="interval_minutes" label="间隔(分)" width="90" />
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

    <div class="card">
      <div style="font-weight:600;margin-bottom:10px">最近运行记录</div>
      <el-table :data="runs" size="small" border v-loading="loading">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="kind" label="类型" width="100" />
        <el-table-column prop="started_at" label="开始" width="180" />
        <el-table-column prop="finished_at" label="结束" width="180" />
        <el-table-column label="状态" width="90"><template #default="{row}">
          <el-tag :type="row.status==='ok'?'success':(row.status==='error'?'danger':'warning')" size="small">{{ row.status }}</el-tag>
        </template></el-table-column>
        <el-table-column prop="rows_written" label="写入行" width="90" />
        <el-table-column prop="detail" label="详情" min-width="200" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const tasks = ref([]); const runs = ref([]); const loading = ref(false)
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
