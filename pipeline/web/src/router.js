import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Accounts from './views/Accounts.vue'
import Tasks from './views/Tasks.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: Dashboard, meta: { title: '数据看板' } },
    { path: '/accounts', component: Accounts, meta: { title: '账号管理' } },
    { path: '/tasks', component: Tasks, meta: { title: '定时任务' } },
  ]
})
