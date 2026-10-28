// Synthetic requests only. Never changes the running server's real database.
const assert = require('node:assert/strict')
const { chromium } = require(process.env.UPDESK_PLAYWRIGHT || 'playwright')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage()
    let groups = []
    const sources = [{ uid: '2', name: 'Source A' }, { uid: '3', name: 'Source B' }]
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/live/**', async route => {
      const action = new URL(route.request().url()).pathname.slice('/api/live/'.length)
      let data
      if (action === 'session') data = { account: null }
      else if (action === 'local-accounts') data = { items: [{ uid: 'test', name: 'Synthetic owner' }] }
      else if (action === 'local/test') data = { items: sources.map(s => ({ ...s, bio: '', group_ids: [] })), groups: [], cached_at: null, historical: true }
      else if (action.startsWith('local/test/tool-groups')) {
        const suffix = action.slice('local/test/tool-groups'.length)
        const body = route.request().postDataJSON() || {}
        if (suffix === '/create') groups.push({ id: String(groups.length + 1), name: body.name, source_uids: [] })
        else if (suffix.endsWith('/rename')) groups.find(g => g.id === suffix.split('/')[1]).name = body.name
        else if (suffix.endsWith('/members')) groups.find(g => g.id === suffix.split('/')[1]).source_uids = body.source_uids
        else if (suffix.endsWith('/delete')) groups = groups.filter(g => g.id !== suffix.split('/')[1])
        else assert.equal(suffix, '')
        data = { items: groups, sources }
      } else throw new Error(`Unexpected platform operation: ${action}`)
      await route.fulfill({ json: data })
    })
    await page.goto(process.env.UPDESK_URL || 'http://127.0.0.1:8768/')
    const panel = page.locator('.local-groups')
    await panel.getByText('本地工具分组', { exact: true }).waitFor()
    await panel.locator('#local-group-name').fill('First')
    await panel.getByRole('button', { name: '新建本机分组', exact: true }).click()
    await panel.locator('#local-group-select option').filter({ hasText: 'First' }).waitFor({ state: 'attached' })
    await page.locator('#live-tool-group option').filter({ hasText: 'First' }).waitFor({ state: 'attached' })
    await panel.getByRole('checkbox', { name: 'Source A · 2' }).check()
    await panel.locator('#local-source-search').fill('Source B')
    await panel.getByRole('checkbox', { name: 'Source B · 3' }).check()
    await panel.getByRole('button', { name: '保存组成员', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.local-groups [role="status"]')?.textContent?.includes('已整组替换'))
    assert.deepEqual(groups[0].source_uids.sort(), ['2', '3'])
    await panel.locator('#local-group-name').fill('Renamed')
    await panel.getByRole('button', { name: '重命名', exact: true }).click()
    await panel.locator('#local-group-select option').filter({ hasText: 'Renamed' }).waitFor({ state: 'attached' })
    await page.locator('#live-tool-group option').filter({ hasText: 'Renamed' }).waitFor({ state: 'attached' })
    await page.reload()
    await panel.locator('#local-group-select option').filter({ hasText: 'Renamed' }).waitFor({ state: 'attached' })
    await panel.getByRole('checkbox', { name: 'Source A · 2' }).waitFor()
    assert(await panel.getByRole('checkbox', { name: 'Source A · 2' }).isChecked())
    await page.setViewportSize({ width: 390, height: 844 })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    page.once('dialog', dialog => dialog.dismiss())
    await panel.getByRole('button', { name: '删除本机分组', exact: true }).click()
    assert.equal(groups.length, 1)
    page.once('dialog', dialog => dialog.accept())
    await panel.getByRole('button', { name: '删除本机分组', exact: true }).click()
    await panel.getByText('暂无本机分组', { exact: true }).waitFor({ state: 'attached' })
    assert.equal(groups.length, 0)
    assert.deepEqual(errors, [])
    console.log('PASS: local group create/rename/delete, search-safe members, refresh and mobile width')
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
