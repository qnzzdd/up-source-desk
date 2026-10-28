<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ApiFailure, friendlyError, get } from './api'
import type { Account, Dynamic, Group, Page, Source, Video } from './api'

type ContentKind = 'videos' | 'dynamics'
type ViewKind = 'overview' | 'followings' | 'groups'

const account = ref<Account | null>(null)
const groups = ref<Group[]>([])
const list = ref<Page<Source> | null>(null)
const selected = ref<Source | null>(null)
const content = ref<Page<Video | Dynamic> | null>(null)
const groupId = ref<string | null>(null)
const search = ref('')
const activeTab = ref<ContentKind>('videos')
const activeView = ref<ViewKind>('overview')
const listLoading = ref(false)
const contentLoading = ref(false)
const listError = ref('')
const contentError = ref('')
const shellError = ref('')
const liveMessage = ref('')
const liveChecking = ref(false)
const listOffset = ref(0)
const contentOffset = ref(0)
const navOpen = ref(false)
let listRevision = 0
let contentRevision = 0
let searchTimer: ReturnType<typeof setTimeout> | undefined
const PAGE_SIZE = 5

const currentGroupName = computed(() => groups.value.find(group => group.id === groupId.value)?.name ?? '全部关注')
const selectedGroups = computed(() => selected.value?.group_ids.map(id => groups.value.find(group => group.id === id)?.name).filter(Boolean) ?? [])
const pageMeta = computed(() => {
  if (activeView.value === 'followings') {
    return { title: '关注列表', description: '检索关注的 UP 主，查看合成视频与动态数据。' }
  }
  if (activeView.value === 'groups') {
    return { title: '分组管理', description: '查看本地演示分组，并快速筛选对应创作者。' }
  }
  return { title: '工作台概览', description: '从关注关系开始，整理一份清晰的内容工作区。' }
})

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function duration(seconds: number): string {
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`
}

function openView(view: ViewKind) {
  activeView.value = view
  navOpen.value = false
}

function openGroup(id: string | null) {
  chooseGroup(id)
  activeView.value = 'followings'
  navOpen.value = false
}

function onGroupSelect(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  chooseGroup(value || null)
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
  if (liveChecking.value) return
  liveChecking.value = true
  liveMessage.value = ''
  try {
    await get('account', { mode: 'live' })
    liveMessage.value = '真实接口返回成功，请继续核验返回身份。'
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
  <svg class="icon-sprite" aria-hidden="true">
    <symbol id="icon-home" viewBox="0 0 24 24">
      <path d="M3.5 10.5 12 3l8.5 7.5v8.2a1.8 1.8 0 0 1-1.8 1.8H5.3a1.8 1.8 0 0 1-1.8-1.8z" />
      <path d="M9.2 20.5v-6.3h5.6v6.3" />
    </symbol>
    <symbol id="icon-list" viewBox="0 0 24 24">
      <path d="M8.5 6h11M8.5 12h11M8.5 18h11" />
      <path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" />
    </symbol>
    <symbol id="icon-folder" viewBox="0 0 24 24">
      <path d="M3.5 7.2a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.6a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
      <path d="M3.8 9.7h16.4" />
    </symbol>
    <symbol id="icon-menu" viewBox="0 0 24 24">
      <path d="M4 7h16M4 12h16M4 17h16" />
    </symbol>
    <symbol id="icon-close" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18" />
    </symbol>
    <symbol id="icon-shield" viewBox="0 0 24 24">
      <path d="M12 3.2 19 6v5.3c0 4.4-2.8 7.7-7 9.5-4.2-1.8-7-5.1-7-9.5V6z" />
      <path d="m8.8 12 2.1 2.1 4.4-4.4" />
    </symbol>
    <symbol id="icon-user" viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="3.4" />
      <path d="M5.5 20c.6-3.2 3-5.2 6.5-5.2s5.9 2 6.5 5.2" />
    </symbol>
    <symbol id="icon-users" viewBox="0 0 24 24">
      <circle cx="9.2" cy="8.6" r="3" />
      <path d="M3.8 19c.4-2.8 2.3-4.6 5.4-4.6s5 1.8 5.4 4.6" />
      <path d="M15 5.7a3 3 0 0 1 0 5.8M16.5 14.7c2 .5 3.3 2 3.7 4.3" />
    </symbol>
    <symbol id="icon-search" viewBox="0 0 24 24">
      <circle cx="10.7" cy="10.7" r="6.2" />
      <path d="m15.4 15.4 4.1 4.1" />
    </symbol>
    <symbol id="icon-chevron" viewBox="0 0 24 24">
      <path d="m9 6 6 6-6 6" />
    </symbol>
    <symbol id="icon-play" viewBox="0 0 24 24">
      <rect x="3.5" y="5" width="17" height="14" rx="3" />
      <path d="m10 9 5 3-5 3z" />
    </symbol>
    <symbol id="icon-message" viewBox="0 0 24 24">
      <path d="M5 4.5h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-8l-4.5 3v-3H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2Z" />
      <path d="M7.5 9h9M7.5 12.5h6" />
    </symbol>
    <symbol id="icon-refresh" viewBox="0 0 24 24">
      <path d="M19.6 8.2A8 8 0 1 0 20 14" />
      <path d="M19.5 3.8v4.6h-4.6" />
    </symbol>
    <symbol id="icon-database" viewBox="0 0 24 24">
      <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
      <path d="M4.5 5.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
      <path d="M4.5 11.5v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" />
    </symbol>
    <symbol id="icon-arrow" viewBox="0 0 24 24">
      <path d="M5 12h14M14 7l5 5-5 5" />
    </symbol>
    <symbol id="icon-check" viewBox="0 0 24 24">
      <path d="m5 12.5 4.2 4.2L19 7" />
    </symbol>
    <symbol id="icon-lock" viewBox="0 0 24 24">
      <rect x="5" y="10" width="14" height="10" rx="2.5" />
      <path d="M8.2 10V7.8a3.8 3.8 0 0 1 7.6 0V10" />
    </symbol>
  </svg>

  <div class="app-frame">
    <header class="topbar">
      <div class="topbar-inner">
        <button class="menu-toggle" type="button" aria-controls="primary-nav" :aria-expanded="navOpen" aria-label="打开导航菜单" @click="navOpen = true">
          <svg class="icon" aria-hidden="true"><use href="#icon-menu" /></svg>
        </button>
        <div class="brand" aria-label="UP源台 UP Source Desk">
          <span class="brand-mark" aria-hidden="true">UP</span>
          <span class="brand-copy"><strong>UP源台</strong><small>UP SOURCE DESK</small></span>
        </div>
        <div class="topbar-right">
          <span class="environment-label"><i aria-hidden="true"></i> 本地演示环境</span>
          <span class="topbar-divider" aria-hidden="true"></span>
          <span class="topbar-mode">READ ONLY</span>
        </div>
      </div>
    </header>

    <div class="demo-banner" role="status" aria-label="合成演示数据提示">
      <div class="demo-banner-inner">
        <span class="demo-icon" aria-hidden="true"><svg class="icon"><use href="#icon-shield" /></svg></span>
        <div class="demo-copy">
          <strong>合成演示数据</strong>
          <span>未登录 B 站，当前关注、分组、视频和动态均为本地合成样例。</span>
        </div>
        <span class="demo-badge">DEMO ONLY</span>
      </div>
    </div>

    <div class="app-body">
      <button v-if="navOpen" class="nav-backdrop" type="button" aria-label="关闭导航菜单" @click="navOpen = false"></button>
      <aside id="primary-nav" class="sidebar" :class="{ 'mobile-open': navOpen }" aria-label="主导航">
        <div class="sidebar-mobile-head">
          <span>导航</span>
          <button type="button" aria-label="关闭导航菜单" @click="navOpen = false">
            <svg class="icon" aria-hidden="true"><use href="#icon-close" /></svg>
          </button>
        </div>

        <div class="account-card">
          <span class="account-avatar" aria-hidden="true">
            <svg class="icon"><use href="#icon-user" /></svg>
          </span>
          <span class="account-copy">
            <small>演示账号 · 未连接 B 站</small>
            <strong>{{ account?.name ?? '演示工作台' }}</strong>
          </span>
        </div>

        <div v-if="shellError" class="shell-error" role="alert">
          <span>{{ shellError }}</span>
          <button type="button" @click="loadShell">重试</button>
        </div>

        <div class="sidebar-section-label">工作台</div>
        <nav class="primary-nav" aria-label="工作台页面">
          <button type="button" :class="{ active: activeView === 'overview' }" :aria-current="activeView === 'overview' ? 'page' : undefined" @click="openView('overview')">
            <svg class="icon" aria-hidden="true"><use href="#icon-home" /></svg>
            <span>概览</span>
          </button>
          <button type="button" :class="{ active: activeView === 'followings' }" :aria-current="activeView === 'followings' ? 'page' : undefined" @click="openView('followings')">
            <svg class="icon" aria-hidden="true"><use href="#icon-list" /></svg>
            <span>关注列表</span>
            <span class="nav-count">{{ account?.following_count ?? '—' }}</span>
          </button>
          <button type="button" :class="{ active: activeView === 'groups' }" :aria-current="activeView === 'groups' ? 'page' : undefined" @click="openView('groups')">
            <svg class="icon" aria-hidden="true"><use href="#icon-folder" /></svg>
            <span>分组管理</span>
            <span class="nav-count">{{ account?.group_count ?? '—' }}</span>
          </button>
        </nav>

        <div class="sidebar-section-row">
          <span class="sidebar-section-label">关注分组</span>
          <span class="sidebar-total">{{ groups.length }} 组</span>
        </div>
        <nav class="group-nav" aria-label="关注分组筛选">
          <button type="button" :class="{ active: groupId === null }" :aria-current="groupId === null ? 'page' : undefined" @click="openGroup(null)">
            <span class="group-icon all" aria-hidden="true"><svg class="icon"><use href="#icon-users" /></svg></span>
            <span class="group-name">全部关注</span>
            <span class="group-count">{{ account?.following_count ?? '—' }}</span>
          </button>
          <button v-for="group in groups" :key="group.id" type="button" :class="{ active: groupId === group.id }" :aria-current="groupId === group.id ? 'page' : undefined" @click="openGroup(group.id)">
            <span class="group-icon" aria-hidden="true"><svg class="icon"><use href="#icon-folder" /></svg></span>
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ group.member_count }}</span>
          </button>
        </nav>

        <div class="sidebar-note">
          <svg class="icon" aria-hidden="true"><use href="#icon-lock" /></svg>
          <div><strong>只读工作区</strong><span>当前版本不会登录、同步或写入真实账号。</span></div>
        </div>
      </aside>

      <main class="main" aria-labelledby="page-title">
        <div class="page-head">
          <div class="page-heading">
            <span class="eyebrow">UP SOURCE DESK / {{ activeView === 'overview' ? '01' : activeView === 'followings' ? '02' : '03' }}</span>
            <h1 id="page-title">{{ pageMeta.title }}</h1>
            <p>{{ pageMeta.description }}</p>
          </div>
          <div class="page-context" aria-live="polite">
            <span class="context-label">当前分组</span>
            <strong>{{ currentGroupName }}</strong>
          </div>
        </div>

        <section v-if="activeView === 'overview'" class="onboarding-hero" aria-labelledby="onboarding-title">
          <div class="hero-copy">
            <span class="hero-kicker">开始使用</span>
            <h2 id="onboarding-title">把关注内容，收进一个清晰的工作台。</h2>
            <p>先用合成数据熟悉关注列表、分组筛选和内容浏览。真实账号接入将在后续版本提供。</p>
            <button class="primary-button" type="button" @click="openView('followings')">
              查看关注列表
              <svg class="icon" aria-hidden="true"><use href="#icon-arrow" /></svg>
            </button>
          </div>
          <ol class="step-list" aria-label="开始使用步骤">
            <li>
              <span class="step-number">01</span>
              <div class="step-copy">
                <div><strong>连接 B 站账号</strong><span class="step-status unavailable">暂不可用</span></div>
                <p>当前版本不提供登录、扫码或账号绑定。</p>
              </div>
            </li>
            <li :class="{ ready: Boolean(account && groups.length) }">
              <span class="step-number">02</span>
              <div class="step-copy">
                <div><strong>读取关注与分组</strong><span class="step-status">{{ shellError ? '读取失败' : account ? '演示数据已就绪' : '读取中' }}</span></div>
                <p>仅从本地 API 读取合成关注关系，不同步 B 站。</p>
              </div>
            </li>
            <li>
              <span class="step-number">03</span>
              <div class="step-copy">
                <div><strong>浏览 UP 主内容</strong><span class="step-status">可立即体验</span></div>
                <p>选择创作者，在视频与动态之间独立切换。</p>
              </div>
            </li>
          </ol>
        </section>

        <section v-if="activeView === 'overview'" class="stats-grid" aria-label="工作区数据概览">
          <article class="stat-card">
            <span class="stat-icon blue" aria-hidden="true"><svg class="icon"><use href="#icon-users" /></svg></span>
            <span class="stat-label">已关注创作者</span>
            <strong>{{ account?.following_count ?? '—' }}</strong>
            <span class="stat-note">来自合成账号</span>
          </article>
          <article class="stat-card">
            <span class="stat-icon sky" aria-hidden="true"><svg class="icon"><use href="#icon-folder" /></svg></span>
            <span class="stat-label">已有分组</span>
            <strong>{{ account?.group_count ?? '—' }}</strong>
            <span class="stat-note">当前筛选：{{ currentGroupName }}</span>
          </article>
          <article class="stat-card">
            <span class="stat-icon mint" aria-hidden="true"><svg class="icon"><use href="#icon-database" /></svg></span>
            <span class="stat-label">当前列表</span>
            <strong>{{ list?.pagination.total ?? '—' }}</strong>
            <span class="stat-note">本地 SQLite · 只读演示</span>
          </article>
        </section>

        <div class="page-layout">
          <div class="primary-column">
            <section v-if="activeView === 'groups'" class="panel groups-panel" aria-labelledby="groups-title">
              <div class="panel-head">
                <div>
                  <span class="section-kicker">分组目录</span>
                  <h2 id="groups-title">查看你的关注分组</h2>
                  <p>选择分组后会带着筛选条件进入关注列表。</p>
                </div>
                <span class="count-pill">{{ groups.length }} 个分组</span>
              </div>
              <div class="read-only-notice">
                <svg class="icon" aria-hidden="true"><use href="#icon-lock" /></svg>
                <span>当前为只读演示，暂不支持新建、编辑或同步分组。</span>
              </div>
              <div class="group-grid">
                <button type="button" class="group-card all-groups" @click="openGroup(null)">
                  <span class="group-card-icon" aria-hidden="true"><svg class="icon"><use href="#icon-users" /></svg></span>
                  <span class="group-card-copy"><small>未筛选</small><strong>全部关注</strong><span>{{ account?.following_count ?? '—' }} 位创作者</span></span>
                  <span class="group-card-action">查看列表 <svg class="icon" aria-hidden="true"><use href="#icon-arrow" /></svg></span>
                </button>
                <button v-for="group in groups" :key="group.id" type="button" class="group-card" @click="openGroup(group.id)">
                  <span class="group-card-icon" aria-hidden="true"><svg class="icon"><use href="#icon-folder" /></svg></span>
                  <span class="group-card-copy"><small>本地分组</small><strong>{{ group.name }}</strong><span>{{ group.member_count }} 位创作者</span></span>
                  <span class="group-card-action">筛选查看 <svg class="icon" aria-hidden="true"><use href="#icon-arrow" /></svg></span>
                </button>
              </div>
              <div v-if="shellError" class="state error-state" role="alert">
                <strong>分组暂时无法读取</strong>
                <span>{{ shellError }}</span>
                <button type="button" @click="loadShell">重试读取</button>
              </div>
            </section>

            <template v-else>
              <div class="data-workspace">
                <section class="panel list-panel" aria-labelledby="source-list-title">
                  <div class="panel-head">
                    <div>
                      <span class="section-kicker">关注数据</span>
                      <h2 id="source-list-title">{{ currentGroupName }}</h2>
                      <p>{{ groupId ? '当前分组内的合成创作者' : '全部合成关注创作者' }}</p>
                    </div>
                    <span class="count-pill">{{ list?.pagination.total ?? '—' }} 位</span>
                  </div>

                  <div class="list-toolbar">
                    <label class="search-field" for="source-search">
                      <svg class="icon" aria-hidden="true"><use href="#icon-search" /></svg>
                      <span class="sr-only">搜索关注的 UP 主</span>
                      <input id="source-search" v-model="search" type="search" placeholder="搜索名称或简介" autocomplete="off" />
                    </label>
                    <label class="select-field" for="group-filter">
                      <span class="sr-only">筛选关注分组</span>
                      <select id="group-filter" :value="groupId ?? ''" @change="onGroupSelect">
                        <option value="">全部分组</option>
                        <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
                      </select>
                      <svg class="icon" aria-hidden="true"><use href="#icon-chevron" /></svg>
                    </label>
                  </div>

                  <div class="list-meta">
                    <span>{{ search ? '搜索结果' : '按名称浏览' }}</span>
                    <span>{{ list?.items.length ?? 0 }} / {{ list?.pagination.total ?? '—' }} 条已显示</span>
                  </div>

                  <div v-if="listError" class="state error-state" role="alert">
                    <strong>列表暂时无法读取</strong>
                    <span>{{ listError }}</span>
                    <button type="button" @click="loadList(listOffset, listOffset > 0)">重试读取</button>
                  </div>
                  <div v-else-if="listLoading && !list" class="state loading-state" role="status">
                    <span class="spinner" aria-hidden="true"></span>
                    <span>正在整理关注列表…</span>
                  </div>
                  <div v-else-if="list && !list.items.length" class="state">
                    <span class="empty-icon" aria-hidden="true"><svg class="icon"><use href="#icon-search" /></svg></span>
                    <strong>这里还没有内容</strong>
                    <span>{{ search ? '试试其他关键词。' : '这个演示分组目前没有创作者。' }}</span>
                  </div>
                  <div v-else class="source-list">
                    <button
                      v-for="(source, index) in list?.items ?? []"
                      :key="source.uid"
                      type="button"
                      class="source-row"
                      :class="{ selected: selected?.uid === source.uid }"
                      :aria-label="`查看 ${source.name} 的视频和动态`"
                      @click="selectSource(source)"
                    >
                      <span class="row-index">{{ String(index + 1).padStart(2, '0') }}</span>
                      <span class="source-avatar" :style="{ backgroundColor: source.color }">{{ source.initials }}</span>
                      <span class="source-copy">
                        <strong>{{ source.name }}</strong>
                        <small>{{ source.bio }}</small>
                      </span>
                      <span class="source-metric"><strong>{{ source.video_count }}</strong><small>视频</small></span>
                      <svg class="row-chevron icon" aria-hidden="true"><use href="#icon-chevron" /></svg>
                    </button>
                  </div>
                  <button v-if="list?.pagination.has_more" class="load-more" type="button" :disabled="listLoading" @click="loadList(listOffset + PAGE_SIZE, true)">
                    {{ listLoading ? '加载中…' : '继续加载创作者' }}
                    <svg class="icon" aria-hidden="true"><use href="#icon-refresh" /></svg>
                  </button>
                </section>

                <section class="panel detail-panel" aria-labelledby="detail-title">
                  <template v-if="selected">
                    <div class="detail-profile">
                      <span class="detail-avatar" :style="{ backgroundColor: selected.color }">{{ selected.initials }}</span>
                      <div class="detail-heading">
                        <span class="section-kicker">UP 主详情</span>
                        <h2 id="detail-title">{{ selected.name }}</h2>
                        <p>{{ selected.bio }}</p>
                      </div>
                    </div>
                    <div class="detail-id">SOURCE ID / {{ selected.uid.toUpperCase() }}</div>
                    <div class="tag-row">
                      <span v-for="name in selectedGroups" :key="name">{{ name }}</span>
                      <span v-if="!selectedGroups.length">未分组</span>
                    </div>
                    <div class="detail-section-title">
                      <span>近期内容</span>
                      <small>合成资料 · 无真实链接</small>
                    </div>
                    <div class="tab-bar" role="tablist" aria-label="内容类型">
                      <button type="button" role="tab" :aria-selected="activeTab === 'videos'" :class="{ active: activeTab === 'videos' }" @click="chooseTab('videos')">
                        <svg class="icon" aria-hidden="true"><use href="#icon-play" /></svg>
                        视频投稿 <span>{{ selected.video_count }}</span>
                      </button>
                      <button type="button" role="tab" :aria-selected="activeTab === 'dynamics'" :class="{ active: activeTab === 'dynamics' }" @click="chooseTab('dynamics')">
                        <svg class="icon" aria-hidden="true"><use href="#icon-message" /></svg>
                        最新动态 <span>{{ selected.dynamic_count }}</span>
                      </button>
                    </div>
                    <div class="detail-content" role="tabpanel">
                      <div v-if="contentError" class="state error-state" role="alert">
                        <strong>内容读取失败</strong>
                        <span>{{ contentError }}</span>
                        <button type="button" @click="loadContent(contentOffset, contentOffset > 0)">重试</button>
                      </div>
                      <div v-else-if="contentLoading && !content" class="state loading-state compact" role="status">
                        <span class="spinner" aria-hidden="true"></span>
                        <span>正在读取演示内容…</span>
                      </div>
                      <div v-else-if="content && !content.items.length" class="state compact">
                        <span class="empty-icon" aria-hidden="true"><svg class="icon"><use href="#icon-database" /></svg></span>
                        <span>此创作者暂无演示{{ activeTab === 'videos' ? '视频' : '动态' }}。</span>
                      </div>
                      <div v-else class="content-list">
                        <article v-for="item in content?.items ?? []" :key="item.id" class="content-item">
                          <div class="content-type">
                            <span class="content-dot" aria-hidden="true"></span>
                            {{ activeTab === 'videos' ? '视频投稿' : (item as Dynamic).kind === 'video' ? '视频动态' : '文字动态' }}
                            <time :datetime="item.published_at">{{ formatDate(item.published_at) }}</time>
                          </div>
                          <h3 v-if="activeTab === 'videos'">{{ (item as Video).title }}</h3>
                          <p v-else>{{ (item as Dynamic).text }}</p>
                          <div class="content-foot">
                            <span>{{ activeTab === 'videos' ? duration((item as Video).duration_seconds) + ' · 合成内容' : '合成内容 · 不可跳转' }}</span>
                            <span class="content-lock"><svg class="icon" aria-hidden="true"><use href="#icon-lock" /></svg> 只读</span>
                          </div>
                        </article>
                      </div>
                    </div>
                    <button v-if="content?.pagination.has_more" class="detail-more" type="button" :disabled="contentLoading" @click="loadContent(contentOffset + PAGE_SIZE, true)">
                      {{ contentLoading ? '加载中…' : '查看更多' }}
                      <svg class="icon" aria-hidden="true"><use href="#icon-arrow" /></svg>
                    </button>
                  </template>
                  <template v-else>
                    <div class="detail-empty">
                      <span class="empty-orbit" aria-hidden="true">
                        <svg class="icon"><use href="#icon-user" /></svg>
                      </span>
                      <span class="section-kicker">UP 主详情</span>
                      <h2 id="detail-title">选择一个 UP 主</h2>
                      <p>从左侧关注列表中选择创作者，查看其合成视频和动态。</p>
                      <span class="empty-hint">视频与动态可独立切换</span>
                    </div>
                  </template>
                </section>
              </div>
            </template>
          </div>

          <aside class="right-rail" aria-label="连接状态与快捷操作">
            <section class="rail-card connection-card">
              <div class="rail-card-head">
                <span class="rail-icon" aria-hidden="true"><svg class="icon"><use href="#icon-shield" /></svg></span>
                <div><h2>连接状态</h2><p>真实账号尚未接入</p></div>
              </div>
              <div class="status-list">
                <div><span>数据模式</span><strong class="status-demo"><i aria-hidden="true"></i> 合成演示</strong></div>
                <div><span>账号状态</span><strong>未连接</strong></div>
                <div><span>写入权限</span><strong>只读</strong></div>
                <div><span>本地存储</span><strong>SQLite</strong></div>
              </div>
              <button class="secondary-button full-width" type="button" :disabled="liveChecking" @click="checkLive">
                <svg class="icon" aria-hidden="true"><use href="#icon-refresh" /></svg>
                {{ liveChecking ? '检查中…' : '检查真实接口' }}
              </button>
              <p v-if="liveMessage" class="live-feedback" role="status">{{ liveMessage }}</p>
              <p class="rail-note">真实接口失败时不会回填为演示成功，也不会改变当前合成数据。</p>
            </section>

            <section class="rail-card actions-card">
              <div class="rail-card-head compact-head">
                <span class="rail-icon light" aria-hidden="true"><svg class="icon"><use href="#icon-list" /></svg></span>
                <div><h2>快捷操作</h2><p>在当前只读工作区内移动</p></div>
              </div>
              <button class="action-row" type="button" @click="openView('followings')">
                <span><svg class="icon" aria-hidden="true"><use href="#icon-users" /></svg> 浏览关注列表</span>
                <svg class="icon" aria-hidden="true"><use href="#icon-arrow" /></svg>
              </button>
              <button class="action-row" type="button" @click="openView('groups')">
                <span><svg class="icon" aria-hidden="true"><use href="#icon-folder" /></svg> 查看分组目录</span>
                <svg class="icon" aria-hidden="true"><use href="#icon-arrow" /></svg>
              </button>
              <div class="action-note">
                <svg class="icon" aria-hidden="true"><use href="#icon-check" /></svg>
                <span>支持搜索、分组筛选、分页和内容切换。</span>
              </div>
            </section>
          </aside>
        </div>
      </main>
    </div>

    <footer class="app-footer">
      <span>UP源台 · UP SOURCE DESK</span>
      <span>本地只读演示 · 不包含真实 B 站数据</span>
      <span>DEMO / 2026</span>
    </footer>
  </div>
</template>
