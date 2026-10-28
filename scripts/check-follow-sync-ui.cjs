// Synthetic sync progression; no real account or platform requests.
const assert = require('node:assert/strict')
const { chromium } = require(process.env.UPDESK_PLAYWRIGHT || 'playwright')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage()
    let polls = 0
    let metadataReads = 0
    const calls = []
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    const source = { uid: '2', name: 'Newly followed source', bio: '', group_ids: [] }
    await page.route('**/api/live/**', async route => {
      const action = new URL(route.request().url()).pathname.slice('/api/live/'.length)
      calls.push(action)
      let data
      if (action === 'session') data = { account: { uid: 'test', name: 'Synthetic' } }
      else if (action === 'local-accounts') data = { items: [{ uid: 'test', name: 'Synthetic' }] }
      else if (action === 'cache' || action === 'local/test') {
        metadataReads++
        data = { items: polls ? [source] : [], groups: [], cached_at: null, historical: true }
      } else if (action === 'sync-status') {
        polls++
        data = { state: polls === 1 ? 'running' : 'complete', page: 1, loaded: 1, total: 1, added: 1,
          last_success: polls > 1 ? '2026-10-29T00:00:00Z' : null, next_run: null, error: '', account_uid: 'test' }
      } else if (action === 'local/test/tool-groups') data = { items: [{ id: 'g', name: 'Managed group', source_uids: ['2'] }], sources: [source] }
      else throw new Error(`Unexpected remote collection or action: ${action}`)
      await route.fulfill({ json: data })
    })
    await page.goto(process.env.UPDESK_URL || 'http://127.0.0.1:8768/')
    await page.waitForTimeout(12000)
    assert(polls >= 2, 'Must poll status while connected')
    assert(metadataReads >= 2, 'Must refresh management data after progress')
    await page.locator('#live-source-list .up-row').filter({ hasText: 'Newly followed source' }).waitFor()
    assert(!calls.some(action => action.startsWith('sources/')), 'Metadata discovery must not collect content')
    assert(!calls.includes('sync-start'), 'Page refresh must not restart existing sync')
    assert.deepEqual(errors, [])
    console.log('PASS: background progress displayed, management data refreshes, no content collection or duplicate start')
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
