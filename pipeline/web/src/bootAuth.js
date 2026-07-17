// 飞书登录回调前置处理：把回调带回的 token 落地到 localStorage，并把 URL 清成 #/dashboard。
// 必须作为 main.js 的第一个 import 执行——要赶在 ./router 的 createWebHashHistory 之前，
// 否则它会快照到还带着 ?token 的旧地址，导致回到登录页/刷新循环。
// 这样 Vue/router 启动时已带 token 且 URL 干净，不会发出无 token 的请求引发竞态。
const hash = window.location.hash            // 形如 #/login?token=xxx&name=yyy
const qi = hash.indexOf('?')
if (qi >= 0) {
  const params = new URLSearchParams(hash.slice(qi + 1))
  const token = params.get('token')
  if (token) {
    localStorage.setItem('authToken', token)
    localStorage.setItem('authUser', params.get('name') || '飞书用户')
    localStorage.setItem('authAdmin', '0')   // 飞书默认普通用户，清掉上一次会话可能残留的 admin；/api/me 再按 is_admin 校正
    window.location.replace(window.location.pathname + '#/dashboard')   // 清掉带 token 的 hash
  }
}
