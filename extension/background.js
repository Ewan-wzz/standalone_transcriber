const SERVICE_URL = 'http://127.0.0.1:8765'
const JOB_KEY = 'xhsOfflineTranscriptionJob'
let running = false

async function saveJob(patch) {
  const current = (await chrome.storage.local.get(JOB_KEY))[JOB_KEY] || {}
  const next = { ...current, ...patch, updatedAt: Date.now() }
  await chrome.storage.local.set({ [JOB_KEY]: next })
  return next
}

// 与 NoteAI 采集插件 CAPTURE_VIDEO 使用同一套解析逻辑。
async function extractCurrentVideo(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    func: () => {
      const out = { url: '', title: '', noteId: '', noteUrl: location.href }
      try {
        const match = location.pathname.match(/(?:explore|discovery\/item)\/([0-9a-z]+)/i)
        out.noteId = match ? match[1] : ''
      } catch (_) {}
      try {
        const state = window.__INITIAL_STATE__
        const seen = new WeakSet()
        let best = ''
        let key = ''
        let titleFound = ''
        const walk = (value, depth) => {
          if (!value || typeof value !== 'object' || depth > 10 || seen.has(value)) return
          seen.add(value)
          for (const name in value) {
            let child
            try { child = value[name] } catch (_) { continue }
            if (name === 'originVideoKey' && typeof child === 'string' && child) key ||= child
            if (name === 'title' && typeof child === 'string' && child && !titleFound) titleFound = child
            if (name === 'masterUrl' && typeof child === 'string' && /\.mp4/i.test(child)) best ||= child
            if (child && typeof child === 'object') walk(child, depth + 1)
          }
        }
        walk(state, 0)
        out.title = titleFound || (document.querySelector('#detail-title')?.textContent || '').trim()
        if (key) out.url = `https://sns-video-bd.xhscdn.com/${key}`
        else if (best) out.url = best
      } catch (error) {
        out.error = error?.message || String(error)
      }
      if (!out.url) {
        try {
          const loadedUrl = performance.getEntriesByType('resource')
            .map(entry => entry.name)
            .find(url => /\.mp4/i.test(url))
          if (loadedUrl) out.url = loadedUrl
        } catch (_) {}
      }
      return out
    }
  })
  return results?.[0]?.result || null
}

// 与 NoteAI 采集插件相同：在小红书页面上下文中下载，自动携带页面会话。
async function downloadCurrentVideo(tabId, videoUrl) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    world: 'MAIN',
    args: [videoUrl],
    func: async mp4Url => {
      try {
        const response = await fetch(mp4Url)
        if (!response.ok) return { error: `HTTP ${response.status}` }
        const blob = await response.blob()
        const dataUrl = await new Promise(resolve => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result || '')
          reader.onerror = () => resolve('')
          reader.readAsDataURL(blob)
        })
        return { dataUrl, size: blob.size }
      } catch (error) {
        return { error: error?.message || String(error) }
      }
    }
  })
  return results?.[0]?.result || null
}

async function transcribeCurrentTab() {
  if (running) return
  running = true
  try {
    await saveJob({ state: 'extracting', message: '正在解析当前视频…', error: '' })
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab || !/xiaohongshu\.com\/(explore|discovery\/item)\//.test(tab.url || '')) {
      throw new Error('请先打开一篇小红书视频笔记')
    }

    const info = await extractCurrentVideo(tab.id)
    if (!info?.url) throw new Error('未能解析到视频地址，请确认当前笔记是视频')

    await saveJob({
      state: 'downloading',
      message: '正在通过当前小红书页面读取视频…',
      title: info.title || ''
    })
    const download = await downloadCurrentVideo(tab.id, info.url)
    if (download?.error || !download?.dataUrl) {
      throw new Error(`视频读取失败：${download?.error || '内容为空'}`)
    }

    const videoBlob = await (await fetch(download.dataUrl)).blob()
    const metadata = encodeURIComponent(JSON.stringify({
      title: info.title || '',
      note_id: info.noteId || '',
      note_url: info.noteUrl || tab.url
    }))
    await saveJob({
      state: 'transcribing',
      message: '视频已读取，正在本机离线转写…',
      title: info.title || ''
    })
    const response = await fetch(`${SERVICE_URL}/api/transcribe-upload`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/octet-stream',
        'X-Transcriber-Client': 'xhs-offline-extension',
        'X-Transcriber-Metadata': metadata
      },
      body: videoBlob
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.error || `本地服务返回 HTTP ${response.status}`)
    await saveJob({
      state: 'completed',
      message: `转写完成，用时 ${payload.elapsed_seconds || 0} 秒`,
      text: payload.text || '',
      outputFile: payload.output_file || '',
      title: payload.title || info.title || '',
      error: ''
    })
  } catch (error) {
    await saveJob({
      state: 'failed',
      message: '转写失败',
      error: error?.message || String(error)
    })
  } finally {
    running = false
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== 'START_TRANSCRIPTION') return false
  if (running) {
    sendResponse({ ok: false, error: '已有视频正在转写' })
    return false
  }
  transcribeCurrentTab()
  sendResponse({ ok: true })
  return false
})
