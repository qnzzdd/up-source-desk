import { writeFile } from 'node:fs/promises'

const endpoint = 'http://127.0.0.1:9224'
const pages = await fetch(`${endpoint}/json/list`).then(response => response.json())
const page = pages.find(item => item.type === 'page' && ['http://127.0.0.1:8767/', 'http://127.0.0.1:8768/'].includes(item.url))
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
await call('Page.navigate', {url:'http://127.0.0.1:8768/'})
await sleep(1000)
await sleep(500)
await evaluate("document.querySelector('.source-row').click()")
await sleep(500)
const selected = await evaluate("document.querySelector('.detail-panel h2').textContent")
const firstVideo = await evaluate("document.querySelector('.content-item h3').textContent")
await evaluate("document.querySelectorAll('.tab-bar button')[1].click()")
await sleep(500)
const firstDynamic = await evaluate("document.querySelector('.content-item p').textContent")
await evaluate("document.querySelector('.connection-card button').click()")
await sleep(500)
const live = await evaluate("document.querySelector('.live-feedback').textContent")
if (!selected || !firstVideo || !firstDynamic || !live.includes('LIVE_NOT_CONNECTED')) throw new Error('Core interaction failed')
await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
await sleep(300)
const desktop = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
await writeFile(new URL('./console-desktop.png', import.meta.url), Buffer.from(desktop.data, 'base64'))
await evaluate("document.querySelectorAll('.primary-nav button')[2].click()")
if (!await evaluate("Boolean(document.querySelector('.groups-panel'))")) throw new Error('Group navigation failed')
await evaluate("document.querySelectorAll('.primary-nav button')[1].click()")
await evaluate("document.querySelector('.load-more').click()")
await sleep(400)
if (await evaluate("document.querySelectorAll('.source-row').length") !== 8) throw new Error('Pagination failed')
await evaluate("var input=document.querySelector('#source-search'); input.value='no-match-xyz'; input.dispatchEvent(new Event('input',{bubbles:true}))")
await sleep(600)
if (await evaluate("document.querySelectorAll('.source-row').length") !== 0) throw new Error('Search failed')
await evaluate("var input=document.querySelector('#source-search'); input.value=''; input.dispatchEvent(new Event('input',{bubbles:true}))")
await sleep(600)
await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
await sleep(300)
if (await evaluate('document.documentElement.scrollWidth > window.innerWidth')) throw new Error('Mobile horizontal overflow')
await evaluate("document.querySelector('.menu-toggle').click()")
await evaluate("document.querySelectorAll('.group-nav button')[1].click()")
await sleep(400)
if (await evaluate("document.querySelector('.sidebar').classList.contains('mobile-open')")) throw new Error('Mobile menu did not close')
const shot = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
await writeFile(new URL('./console-mobile.png', import.meta.url), Buffer.from(shot.data, 'base64'))
console.log(JSON.stringify({ selected, firstVideo, firstDynamic, live, mobileScreenshot: 'console-mobile.png', navigation: 'passed', pagination: 'passed', search: 'passed', mobileOverflow: false }, null, 2))
socket.close()
