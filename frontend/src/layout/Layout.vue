<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">
        <span class="brand-mark">☀</span>
        <div>
          <div class="brand-name">光溯 SolarTrace</div>
          <div class="brand-sub">光伏政策智能问答</div>
        </div>
      </div>
      <el-menu :default-active="active" router class="menu">
        <el-menu-item index="/qa"><el-icon><ChatDotRound /></el-icon>智能问答</el-menu-item>
        <el-menu-item index="/search"><el-icon><Search /></el-icon>检索调试</el-menu-item>
        <el-menu-item index="/docs"><el-icon><Folder /></el-icon>文档库</el-menu-item>
        <el-menu-item index="/eval"><el-icon><DataAnalysis /></el-icon>RAG 评测</el-menu-item>
        <el-menu-item v-if="user.role === 'admin'" index="/users">
          <el-icon><User /></el-icon>用户管理
        </el-menu-item>
      </el-menu>
      <div class="aside-foot">
        <el-dropdown @command="onCommand">
          <span class="user-chip">
            <el-avatar :size="24">{{ (user.display_name || user.username || '?').slice(0, 1) }}</el-avatar>
            <span class="text">{{ user.display_name || user.username }}</span>
            <el-tag size="small" type="info" effect="plain">{{ roleLabel }}</el-tag>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-aside>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound, Search, Folder, DataAnalysis, User } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const user = computed(() => JSON.parse(localStorage.getItem('solartrace_user') || '{}'))
const active = computed(() => '/' + (route.path.split('/')[1] || 'qa'))
const roleLabel = computed(() => ({ admin: '管理员', editor: '编辑', viewer: '访客' }[user.value.role] || user.value.role))

function onCommand(cmd) {
  if (cmd === 'logout') {
    localStorage.removeItem('solartrace_token')
    localStorage.removeItem('solartrace_user')
    router.push('/login')
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  border-bottom: 1px solid #f0f0f0;
}
.brand-mark {
  font-size: 26px;
}
.brand-name {
  font-weight: 700;
  font-size: 16px;
}
.brand-sub {
  font-size: 11px;
  color: #909399;
}
.menu {
  flex: 1;
  border-right: none;
}
.aside-foot {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none;
}
.main {
  padding: 16px 20px;
  overflow: auto;
}
</style>
