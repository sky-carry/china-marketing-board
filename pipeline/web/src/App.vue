<template>
  <!-- 登录页：全屏，无侧边栏 -->
  <router-view v-if="isLogin" />
  <!-- 主界面 -->
  <el-container v-else style="height:100%">
    <el-aside :width="isCollapse ? '64px' : '178px'" class="side-aside">
      <div class="side-head" :class="{ collapsed: isCollapse }">
        <span v-show="!isCollapse" class="side-title">SKG 站外投放</span>
        <el-icon class="collapse-btn" :title="isCollapse ? '展开侧栏' : '收起侧栏'" @click="toggleCollapse">
          <Expand v-if="isCollapse" /><Fold v-else />
        </el-icon>
      </div>
      <el-menu :default-active="$route.path" router :collapse="isCollapse" :collapse-transition="false"
        background-color="transparent" text-color="#5b6472" active-text-color="#4f46e5">
        <el-menu-item index="/board"><el-icon><TrendCharts /></el-icon><span>数据看板</span></el-menu-item>
        <el-menu-item index="/account-board"><el-icon><DataBoard /></el-icon><span>账户看板</span></el-menu-item>
        <el-sub-menu index="platforms">
          <template #title><el-icon><Grid /></el-icon><span>平台明细</span></template>
          <el-menu-item v-for="p in platforms" :key="p" :index="`/platform/${p}`">{{ p }}</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/orders"><el-icon><List /></el-icon><span>订单明细</span></el-menu-item>
        <!-- 以下三个为管理页，仅管理员(密码登录)可见 -->
        <el-menu-item v-if="isAdmin" index="/accounts"><el-icon><User /></el-icon><span>账号管理</span></el-menu-item>
        <el-menu-item v-if="isAdmin" index="/users"><el-icon><Avatar /></el-icon><span>用户管理</span></el-menu-item>
        <el-menu-item v-if="isAdmin" index="/tasks"><el-icon><Timer /></el-icon><span>定时任务</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #ebeef5;display:flex;align-items:center;justify-content:space-between">
        <div v-if="isBoard" class="hdr-tabs">
          <button :class="{ active: boardTab==='realtime' }" @click="setBoardTab('realtime')">实时数据</button>
          <button v-if="isMain" :class="{ active: boardTab==='daily' }" @click="setBoardTab('daily')">日报看板</button>
          <button :class="{ active: boardTab==='overview' }" @click="setBoardTab('overview')">数据总览</button>
        </div>
        <span v-else style="font-size:16px;font-weight:600">{{ headerTitle }}</span>
        <el-dropdown @command="onCmd">
          <span style="cursor:pointer;color:#606266;font-size:14px;display:flex;align-items:center;gap:6px">
            <el-avatar v-if="me.avatar_url" :size="26" :src="me.avatar_url" />
            <el-icon v-else><UserFilled /></el-icon>{{ me.name || username }}<el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="isAdmin" command="pwd">修改密码</el-dropdown-item>
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
const isCollapse = ref(localStorage.getItem('sidebarCollapse') === '1')   // 侧栏收缩(记忆上次状态)
function toggleCollapse() { isCollapse.value = !isCollapse.value; localStorage.setItem('sidebarCollapse', isCollapse.value ? '1' : '0') }
const isLogin = computed(() => route.path === '/login')
const username = ref(localStorage.getItem('authUser') || 'skg')
const me = ref({})   // 当前登录用户(飞书资料，来自 /api/me)
const isAdmin = ref(localStorage.getItem('authAdmin') === '1')   // 管理员(密码登录/授权) 才显示管理页
const isMain = ref(localStorage.getItem('authMain') === '1')     // 主账号(密码管理员) 才显示日报看板
const headerTitle = computed(() => route.params.name ? `平台明细 · ${route.params.name}` : route.meta.title)
// 数据看板：header 里显示「实时数据/数据总览」标签，用 route.query.tab 驱动内容
const isBoard = computed(() => route.path === '/board')
const boardTab = computed(() => (['overview', 'daily'].includes(route.query.tab) ? route.query.tab : 'realtime'))
function setBoardTab(t) { router.push({ path: '/board', query: t === 'realtime' ? {} : { tab: t } }) }

