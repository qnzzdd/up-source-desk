// Uses synthetic API responses only; never reads or logs real account data.
const assert = require('node:assert/strict')
const { chromium } = require(process.env.UPDESK_PLAYWRIGHT || 'playwright')

async function main() {
  const browser = await chromium.launch({ headless: true, channel: 'msedge' })
  try {
    const page = await browser.newPage()
    const calls = []
    let connected = false
    await page.route('**/api/live/**', route => {
      const action = new URL(route.request().url()).pathname.slice('/api/live/'.length)
      calls.push(action)
      let data
      if (action === 'session') data = { account: connected ? { uid: 'synthetic', name: 'Saved account' } : null }
      else if (action === 'local-accounts') data = { items: [{ uid: 'synthetic', name: 'Saved account' }] }
      else if (action === 'cache' || action === 'local/synthetic') data = {
        items: [{ uid: '2', name: 'Saved source', bio: '', group_ids: [5] }],
        groups: [{ id: '5', name: 'Saved group', member_count: 1 }],
        cached_at: '2026-10-29T00:00:00Z', historical: true,
      }
      else if (action === 'local/synthetic/sources/2/dynamics') data = {
        items: [{ id: '123', text: 'Saved dynamic text' }], historical: true,
        cached_at: '2026-10-29T00:00:00Z',
      }
      else throw new Error(`Unexpected live request: ${action}`)
      return route.fulfill({ json: data })
    })
    await page.goto(process.env.UPDESK_URL || 'http://127.0.0.1:8768/')
    await page.locator('#live-source option[value="2"]').waitFor({ state: 'attached' })
    assert.equal(await page.locator('#local-account').inputValue(), 'synthetic')
    assert.equal(await page.getByRole('button', { name: '读取并保存动态首屏', exact: true }).isDisabled(), true)
    await page.locator('#live-source').selectOption('2')
    await page.getByRole('button', { name: '已保存动态', exact: true }).click()
    await page.getByText('Saved dynamic text', { exact: true }).waitFor()
    await page.reload()
    await page.locator('#live-source option[value="2"]').waitFor({ state: 'attached' })
    connected = true
    await page.reload()
    await page.getByText('已恢复本机登录会话与保存记录（未请求 B站）', { exact: true }).waitFor()
    assert(calls.includes('cache'))
    assert(!calls.some(action => /followings|^sources\//.test(action)))
    console.log('PASS: offline startup, saved content, page reload and connected restoration; no live collection')
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
