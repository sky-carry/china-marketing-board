<template>
  <div style="padding:16px;height:100%;box-sizing:border-box;overflow:auto">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
      <span style="font-size:15px;font-weight:600">用户管理</span>
      <span style="color:#909399;font-size:13px">共 {{ rows.length }} 人（飞书登录自动建号；禁用后无法再次登录）</span>
      <el-button size="small" :loading="loading" @click="load" style="margin-left:auto">刷新</el-button>
    </div>
    <el-table :data="rows" v-loading="loading" size="small" border stripe style="width:100%">
      <el-table-column label="头像" width="70" align="center">
        <template #default="{ row }">
          <el-avatar v-if="row.avatar_url" :size="32" :src="row.avatar_url" />
          <el-icon v-else :size="22"><UserFilled /></el-icon>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="姓名" min-width="120" />
      <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
      <el-table-column prop="mobile" label="手机" width="130" />
      <el-table-column label="来源" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.source==='feishu' ? 'success' : 'info'">{{ row.source }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="login_count" label="登录次数" width="90" align="center" sortable />
      <el-table-column label="首次登录" width="160" align="center">
        <template #default="{ row }">{{ fmt(row.first_login_at) }}</template>
      </el-table-column>
      <el-table-column label="最近登录" width="160" align="center" sortable :sort-by="r => r.last_login_at || ''">
        <template #default="{ row }">{{ fmt(row.last_login_at) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-switch v-model="row.is_active" :loading="row._saving"
            active-text="启用" inactive-text="禁用" inline-prompt @change="v => toggle(row, v)" />
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'
import { ElMessage } from 'element-plus'

const rows = ref([]); const loading = ref(false)

function fmt(s) {
  if (!s) return '—'
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}

async function load() {
  loading.value = true
  try { const { data } = await api.get('/users'); rows.value = data.users || [] }
  catch (e) { ElMessage.error(e.response?.data?.detail || '加载失败') }
  finally { loading.value = false }
}

async function toggle(row, v) {
  row._saving = true
  try {
    await api.post('/users/set_active', { id: row.id, is_active: v })
    ElMessage.success(v ? '已启用' : '已禁用')
  } catch (e) {
    row.is_active = !v   // 回滚
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally { row._saving = false }
}

onMounted(load)
</script>
