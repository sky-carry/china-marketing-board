<template>
  <el-container style="height:100%">
    <el-aside width="200px" style="background:#20222a">
      <div style="color:#fff;font-size:16px;font-weight:600;padding:18px 20px;letter-spacing:1px">📊 投放数据平台</div>
      <el-menu :default-active="$route.fullPath" router background-color="#20222a" text-color="#c6cad4" active-text-color="#409EFF">
        <el-menu-item index="/dashboard"><el-icon><TrendCharts /></el-icon><span>数据看板</span></el-menu-item>
        <el-menu-item index="/account-board"><el-icon><DataBoard /></el-icon><span>账户看板</span></el-menu-item>
        <el-sub-menu index="platforms">
          <template #title><el-icon><Grid /></el-icon><span>平台明细</span></template>
          <el-menu-item v-for="p in platforms" :key="p" :index="`/platform/${p}`">{{ p }}</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/accounts"><el-icon><User /></el-icon><span>账号管理</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><Timer /></el-icon><span>定时任务</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #ebeef5;display:flex;align-items:center">
        <span style="font-size:16px;font-weight:600">{{ headerTitle }}</span>
      </el-header>
      <el-main style="padding:0;overflow:hidden"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from './api'
const route = useRoute()
const platforms = ref(['小飞机', '沸点', '微橙', '麦斯'])
const headerTitle = computed(() => route.params.name ? `平台明细 · ${route.params.name}` : route.meta.title)
onMounted(async () => {
  try { const { data } = await api.get('/meta'); if (data.platforms?.length) platforms.value = data.platforms } catch {}
})
</script>
