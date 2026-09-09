import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const http = axios.create({ baseURL: '/api/v1', timeout: 120000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('solartrace_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error.response?.status
    const msg = error.response?.data?.error?.message || error.message || '请求失败'
    if (status === 401) {
      localStorage.removeItem('solartrace_token')
      localStorage.removeItem('solartrace_user')
      router.push('/login')
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export function authHeaders() {
  const token = localStorage.getItem('solartrace_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export default http
