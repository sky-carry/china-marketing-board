import './bootAuth'   // 必须最前：飞书 token 前置落地并清理 URL(须在 router 创建前执行)
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'   // 注册 dayjs 中文 locale：weekStart=1，日期选择器一周从周一起（一二三四五六日，日在最后）
dayjs.locale('zh-cn')
import * as Icons from '@element-plus/icons-vue'
import router from './router'
import App from './App.vue'
import './style.css'

const app = createApp(App)
for (const [k, v] of Object.entries(Icons)) app.component(k, v)
app.use(ElementPlus, { locale: zhCn }).use(router).mount('#app')

// 切走浏览器标签/窗口时，让当前聚焦元素失焦。否则 el-date-picker 选完日期后输入框仍持有焦点，
// 回到本标签页时浏览器会自动重新聚焦它 -> Element Plus 又把日期面板弹出来。切走时先失焦即可根治。
function blurActive() {
  const el = document.activeElement
  if (el instanceof HTMLElement && el !== document.body) el.blur()
}
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') blurActive() })
window.addEventListener('blur', blurActive)   // 切换到别的应用/窗口时同理
