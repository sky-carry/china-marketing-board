<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand">📊 投放数据平台</div>
      <div class="sub">请登录后查看数据</div>
      <el-form @submit.prevent="submit">
        <el-input v-model="username" size="large" placeholder="账号" prefix-icon="User" style="margin-bottom:14px" @keyup.enter="submit" />
        <el-input v-model="password" type="password" size="large" placeholder="密码" prefix-icon="Lock" show-password
          style="margin-bottom:18px" @keyup.enter="submit" />
        <el-button type="primary" size="large" style="width:100%" :loading="loading" @click="submit">登 录</el-button>
      </el-form>

      <div v-if="authCfg.dev_login || authCfg.feishu_enabled" class="alt">
        <div class="divider"><span>或</span></div>
        <!-- 本地开发免登录(dev_login 优先，服务器不会有此项) -->
        <el-button v-if="authCfg.dev_login" size="large" style="width:100%" @click="devLogin">🛠 开发免登录</el-button>
        <!-- 飞书登录 -->
        <el-button v-else type="success" size="large" style="width:100%" :loading="fsLoading" @click="feishuLogin">
          飞书登录
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'
import { ElMessage } from 'element-plus'

const username = ref(''); const password = ref(''); const loading = ref(false); const fsLoading = ref(false)
const router = useRouter(); const route = useRoute()
const authCfg = ref({ feishu_enabled: false, dev_login: false })

function finishLogin(token, user, admin) {
  localStorage.setItem('authToken', token)
  localStorage.setItem('authUser', user)
  localStorage.setItem('authAdmin', admin ? '1' : '0')
  router.replace(route.query.redirect || '/board')
}

async function submit() {
  if (!username.value || !password.value) return ElMessage.warning('请输入账号和密码')
  loading.value = true
  try {
    const { data } = await api.post('/login', { username: username.value, password: password.value })
    finishLogin(data.token, data.username, data.admin)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally { loading.value = false }
}

async function feishuLogin() {
  fsLoading.value = true
  try {
    const { data } = await api.get('/feishu/login_url')
    window.location.href = data.url          // 跳转飞书授权页，回调后带 token 跳回本页
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '获取飞书登录地址失败'); fsLoading.value = false
  }
}

async function devLogin() {
  try {
    const { data } = await api.post('/dev_login')
    finishLogin(data.token, data.username, data.admin)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '开发免登录失败')
  }
}

onMounted(async () => {
  // 飞书回调的 token 已由 main.js(bootAuth) 在应用启动前处理，这里只管错误提示与登录方式
  if (route.query.err) ElMessage.error(String(route.query.err))
  try { const { data } = await api.get('/auth_config'); authCfg.value = data } catch {}
})
</script>

<style scoped>
.login-wrap { height: 100%; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1f2735 0%, #2b3a52 100%); }
.login-card { width: 340px; background: #fff; border-radius: 14px; padding: 34px 30px 30px;
  box-shadow: 0 12px 40px rgba(0,0,0,.25); }
.brand { font-size: 20px; font-weight: 700; text-align: center; color: #303133; }
.sub { font-size: 13px; color: #909399; text-align: center; margin: 6px 0 24px; }
.alt { margin-top: 16px; }
.divider { display: flex; align-items: center; color: #c0c4cc; font-size: 12px; margin-bottom: 14px; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: #ebeef5; }
.divider span { padding: 0 12px; }
</style>
