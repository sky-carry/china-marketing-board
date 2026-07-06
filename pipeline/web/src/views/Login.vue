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
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'
import { ElMessage } from 'element-plus'

const username = ref(''); const password = ref(''); const loading = ref(false)
const router = useRouter(); const route = useRoute()

async function submit() {
  if (!username.value || !password.value) return ElMessage.warning('请输入账号和密码')
  loading.value = true
  try {
    const { data } = await api.post('/login', { username: username.value, password: password.value })
    localStorage.setItem('authToken', data.token)
    localStorage.setItem('authUser', data.username)
    router.replace(route.query.redirect || '/dashboard')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally { loading.value = false }
}
</script>

<style scoped>
.login-wrap { height: 100%; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1f2735 0%, #2b3a52 100%); }
.login-card { width: 340px; background: #fff; border-radius: 14px; padding: 34px 30px 30px;
  box-shadow: 0 12px 40px rgba(0,0,0,.25); }
.brand { font-size: 20px; font-weight: 700; text-align: center; color: #303133; }
.sub { font-size: 13px; color: #909399; text-align: center; margin: 6px 0 24px; }
</style>
