const JOB_KEY = 'xhsVideoDownloadJob'
const elements = {
  start: document.getElementById('start'),
  progress: document.getElementById('progress'),
  progressTitle: document.getElementById('progress-title'),
  message: document.getElementById('message'),
  error: document.getElementById('error'),
  result: document.getElementById('result'),
  title: document.getElementById('title'),
  outputFile: document.getElementById('output-file'),
  showDownload: document.getElementById('show-download')
}

function renderJob(job = {}) {
  const busy = ['extracting', 'reading', 'saving'].includes(job.state)
  const state = job.state || 'idle'
  elements.start.disabled = busy
  elements.start.querySelector('span:last-child').textContent = busy ? '正在下载，请稍候' : '下载当前视频'
  elements.progress.className = `progress-card ${busy ? 'busy' : state}`
  elements.progressTitle.textContent = {
    extracting: '正在解析视频',
    reading: '正在读取视频',
    saving: '正在保存文件',
    completed: '下载完成',
    failed: '未能完成',
    idle: '准备就绪'
  }[state] || '准备就绪'
  elements.message.textContent = job.message || '打开小红书视频笔记后开始下载。'
  elements.error.hidden = !job.error
  elements.error.textContent = job.error || ''
  elements.result.hidden = state !== 'completed'
  if (state === 'completed') {
    elements.title.textContent = job.title || '当前视频'
    const size = Number(job.size || 0)
    const sizeText = size ? ` · ${(size / 1024 / 1024).toFixed(1)} MB` : ''
    elements.outputFile.textContent = `下载/小红书视频转写${sizeText}`
  }
}

async function loadJob() {
  const stored = await chrome.storage.local.get(JOB_KEY)
  renderJob(stored[JOB_KEY] || {})
}

elements.start.addEventListener('click', async () => {
  elements.error.hidden = true
  const response = await chrome.runtime.sendMessage({ type: 'START_DOWNLOAD' })
  if (!response?.ok) {
    elements.error.hidden = false
    elements.error.textContent = response?.error || '无法开始下载'
  }
  await loadJob()
})

elements.showDownload.addEventListener('click', async () => {
  await chrome.runtime.sendMessage({ type: 'SHOW_DOWNLOAD' })
})

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes[JOB_KEY]) renderJob(changes[JOB_KEY].newValue || {})
})

loadJob()
