import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
  {
    path: '/',
    component: () => import('../layout/Layout.vue'),
    redirect: '/qa',
    children: [
      { path: 'qa', name: 'qa', component: () => import('../views/Chat.vue'), meta: { title: '智能问答' } },
      { path: 'search', name: 'search', component: () => import('../views/SearchLab.vue'), meta: { title: '检索调试' } },
      { path: 'docs', name: 'docs', component: () => import('../views/Knowledge.vue'), meta: { title: '文档库' } },
      { path: 'eval', name: 'eval', component: () => import('../views/Eval.vue'), meta: { title: 'RAG 评测' } },
      { path: 'users', name: 'users', component: () => import('../views/Users.vue'), meta: { title: '用户管理', admin: true } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/qa' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const token = localStorage.getItem('solartrace_token')
  if (!to.meta.public && !token) return { name: 'login' }
  if (to.meta.admin) {
    const user = JSON.parse(localStorage.getItem('solartrace_user') || '{}')
    if (user.role !== 'admin') return { name: 'qa' }
  }
  return true
})

export default router
