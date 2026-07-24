<template>
  <div style="padding:16px;height:100%;box-sizing:border-box;overflow:auto">
    <el-tabs v-model="tab">
      <!-- ========== 账号密码用户 ========== -->
      <el-tab-pane label="账号密码" name="pw">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <span style="color:#909399;font-size:13px">
            给公司外的人开账号用。<b>外部账号一律普通用户</b>，只能看分配给他的「代理商/账户」数据，进不了管理页。内置 <b>skg</b> 为管理员。
          </span>
          <el-button size="small" type="primary" @click="openCreate" style="margin-left:auto">+ 新增账号</el-button>
          <el-button size="small" :loading="pwLoading" @click="loadPw">刷新</el-button>
        </div>
        <el-table :data="pwRows" v-loading="pwLoading" size="small" border stripe style="width:100%">
          <el-table-column prop="username" label="用户名" width="130" />
          <el-table-column prop="name" label="显示名" min-width="110" show-overflow-tooltip />
          <el-table-column label="角色" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_admin?'danger':'info'" effect="plain">{{ row.is_admin?'管理员':'普通' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="数据范围" min-width="200">
            <template #default="{ row }">
              <span v-if="row.is_admin" style="color:#909399">全部数据</span>
              <template v-else>
                <el-tag v-for="a in row.scope_agencies" :key="'a'+a" size="small" effect="plain" style="margin:1px">{{ a }}</el-tag>
                <el-tag v-for="s in row.scope_stores" :key="'s'+s" size="small" type="warning" effect="plain" style="margin:1px">店:{{ s }}</el-tag>
                <el-tag v-if="row.scope_accounts.length" size="small" type="success" effect="plain" style="margin:1px">+{{ row.scope_accounts.length }} 个账户</el-tag>
                <span v-if="!row.scope_agencies.length && !row.scope_stores.length && !row.scope_accounts.length" style="color:#e6a23c">未分配（看不到数据）</span>
              </template>
            </template>
          </el-table-column>
          <el-table-column label="有效期" width="110" align="center">
            <template #default="{ row }">
              <span v-if="!row.expires_at" style="color:#909399">长期</span>
              <span v-else :style="{ color: isExpired(row.expires_at) ? '#f56c6c' : '' }">{{ row.expires_at }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="note" label="备注" min-width="90" show-overflow-tooltip />
          <el-table-column prop="login_count" label="登录次数" width="90" align="center" sortable />
          <el-table-column label="首次登录" width="160" align="center">
            <template #default="{ row }"><span style="white-space:nowrap">{{ row.first_login_at || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="最近登录" width="160" align="center">
            <template #default="{ row }"><span style="white-space:nowrap">{{ row.last_login_at || '—' }}</span></template>
          </el-table-column>
          <el-table-column label="近30天停留" width="110" align="center">
            <template #default="{ row }">{{ dur(row.d30_seconds) }}</template>
          </el-table-column>
          <el-table-column label="今日停留" width="100" align="center">
            <template #default="{ row }">{{ dur(row.today_seconds) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-switch v-model="row.is_active" :loading="row._saving" :disabled="row.username==='skg'"
                inline-prompt @change="v => toggleActive(row, v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" type="warning" plain @click="resetPw(row)">重置密码</el-button>
              <el-button size="small" type="danger" plain :disabled="row.username==='skg'" @click="del(row)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ========== 飞书登录用户（原有） ========== -->
      <el-tab-pane :label="`飞书登录（${fsRows.length}）`" name="feishu">
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
          <span style="color:#909399;font-size:13px">飞书扫码登录自动建号（公司内部）；禁用后无法再次登录。飞书普通用户默认可看全部数据。</span>
          <el-button size="small" :loading="fsLoading" @click="loadFs" style="margin-left:auto">刷新</el-button>
        </div>
        <el-table :data="fsRows" v-loading="fsLoading" size="small" border stripe style="width:100%">
          <el-table-column label="头像" width="66" align="center">
            <template #default="{ row }">
              <el-avatar v-if="row.avatar_url" :size="30" :src="row.avatar_url" />
              <el-icon v-else :size="20"><UserFilled /></el-icon>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="姓名" min-width="120" />
          <el-table-column prop="email" label="邮箱" min-width="170" show-overflow-tooltip />
          <el-table-column prop="mobile" label="手机" width="120" />
          <el-table-column label="角色" width="80" align="center">
            <template #default="{ row }"><el-tag size="small" :type="row.is_admin?'danger':'info'" effect="plain">{{ row.is_admin?'管理员':'普通' }}</el-tag></template>
          </el-table-column>
          <el-table-column prop="login_count" label="登录次数" width="90" align="center" sortable />
          <el-table-column label="首次登录" width="160" align="center" sortable :sort-by="r => r.first_login_at || ''">
            <template #default="{ row }">{{ fmt(row.first_login_at) }}</template>
          </el-table-column>
          <el-table-column label="最近登录" width="160" align="center" sortable :sort-by="r => r.last_login_at || ''">
            <template #default="{ row }">{{ fmt(row.last_login_at) }}</template>
          </el-table-column>
          <el-table-column label="今日停留" width="100" align="center" sortable :sort-by="r => r.today_seconds || 0">
            <template #default="{ row }">{{ dur(row.today_seconds) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center" fixed="right">
            <template #default="{ row }">
              <el-switch v-model="row.is_active" :loading="row._saving" inline-prompt @change="v => toggleFs(row, v)" />
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 新增/编辑 账号 弹窗 -->
    <el-dialog v-model="dlg" :title="form._new ? '新增账号' : ('编辑 ' + form.username)" width="560">
      <el-form label-width="90">
        <el-form-item label="用户名">
          <el-input v-model="form.username" :disabled="!form._new" placeholder="登录用户名（英文/数字）" />
        </el-form-item>
        <el-form-item :label="form._new ? '密码' : '新密码'">
          <el-input v-model="form.password" type="password" show-password
            :placeholder="form._new ? '至少6位' : '留空则不修改'" />
        </el-form-item>
        <el-form-item label="显示名"><el-input v-model="form.name" placeholder="展示用名称" /></el-form-item>
        <el-form-item label="数据范围">
          <div style="width:100%">
            <el-select v-model="form.scope_agencies" multiple filterable clearable collapse-tags collapse-tags-tooltip
              placeholder="按代理商授权（可多选）" style="width:100%;margin-bottom:8px">
              <el-option v-for="a in scopeOpt.agencies" :key="a" :label="a" :value="a" />
            </el-select>
            <el-select v-model="form.scope_stores" multiple filterable clearable collapse-tags collapse-tags-tooltip
              placeholder="按店铺授权（可多选）" style="width:100%;margin-bottom:8px">
              <el-option v-for="s in scopeOpt.stores" :key="s" :label="s" :value="s" />
            </el-select>
            <el-select v-model="form.scope_accounts" multiple filterable clearable collapse-tags collapse-tags-tooltip
              placeholder="或按具体账户授权（可多选）" style="width:100%">
              <el-option v-for="a in scopeOpt.accounts" :key="a.id" :label="a.name" :value="a.id" />
            </el-select>
            <div style="color:#909399;font-size:12px;margin-top:4px">
              代理商与店铺：<b>都选取交集</b>（既属该代理商又属该店铺的账户），<b>只选其一则按该维度</b>。再 ∪ 上单独选中的账户。都不选 = 看不到任何数据。
            </div>
          </div>
        </el-form-item>
        <el-form-item label="有效期">
          <el-date-picker v-model="form.expires_at" type="date" value-format="YYYY-MM-DD"
            placeholder="留空=长期有效" style="width:200px" />
          <span style="color:#909399;font-size:12px;margin-left:8px">到期后自动无法登录</span>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" placeholder="选填" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg=false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const tab = ref('pw')
function fmt(s) { return s ? new Date(s).toLocaleString('zh-CN', { hour12: false }) : '—' }
function isExpired(d) { return d && d < new Date().toISOString().slice(0, 10) }
// 今日停留秒数 -> 可读时长
function dur(sec) {
  sec = Number(sec) || 0
  if (sec < 60) return sec ? sec + '秒' : '—'
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60)
  return h ? `${h}时${m}分` : `${m}分`
}

