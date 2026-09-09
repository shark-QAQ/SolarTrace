<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <div class="title">☀ 光溯 · SolarTrace</div>
      <div class="subtitle">光伏电站建设政策与规范智能问答平台</div>
      <el-form :model="form" label-position="top" @keyup.enter="doLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" />
        </el-form-item>
        <el-button type="primary" class="full" :loading="loading" @click="doLogin">登 录</el-button>
        <div class="hint">
          演示账号：admin/admin123（管理员）；editor/secret123；viewer/secret123
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import http from '../api/http'

const router = useRouter()
const form = reactive({ username: 'admin', password: 'admin123' })
const loading = ref(false)

async function doLogin() {
  loading.value = true
  try {
    const { data } = await http.post('/auth/login', form)
    localStorage.setItem('solartrace_token', data.access_token)
    localStorage.setItem('solartrace_user', JSON.stringify(data.user))
    router.push('/qa')
  } catch (_e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eaf4ff, #f6f9fb);
}
.login-card {
  width: 380px;
  padding: 12px 8px;
}
.title {
  font-size: 22px;
  font-weight: 700;
  text-align: center;
}
.subtitle {
  color: #909399;
  text-align: center;
  margin: 6px 0 18px;
  font-size: 13px;
}
.full {
  width: 100%;
}
.hint {
  margin-top: 14px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
