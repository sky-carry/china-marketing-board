<template>
  <div class="db-wrap">
    <!-- 顶部标签：实时数据 / 数据总览（默认实时数据） -->
    <div class="db-tabs">
      <button :class="{ active: tab === 'realtime' }" @click="tab = 'realtime'">实时数据</button>
      <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">数据总览</button>
    </div>
    <div class="db-body">
      <RealtimeBoard v-if="tab === 'realtime'" />
      <Dashboard v-else />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import RealtimeBoard from './RealtimeBoard.vue'
import Dashboard from './Dashboard.vue'
const tab = ref('realtime')   // 进入「数据看板」默认显示实时数据
</script>

<style scoped>
.db-wrap { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.db-tabs { display: flex; gap: 8px; padding: 8px 12px; background: #fff; border-bottom: 1px solid #ebeef5; flex: none; }
.db-tabs button {
  border: none; background: transparent; font-size: 15px; font-weight: 600; color: #606266;
  cursor: pointer; padding: 6px 18px; border-radius: 6px; transition: all .15s;
}
.db-tabs button:hover:not(.active) { background: #f5f7fa; color: #303133; }
.db-tabs button.active { color: #fff; background: #20222a; }
.db-body { flex: 1 1 auto; min-height: 0; overflow: auto; }
</style>
