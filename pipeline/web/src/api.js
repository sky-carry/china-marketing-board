import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 60000 })

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
