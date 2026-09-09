<template>
  <div>
    <h2 class="page-title">检索调试</h2>
    <div class="page-sub">查看查询改写 → 混合召回 → 两阶段精排的完整过程，便于定位召回问题</div>
    <div class="toolbar">
      <el-input v-model="q" placeholder="输入问题，观察重写与召回" style="max-width: 560px" clearable @keyup.enter="run" />
      <el-select v-model="topK" style="width: 120px; margin: 0 10px">
        <el-option v-for="n in [3, 5, 8, 10]" :key="n" :value="n" :label="`Top ${n}`" />
      </el-select>
      <el-button type="primary" :loading="loading" @click="run">检索</el-button>
    </div>

    <el-descriptions v-if="res" title="查询理解与改写" :column="2" border class="block">
      <el-descriptions-item label="原始提问">{{ res.rewritten.original }}</el-descriptions-item>
      <el-descriptions-item label="类型提示">{{ typeLabel(res.rewritten.doc_type_hint) }}</el-descriptions-item>
      <el-descriptions-item label="改写后检索串（向量+BM25）" :span="2">
        {{ res.rewritten.expanded }}
      </el-descriptions-item>
      <el-descriptions-item label="追加术语" :span="2">{{ (res.rewritten.appended_terms || []).join('、') || '—' }}</el-descriptions-item>
      <el-descriptions-item label="耗时">{{ res.latency_ms }}ms</el-descriptions-item>
      <el-descriptions-item label="已发布片段">{{ res.store_count }} 条</el-descriptions-item>
    </el-descriptions>

    <el-table v-if="res && res.hits.length" :data="res.hits" class="block" border>
      <el-table-column type="index" label="#" width="46" />
      <el-table-column prop="score" label="精排分" width="90" />
      <el-table-column prop="doc_code" label="文号/规范" width="210" show-overflow-tooltip />
      <el-table-column prop="section_path" label="章节" width="180" show-overflow-tooltip />
      <el-table-column label="片段">
        <template #default="{ row }">
          <div class="snippet">{{ row.snippet }}</div>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else-if="res && !res.hits.length" description="未检索到有效依据（可能知识库为空或相关文档已归档）" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import http from '../api/http'

const q = ref('分布式光伏并网前需要完成什么手续？')
const topK = ref(5)
const res = ref(null)
const loading = ref(false)

const TYPES = {
  building_standard: '建设规范',
  grid_connection: '并网政策',
  early_procedure: '前期手续',
  tariff_subsidy: '电价补贴',
  other: '其他',
}
function typeLabel(v) {
  return v ? TYPES[v] || v : '—'
}

async function run() {
  if (!q.value.trim()) return
  loading.value = true
  try {
    const { data } = await http.get('/search', { params: { q: q.value, top_k: topK.value } })
    res.value = data
  } finally {
    loading.value = false
  }
}
run()
</script>

<style scoped>
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
}
.page-sub {
  color: #909399;
  font-size: 13px;
  margin-bottom: 14px;
}
.toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 14px;
}
.block {
  margin-top: 10px;
}
.snippet {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
