import { authHeaders } from './http'

/**
 * 调用后端 SSE 流式问答接口。
 * onEvent(event, data) 收到事件帧；onError(err) 异常。
 * 事件：meta / delta* / done | error
 */
export async function streamChat(question, onEvent, onError) {
  try {
    const resp = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ question }),
    })
    if (!resp.ok || !resp.body) {
      onError(new Error(`HTTP ${resp.status}`))
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    const dispatch = (raw) => {
      // SSE 帧：event: xxx\ndata: {...}
      let event = 'message'
      let data = ''
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (event === 'message' && !data) return
      let payload = {}
      try {
        payload = data ? JSON.parse(data) : {}
      } catch (_e) {
        payload = { text: data }
      }
      onEvent(event, payload)
    }

    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        if (frame.trim()) dispatch(frame.trim())
      }
    }
  } catch (err) {
    onError(err)
  }
}
