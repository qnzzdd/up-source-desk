// Visual acceptance uses synthetic UP names only; never screenshots real account data.
const assert = require('node:assert/strict')
const { chromium } = require(process.env.UPDESK_PLAYWRIGHT || 'playwright')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
    const sources = Array.from({ length: 45 }, (_, i) => ({ uid: String(i + 1), name: `Synthetic UP ${String(i + 1).padStart(2, '0')}`, bio: '', group_ids: [] }))
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/live/**', route => {
      const action = new URL(route.request().url()).pathname.slice('/api/live/'.length)
      let data
      if (action === 'session') data = { account: null }
      else if (action === 'local-accounts') data = { items: [{ uid: 'synthetic', name: 'Synthetic owner' }] }
      else if (action === 'local/synthetic') data = { items: sources, groups: [], cached_at: '2026-10-29T00:00:00Z', historical: true }
      else if (action === 'local/synthetic/tool-groups') data = { items: [], sources }
      else throw new Error(`Unexpected request: ${action}`)
      return route.fulfill({ json: data })
    })
    await page.goto(process.env.UPDESK_URL || 'http://127.0.0.1:8768/')
    const list = page.locator('#live-source-list')
    await list.getByText('Synthetic UP 01').waitFor()
    assert.equal(await list.locator('li').count(), 20)
    assert.equal(await list.getByText('Synthetic UP 21').count(), 0)
    await page.screenshot({ path: 'artifacts/up-page-1.png', fullPage: true })
    await page.locator('.up-picker').screenshot({ path: 'artifacts/up-list-page-1.png' })
    await page.getByRole('button', { name: '下一页 UP', exact: true }).click()
    await list.getByText('Synthetic UP 21').waitFor()
    assert.equal(await list.locator('li').count(), 20)
    assert.equal(await list.getByText('Synthetic UP 01').count(), 0)
    await page.screenshot({ path: 'artifacts/up-page-2.png', fullPage: true })
    await page.locator('.up-picker').screenshot({ path: 'artifacts/up-list-page-2.png' })
    await page.getByRole('button', { name: '下一页 UP', exact: true }).click()
    await list.getByText('Synthetic UP 45').waitFor()
    assert.equal(await list.locator('li').count(), 5)
    assert(await page.getByRole('button', { name: '下一页 UP', exact: true }).isDisabled())
    await page.screenshot({ path: 'artifacts/up-page-3.png', fullPage: true })
    await page.locator('.up-picker').screenshot({ path: 'artifacts/up-list-page-3.png' })
    await page.setViewportSize({ width: 390, height: 844 })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    await page.screenshot({ path: 'artifacts/up-page-mobile.png', fullPage: true })
    await page.locator('.up-picker').screenshot({ path: 'artifacts/up-list-mobile.png' })
    const management = page.locator('.local-groups')
    await management.locator('.source-list li').first().waitFor()
    assert.equal(await management.locator('.source-list li').count(), 20)
    await management.getByRole('checkbox', { name: 'Synthetic UP 01 · 1' }).check()
    await management.getByRole('button', { name: '下一页', exact: true }).click()
    assert.equal(await management.locator('.source-list li').count(), 20)
    await management.getByRole('checkbox', { name: 'Synthetic UP 21 · 21' }).waitFor()
    await page.screenshot({ path: 'artifacts/group-members-page-2.png', fullPage: true })
    await management.locator('.local-members').screenshot({ path: 'artifacts/group-list-page-2.png' })
    await management.getByRole('button', { name: '下一页', exact: true }).click()
    assert.equal(await management.locator('.source-list li').count(), 5)
    assert(await management.getByRole('button', { name: '下一页', exact: true }).isDisabled())
    await management.getByRole('button', { name: '上一页', exact: true }).click()
    await management.getByRole('button', { name: '上一页', exact: true }).click()
    assert(await management.getByRole('checkbox', { name: 'Synthetic UP 01 · 1' }).isChecked())
    assert.deepEqual(errors, [])
    console.log('PASS: 45 synthetic UPs paginate 20/20/5, page switching and desktop/mobile screenshots')
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
