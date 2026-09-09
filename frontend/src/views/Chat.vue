<template>
  <div class="chat-page">
    <div class="chat-head">
      <div>
        <h2 class="page-title">光伏政策智能问答</h2>
        <div class="page-sub">混合检索 + 两阶段精排 + 引用溯源：答案强制绑定原文出处，禁止编造条款</div>
      </div>
      <div class="suggest-box">
        <el-tag v-for="s in suggests" :key="s" class="suggest" effect="plain" @click="ask(s)">{{ s }}</el-tag>
      </div>
    </div>

    <div class="chat-body" ref="bodyRef">
      <el-empty v-if="!messages.length" description="从上方示例问题开始，或输入你的问题" />
      <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
        <div class="bubble">
          <div class="who">{{ m.role === 'user' ? '我' : '光溯' }}</div>
          <div class="text" :class="{ streaming: m.streaming }">{{ m.text || (m.streaming ? '思考中…' : '') }}</div>

          <template v-if="m.role === 'assistant'">
            <div v-if="m.empty" class="empty-hint">未检索到可靠依据</div>
            <div v-if="m.citations && m.citations.length" class="cites">
              <div class="cite-title">📎 引用来源（{{ m.citations.length }}）</div>
              <el-collapse>
                <el-collapse-item v-for="(c, ci) in m.citations" :key="ci" :name="ci + 1">
                  <template #title>
                    <span class="cite-code">[{{ c.index }}] {{ c.doc_code || c.title }}</span>
                    <span class="cite-sec">{{ c.section_path }}</span>
                  </template>
                  <div class="cite-text">{{ c.text }}</div>
                  <div class="cite-score">精排得分 {{ c.score }}</div>
                </el-collapse-item>
              </el-collapse>
            </div>
            <div v-if="!m.streaming && m.latency" class="meta-line">
              生成 {{ m.latency }}ms{{ m.grounded ? ' · 已引用原文' : ' · 无引用（谨慎）' }}
            </div>
          </template>
        </div>
      </div>
    </div>

    <div class="chat-input">
      <el-input
        v-model="q"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="例如：分布式光伏并网前需要完成什么手续？支持 / 检索调试查看召回过程"
        :disabled="busy"
        @keydown.enter.exact.prevent="send"
      />
      <div class="input-bar">
        <el-button type="primary" :loading="busy" @click="send">发送</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, reactive, ref } from 'vue'
import { streamChat } from '../api/sse'

const suggests = [
  '分布式光伏并网前需要完成什么手续？',
  '光伏发电站并网对电能质量有哪些要求？',
  '户用光伏并网验收重点关注什么？',
  '并网逆变器为什么要具备防孤岛保护？',
  '新备案的集中式光伏还有固定补贴电价吗？',
]
const messages = reactive([])
const q = ref('')
const busy = ref(false)
const bodyRef = ref(null)

async function scrollBottom() {
  await nextTick()
  if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
}

async function ask(text) {
  q.value = text
  await send()
}

async function send() {
  const question = q.value.trim()
  if (!question || busy.value) return
  q.value = ''
  messages.push({ role: 'user', text: question })
  const assistant = reactive({
    role: 'assistant',
    text: '',
    citations: [],
    grounded: false,
    latency: 0,
    empty: false,
    streaming: true,
  })
  messages.push(assistant)
  busy.value = true
  await scrollBottom()

  await streamChat(
    question,
    (event, payload) => {
      if (event === 'meta') {
        assistant.citations = payload.citations || []
      } else if (event === 'delta') {
        assistant.text += payload.text || ''
        scrollBottom()
      } else if (event === 'done') {
        assistant.text = payload.text || assistant.text
        assistant.grounded = payload.grounded
        assistant.latency = payload.latency_ms
        assistant.empty = !!payload.empty
        assistant.streaming = false
        busy.value = false
        scrollBottom()
      } else if (event === 'error') {
        assistant.text = '服务异常：' + (payload.message || '未知错误')
        assistant.streaming = false
        busy.value = false
      }
    },
    (err) => {
      assistant.text = '连接失败：' + (err && err.message)
      assistant.streaming = false
      busy.value = false
    },
  )
}
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 120px);
}
.page-title {
  margin: 0;
  font-size: 20px;
}
.page-sub {
  color: #909399;
  font-size: 13px;
  margin-top: 4px;
}
.suggest-box {
  margin-top: 10px;
}
.suggest {
  margin: 2px 6px 2px 0;
  cursor: pointer;
}
.chat-body {
  flex: 1;
  overflow: auto;
  padding: 12px 4px;
}
.msg-row {
  display: flex;
  margin: 10px 0;
}
.msg-row.user {
  justify-content: flex-end;
}
.bubble {
  max-width: 76%;
  background: #fff;
  border-radius: 10px;
  padding: 12px 14px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.msg-row.user .bubble {
  background: #ecf5ff;
}
.who {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.7;
}
.streaming {
  opacity: 0.85;
}
.empty-hint {
  color: #e6a23c;
  font-size: 12px;
}
.cites {
  margin-top: 10px;
  border-top: 1px dashed #ebeef5;
  padding-top: 8px;
}
.cite-title {
  font-size: 12px;
  color: #606266;
  margin-bottom: 4px;
}
.cite-code {
  font-size: 13px;
}
.cite-sec {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
}
.cite-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.cite-score {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 4px;
}
.meta-line {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 6px;
}
.chat-input {
  margin-top: 8px;
}
.input-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
