<template>
  <div class="page">
    <div class="card grow">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="color:#909399;font-size:13px">
          共 {{ rows.length }} 个登录账号。<b>沸点/微橙/麦斯</b> 已存密码，点「自动登录」后台无人值守重登；
          <b>小飞机</b> 需短信验证码，用「手动登录」登一次（会话可自动续期）。
        </span>
        <div>
          <el-button size="small" @click="keepAll" :loading="keeping">一键保活全部</el-button>
          <el-button type="primary" size="small" @click="openAdd">新增登录</el-button>
        </div>
      </div>
      <div class="table-wrap">
      <el-table :data="rows" size="small" border v-loading="loading" height="100%">
        <el-table-column prop="platform" label="平台" width="80" />
        <el-table-column prop="tag" label="登录标识" min-width="140" show-overflow-tooltip />
        <el-table-column prop="username" label="登录账号" min-width="170" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.username || '—' }}</span>
            <el-tag v-if="row.has_pw" size="small" type="success" effect="plain" style="margin-left:6px">已存密码</el-tag>
            <el-tag v-else size="small" type="info" effect="plain" style="margin-left:6px">无密码</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="60">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" size="small" @change="v => toggle(row, v)" />
          </template>
        </el-table-column>
        <el-table-column label="登录态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.is_historical" type="info" size="small" effect="plain">历史账号</el-tag>
            <el-tag v-else :type="statusType(row.token_status)" size="small">{{ statusText(row.token_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="token_updated_at" label="登录刷新时间" min-width="165" align="center" />
        <el-table-column prop="rows" label="已入库行数" min-width="120" align="right">
          <template #default="{ row }">{{ (row.rows||0).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="数据覆盖" min-width="200" align="center">
          <template #default="{ row }">
            <span v-if="row.first_date">{{ row.first_date }} ~ {{ row.last_date }}</span>
            <span v-else style="color:#c0c4cc">暂无数据</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="380" fixed="right">
          <template #default="{ row }">
            <div class="op-btns">
              <template v-if="!row.is_historical">
                <el-button size="small" type="primary" :loading="row._auto" @click="autoLogin(row)">自动登录</el-button>
                <el-button size="small" :loading="row._logging" @click="refreshLogin(row)">手动登录</el-button>
              </template>
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" :type="row.is_historical?'success':'info'" @click="toggleHistorical(row)">
                {{ row.is_historical ? '恢复' : '设为历史' }}
              </el-button>
              <el-button size="small" type="danger" @click="del(row)">删</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      </div>
    </div>

    <el-dialog v-model="dlg" :title="form.id?'编辑登录':'新增登录'" width="460">
      <el-form label-width="90">
        <el-form-item label="平台">
          <el-select v-model="form.platform" style="width:100%">
            <el-option v-for="p in ['小飞机','沸点','微橙','麦斯']" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="登录标识"><el-input v-model="form.tag" placeholder="如 小飞机·项目B" /></el-form-item>
        <el-form-item label="登录账号"><el-input v-model="form.username" placeholder="平台登录用户名/邮箱" /></el-form-item>
        <el-form-item label="登录密码">
          <el-input v-model="form.password" type="password" show-password placeholder="留空则不修改" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" /></el-form-item>
      </el-form>
      <div style="color:#909399;font-size:12px">
        沸点/微橙/麦斯：填账号密码后可「自动登录」。小飞机需短信验证码，走「手动登录」。
      </div>
      <template #footer><el-button @click="dlg=false">取消</el-button><el-button type="primary" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const rows = ref([]); const loading = ref(false); const keeping = ref(false)
const dlg = ref(false)
const form = reactive({ id: null, platform: '小飞机', tag: '', username: '', password: '', note: '' })

const statusType = s => ({ ok:'success', expired:'danger', error:'danger', need_login:'warning' }[s] || 'info')
const statusText = s => ({ ok:'正常', expired:'已过期', error:'异常', need_login:'需手动登录' }[s] || (s||'未登录'))

async function load() { loading.value = true; rows.value = (await api.get('/accounts')).data; loading.value = false }
function openAdd() { Object.assign(form, { id: null, platform: '小飞机', tag: '', username: '', password: '', note: '' }); dlg.value = true }
function openEdit(r) { Object.assign(form, { id: r.id, platform: r.platform, tag: r.tag, username: r.username||'', password: '', note: r.note }); dlg.value = true }
async function save() {
  const body = { ...form }
  if (!body.password) delete body.password   // 留空不覆盖
  if (form.id) await api.put(`/accounts/${form.id}`, body)
  else await api.post('/accounts', body)
  dlg.value = false; ElMessage.success('已保存'); load()
}
async function toggle(row, v) { await api.put(`/accounts/${row.id}`, { enabled: v }) }
async function toggleHistorical(row) {
  const to = !row.is_historical
  if (to) await ElMessageBox.confirm(`把 ${row.tag} 设为历史账号？将停止抓取并置于列表底部（已入库数据保留）`, '确认', { type: 'warning' })
  await api.put(`/accounts/${row.id}`, { is_historical: to })
  ElMessage.success(to ? '已设为历史账号' : '已恢复'); load()
}
async function del(row) {
  await ElMessageBox.confirm(`删除登录 ${row.tag}？（不会删已入库的历史数据）`, '确认', { type: 'warning' })
  await api.delete(`/accounts/${row.id}`); ElMessage.success('已删除'); load()
}
async function autoLogin(row) {
  row._auto = true
  try {
    const { data } = await api.post(`/accounts/${row.id}/autologin`, {}, { timeout: 240000 })
    if (data.ok) ElMessage.success('自动登录成功，凭证已刷新')
    else if (data.need_login) ElMessageBox.alert(data.detail, '需手动登录', { type: 'warning' })
    else ElMessage.warning(data.detail || '自动登录未成功')
    load()
  } catch (e) { ElMessage.error('自动登录失败：' + (e.response?.data?.detail || e.message)) }
  row._auto = false
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
async function keepAll() {
  keeping.value = true
  try { await api.post('/keep_tokens'); ElMessage.success('已触发后台保活，稍后刷新查看登录态') }
  catch (e) { ElMessage.error('触发失败：' + (e.response?.data?.detail || e.message)) }
  keeping.value = false
}
onMounted(load)
</script>

<style scoped>
/* 操作列四个按钮一行排列，去掉 Element 默认的按钮间距只保留 gap */
.op-btns { display: flex; flex-wrap: nowrap; gap: 6px; }
.op-btns :deep(.el-button + .el-button) { margin-left: 0; }
</style>
