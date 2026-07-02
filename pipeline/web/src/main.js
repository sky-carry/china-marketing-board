import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import * as Icons from '@element-plus/icons-vue'
import router from './router'
import App from './App.vue'
import './style.css'

const app = createApp(App)
for (const [k, v] of Object.entries(Icons)) app.component(k, v)
app.use(ElementPlus, { locale: zhCn }).use(router).mount('#app')
