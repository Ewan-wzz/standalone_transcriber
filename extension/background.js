const JOB_KEY = 'xhsVideoDownloadJob'
const DOWNLOAD_FOLDER = '小红书视频转写'
let running = false

async function saveJob(patch) {
  const current = (await chrome.storage.local.get(JOB_KEY))[JOB_KEY] || {}
  const next = { ...current, ...patch, updatedAt: Date.now() }
  await chrome.storage.local.set({ [JOB_KEY]: next })
  return next
}

// 复用 NoteAI 采集插件的页面解析方式，不对视频 URL 做额外限制。
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

// 在小红书页面上下文中读取视频，自动携带当前页面会话。
async function readCurrentVideo(tabId, videoUrl) {
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

function safeFileName(value) {
  return String(value || '小红书视频')
    .replace(/[\\/:*?"<>|\n\r]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 70) || '小红书视频'
}

function localTimestamp(date = new Date()) {
  const pad = value => String(value).padStart(2, '0')
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
}

async function waitForDownload(downloadId) {
  const existing = await chrome.downloads.search({ id: downloadId })
  if (existing[0]?.state === 'complete') return
  if (existing[0]?.state === 'interrupted') throw new Error('浏览器下载被中断')
  return new Promise((resolve, reject) => {
    const listener = delta => {
      if (delta.id !== downloadId || !delta.state) return
      if (delta.state.current === 'complete') {
        chrome.downloads.onChanged.removeListener(listener)
        resolve()
      } else if (delta.state.current === 'interrupted') {
        chrome.downloads.onChanged.removeListener(listener)
        reject(new Error('浏览器下载被中断'))
      }
    }
    chrome.downloads.onChanged.addListener(listener)
  })
}

async function downloadCurrentTab() {
  if (running) return
  running = true
  try {
    await saveJob({ state: 'extracting', message: '正在解析当前视频…', error: '' })
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab || !/xiaohongshu\.com\/(explore|discovery\/item)\//.test(tab.url || '')) {
      throw new Error('请先打开一篇小红书视频笔记')
    }

    const info = await extractCurrentVideo(tab.id)
    if (!info?.url) throw new Error('未能解析到视频，请确认当前笔记是视频')

    await saveJob({ state: 'reading', message: '正在从当前页面读取视频…', title: info.title || '' })
    const video = await readCurrentVideo(tab.id, info.url)
    if (video?.error || !video?.dataUrl) {
      throw new Error(`视频读取失败：${video?.error || '内容为空'}`)
    }

    const stamp = localTimestamp()
    const filename = `${DOWNLOAD_FOLDER}/${safeFileName(info.title || '未命名视频')}_${stamp}.mp4`
    await saveJob({
      state: 'saving',
      message: `正在保存到“下载/${DOWNLOAD_FOLDER}”…`,
      title: info.title || '',
      filename,
      size: video.size || 0
    })
    const downloadId = await chrome.downloads.download({ url: video.dataUrl, filename, saveAs: false })
    await saveJob({ downloadId })
    await waitForDownload(downloadId)
    await saveJob({
      state: 'completed',
      message: `已保存到“下载/${DOWNLOAD_FOLDER}”，请在桌面程序中手动选择转写。`,
      error: ''
    })
  } catch (error) {
    await saveJob({ state: 'failed', message: '下载失败', error: error?.message || String(error) })
  } finally {
    running = false
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'START_DOWNLOAD') {
    if (running) {
      sendResponse({ ok: false, error: '已有视频正在下载' })
      return false
    }
    downloadCurrentTab()
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'SHOW_DOWNLOAD') {
    chrome.storage.local.get(JOB_KEY).then(stored => {
      const downloadId = stored[JOB_KEY]?.downloadId
      if (Number.isInteger(downloadId)) chrome.downloads.show(downloadId)
      else chrome.downloads.showDefaultFolder()
    })
    sendResponse({ ok: true })
    return false
  }
  return false
})
