<template>
  <div class="page">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="color:#909399;font-size:13px">共 {{ rows.length }} 个登录账号。登录态过期时点「刷新登录」会在服务器机器上弹出浏览器登录。</span>
        <el-button type="primary" size="small" @click="openAdd">新增登录</el-button>
      </div>
      <el-table :data="rows" size="small" border v-loading="loading">
        <el-table-column prop="platform" label="平台" width="90" />
        <el-table-column prop="tag" label="登录标识" min-width="150" />
        <el-table-column label="启用" width="70">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" size="small" @change="v => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="登录态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.token_status==='ok'?'success':(row.token_status==='expired'?'danger':'info')" size="small">
              {{ row.token_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="token_updated_at" label="登录刷新时间" width="180" />
        <el-table-column prop="rows" label="已入库行数" width="110">
          <template #default="{ row }">{{ (row.rows||0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="数据覆盖" width="200">
          <template #default="{ row }">
            <span v-if="row.first_date">{{ row.first_date }} ~ {{ row.last_date }}</span>
            <span v-else style="color:#c0c4cc">暂无数据</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" type="primary" :loading="row._logging" @click="refreshLogin(row)">刷新登录</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="del(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dlg" :title="form.id?'编辑登录':'新增登录'" width="460">
      <el-form label-width="90">
        <el-form-item label="平台">
          <el-select v-model="form.platform" style="width:100%">
            <el-option v-for="p in ['小飞机','沸点','微橙','麦斯']" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="登录标识"><el-input v-model="form.tag" placeholder="如 小飞机-项目B" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" /></el-form-item>
      </el-form>
      <div style="color:#909399;font-size:12px">凭证(token/session)通过「刷新登录」按钮弹浏览器登录后自动获取，无需手填。</div>
      <template #footer><el-button @click="dlg=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const rows = ref([]); const loading = ref(false)
const dlg = ref(false); const form = reactive({ id: null, platform: '小飞机', tag: '', note: '' })

async function load() { loading.value = true; rows.value = (await api.get('/accounts')).data; loading.value = false }
function openAdd() { Object.assign(form, { id: null, platform: '小飞机', tag: '', note: '' }); dlg.value = true }
function openEdit(r) { Object.assign(form, { id: r.id, platform: r.platform, tag: r.tag, note: r.note }); dlg.value = true }
async function save() {
  if (form.id) await api.put(`/accounts/${form.id}`, form)
  else await api.post('/accounts', form)
  dlg.value = false; ElMessage.success('已保存'); load()
}
async function toggle(row, v) { await api.put(`/accounts/${row.id}`, { enabled: v }) }
async function del(row) {
  await ElMessageBox.confirm(`删除登录 ${row.tag}？（不会删已入库的历史数据）`, '确认', { type: 'warning' })
  await api.delete(`/accounts/${row.id}`); ElMessage.success('已删除'); load()
}
async function refreshLogin(row) {
  row._logging = true
  try {
    ElMessage.info('已在服务器机器上打开浏览器，请在该窗口完成登录…')
    await api.post(`/accounts/${row.id}/login`, {}, { timeout: 400000 })
    ElMessage.success('登录态已刷新'); load()
  } catch (e) { ElMessage.error('刷新失败：' + (e.response?.data?.detail || e.message)) }
  row._logging = false
}
onMounted(load)
</script>