const pwdDlg = ref(false); const pwd = reactive({ old: '', new: '' })
function onCmd(cmd) {
  if (cmd === 'logout') logout()
  else if (cmd === 'pwd') { pwd.old = ''; pwd.new = ''; pwdDlg.value = true }
}
async function logout() {
  try { await ElMessageBox.confirm('确认退出登录？', '提示', { type: 'warning' }) } catch { return }
  localStorage.removeItem('authToken')
  localStorage.removeItem('authAdmin')
  localStorage.removeItem('authMain')
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

// 心跳上报：统计用户在网页的停留时长（仅登录后、页面可见时；每 30 秒一次）
let lastBeat = Date.now()
function heartbeat() {
  if (document.visibilityState !== 'visible' || !localStorage.getItem('authToken')) return
  const now = Date.now(); const sec = Math.min(Math.round((now - lastBeat) / 1000), 90); lastBeat = now
  if (sec > 0) api.post('/heartbeat', { seconds: sec }).catch(() => {})
}

onMounted(async () => {
  try { const { data } = await api.get('/meta'); if (data.platforms?.length) platforms.value = data.platforms } catch {}
  try {
    const { data } = await api.get('/me')
    if (data.user) me.value = data.user
    else if (data.name) me.value = { name: data.name }   // 密码账号：显示名
    isAdmin.value = !!data.admin
    isMain.value = !!data.main
    localStorage.setItem('authAdmin', data.admin ? '1' : '0')
    localStorage.setItem('authMain', data.main ? '1' : '0')
  } catch {}
  setInterval(heartbeat, 30000)
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') lastBeat = Date.now() })
})
</script>

<style scoped>
/* 侧栏：明亮简约（设计方案1） */
.side-aside { background: #fff; border-right: 1px solid #eceef1; transition: width .2s; }
.side-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 14px 12px; }
.side-head.collapsed { justify-content: center; padding: 16px 0; }
.side-title { color: #1a1d23; font-size: 16px; font-weight: 600; letter-spacing: .5px; white-space: nowrap; overflow: hidden; }
.collapse-btn { color: #9aa1ab; font-size: 18px; cursor: pointer; flex: none; }
.collapse-btn:hover { color: #4f46e5; }
/* 菜单：圆角 pill、柔和 hover/active */
.el-menu { border-right: none; }
/* 展开态：圆角 pill + 间距（收起态用 Element Plus 默认布局，保证图标居中） */
.el-menu:not(.el-menu--collapse) { padding: 4px 10px; }
:deep(.el-menu:not(.el-menu--collapse) .el-menu-item),
:deep(.el-menu:not(.el-menu--collapse) .el-sub-menu__title) { height: 42px; line-height: 42px; margin: 3px 0; border-radius: 10px; }
/* 颜色 / 选中态：两种模式通用 */
:deep(.el-menu-item), :deep(.el-sub-menu__title) { color: #5b6472; }
:deep(.el-menu-item:hover), :deep(.el-sub-menu__title:hover) { background: #f2f3f5; color: #1a1d23; }
:deep(.el-menu-item.is-active) { background: #eef0fe; color: #4f46e5; font-weight: 600; }
:deep(.el-sub-menu.is-active > .el-sub-menu__title) { color: #4f46e5; }
:deep(.el-sub-menu .el-menu-item) { height: 38px; line-height: 38px; }
/* 数据看板 header 顶部标签（实时数据/数据总览） */
.hdr-tabs { display: flex; gap: 6px; }
.hdr-tabs button {
  border: none; background: transparent; font-size: 14.5px; font-weight: 600; color: #606266;
  cursor: pointer; padding: 6px 16px; border-radius: 8px; transition: all .15s;
}
.hdr-tabs button:hover:not(.active) { background: #f5f6f8; color: #1a1d23; }
.hdr-tabs button.active { color: #1a1d23; background: #ebedf0; font-weight: 700; }
</style>
