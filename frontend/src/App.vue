<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ApiFailure, friendlyError, get } from './api'
import type { Account, Dynamic, Group, Page, Source, Video } from './api'

type ContentKind = 'videos' | 'dynamics'
const account = ref<Account | null>(null)
const groups = ref<Group[]>([])
const list = ref<Page<Source> | null>(null)
const selected = ref<Source | null>(null)
const content = ref<Page<Video | Dynamic> | null>(null)
const groupId = ref<string | null>(null)
const search = ref('')
const activeTab = ref<ContentKind>('videos')
const listLoading = ref(false)
const contentLoading = ref(false)
const listError = ref('')
const contentError = ref('')
const shellError = ref('')
const liveMessage = ref('')
const liveChecking = ref(false)
const listOffset = ref(0)
const contentOffset = ref(0)
let listRevision = 0
let contentRevision = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined
const PAGE_SIZE = 5

const currentGroupName = computed(() => groups.value.find(group => group.id === groupId.value)?.name ?? '全部关注')
const selectedGroups = computed(() => selected.value?.group_ids.map(id => groups.value.find(group => group.id === id)?.name).filter(Boolean) ?? [])

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function duration(seconds: number): string {
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}

async function loadShell() {
  shellError.value = ''
  try {
    const [accountResponse, groupResponse] = await Promise.all([
      get<{ mode: 'demo'; account: Account; warning: string }>('account'),
      get<Page<Group>>('groups'),
    ])
    account.value = accountResponse.account
    groups.value = groupResponse.items
  } catch (error) {
    shellError.value = friendlyError(error)
  }
}

async function loadList(offset = 0, append = false) {
  const revision = ++listRevision
  listOffset.value = offset
  listLoading.value = true
  listError.value = ''
  try {
    const response = await get<Page<Source>>('followings', {
      group_id: groupId.value ?? undefined, query: search.value.trim(), offset, limit: PAGE_SIZE,
    })
    if (revision !== listRevision) return
    list.value = append && list.value ? { ...response, items: [...list.value.items, ...response.items] } : response
    listOffset.value = offset
  } catch (error) {
    if (revision === listRevision) listError.value = friendlyError(error)
  } finally {
    if (revision === listRevision) listLoading.value = false
  }
}

async function loadContent(offset = 0, append = false) {
  const sourceId = selected.value?.uid
  if (!sourceId) return
  const kind = activeTab.value
  const revision = ++contentRevision
  contentOffset.value = offset
  contentLoading.value = true
  contentError.value = ''
  try {
    const response = await get<Page<Video | Dynamic>>(`sources/${encodeURIComponent(sourceId)}/${kind}`, { offset, limit: PAGE_SIZE })
    if (revision !== contentRevision || selected.value?.uid !== sourceId || activeTab.value !== kind) return
    content.value = append && content.value ? { ...response, items: [...content.value.items, ...response.items] } : response
    contentOffset.value = offset
  } catch (error) {
    if (revision === contentRevision) contentError.value = friendlyError(error)
  } finally {
    if (revision === contentRevision) contentLoading.value = false
  }
}

function selectSource(source: Source) {
  if (selected.value?.uid === source.uid) return
  selected.value = source
  activeTab.value = 'videos'
  content.value = null
  contentError.value = ''
  void loadContent()
}

function chooseTab(kind: ContentKind) {
  if (activeTab.value === kind) return
  activeTab.value = kind
  content.value = null
  contentError.value = ''
  void loadContent()
}

function chooseGroup(id: string | null) {
  if (groupId.value === id) return
  groupId.value = id
  ++listRevision
  listLoading.value = false
  list.value = null
  listError.value = ''
  void loadList()
}

async function checkLive() {
  liveChecking.value = true
  liveMessage.value = ''
  try {
    await get('account', { mode: 'live' })
    liveMessage.value = '真实接口已响应，请进一步核验返回身份。'
  } catch (error) {
    const code = error instanceof ApiFailure ? error.code : 'UNKNOWN'
    liveMessage.value = `${code} · ${friendlyError(error)}`
  } finally {
    liveChecking.value = false
  }
}

watch(search, () => {
  clearTimeout(searchTimer)
  ++listRevision
  listLoading.value = false
  searchTimer = setTimeout(() => {
    list.value = null
    void loadList()
  }, 240)
})

onMounted(() => {
  void loadShell()
  void loadList()
})
</script>

