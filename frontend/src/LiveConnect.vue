<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
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
onUnmounted(stopPolling)
const busy = ref(false)
const error = ref('')
const qr = ref('')
const state = ref('尚未连接')
const account = ref<{ uid: string; name: string } | null>(null)
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
const visibleSources = computed(() => sources.value.filter(source =>
  (!groupFilter.value || (Array.isArray(source.group_ids) && source.group_ids.some(id => String(id) === groupFilter.value))) &&
  `${source.name} ${source.uid}`.toLowerCase().includes(sourceQuery.value.trim().toLowerCase())))
const selected = ref('')
const items = ref<{ id: string; text: string }[]>([])
const contentLoaded = ref(false)
const contentLabel = ref('')
async function run(action: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  if (action.startsWith('sources/')) { items.value = []; contentLoaded.value = false }
  try {
    const response = await fetch(`/api/live/${action}`, { method: 'POST', headers: { 'X-UPDesk-Local': '1' }, cache: 'no-store' })
    const data = await response.json()
    if (!response.ok) {
      if (response.status === 401) { account.value = null; sources.value = []; groups.value = []; items.value = []; groupsLoaded.value = followsLoaded.value = contentLoaded.value = false }
      throw new Error(`${data.error?.code ?? response.status} · ${data.error?.message ?? '请求失败'}`)
    }
    if (action === 'qr') { qr.value = data.image; state.value = '请用 B站 App 扫码，并在手机上确认'; startPolling() }
    if (action === 'poll') {
      state.value = ({ waiting_scan: '等待扫码', waiting_confirm: '请在手机上确认', expired: '二维码已过期，请重新生成', connected: '已连接，身份验证成功' } as Record<string, string>)[data.state] ?? '未知状态'
      if (data.account) account.value = data.account
      if (['expired', 'connected'].includes(data.state)) { qr.value = ''; stopPolling() }
    }
    if (action === 'account') { account.value = data.account; state.value = '身份验证成功' }
    if (action === 'followings' || action === 'followings-next') {
      const merged = new Map((action === 'followings' ? [] : sources.value).map(source => [source.uid, source]))
      for (const source of data.items) merged.set(source.uid, source)
      sources.value = [...merged.values()]; total.value = data.total; followsLoaded.value = true
      hasMore.value = data.has_more; page.value = data.page; warning.value = data.warning
      if (action === 'followings') { selected.value = ''; items.value = []; contentLoaded.value = false; groupFilter.value = '' }
    }
    if (action === 'groups') { groups.value = data.items; groupsLoaded.value = true }
    if (action.startsWith('sources/')) { items.value = data.items; contentLoaded.value = true; contentLabel.value = action.endsWith('videos') ? '视频投稿' : '动态' }
    if (action === 'disconnect') {
      stopPolling()
      account.value = null; qr.value = ''; sources.value = []; groups.value = []; items.value = []
      groupsLoaded.value = followsLoaded.value = contentLoaded.value = false; state.value = '已清除本机内存登录态（不代表退出其他 B站设备）'
    }
  } catch (e) { stopPolling(); error.value = (e instanceof Error ? e.message : '本地服务连接失败') + '；自动检查已暂停，可手动重试。' }
  finally { busy.value = false }
}
</script>

