<template>
  <div>
    <div class="head-row">
      <h2 class="page-title">用户与权限</h2>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
    </div>

    <el-table :data="rows" border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" width="160" />
      <el-table-column prop="display_name" label="显示名" width="160" />
      <el-table-column label="角色" width="140">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'editor' ? 'warning' : 'info'">
            {{ roleLabel(row.role) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-select :model-value="row.role" size="small" style="width: 110px" @change="(v) => changeRole(row, v)">
            <el-option label="管理员" value="admin" />
            <el-option label="编辑" value="editor" />
            <el-option label="访客" value="viewer" />
          </el-select>
          <el-button size="small" :type="row.is_active ? 'danger' : 'success'" plain @click="toggleActive(row)">
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新建用户" width="440px">
      <el-form label-width="90px">
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="显示名"><el-input v-model="form.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role">
            <el-option label="编辑" value="editor" />
            <el-option label="访客" value="viewer" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const rows = ref([])
const dialog = ref(false)
const saving = ref(false)
const form = reactive({ username: '', password: '', display_name: '', role: 'editor' })

function roleLabel(r) {
  return { admin: '管理员', editor: '编辑', viewer: '访客' }[r] || r
}
async function load() {
  const { data } = await http.get('/users')
  rows.value = data.items
}
function openCreate() {
  Object.assign(form, { username: '', password: '', display_name: '', role: 'editor' })
  dialog.value = true
}
async function create() {
  saving.value = true
  try {
    await http.post('/users', form)
    ElMessage.success('创建成功')
    dialog.value = false
    load()
  } finally {
    saving.value = false
  }
}
async function changeRole(row, role) {
  await http.patch(`/users/${row.id}`, { role })
  ElMessage.success('已更新角色')
  load()
}
async function toggleActive(row) {
  await http.patch(`/users/${row.id}`, { is_active: !row.is_active })
  load()
}

load()
</script>

<style scoped>
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.page-title {
  font-size: 20px;
}
</style>