<template>
  <div class="app-frame">
    <header class="topbar">
      <div class="brand" aria-label="UP源台">
        <span class="brand-glyph" aria-hidden="true">源<span class="brand-dot"></span></span>
        <span><strong>UP源台</strong><small>YOUR SOURCE DESK</small></span>
      </div>
      <div class="topbar-right">
        <span class="environment-pill"><i></i> 本地演示环境</span>
        <span class="topbar-version">PREVIEW / 01</span>
      </div>
    </header>

    <div class="demo-ribbon" role="status">
      <span class="demo-ribbon-label">DEMO DATA</span>
      <span>当前展示的是合成样例，未登录 B 站，也未读取真实关注、视频或动态。</span>
      <button type="button" :disabled="liveChecking" @click="checkLive">{{ liveChecking ? '检查中…' : '检查真实接口' }} <span aria-hidden="true">↗</span></button>
    </div>
    <div v-if="liveMessage" class="live-result" role="status">{{ liveMessage }}</div>

    <main class="workspace">
      <aside class="sidebar" aria-label="分组导航">
        <div class="sidebar-heading"><span>工作区</span><span class="sidebar-line"></span></div>
        <div class="account-card">
          <div class="account-icon">我</div>
          <div><span class="account-kicker">演示账号 · 未登录 B 站</span><strong>{{ account?.name ?? '演示工作台' }}</strong></div>
        </div>
        <div v-if="shellError" class="sidebar-error" role="alert">{{ shellError }} <button type="button" @click="loadShell">重试</button></div>
        <div class="sidebar-heading groups-heading"><span>关注分组</span><span class="sidebar-line"></span></div>
        <nav class="group-nav" aria-label="关注分组">
          <button type="button" class="group-button" :class="{ active: groupId === null }" :aria-current="groupId === null ? 'page' : undefined" @click="chooseGroup(null)">
            <span class="group-mark all-mark">◈</span><span>全部关注</span><span class="group-count">{{ account?.following_count ?? '—' }}</span>
          </button>
          <button v-for="group in groups" :key="group.id" type="button" class="group-button" :class="{ active: groupId === group.id }" :aria-current="groupId === group.id ? 'page' : undefined" @click="chooseGroup(group.id)">
            <span class="group-mark">□</span><span>{{ group.name }}</span><span class="group-count">{{ group.member_count }}</span>
          </button>
        </nav>
        <div class="sidebar-note"><span class="note-number">01 / SCOPE</span><p>先看清信息源。分类、监控与日报，将从这里开始。</p></div>
        <div class="sidebar-footer">LOCAL FIRST <span>·</span> READ ONLY</div>
      </aside>

      <section class="main-column" aria-label="关注列表">
        <div class="eyebrow"><span class="eyebrow-dash"></span> 你的信息源 / EXPLORE</div>
        <div class="page-title-row"><div><h1>把关注，整理成<span>线索。</span></h1><p class="lead">从账号与分组开始，逐个了解你关注的创作者。</p></div><span class="index-mark">01<span>/</span>04</span></div>

        <div class="overview-grid">
          <div class="overview-card primary"><span>已关注创作者</span><strong>{{ account?.following_count ?? '—' }}<small> / 演示</small></strong><span class="overview-caption">等待接入真实账号</span></div>
          <div class="overview-card"><span>已有分组</span><strong>{{ account?.group_count ?? '—' }}<small> 组</small></strong><span class="overview-caption">来自合成样例</span></div>
          <div class="overview-card accent"><span>数据状态</span><strong class="status-word">只读演示</strong><span class="overview-caption"><i></i> 真实接口尚未连接</span></div>
        </div>

        <section class="list-panel">
          <div class="panel-topline"><div><span class="section-index">A / SOURCE LIST</span><h2>{{ currentGroupName }}</h2><p>{{ groupId ? '按分组查看创作者' : '所有关注的创作者，一目了然' }}</p></div><span class="results-count">{{ list?.pagination.total ?? '—' }} <small>位创作者</small></span></div>
          <label class="search-box"><span aria-hidden="true">⌕</span><span class="sr-only">搜索关注的 UP 主</span><input v-model="search" type="search" placeholder="搜索名称或简介…" autocomplete="off" /><kbd>SEARCH</kbd></label>
          <div class="list-meta"><span>按名称浏览</span><span>{{ list?.items.length ?? 0 }} / {{ list?.pagination.total ?? '—' }} 条已显示</span></div>
          <div v-if="listError" class="state error-state" role="alert"><strong>列表暂时无法读取</strong><span>{{ listError }}</span><button type="button" @click="loadList(listOffset, listOffset > 0)">重试读取</button></div>
          <div v-else-if="listLoading && !list" class="state">正在整理关注列表…</div>
          <div v-else-if="list && !list.items.length" class="state"><strong>这里还没有内容</strong><span>{{ search ? '试试其他关键词。' : '这个演示分组目前没有创作者。' }}</span></div>
          <div v-else class="source-list">
            <button v-for="(source, index) in list?.items ?? []" :key="source.uid" type="button" class="source-row" :class="{ selected: selected?.uid === source.uid }" @click="selectSource(source)">
              <span class="row-index">{{ String(index + 1).padStart(2, '0') }}</span><span class="avatar" :style="{ backgroundColor: source.color }">{{ source.initials }}</span>
              <span class="row-content"><strong>{{ source.name }}</strong><small>{{ source.bio }}</small></span>
              <span class="row-stat"><strong>{{ source.video_count }}</strong><small>视频</small></span><span class="row-arrow" aria-hidden="true">↗</span>
            </button>
          </div>
          <button v-if="list?.pagination.has_more" class="load-more" type="button" :disabled="listLoading" @click="loadList(listOffset + PAGE_SIZE, true)">{{ listLoading ? '加载中…' : '继续加载创作者' }} <span aria-hidden="true">↓</span></button>
        </section>
      </section>

      <aside class="detail-column" aria-label="创作者详情">
        <template v-if="selected">
          <div class="detail-label"><span>创作者档案</span><span>PROFILE / {{ selected.uid.slice(-2) }}</span></div>
          <div class="detail-avatar" :style="{ backgroundColor: selected.color }">{{ selected.initials }}<span class="avatar-corner">✳</span></div>
          <div class="detail-id">SOURCE ID / {{ selected.uid.toUpperCase() }}</div>
          <h2>{{ selected.name }}</h2><p class="detail-bio">{{ selected.bio }}</p>
          <div class="tags"><span v-for="name in selectedGroups" :key="name">{{ name }}</span><span v-if="!selectedGroups.length">未分组</span></div>
          <div class="detail-divider"></div>
          <div class="detail-section-title"><span>近期内容</span><small>演示资料 / 无真实链接</small></div>
          <div class="tab-bar" role="tablist" aria-label="内容类型">
            <button type="button" role="tab" :aria-selected="activeTab === 'videos'" :class="{ active: activeTab === 'videos' }" @click="chooseTab('videos')">视频投稿 <span>{{ selected.video_count }}</span></button>
            <button type="button" role="tab" :aria-selected="activeTab === 'dynamics'" :class="{ active: activeTab === 'dynamics' }" @click="chooseTab('dynamics')">最新动态 <span>{{ selected.dynamic_count }}</span></button>
          </div>
          <div v-if="contentError" class="state error-state" role="alert"><strong>内容读取失败</strong><span>{{ contentError }}</span><button type="button" @click="loadContent(contentOffset, contentOffset > 0)">重试</button></div>
          <div v-else-if="contentLoading && !content" class="state compact">正在读取演示内容…</div>
          <div v-else-if="content && !content.items.length" class="state compact">此创作者暂无演示{{ activeTab === 'videos' ? '视频' : '动态' }}。</div>
          <div v-else class="content-list">
            <article v-for="item in content?.items ?? []" :key="item.id" class="content-item">
              <div class="content-type"><span class="content-dot"></span> {{ activeTab === 'videos' ? '视频投稿' : '文字动态' }} <time :datetime="item.published_at">{{ formatDate(item.published_at) }}</time></div>
              <h3 v-if="activeTab === 'videos'">{{ (item as Video).title }}</h3><p v-else>{{ (item as Dynamic).text }}</p>
              <div class="content-foot"><span>{{ activeTab === 'videos' ? duration((item as Video).duration_seconds) + ' · 合成内容' : '合成内容 · 不可跳转' }}</span><span aria-hidden="true">↗</span></div>
            </article>
          </div>
          <button v-if="content?.pagination.has_more" class="detail-more" type="button" :disabled="contentLoading" @click="loadContent(contentOffset + PAGE_SIZE, true)">{{ contentLoading ? '加载中…' : '查看更多' }} ↓</button>
        </template>
        <template v-else>
          <div class="detail-label"><span>创作者档案</span><span>PROFILE / —</span></div>
          <div class="empty-illustration" aria-hidden="true"><span>◌</span><i></i><b>✳</b></div>
          <div class="empty-number">SELECT / 01</div><h2 class="empty-heading">从一个 UP 主<br />开始探索。</h2>
          <p class="empty-description">在左侧选择创作者，查看其演示视频与动态。真实账号读取还没有接入。</p>
          <div class="empty-rule"></div><span class="empty-foot">观察 · 整理 · 再决定</span>
        </template>
      </aside>
    </main>
    <footer class="app-footer"><span>UP源台 · PERSONAL SOURCE DESK</span><span>此页面仅供交互与架构验证，不包含真实 B 站数据。</span><span>2026 / DEMO 01</span></footer>
  </div>
</template>
