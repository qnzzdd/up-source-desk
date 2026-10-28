<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import LocalGroups from './LocalGroups.vue'
const remaining = ref(0)
let deadline = 0
let nextPoll = 0
let timer: ReturnType<typeof setInterval> | undefined
function stopPolling() { clearInterval(timer); timer = undefined }
function startPolling() {
  stopPolling()
  deadline = Date.now() + 180000
  nextPoll = Date.now() + 5000
  remaining.value = 180
  timer = setInterval(() => {
    remaining.value = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
    if (!remaining.value) {
      stopPolling()
      qr.value = ''
      state.value = '本次扫码窗口已结束，请生成新二维码；平台可能提前使二维码失效'
      return
    }
    if (!busy.value && Date.now() >= nextPoll) {
      nextPoll = Date.now() + 5000
      void run('poll')
    }
  }, 1000)
}
onUnmounted(() => { stopPolling(); stopSyncPolling() })
const busy = ref(false)
const error = ref('')
const qr = ref('')
const state = ref('尚未连接')
const account = ref<{ uid: string; name: string } | null>(null)
const localAccounts = ref<{ uid: string; name: string }[]>([])
const localUid = ref('')
const localGroupsRef = ref<InstanceType<typeof LocalGroups> | null>(null)
type SyncStatus = {
  state: 'idle' | 'running' | 'complete' | 'incomplete' | 'error' | 'stopped'
  page: number
  loaded: number
  total: number
  added: number
  last_success: string | null
  next_run: string | null
  error: string | null
  account_uid: string | null
}
const syncStatus = ref<SyncStatus | null>(null)
const toolGroups = ref<{ id: string; name: string; source_uids: string[] }[]>([])
const toolGroupFilter = ref('')
const toolGroupsBusy = ref(false)
function applyLocalGroups(next: { id: string; name: string; source_uids: string[] }[]) {
  toolGroups.value = next
  if (toolGroupFilter.value && !toolGroups.value.some(group => group.id === toolGroupFilter.value)) toolGroupFilter.value = ''
}
let syncRevision = 0
let syncRequesting = false
let syncTimer: ReturnType<typeof setInterval> | undefined
let metadataRevision = 0
let toolGroupsRevision = 0
const contentHistorical = ref(false)
const contentSavedAt = ref<string | null>(null)
const sources = ref<{ uid: string; name: string; bio: string; group_ids: unknown }[]>([])
const groups = ref<{ id: string; name: string; member_count: number | null }[]>([])
const groupsLoaded = ref(false)
const followsLoaded = ref(false)
const total = ref(0)
const hasMore = ref(false)
const page = ref(0)
const warning = ref('')
const groupFilter = ref('')
const sourceQuery = ref('')
const historical = ref(false)
const groupsHistorical = ref(false)
const cachedAt = ref<string | null>(null)
const activeToolGroup = computed(() => toolGroups.value.find(group => group.id === toolGroupFilter.value) ?? null)
const syncStateLabel = computed(() => {
  const status = syncStatus.value
  if (!status) return '正在读取后端同步状态…'
  const labels: Record<SyncStatus['state'], string> = {
    idle: '后端同步当前空闲；首次同步由登录后的后端任务启动',
    running: '后端正在同步关注与分组元数据',
    complete: '后端报告本轮同步完成；下一次自动同步由后端调度',
    incomplete: '后端报告本轮同步未完整完成，未标记为完整同步',
    error: '后端报告同步失败',
    stopped: '后端同步已停止；账号仍保持登录，可手动启动',
  }
  return labels[status.state] ?? '未知同步状态'
})
const visibleSources = computed(() => sources.value.filter(source =>
  (!groupFilter.value || (Array.isArray(source.group_ids) && source.group_ids.some(id => String(id) === groupFilter.value))) &&
  (!toolGroupFilter.value || !!activeToolGroup.value?.source_uids.includes(source.uid)) &&
  `${source.name} ${source.uid}`.toLowerCase().includes(sourceQuery.value.trim().toLowerCase())))
