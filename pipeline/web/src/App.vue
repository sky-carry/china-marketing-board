<template>
  <!-- 登录页：全屏，无侧边栏 -->
  <router-view v-if="isLogin" />
  <!-- 主界面 -->
  <el-container v-else style="height:100%">
    <el-aside width="200px" style="background:#20222a">
      <div style="color:#fff;font-size:16px;font-weight:600;padding:18px 20px;letter-spacing:1px">📊 投放数据平台</div>
      <el-menu :default-active="$route.fullPath" router background-color="#20222a" text-color="#c6cad4" active-text-color="#409EFF">
        <el-menu-item index="/dashboard"><el-icon><TrendCharts /></el-icon><span>数据看板</span></el-menu-item>
        <el-menu-item index="/account-board"><el-icon><DataBoard /></el-icon><span>账户看板</span></el-menu-item>
        <el-sub-menu index="platforms">
          <template #title><el-icon><Grid /></el-icon><span>平台明细</span></template>
          <el-menu-item v-for="p in platforms" :key="p" :index="`/platform/${p}`">{{ p }}</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/orders"><el-icon><List /></el-icon><span>订单明细</span></el-menu-item>
        <el-menu-item index="/accounts"><el-icon><User /></el-icon><span>账号管理</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><Timer /></el-icon><span>定时任务</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #ebeef5;display:flex;align-items:center;justify-content:space-between">
        <span style="font-size:16px;font-weight:600">{{ headerTitle }}</span>
        <el-dropdown @command="onCmd">
          <span style="cursor:pointer;color:#606266;font-size:14px;display:flex;align-items:center;gap:4px">
            <el-icon><UserFilled /></el-icon>{{ username }}<el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="pwd">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main style="padding:0;overflow:hidden"><router-view /></el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="pwdDlg" title="修改密码" width="360">
    <el-form label-width="80">
      <el-form-item label="原密码"><el-input v-model="pwd.old" type="password" show-password /></el-form-item>
      <el-form-item label="新密码"><el-input v-model="pwd.new" type="password" show-password placeholder="至少6位" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDlg=false">取消</el-button>
      <el-button type="primary" @click="savePwd">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from './api'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute(); const router = useRouter()
const platforms = ref(['小飞机', '沸点', '微橙', '麦斯'])
const isLogin = computed(() => route.path === '/login')
const username = ref(localStorage.getItem('authUser') || 'skg')
const headerTitle = computed(() => route.params.name ? `平台明细 · ${route.params.name}` : route.meta.title)

const pwdDlg = ref(false); const pwd = reactive({ old: '', new: '' })
function onCmd(cmd) {
  if (cmd === 'logout') logout()
  else if (cmd === 'pwd') { pwd.old = ''; pwd.new = ''; pwdDlg.value = true }
}
async function logout() {
  try { await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' }) } catch { return }
  localStorage.removeItem('authToken')
  router.replace('/login')
}
async function savePwd() {
  if ((pwd.new || '').length < 6) return ElMessage.warning('新密码至少 6 位')
  try {
    await api.post('/change_password', { username: username.value, old: pwd.old, new: pwd.new })
    ElMessage.success('密码已修改，请重新登录')
    pwdDlg.value = false
    localStorage.removeItem('authToken'); router.replace('/login')
  } catch (e) { ElMessage.error(e.response?.data?.detail || '修改失败') }
}

onMounted(async () => {
  try { const { data } = await api.get('/meta'); if (data.platforms?.length) platforms.value = data.platforms } catch {}
})
</script>