// ---------- 账号密码 ----------
const pwRows = ref([]); const pwLoading = ref(false)
const scopeOpt = reactive({ agencies: [], stores: [], accounts: [] })
async function loadPw() {
  pwLoading.value = true
  try { const { data } = await api.get('/auth_accounts'); pwRows.value = data.accounts || [] }
  catch (e) { ElMessage.error(e.response?.data?.detail || '加载失败') }
  finally { pwLoading.value = false }
}
async function loadScopeOptions() {
  try { const { data } = await api.get('/scope_options'); scopeOpt.agencies = data.agencies || []; scopeOpt.stores = data.stores || []; scopeOpt.accounts = data.accounts || [] } catch {}
}

const dlg = ref(false); const saving = ref(false)
const form = reactive({ _new: true, username: '', password: '', name: '', scope_agencies: [], scope_stores: [], scope_accounts: [], expires_at: null, note: '' })
function openCreate() {
  Object.assign(form, { _new: true, username: '', password: '', name: '', scope_agencies: [], scope_stores: [], scope_accounts: [], expires_at: null, note: '' })
  dlg.value = true
}
function openEdit(row) {
  Object.assign(form, {
    _new: false, username: row.username, password: '', name: row.name || '',
    scope_agencies: [...(row.scope_agencies || [])], scope_stores: [...(row.scope_stores || [])], scope_accounts: [...(row.scope_accounts || [])],
    expires_at: row.expires_at || null, note: row.note || '',
  })
  dlg.value = true
}
async function save() {
  if (form._new && !form.username.trim()) return ElMessage.warning('请填用户名')
  if (form._new && (form.password || '').length < 6) return ElMessage.warning('密码至少 6 位')
  if (!form._new && form.password && form.password.length < 6) return ElMessage.warning('新密码至少 6 位')
  saving.value = true
  try {
    const body = {
      name: form.name, note: form.note, expires_at: form.expires_at || null,
      scope_agencies: form.scope_agencies, scope_stores: form.scope_stores, scope_accounts: form.scope_accounts,
    }
    if (form.password) body.password = form.password
    if (form._new) { body.username = form.username.trim(); await api.post('/auth_accounts', body) }
    else await api.put(`/auth_accounts/${encodeURIComponent(form.username)}`, body)
    ElMessage.success('已保存'); dlg.value = false; loadPw()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}
async function toggleActive(row, v) {
  row._saving = true
  try { await api.put(`/auth_accounts/${encodeURIComponent(row.username)}`, { is_active: v }); ElMessage.success(v ? '已启用' : '已停用') }
  catch (e) { row.is_active = !v; ElMessage.error(e.response?.data?.detail || '操作失败') }
  finally { row._saving = false }
}
async function resetPw(row) {
  try {
    const { value } = await ElMessageBox.prompt(`给「${row.name || row.username}」设置新密码（至少6位）`, '重置密码',
      { inputType: 'password', inputPlaceholder: '新密码', confirmButtonText: '确定', cancelButtonText: '取消',
        inputValidator: v => (v && v.length >= 6) || '至少 6 位' })
    await api.put(`/auth_accounts/${encodeURIComponent(row.username)}`, { password: value })
    ElMessage.success('密码已重置')
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '重置失败') }
}
async function del(row) {
  try {
    await ElMessageBox.confirm(`删除账号「${row.username}」？删除后该账号无法登录。`, '确认', { type: 'warning' })
    await api.delete(`/auth_accounts/${encodeURIComponent(row.username)}`); ElMessage.success('已删除'); loadPw()
  } catch (e) { if (e !== 'cancel') ElMessage.error(e.response?.data?.detail || '删除失败') }
}

// ---------- 飞书登录用户 ----------
const fsRows = ref([]); const fsLoading = ref(false)
async function loadFs() {
  fsLoading.value = true
  try { const { data } = await api.get('/users'); fsRows.value = data.users || [] }
  catch (e) { ElMessage.error(e.response?.data?.detail || '加载失败') }
  finally { fsLoading.value = false }
}
async function toggleFs(row, v) {
  row._saving = true
  try { await api.post('/users/set_active', { id: row.id, is_active: v }); ElMessage.success(v ? '已启用' : '已禁用') }
  catch (e) { row.is_active = !v; ElMessage.error(e.response?.data?.detail || '操作失败') }
  finally { row._saving = false }
}

onMounted(() => { loadPw(); loadScopeOptions(); loadFs() })
</script>