const selected = ref('')
const items = ref<{ id: string; text: string }[]>([])
const contentLoaded = ref(false)
const contentLabel = ref('')
const UP_PAGE_SIZE = 20
const upPage = ref(1)
const upPageCount = computed(() => Math.max(1, Math.ceil(visibleSources.value.length / UP_PAGE_SIZE)))
const pagedSources = computed(() => {
  const safePage = Math.min(Math.max(1, upPage.value), upPageCount.value)
  const start = (safePage - 1) * UP_PAGE_SIZE
  return visibleSources.value.slice(start, start + UP_PAGE_SIZE)
})
function clearUpContent() {
  selected.value = ''
  items.value = []
  contentLoaded.value = false
}
function resetUpPage() {
  upPage.value = 1
  clearUpContent()
}
function goToUpPage(targetPage: number) {
  const nextPage = Math.min(Math.max(1, targetPage), upPageCount.value)
  if (nextPage === upPage.value) return
  upPage.value = nextPage
  clearUpContent()
}
function clampUpPage() {
  if (upPage.value > upPageCount.value) {
    upPage.value = upPageCount.value
    clearUpContent()
  } else if (upPage.value < 1) {
    upPage.value = 1
    clearUpContent()
  }
  if (selected.value && !visibleSources.value.some(source => source.uid === selected.value)) clearUpContent()
}
function selectSource(uid: string) {
  selected.value = uid
  items.value = []
  contentLoaded.value = false
}
watch([groupFilter, toolGroupFilter, sourceQuery], resetUpPage)
watch(visibleSources, () => clampUpPage())
function clearAccountData() {
  sources.value = []; groups.value = []; items.value = []; selected.value = ''
  groupFilter.value = ''; sourceQuery.value = ''; warning.value = ''; cachedAt.value = null
  groupsLoaded.value = followsLoaded.value = contentLoaded.value = false
  historical.value = groupsHistorical.value = hasMore.value = false
  total.value = page.value = 0
  upPage.value = 1
  toolGroups.value = []; toolGroupFilter.value = ''
  resetSyncState()
  toolGroupsRevision++
}
function acceptAccount(value: { uid: string; name: string }) {
  if (account.value?.uid !== value.uid) clearAccountData()
  account.value = value
}
async function request(action: string) {
  const response = await fetch(`/api/live/${action}`, { method: 'POST', headers: { 'X-UPDesk-Local': '1' }, cache: 'no-store' })
  const data = await response.json()
  if (!response.ok) {
    if (response.status === 401) { account.value = null; clearAccountData(); state.value = '登录已失效，请重新扫码' }
    throw new Error(`${data.error?.code ?? response.status} · ${data.error?.message ?? '请求失败'}`)
  }
  return data
}
function applyCache(data: { items: typeof sources.value; groups: typeof groups.value; cached_at: string | null }) {
  sources.value = data.items; groups.value = data.groups; cachedAt.value = data.cached_at
  historical.value = groupsHistorical.value = true; followsLoaded.value = groupsLoaded.value = true
  hasMore.value = false; page.value = 0; total.value = 0; warning.value = ''; upPage.value = 1
  selected.value = ''; groupFilter.value = ''; sourceQuery.value = ''; items.value = []; contentLoaded.value = false
}
function applyMetadata(data: { items: typeof sources.value; groups: typeof groups.value; cached_at: string | null }) {
  sources.value = data.items; groups.value = data.groups; cachedAt.value = data.cached_at
  historical.value = groupsHistorical.value = true; followsLoaded.value = groupsLoaded.value = true
  clampUpPage()
}
function stopSyncPolling() {
  if (syncTimer !== undefined) { clearInterval(syncTimer); syncTimer = undefined }
}
function resetSyncState() {
  syncRevision++
  metadataRevision++
  stopSyncPolling()
  syncRequesting = false
  syncStatus.value = null
}
async function loadToolGroups() {
  const uid = account.value?.uid ?? localUid.value
  if (!uid) {
    toolGroupsRevision++
    toolGroups.value = []; toolGroupFilter.value = ''; toolGroupsBusy.value = false
    return
  }
  const currentRevision = ++toolGroupsRevision
  const currentUid = uid
  toolGroupsBusy.value = true
  try {
    const data = await request(`local/${encodeURIComponent(uid)}/tool-groups`) as { items: { id: string; name: string; source_uids: string[] }[] }
    if (currentRevision !== toolGroupsRevision || (account.value?.uid ?? localUid.value) !== currentUid) return
    toolGroups.value = Array.isArray(data.items) ? data.items : []
    if (toolGroupFilter.value && !toolGroups.value.some(group => group.id === toolGroupFilter.value)) toolGroupFilter.value = ''
  } catch (e) {
    if (currentRevision !== toolGroupsRevision) return
    error.value = e instanceof Error ? e.message : '本机工具分组读取失败'
  } finally {
    if (currentRevision === toolGroupsRevision) toolGroupsBusy.value = false
  }
}
async function refreshMetadata(uid: string, refreshLocalGroups = false): Promise<boolean> {
  const currentRevision = ++metadataRevision
  const syncAtStart = syncRevision
  if (busy.value) return false
  try {
    const data = await request(`local/${encodeURIComponent(uid)}`)
    if (currentRevision !== metadataRevision || syncAtStart !== syncRevision || account.value?.uid !== uid) return false
    applyMetadata(data)
    await loadToolGroups()
    if (refreshLocalGroups && currentRevision === metadataRevision && syncAtStart === syncRevision && account.value?.uid === uid) {
      void localGroupsRef.value?.refresh()
    }
    return true
  } catch (e) {
    if (currentRevision === metadataRevision && syncAtStart === syncRevision && account.value?.uid === uid) {
      error.value = e instanceof Error ? e.message : '刷新本机元数据失败'
    }
    return false
  }
}
async function refreshCurrentMetadata() {
  const uid = account.value?.uid
  if (!uid || busy.value) return
  busy.value = true
  try {
    const refreshed = await refreshMetadata(uid, false)
    if (refreshed && account.value?.uid === uid) state.value = '已刷新本机保存的关注与 B站原生分组记录'
  } finally { busy.value = false }
}
function applySyncStatus(data: SyncStatus, uid: string) {
  if (data.account_uid && data.account_uid !== uid) return false
  const previous = syncStatus.value
  const progressChanged = !previous || previous.page !== data.page || previous.loaded !== data.loaded
  const becameComplete = data.state === 'complete' && previous?.state !== 'complete'
  syncStatus.value = data
  if (progressChanged || becameComplete) void refreshMetadata(uid, becameComplete)
  return true
}
async function pollSyncStatus() {
  const uid = account.value?.uid
  if (!uid || busy.value || syncRequesting) return
  const currentRevision = syncRevision
  syncRequesting = true
  try {
    const data = await request('sync-status') as SyncStatus
    if (currentRevision !== syncRevision || account.value?.uid !== uid) return
    applySyncStatus(data, uid)
  } catch (e) {
    if (currentRevision !== syncRevision || account.value?.uid !== uid) return
    error.value = e instanceof Error ? e.message : '读取后端同步状态失败'
  } finally {
    if (currentRevision === syncRevision) syncRequesting = false
  }
}
function startSyncPolling() {
  if (!account.value) return
  if (syncTimer === undefined) {
    syncTimer = setInterval(() => {
      if (!account.value || busy.value || syncRequesting) return
      void pollSyncStatus()
    }, 5000)
  }
  if (!busy.value && !syncRequesting) void pollSyncStatus()
}
function formatTime(value: string | null) {
  if (!value) return '暂无'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}
