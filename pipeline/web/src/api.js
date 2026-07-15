import axios from 'axios'

// paramsSerializer.indexes=null：数组参数序列化为重复键 key=a&key=b（FastAPI 的 Query(list) 需要此格式，
// 而非默认的 key[]=a）。多选筛选(账户/类目等)依赖它。
const api = axios.create({ baseURL: '/api', timeout: 60000, paramsSerializer: { indexes: null } })

// 请求带上登录 token
api.interceptors.request.use(cfg => {
  const t = localStorage.getItem('authToken')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

// 401 未登录/过期 -> 清除并跳登录页
api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401 && !location.hash.startsWith('#/login')) {
      localStorage.removeItem('authToken')
      location.hash = '#/login'
    }
    return Promise.reject(err)
  }
)

export default api
