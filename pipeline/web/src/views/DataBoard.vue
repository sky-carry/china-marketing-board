<template>
  <!-- 标签栏在顶部 header（App.vue）里，这里只按 route.query.tab 显示对应看板 -->
  <div class="db-wrap">
    <RealtimeBoard v-if="tab === 'realtime'" />
    <DailyReport v-else-if="tab === 'daily'" />
    <Dashboard v-else />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import RealtimeBoard from './RealtimeBoard.vue'
import DailyReport from './DailyReport.vue'
import Dashboard from './Dashboard.vue'
const route = useRoute()
const isMain = localStorage.getItem('authMain') === '1'   // 日报看板仅主账号可见(直接改 URL 也回落到实时数据)
const tab = computed(() => {
  const t = ['overview', 'daily'].includes(route.query.tab) ? route.query.tab : 'realtime'   // 默认实时数据
  return t === 'daily' && !isMain ? 'realtime' : t
})
</script>

<style scoped>
.db-wrap { height: 100%; min-height: 0; overflow: auto; }
</style>
