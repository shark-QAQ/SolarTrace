<template>
  <div>
    <h2 class="page-title">RAG 评测闭环</h2>
    <div class="page-sub">对标注问答集回归命中率(召回@K)、上下文召回率、引用忠实度，驱动分块/重排迭代</div>

    <div class="toolbar">
      <el-select v-model="setId" placeholder="选择评测集" style="width: 240px">
        <el-option v-for="s in sets" :key="s.id" :value="s.id" :label="`${s.name}（${s.case_count} 题）`" />
      </el-select>
      <el-select v-model="topK" style="width: 110px; margin-left: 8px">
        <el-option v-for="n in [3, 5, 8, 10]" :key="n" :value="n" :label="`Top ${n}`" />
      </el-select>
      <el-checkbox v-model="generate" style="margin-left: 8px">生成以评测引用忠实度（较慢）</el-checkbox>
      <el-button type="primary" style="margin-left: 8px" :loading="running" @click="runEval">开始评测</el-button>
    </div>

    <el-table :data="runs" border class="block" v-loading="loading">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div v-if="row.details && row.details.length" class="detail-box">
            <div v-for="(d, i) in row.details" :key="i" class="detail-row">
              <span class="dq">{{ d.hit ? '✅' : '❌' }} {{ d.question }}</span>
              <span class="dm">命中文号：{{ (d.top_doc_codes || []).join('、') || '—' }}</span>
              <span v-if="d.keywords_found && d.keywords_found.length" class="dm">关键词命中：{{ d.keywords_found.join('、') }}</span>
              <span v-if="d.faithfulness !== undefined && d.faithfulness !== null" class="dm">忠实度 {{ d.faithfulness }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无明细" :image-size="40" />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column prop="name" label="评测集" width="160" />
      <el-table-column label="模型" width="150">
        <template #default="{ row }">{{ row.params?.model }}</template>
      </el-table-column>
      <el-table-column prop="case_count" label="题数" width="70" />
      <el-table-column label="命中率@K">
        <template #default="{ row }">
          <b>{{ (row.hit_rate * 100).toFixed(1) }}%</b>
          <span class="muted">Top1 {{ (row.hit_rate_top1 * 100).toFixed(1) }}%</span>
        </template>
      </el-table-column>
      <el-table-column label="上下文召回">
        <template #default="{ row }">{{ (row.context_recall * 100).toFixed(1) }}%</template>
      </el-table-column>
      <el-table-column label="引用忠实度">
        <template #default="{ row }">
          <span v-if="row.faithfulness === null || row.faithfulness === undefined">未评测</span>
          <span v-else>{{ (row.faithfulness * 100).toFixed(1) }}%</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '../api/http'

const sets = ref([])
const runs = ref([])
const setId = ref(null)
const topK = ref(5)
const generate = ref(false)
const running = ref(false)
const loading = ref(false)

async function loadSets() {
  const { data } = await http.get('/eval/sets')
  sets.value = data.items
  if (!setId.value && data.items.length) setId.value = data.items[0].id
}
async function loadRuns() {
  loading.value = true
  try {
    const { data } = await http.get('/eval/runs')
    runs.value = data.items
  } finally {
    loading.value = false
  }
}
async function runEval() {
  if (!setId.value) {
    ElMessage.warning('请先选择评测集（可运行演示语料种子脚本创建）')
    return
  }
  running.value = true
  try {
    const { data } = await http.post('/eval/runs', { eval_set_id: setId.value, top_k: topK.value, generate: generate.value })
    ElMessage.success(`评测完成：命中率 ${(data.hit_rate * 100).toFixed(1)}%`)
    await loadRuns()
  } finally {
    running.value = false
  }
}

loadSets()
loadRuns()
</script>

<style scoped>
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
.block {
  margin-top: 6px;
}
.muted {
  color: #c0c4cc;
  font-size: 12px;
  margin-left: 6px;
}
.detail-box {
  padding: 6px 12px;
}
.detail-row {
  border-bottom: 1px dashed #f0f0f0;
  padding: 6px 0;
}
.dq {
  font-weight: 600;
}
.dm {
  color: #909399;
  font-size: 12px;
  margin-left: 14px;
}
</style>