<template>
  <section class="live-connect" aria-labelledby="live-title">
    <h2 id="live-title">真实账号接入 · 手动验证</h2>
    <p>此区域读取真实 B站数据，与下方演示工作台分开。凭据仅留后端内存，重启失效；不落盘、不发给 AI、不自动扫描。</p>
    <div class="live-controls">
      <button :disabled="busy || !!account" @click="run('qr')">生成登录二维码</button>
      <button :disabled="busy || !qr" @click="run('poll')">我已扫码，检查状态</button>
      <button :disabled="busy || !account" @click="run('account')">验证账号</button>
      <button :disabled="busy || (!account && !qr)" @click="run('disconnect')">断开并清除</button>
    </div>
    <p role="status">{{ busy ? '请求中，请稍候（请求间隔至少 3 秒）…' : state }}</p>
    <img v-if="qr" :src="qr" width="220" height="220" alt="B站登录二维码，仅用于本次本机连接" />
    <p v-if="qr">本次本地扫码窗口剩余 {{ remaining }} 秒，每约 5 秒自动检查。实际有效期以 B站为准；请在手机上完成确认。</p>
    <p v-if="account"><strong>真实账号：{{ account.name }}</strong> · UID {{ account.uid }}</p>
    <p v-if="error" role="alert" class="live-error">{{ error }}</p>
    <div v-if="account" class="live-controls">
      <button :disabled="busy" @click="run('followings')">{{ followsLoaded ? '重新读取首页（重置列表）' : '读取关注首页（20 个）' }}</button>
      <button v-if="followsLoaded" :disabled="busy || !hasMore" @click="run('followings-next')">加载下一页</button>
      <button :disabled="busy" @click="run('groups')">读取 B站已有分组</button>
    </div>
    <p v-if="followsLoaded">已读取 {{ page }} 页，去重后 {{ sources.length }} / 平台报告 {{ total }} 个关注。手动分页不保证稳定快照，不会据此标记取关。</p>
    <p v-if="followsLoaded && warning" role="status">{{ warning }}</p>
    <div v-if="groupsLoaded"><h3>B站已有分组</h3><p v-if="!groups.length">接口成功返回空分组列表。</p>
      <ul><li v-for="group in groups" :key="group.id">{{ group.name }}（{{ group.member_count ?? '人数未知' }}） · ID {{ group.id }}</li></ul>
    </div>
    <div v-if="sources.length">
      <label for="live-group">按 B站分组筛选已读取的关注</label>
      <select id="live-group" v-model="groupFilter" :disabled="busy" @change="selected = ''; items = []; contentLoaded = false">
        <option value="">全部已读取关注</option><option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
      </select>
      <label for="live-query">搜索昵称或 UID（仅已读取数据）</label>
      <input id="live-query" v-model="sourceQuery" :disabled="busy" @input="selected = ''; items = []; contentLoaded = false" />
      <p>当前筛选 {{ visibleSources.length }} 个。未返回分组归属的账号不会被猜测为未分组。</p>
      <label for="live-source">选择真实 UP（仅来自已读取关注）</label>
      <select id="live-source" v-model="selected" :disabled="busy" @change="items = []; contentLoaded = false">
        <option value="">请选择</option><option v-for="source in visibleSources" :key="source.uid" :value="source.uid">{{ source.name }} · {{ source.uid }}</option>
      </select>
      <p v-if="selected">平台返回的分组 ID：{{ JSON.stringify(sources.find(s => s.uid === selected)?.group_ids ?? '未提供，不能判断未分组') }}</p>
      <div class="live-controls"><button :disabled="busy || !selected" @click="run(`sources/${selected}/videos`)">读取视频首屏</button>
        <button :disabled="busy || !selected" @click="run(`sources/${selected}/dynamics`)">读取动态首屏</button></div>
    </div>
    <div v-if="contentLoaded"><h3>{{ contentLabel }} · 仅首屏</h3><p v-if="!items.length">接口成功返回空内容列表。</p>
      <p v-if="contentLabel === '动态'">读取图文、视频分享、专栏及转发中的文字；不读取或分析图片，也不转写视频。</p>
      <ul><li v-for="item in items" :key="item.id"><span style="white-space: pre-wrap">{{ item.text }}</span> <small>（{{ item.id }}）</small>
        <a v-if="contentLabel === '动态'" :href="`https://t.bilibili.com/${encodeURIComponent(item.id)}`" target="_blank" rel="noopener noreferrer">查看原动态</a>
      </li></ul>
    </div>
  </section>
</template>

<style scoped>
.live-connect{margin:0 0 24px;padding:24px;border:1px solid #bcd8ff;border-radius:24px;background:#fff;color:#20334f;overflow-wrap:anywhere}.live-connect h2{font-size:21px;margin-bottom:12px}.live-connect p{line-height:1.8;margin:12px 0}.live-controls{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.live-controls button,.live-connect select{border:1px solid #c5dbf8;border-radius:12px;padding:10px 14px;background:#f0f7ff;color:#1455a0;max-width:100%}.live-controls button:disabled{opacity:.45;cursor:not-allowed}.live-controls button:focus-visible,.live-connect select:focus-visible{outline:3px solid #1778ff}.live-error{background:#fff0ef;color:#9b2922;padding:12px;border-radius:12px}.live-connect ul{padding-left:22px}.live-connect li{line-height:1.8;margin:6px 0}.live-connect label{display:block;margin:12px 0}.live-connect img{display:block;max-width:100%}
</style>