async function restore() {
  busy.value = true
  try {
    const session = await request('session')
    localAccounts.value = (await request('local-accounts')).items
    if (session.account) {
      const uid = session.account.uid
      acceptAccount(session.account); localUid.value = uid
      state.value = '已恢复本机登录会话；仅轮询后端同步状态，刷新页面不会启动新同步任务'
      startSyncPolling()
      applyMetadata(await request(`local/${encodeURIComponent(uid)}`))
      await loadToolGroups()
    } else if (localAccounts.value.length) {
      localUid.value = localAccounts.value[0]!.uid
      applyCache(await request(`local/${encodeURIComponent(localUid.value)}`))
      await loadToolGroups()
      state.value = '离线浏览本机历史；读取 B站新数据需要扫码'
    }
  } catch (e) { error.value = e instanceof Error ? e.message : '恢复本机记录失败' }
  finally { busy.value = false }
}
onMounted(restore)
async function run(action: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  if (action.includes('sources/')) { items.value = []; contentLoaded.value = false }
  try {
    const data = await request(action)
    if (action === 'qr') { qr.value = data.image; state.value = '请用 B站 App 扫码，并在手机上确认'; startPolling() }
    if (action === 'poll') {
      state.value = ({ waiting_scan: '等待扫码', waiting_confirm: '请在手机上确认', expired: '二维码已过期，请重新生成', connected: '已连接，身份验证成功' } as Record<string, string>)[data.state] ?? '未知状态'
      if (data.account) {
        const uid = data.account.uid
        acceptAccount(data.account); localUid.value = uid
        startSyncPolling()
        applyMetadata(await request(`local/${encodeURIComponent(uid)}`))
        localAccounts.value = (await request('local-accounts')).items
        await loadToolGroups()
        if (data.state === 'connected') state.value = '身份验证成功；后端已自动启动首次完整关注同步，正在读取同步状态'
      }
      if (['expired', 'connected'].includes(data.state)) { qr.value = ''; stopPolling() }
    }
    if (action === 'account') {
      acceptAccount(data.account)
      if (data.account) { localUid.value = data.account.uid; startSyncPolling() }
      state.value = '身份验证成功'
    }
    if (action === 'sync-start' || action === 'sync-stop') {
      const uid = account.value?.uid
      if (uid && applySyncStatus(data as SyncStatus, uid)) startSyncPolling()
      state.value = action === 'sync-start'
        ? '已请求后端启动关注同步；仅同步关注与分组元数据'
        : '已请求后端停止自动关注同步'
    }
    if (action === 'cache' || (action.startsWith('local/') && !action.includes('/sources/') && !action.endsWith('/tool-groups'))) applyCache(data)
    if (action === 'groups') {
      groups.value = data.items; groupsLoaded.value = true; groupsHistorical.value = false
      if (groupFilter.value && !groups.value.some(group => group.id === groupFilter.value)) {
        groupFilter.value = ''; selected.value = ''; items.value = []; contentLoaded.value = false
      }
    }
    if (action.includes('sources/')) { items.value = data.items; contentLoaded.value = true; contentLabel.value = action.endsWith('videos') ? '视频投稿' : '动态'; contentHistorical.value = !!data.historical; contentSavedAt.value = data.cached_at ?? null }
    if (action === 'disconnect') {
      stopPolling()
      account.value = null; qr.value = ''; clearAccountData()
      state.value = '已断开登录并停止同步轮询；本机保存的关注与分组仍保留（不代表退出其他 B站设备）'
    }
  } catch (e) { stopPolling(); error.value = e instanceof Error ? e.message : '本地服务连接失败' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="live-connect" aria-labelledby="live-title">
    <h2 id="live-title">真实账号接入与关注管理</h2>
    <p>本区管理真实 B站账号、关注与本机分组，与下方演示工作台分开。登录成功后由本地后端自动启动首次完整关注同步，完成后在登录期间每 10 分钟自动同步；仅同步关注和分组元数据，不读取投稿、动态等内容。关注与分组保存在本机 SQLite；登录凭据仅留后端内存，重启失效，不落盘、不发给 AI。</p>
    <div class="live-controls">
      <button :disabled="busy || !!account" @click="run('qr')">生成登录二维码</button>
      <button :disabled="busy || !qr" @click="run('poll')">我已扫码，检查状态</button>
      <button :disabled="busy || !account" @click="run('account')">验证账号</button>
      <button :disabled="busy || (!account && !qr)" @click="run('disconnect')">断开并清除</button>
    </div>
    <p role="status">{{ busy ? '正在处理本机请求，请稍候…' : state }}</p>
    <img v-if="qr" :src="qr" width="220" height="220" alt="B站登录二维码，仅用于本次本机连接" />
    <p v-if="qr">本次本地扫码窗口剩余 {{ remaining }} 秒，每约 5 秒自动检查。实际有效期以 B站为准；请在手机上完成确认。</p>
    <p v-if="account"><strong>真实账号：{{ account.name }}</strong> · UID {{ account.uid }}</p>
    <p v-if="error" role="alert" class="live-error">{{ error }}</p>
    <div v-if="!account && localAccounts.length">
      <label for="local-account">本机历史账号（不是当前登录身份）</label>
      <select id="local-account" v-model="localUid" :disabled="busy" @change="clearAccountData(); run(`local/${encodeURIComponent(localUid)}`)">
        <option v-for="saved in localAccounts" :key="saved.uid" :value="saved.uid">{{ saved.name }} · {{ saved.uid }}</option>
      </select>
      <button :disabled="busy" @click="run(`local/${encodeURIComponent(localUid)}`)">打开本机历史</button>
      <p>仅在这台电脑浏览已保存资料，不会登录 B站或发起采集。数据库未加密，请保护本机账户。</p>
    </div>
    <h3>关注与分组管理</h3>
    <div v-if="account" class="live-controls">
      <button :disabled="busy || syncStatus?.state === 'running'" @click="run('sync-start')">启动关注同步</button>
      <button :disabled="busy || !syncStatus || ['idle', 'stopped'].includes(syncStatus.state)" @click="run('sync-stop')">停止自动同步</button>
      <button :disabled="busy" @click="refreshCurrentMetadata">刷新本机已保存元数据</button>
      <button :disabled="busy" @click="run('groups')">读取 B站已有分组</button>
    </div>
    <div v-if="account" class="sync-status" aria-live="polite">
      <h4>关注自动同步状态</h4>
      <p>{{ syncStateLabel }}</p>
      <p v-if="syncStatus">进度：第 {{ syncStatus.page }} 页，已加载 {{ syncStatus.loaded }}<template v-if="syncStatus.total"> / {{ syncStatus.total }}</template>；新增 {{ syncStatus.added }}。最近成功：{{ formatTime(syncStatus.last_success) }}；下次计划：{{ formatTime(syncStatus.next_run) }}。</p>
      <p v-else>正在读取后端同步状态；本机历史仍可浏览。</p>
      <p v-if="syncStatus?.state === 'incomplete'" role="alert">后端报告本轮同步未完整完成，页面不会将其显示为完整同步；可稍后重新启动同步。</p>
      <p v-if="syncStatus?.error" role="alert" class="live-error">同步错误：{{ syncStatus.error }}</p>
    </div>
    <p v-if="followsLoaded" role="status">本机已保存 {{ sources.length }} 个 UP，{{ groups.length }} 个 B站原生分组记录。最近保存：{{ cachedAt ? new Date(cachedAt).toLocaleString() : '暂无记录' }}。本机记录可能滞后于 B站；未收到“同步完成”状态时，不代表当前完整关注，也不会据此自动标记取关。</p>
    <p v-if="followsLoaded && warning" role="status">{{ warning }}</p>
    <div v-if="groupsLoaded"><h3>B站原生分组记录{{ groupsHistorical ? ' · 本机历史' : ' · 本次读取' }}</h3><p v-if="!groups.length">{{ groupsHistorical ? '本机暂无保存的 B站原生分组。' : '接口成功返回空 B站原生分组列表。' }}</p>
      <ul><li v-for="group in groups" :key="group.id">{{ group.name }}（{{ group.member_count ?? '人数未知' }}） · ID {{ group.id }}</li></ul>
    </div>
    <div v-if="account?.uid || localUid" class="manual-content">
      <h3>UP内容监控（手动）</h3>
      <p>关注自动同步只更新关注与分组元数据，不会读取投稿、动态或媒体内容。以下内容读取只会在手动点击按钮时发生。</p>
      <template v-if="sources.length">
        <label for="live-group">按 B站原生分组筛选已保存 UP</label>
        <select id="live-group" v-model="groupFilter" :disabled="busy" @change="resetUpPage">
          <option value="">全部已保存 UP</option><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
        </select>
        <label for="live-tool-group">按本地工具分组筛选已保存 UP</label>
        <select id="live-tool-group" v-model="toolGroupFilter" :disabled="busy || toolGroupsBusy" @change="resetUpPage">
          <option value="">全部已保存 UP</option><option v-for="group in toolGroups" :key="group.id" :value="group.id">{{ group.name }}</option>
        </select>
        <div class="live-controls"><button type="button" :disabled="toolGroupsBusy" @click="loadToolGroups">刷新工具分组筛选</button></div>
        <label for="live-query">搜索昵称或 UID（仅本机已保存数据）</label>
        <input id="live-query" v-model="sourceQuery" :disabled="busy" @input="resetUpPage" />
        <p>当前筛选 {{ visibleSources.length }} 个。B站原生分组与本地工具分组相互独立；未返回的 B站分组归属不会被猜测。</p>
        <div class='up-picker' role='group' aria-labelledby='live-source-label'>
          <span id='live-source-label' class='up-picker-label'>选择已保存 UP</span>
          <p class='up-page-summary'>当前筛选 {{ visibleSources.length }} 个 UP，本页显示 {{ pagedSources.length }} 个（每页 {{ UP_PAGE_SIZE }} 个）</p>
          <ul id='live-source-list' class='up-list' aria-label='已保存 UP 列表' :aria-busy='busy'>
            <li v-for='source in pagedSources' :key='source.uid'>
              <button type='button' class='up-row' :aria-pressed='selected === source.uid' :disabled='busy' @click='selectSource(source.uid)'>
                <span>{{ source.name }}</span><small>UID {{ source.uid }}</small>
              </button>
            </li>
          </ul>
          <p v-if='!pagedSources.length' class='up-empty'>当前筛选没有可选择的 UP。</p>
          <nav class='up-pagination' aria-label='已保存 UP 列表分页'>
            <button type='button' :disabled='busy || upPage <= 1' aria-label='上一页 UP' @click='goToUpPage(upPage - 1)'>上一页</button>
            <span>第 {{ upPage }} / {{ upPageCount }} 页</span>
            <button type='button' :disabled='busy || upPage >= upPageCount' aria-label='下一页 UP' @click='goToUpPage(upPage + 1)'>下一页</button>
          </nav>
        </div>
        <p v-if="selected">平台返回的分组 ID：{{ JSON.stringify(sources.find(s => s.uid === selected)?.group_ids ?? '未提供，不能判断未分组') }}</p>
        <div class="live-controls"><button :disabled="busy || !selected || !account" @click="run(`sources/${selected}/videos`)">手动读取并保存视频</button>
          <button :disabled="busy || !selected || !account" @click="run(`sources/${selected}/dynamics`)">手动读取并保存动态</button>
          <button :disabled="busy || !selected" @click="run(`local/${encodeURIComponent(account?.uid ?? localUid)}/sources/${selected}/videos`)">已保存视频</button>
          <button :disabled="busy || !selected" @click="run(`local/${encodeURIComponent(account?.uid ?? localUid)}/sources/${selected}/dynamics`)">已保存动态</button></div>
      </template>
      <p v-else>本机尚未保存可选择的 UP。请先完成关注同步，或在离线历史中打开本机账号。</p>
    </div>
    <div v-if="contentLoaded"><h3>{{ contentLabel }} · {{ contentHistorical ? '本机历史' : '本次手动读取，已保存' }}</h3>
      <p v-if="contentHistorical">最近保存：{{ contentSavedAt ? new Date(contentSavedAt).toLocaleString() : '尚未采集保存' }}，不代表当前全部内容。</p>
      <p v-if="!items.length">{{ contentHistorical ? '本机没有保存的内容条目。' : '接口成功返回空内容列表。' }}</p>
      <p v-if="contentLabel === '动态'">读取图文、视频分享、专栏及转发中的文字；不读取或分析图片，也不转写视频。</p>
      <ul><li v-for="item in items" :key="item.id"><span style="white-space: pre-wrap">{{ item.text }}</span> <small>（{{ item.id }}）</small>
        <a v-if="contentLabel === '动态'" :href="`https://t.bilibili.com/${encodeURIComponent(item.id)}`" target="_blank" rel="noopener noreferrer">查看原动态</a>
      </li></ul>
    </div>
    <LocalGroups v-if="account?.uid || localUid" ref="localGroupsRef" :key="account?.uid ?? localUid" :account-uid="account?.uid ?? localUid" @changed="applyLocalGroups" />
  </section>
</template>

<style scoped>
.live-connect{margin:0 0 24px;padding:24px;border:1px solid #bcd8ff;border-radius:24px;background:#fff;color:#20334f;overflow-wrap:anywhere}.live-connect h2{font-size:21px;margin-bottom:12px}.live-connect p{line-height:1.8;margin:12px 0}.live-controls{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.live-controls button,.live-connect select{border:1px solid #c5dbf8;border-radius:12px;padding:10px 14px;background:#f0f7ff;color:#1455a0;max-width:100%}.live-controls button:disabled{opacity:.45;cursor:not-allowed}.live-controls button:focus-visible,.live-connect select:focus-visible{outline:3px solid #1778ff}.live-error{background:#fff0ef;color:#9b2922;padding:12px;border-radius:12px}.live-connect ul{padding-left:22px}.live-connect li{line-height:1.8;margin:6px 0}.live-connect label{display:block;margin:12px 0}.live-connect img{display:block;max-width:100%}.manual-content{border-top:1px solid #dbebfd;margin-top:18px;padding-top:4px}.sync-status{background:#f7fbff;border:1px solid #d7e8fb;border-radius:12px;padding:12px}.sync-status h4{margin:0 0 8px}.up-picker{border:1px solid #d7e8fb;border-radius:16px;padding:12px;background:#f7fbff}.up-picker-label{display:block;font-weight:700;margin:0 0 6px}.live-connect .up-page-summary{margin:0 0 10px;color:#4b6688}.up-list{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.up-list li{margin:0}.up-row{display:flex;flex-direction:column;align-items:flex-start;gap:3px;width:100%;min-width:0;min-height:48px;border:1px solid #c5dbf8;border-radius:12px;padding:10px 12px;background:#fff;color:#20334f;text-align:left;cursor:pointer;font:inherit}.up-row span,.up-row small{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.up-row small{color:#5b718d}.up-row:hover:not(:disabled){border-color:#77aef0;background:#eef7ff}.up-row[aria-pressed='true']{border-color:#1778ff;background:#e6f1ff;box-shadow:inset 0 0 0 1px #1778ff}.up-row:disabled{opacity:.45;cursor:not-allowed}.up-row:focus-visible,.up-pagination button:focus-visible{outline:3px solid #1778ff;outline-offset:2px}.live-connect .up-empty{margin:10px 0}.up-pagination{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px;margin-top:12px}.up-pagination button{border:1px solid #c5dbf8;border-radius:12px;padding:9px 14px;background:#fff;color:#1455a0;font:inherit}.up-pagination button:disabled{opacity:.45;cursor:not-allowed}.up-pagination span{font-weight:700}@media (max-width:640px){.up-list{grid-template-columns:1fr}.up-pagination{justify-content:space-between}}
</style>
