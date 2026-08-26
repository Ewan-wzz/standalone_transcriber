const SERVICE_URL = 'http://127.0.0.1:8765'
const JOB_KEY = 'xhsOfflineTranscriptionJob'
const elements = {
  service: document.getElementById('service-status'),
  start: document.getElementById('start'),
  progress: document.getElementById('progress'),
  progressTitle: document.getElementById('progress-title'),
  message: document.getElementById('message'),
  error: document.getElementById('error'),
  result: document.getElementById('result'),
  title: document.getElementById('title'),
  text: document.getElementById('text'),
  outputFile: document.getElementById('output-file'),
  copy: document.getElementById('copy')
}

function renderJob(job = {}) {
  const busy = ['extracting', 'downloading', 'transcribing'].includes(job.state)
  const state = job.state || 'idle'
  elements.start.disabled = busy || elements.service.dataset.ready !== 'true'
  elements.start.querySelector('span:last-child').textContent = busy ? '正在提取，请稍候' : '提取视频文案'
  elements.progress.className = `progress-card ${busy ? 'busy' : state}`
  elements.progressTitle.textContent = {
    extracting: '正在解析视频',
    downloading: '正在读取视频',
    transcribing: '正在本机转写',
    completed: '提取完成',
    failed: '未能完成',
    idle: '准备就绪'
  }[state] || '准备就绪'
  elements.message.textContent = job.message || '打开小红书视频笔记后开始提取。'
  elements.error.hidden = !job.error
  elements.error.textContent = job.error || ''
  const hasResult = Boolean(job.text)
  elements.result.hidden = !hasResult
  if (hasResult) {
    elements.title.textContent = job.title || '转写结果'
    elements.text.value = job.text
    elements.outputFile.textContent = job.outputFile ? `已保存：${job.outputFile}` : ''
  }
}

async function loadJob() {
  const stored = await chrome.storage.local.get(JOB_KEY)
  renderJob(stored[JOB_KEY] || {})
}

async function checkService() {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 2500)
  let serviceError = ''
  try {
    const response = await fetch(`${SERVICE_URL}/health`, { signal: controller.signal })
    const data = await response.json()
    if (!response.ok || !data.ready) {
      throw new Error(data.missing?.length ? `缺少：${data.missing.join('、')}` : '本地服务未就绪')
    }
    elements.service.textContent = '本机可用'
    elements.service.className = 'status ready'
    elements.service.dataset.ready = 'true'
  } catch (error) {
    serviceError = error?.message || '请先启动本地转写程序'
    elements.service.textContent = '服务未启动'
    elements.service.className = 'status offline'
    elements.service.dataset.ready = 'false'
  } finally {
    clearTimeout(timer)
    await loadJob()
    if (serviceError) {
      elements.progress.className = 'progress-card failed'
      elements.progressTitle.textContent = '桌面程序未就绪'
      elements.message.textContent = serviceError
      elements.start.disabled = true
    }
  }
}

elements.start.addEventListener('click', async () => {
  elements.error.hidden = true
  const response = await chrome.runtime.sendMessage({ type: 'START_TRANSCRIPTION' })
  if (!response?.ok) {
    elements.error.hidden = false
    elements.error.textContent = response?.error || '无法开始转写'
  }
  await loadJob()
})

elements.copy.addEventListener('click', async () => {
  await navigator.clipboard.writeText(elements.text.value || '')
  elements.copy.textContent = '已复制'
  setTimeout(() => { elements.copy.textContent = '复制' }, 1200)
})

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes[JOB_KEY]) renderJob(changes[JOB_KEY].newValue || {})
})

checkService()
