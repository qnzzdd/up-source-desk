import { writeFile } from 'node:fs/promises'

const endpoint = 'http://127.0.0.1:9223'
const pages = await fetch(`${endpoint}/json/list`).then(response => response.json())
const page = pages.find(item => item.type === 'page')
if (!page) throw new Error('No debuggable page')
const socket = new WebSocket(page.webSocketDebuggerUrl)
const pending = new Map()
let nextId = 0
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data)
  if (!message.id || !pending.has(message.id)) return
  const { resolve, reject } = pending.get(message.id)
  pending.delete(message.id)
  message.error ? reject(new Error(message.error.message)) : resolve(message.result)
})
function call(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId
    pending.set(id, { resolve, reject })
    socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text)
  return result.result.value
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
await sleep(500)
await evaluate("document.querySelector('.source-row').click()")
await sleep(500)
const selected = await evaluate("document.querySelector('.detail-column h2').textContent")
const firstVideo = await evaluate("document.querySelector('.content-item h3').textContent")
await evaluate("document.querySelectorAll('.tab-bar button')[1].click()")
await sleep(500)
const firstDynamic = await evaluate("document.querySelector('.content-item p').textContent")
await evaluate("document.querySelector('.demo-ribbon button').click()")
await sleep(500)
const live = await evaluate("document.querySelector('.live-result').textContent")
await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
await sleep(300)
const shot = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
await writeFile(new URL('./demo-mobile.png', import.meta.url), Buffer.from(shot.data, 'base64'))
console.log(JSON.stringify({ selected, firstVideo, firstDynamic, live, mobileScreenshot: 'demo-mobile.png' }, null, 2))
socket.close()
