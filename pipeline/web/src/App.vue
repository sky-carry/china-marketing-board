<template>
  <el-container style="height:100%">
    <el-aside width="200px" style="background:#20222a">
      <div style="color:#fff;font-size:16px;font-weight:600;padding:18px 20px;letter-spacing:1px">📊 投放数据平台</div>
      <el-menu :default-active="$route.path" router background-color="#20222a" text-color="#c6cad4" active-text-color="#409EFF">
        <el-menu-item index="/dashboard"><el-icon><TrendCharts /></el-icon><span>数据看板</span></el-menu-item>
        <el-menu-item index="/accounts"><el-icon><User /></el-icon><span>账号管理</span></el-menu-item>
        <el-menu-item index="/tasks"><el-icon><Timer /></el-icon><span>定时任务</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #ebeef5;display:flex;align-items:center">
        <span style="font-size:16px;font-weight:600">{{ $route.meta.title }}</span>
      </el-header>
      <el-main style="padding:0;overflow:auto"><router-view /></el-main>
    </el-container>
  </el-container>
</template>
