<template>
  <div>
    <div class="head-row">
      <div>
        <h2 class="page-title">文档库 · 知识管理</h2>
        <div class="page-sub">上传即自动建索引；发布/归档保证“索引与文档库一致”；退稿即清理向量，杜绝引用失效政策</div>
      </div>
      <div v-if="canEdit">
        <el-button type="primary" @click="openUpload">上传文档</el-button>
      </div>
    </div>

    <div class="toolbar">
      <el-select v-model="filter.status" placeholder="状态" clearable style="width: 130px">
        <el-option label="已发布" value="published" />
        <el-option label="草稿" value="draft" />
        <el-option label="已归档" value="archived" />
      </el-select>
      <el-select v-model="filter.type" placeholder="类型" clearable style="width: 150px; margin-left: 8px">
        <el-option v-for="(l, k) in types" :key="k" :value="k" :label="l" />
      </el-select>
      <el-input v-model="filter.keyword" placeholder="标题/文号/发文机关" style="width: 260px; margin-left: 8px" clearable />
      <el-button style="margin-left: 8px" @click="load(1)">查询</el-button>
      <el-button type="warning" plain style="margin-left: 8px" @click="reconcile">对账索引</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" border>
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-table :data="row._versions || []" size="small">
            <el-table-column prop="version_no" label="版本" width="80" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row: v }">
                <el-tag size="small" :type="statusType(v.status)">{{ statusText(v.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source_file_name" label="源文件" width="200" show-overflow-tooltip />
            <el-table-column prop="chunk_count" label="片段数" width="90" />
            <el-table-column prop="notes" label="备注" />
            <el-table-column label="操作" width="180">
              <template #default="{ row: v }">
                <el-button v-if="v.status !== 'published' && canEdit" size="small" type="success" @click="publish(row, v)">发布建索引</el-button>
                <el-button v-else-if="canEdit" size="small" type="danger" plain @click="archive(row, v)">归档退稿</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="文档标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="doc_code" label="文号" width="200" show-overflow-tooltip />
      <el-table-column prop="issuing_body" label="发文机关" width="150" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ types[row.doc_type] || row.doc_type }}</template>
      </el-table-column>
      <el-table-column prop="issue_year" label="年份" width="80" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination background layout="total, prev, pager, next" :total="total" :page-size="pageSize" :current-page="page" @current-change="load" />
    </div>

    <el-dialog v-model="dialog" title="上传政策 / 规范文档" width="640px">
      <el-form label-width="100px">
        <el-form-item label="文档文件" required>
          <el-upload drag :auto-upload="false" :limit="1" :on-change="onFile" :file-list="fileList">
            <div>点击或拖拽上传（PDF / DOCX / Markdown / TXT）</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="标题"><el-input v-model="form.title" placeholder="留空取文件名" /></el-form-item>
        <el-form-item label="文号"><el-input v-model="form.doc_code" placeholder="如 国能发新能规〔2025〕7号" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.doc_type">
            <el-option v-for="(l, k) in types" :key="k" :value="k" :label="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="发文机关"><el-input v-model="form.issuing_body" /></el-form-item>
        <el-form-item label="年份"><el-input-number v-model="form.issue_year" :min="1990" :max="2100" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.notes" /></el-form-item>
        <el-form-item label="发布">
          <el-switch v-model="form.publish" active-text="上传后立即发布建索引" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="doUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'
import { authHeaders } from '../api/http'

const types = { building_standard: '建设规范', grid_connection: '并网政策', early_procedure: '前期手续', tariff_subsidy: '电价补贴', other: '其他' }
const user = JSON.parse(localStorage.getItem('solartrace_user') || '{}')
const canEdit = ['editor', 'admin'].includes(user.role)

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const filter = reactive({ status: '', type: '', keyword: '' })

const dialog = ref(false)
const uploading = ref(false)
const fileList = ref([])
let pickedFile = null
const form = reactive({ title: '', doc_code: '', doc_type: 'grid_connection', issuing_body: '', issue_year: 2025, notes: '', publish: true })

function statusText(s) {
  return { published: '已发布', draft: '草稿', archived: '已归档' }[s] || s
}
function statusType(s) {
  return { published: 'success', draft: 'info', archived: 'danger' }[s] || 'info'
}

async function load(p = 1) {
  page.value = p
  loading.value = true
  try {
    const { data } = await http.get('/documents', {
      params: { page: p, page_size: pageSize, ...(filter.status || {}), ...(filter.type ? { doc_type: filter.type } : {}), ...(filter.keyword ? { keyword: filter.keyword } : {}) },
    })
    rows.value = data.items
    total.value = data.total
    // 拉取每个文档版本（展开行用）
    rows.value = await Promise.all(
      rows.value.map(async (d) => {
        const v = await http.get(`/documents/${d.id}/versions`)
        return { ...d, _versions: v.data.versions }
      }),
    )
  } finally {
    loading.value = false
  }
}

function openUpload() {
  fileList.value = []
  pickedFile = null
  Object.assign(form, { title: '', doc_code: '', doc_type: 'grid_connection', issuing_body: '', issue_year: 2025, notes: '', publish: true })
  dialog.value = true
}
function onFile(f) {
  pickedFile = f.raw
}

async function doUpload() {
  if (!pickedFile) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  const fd = new FormData()
  fd.append('file', pickedFile)
  fd.append('title', form.title)
  fd.append('doc_code', form.doc_code)
  fd.append('doc_type', form.doc_type)
  fd.append('issuing_body', form.issuing_body)
  fd.append('issue_year', form.issue_year || '')
  fd.append('notes', form.notes)
  fd.append('publish', form.publish ? 'true' : 'false')
  try {
    const { data } = await http.post('/documents/upload', fd, { headers: authHeaders() })
    ElMessage.success(data.indexed ? '上传并发布建索引成功' : '已上传（草稿）')
    dialog.value = false
    load(page.value)
  } finally {
    uploading.value = false
  }
}

async function publish(doc, version) {
  await http.post(`/documents/${doc.id}/publish`, { version_id: version.id })
  ElMessage.success('发布成功，索引已重建')
  load(page.value)
}
async function archive(doc, version) {
  await http.post(`/documents/${doc.id}/archive`, { version_id: version.id })
  ElMessage.success('已归档并清理索引')
  load(page.value)
}
async function reconcile() {
  await http.post('/system/reconcile')
  ElMessage.success('索引对账完成')
  load(page.value)
}

load(1)
</script>

<style scoped>
.head-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
}
.page-sub {
  color: #909399;
  font-size: 13px;
}
.toolbar {
  margin: 12px 0;
  display: flex;
  align-items: center;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
