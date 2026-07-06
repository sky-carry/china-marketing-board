import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import AccountBoard from './views/AccountBoard.vue'
import PlatformDetail from './views/PlatformDetail.vue'
import Accounts from './views/Accounts.vue'
import Tasks from './views/Tasks.vue'
import Login from './views/Login.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: Login, meta: { public: true, title: '登录' } },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: Dashboard, meta: { title: '数据看板' } },
    { path: '/account-board', component: AccountBoard, meta: { title: '账户看板' } },
    { path: '/platform/:name', component: PlatformDetail, meta: { title: '平台明细' } },
    { path: '/accounts', component: Accounts, meta: { title: '账号管理' } },
    { path: '/tasks', component: Tasks, meta: { title: '定时任务' } },
  ]
})

// 未登录一律跳登录页；已登录访问登录页则回看板
router.beforeEach((to) => {
  const authed = !!localStorage.getItem('authToken')
  if (!to.meta.public && !authed) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.path === '/login' && authed) return { path: '/dashboard' }
})

export default router
