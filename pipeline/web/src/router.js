import { createRouter, createWebHashHistory } from 'vue-router'
import DataBoard from './views/DataBoard.vue'
import AccountBoard from './views/AccountBoard.vue'
import PlatformDetail from './views/PlatformDetail.vue'
import Orders from './views/Orders.vue'
import Accounts from './views/Accounts.vue'
import Users from './views/Users.vue'
import Tasks from './views/Tasks.vue'
import Login from './views/Login.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: Login, meta: { public: true, title: '登录' } },
    { path: '/', redirect: '/board' },
    { path: '/board', component: DataBoard, meta: { title: '数据看板' } },   // 内含 实时数据/数据总览 两个标签
    { path: '/realtime', redirect: '/board' },                              // 兼容旧路径
    { path: '/overview', redirect: '/board' },
    { path: '/dashboard', redirect: '/board' },
    { path: '/account-board', component: AccountBoard, meta: { title: '账户看板' } },
    { path: '/platform/:name', component: PlatformDetail, meta: { title: '平台明细' } },
    { path: '/orders', component: Orders, meta: { title: '订单明细' } },
    { path: '/accounts', component: Accounts, meta: { title: '账号管理', admin: true } },
    { path: '/users', component: Users, meta: { title: '用户管理', admin: true } },
    { path: '/tasks', component: Tasks, meta: { title: '定时任务', admin: true } },
  ]
})

// 未登录一律跳登录页；已登录访问登录页则回看板
router.beforeEach((to) => {
  // 切页前让当前聚焦元素失焦：否则 el-date-picker/下拉筛选器选完后仍持有焦点，
  // 其 teleport 到 body 的下拉面板不随切页关闭，切回本页时会再次弹出(bug 修复)
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
  const authed = !!localStorage.getItem('authToken')
  if (!to.meta.public && !authed) return { path: '/login', query: { redirect: to.fullPath } }
  // 已登录访问登录页回看板；但飞书回调带 token(?token=)时要放行，让 Login 存下新 token(否则旧token把新token挡掉)
  if (to.path === '/login' && authed && !to.query.token) return { path: '/board' }
  // 管理页(账号管理/用户管理/定时任务)仅管理员可进；非管理员直接回看板(后端也有403兜底)
  if (to.meta.admin && localStorage.getItem('authAdmin') !== '1') return { path: '/board' }
})

export default router
