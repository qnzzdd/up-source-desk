<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{ accountUid: string }>()

type LocalGroup = { id: string; name: string; source_uids: string[] }
type LocalSource = { uid: string; name: string }
type GroupList = { items: LocalGroup[]; sources: LocalSource[] }
const emit = defineEmits<{ changed: [groups: LocalGroup[]] }>()

const groups = ref<LocalGroup[]>([])
const sources = ref<LocalSource[]>([])
const selectedGroupId = ref('')
const nameInput = ref('')
const sourceQuery = ref('')
const memberSelection = ref<string[]>([])
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const status = ref('')

let revision = 0

const selectedGroup = computed(() => groups.value.find(group => group.id === selectedGroupId.value) ?? null)
const query = computed(() => sourceQuery.value.trim().toLowerCase())
const visibleSources = computed(() => sources.value.filter(source =>
  `${source.name} ${source.uid}`.toLowerCase().includes(query.value)))
const page = ref(1)
const PAGE_SIZE = 20
const pageCount = computed(() => Math.max(1, Math.ceil(visibleSources.value.length / PAGE_SIZE)))
const pagedSources = computed(() => visibleSources.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
const selectedCount = computed(() => {
  const available = new Set(sources.value.map(source => source.uid))
  return memberSelection.value.filter(uid => available.has(uid)).length
})
const cleanName = computed(() => nameInput.value.trim())

function clearLocalData() {
  groups.value = []
  sources.value = []
  selectedGroupId.value = ''
  nameInput.value = ''
  sourceQuery.value = ''
  memberSelection.value = []
  loaded.value = false
  emit('changed', groups.value)
}

function selectGroup(group: LocalGroup | undefined) {
  selectedGroupId.value = group?.id ?? ''
  nameInput.value = group?.name ?? ''
  memberSelection.value = group ? [...group.source_uids] : []
}

function applyList(data: GroupList, keepSelection = true, preferredId = '') {
  groups.value = data.items
  sources.value = data.sources
  const current = keepSelection ? groups.value.find(group => group.id === selectedGroupId.value) : undefined
  selectGroup(groups.value.find(group => group.id === preferredId) ?? current ?? groups.value[0])
  loaded.value = true
  emit('changed', groups.value)
}

async function post(path: string, body: Record<string, unknown> = {}) {
  const response = await fetch(`/api/live/local/${encodeURIComponent(props.accountUid)}/tool-groups${path}`, {
    method: 'POST',
    headers: { 'X-UPDesk-Local': '1', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'error' in data
      ? (data.error as { message?: string; code?: string })
      : null
    throw new Error(`${detail?.code ?? response.status} · ${detail?.message ?? '请求失败'}`)
  }
  return data as GroupList
}

async function load(keepSelection = false) {
  const currentRevision = ++revision
  if (!keepSelection) clearLocalData()
  error.value = ''
  status.value = ''
  busy.value = true
  try {
    const data = await post('', {})
    if (currentRevision !== revision) return
    applyList(data, keepSelection)
    status.value = keepSelection ? '已刷新本机已保存 UP 与本机分组。' : '已读取本机工具分组与已保存 UP。'
  } catch (e) {
    if (currentRevision !== revision) return
    error.value = e instanceof Error ? e.message : '本机分组读取失败'
  } finally {
    if (currentRevision === revision) busy.value = false
  }
}

function refresh() { return load(true) }

watch(() => props.accountUid, (uid) => {
  if (!uid) {
    revision++
    clearLocalData()
    busy.value = false
    error.value = ''
    status.value = ''
    return
  }
  void load()
}, { immediate: true })

watch([sourceQuery, selectedGroupId, () => props.accountUid], () => {
  page.value = 1
})

watch(pageCount, (count) => {
  if (page.value > count) page.value = count
})

onUnmounted(() => { revision++ })

async function mutate(path: string, body: Record<string, unknown>, success: string, keepSelection = true, selectCreated = false) {
  if (busy.value) return
  const currentRevision = revision
  const previousIds = new Set(groups.value.map(group => group.id))
  busy.value = true
  error.value = ''
  status.value = ''
  try {
    const data = await post(path, body)
    if (currentRevision !== revision) return
    const createdId = selectCreated ? (data.items.find(group => !previousIds.has(group.id))?.id ?? '') : ''
    applyList(data, keepSelection, createdId)
    status.value = success
  } catch (e) {
    if (currentRevision !== revision) return
    error.value = e instanceof Error ? e.message : '本机分组保存失败'
  } finally {
    if (currentRevision === revision) busy.value = false
  }
}

function createGroup() {
  if (!cleanName.value) return
  void mutate('/create', { name: cleanName.value }, '本机分组已创建；B站分组未被修改。', true, true)
}

function renameGroup() {
  if (!selectedGroup.value || !cleanName.value) return
  void mutate(`/${encodeURIComponent(selectedGroup.value.id)}/rename`, { name: cleanName.value }, '本机分组名称已更新；B站分组未被修改。')
}

function previousPage() {
  page.value = Math.max(1, page.value - 1)
}

function nextPage() {
  page.value = Math.min(pageCount.value, page.value + 1)
}

function saveMembers() {
  if (!selectedGroup.value) return
  const savedUids = new Set(sources.value.map(source => source.uid))
  const sourceUids = memberSelection.value.filter(uid => savedUids.has(uid))
  void mutate(`/${encodeURIComponent(selectedGroup.value.id)}/members`, { source_uids: sourceUids }, '本机组成员已整组替换；B站分组未被修改。')
}

function deleteGroup() {
  const group = selectedGroup.value
  if (!group || busy.value) return
  const confirmed = window.confirm(`确定删除本机分组“${group.name}”吗？\n\n只删除这台电脑上的本地工具分组；不会删除 B站分组，也不会删除或取关任何已保存 UP。`)
  if (!confirmed) return
  void mutate(`/${encodeURIComponent(group.id)}/delete`, {}, '本机分组已删除；B站分组和已保存 UP 均未被修改。')
}

defineExpose({ refresh })
</script>

<template>
  <section class="local-groups" aria-labelledby="local-groups-title">
    <h2 id="local-groups-title">本地工具分组</h2>
    <p>这里只写入这台电脑的离线工具分组，用来筛选已保存的 UP；B站真实分组不会被创建、改名、删除或改成员。</p>
    <p role="status">{{ busy ? '正在处理本机数据…' : status }}</p>
    <p v-if="error" role="alert" class="local-error">{{ error }}</p>

    <template v-if="accountUid">
      <div class="local-field">
        <label for="local-group-select">选择本机分组</label>
        <select id="local-group-select" v-model="selectedGroupId" :disabled="busy || !groups.length" @change="selectGroup(selectedGroup ?? undefined)">
          <option v-if="!groups.length" value="">暂无本机分组</option>
          <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }} · {{ group.source_uids.length }} 个 UP</option>
        </select>
      </div>

      <div class="local-field">
        <label for="local-group-name">分组名称</label>
        <input id="local-group-name" v-model="nameInput" :disabled="busy" :placeholder="selectedGroup ? '输入新名称' : '输入新分组名称'" />
        <div class="local-actions">
          <button type="button" :disabled="busy || !cleanName" @click="createGroup">新建本机分组</button>
          <button type="button" :disabled="busy || !selectedGroup || !cleanName" @click="renameGroup">重命名</button>
          <button type="button" :disabled="busy || !selectedGroup" @click="deleteGroup">删除本机分组</button>
          <button type="button" :disabled="busy" @click="refresh">刷新已保存 UP 与本机分组</button>
        </div>
      </div>

      <div v-if="loaded" class="local-members">
        <h3>组成员</h3>
        <p v-if="!sources.length">本机还没有已保存 UP，请先在真实账号接入区域保存关注。</p>
        <template v-else>
          <div class="local-field">
            <label for="local-source-search">搜索已保存 UP（只影响显示，不改变勾选）</label>
            <input id="local-source-search" v-model="sourceQuery" :disabled="busy" placeholder="昵称或 UID" />
          </div>
          <p>当前筛选显示 {{ visibleSources.length }} / {{ sources.length }} 个已保存 UP；本页最多 {{ PAGE_SIZE }} 个；已勾选 {{ selectedCount }} 个。搜索或翻页不会取消其他页的勾选。</p>
          <ul id="local-source-page" class="source-list">
            <li v-for="source in pagedSources" :key="source.uid">
              <label>
                <input v-model="memberSelection" type="checkbox" :value="source.uid" :disabled="busy" />
                <span>{{ source.name }} · {{ source.uid }}</span>
              </label>
            </li>
          </ul>
          <nav v-if="visibleSources.length" class="local-pagination" aria-label="已保存 UP 分页">
            <button type="button" aria-controls="local-source-page" :disabled="busy || page <= 1" @click="previousPage">上一页</button>
            <span aria-live="polite" aria-atomic="true">第 {{ page }} / {{ pageCount }} 页 · 每页 {{ PAGE_SIZE }} 个</span>
            <button type="button" aria-controls="local-source-page" :disabled="busy || page >= pageCount" @click="nextPage">下一页</button>
          </nav>
          <p v-if="!visibleSources.length">没有匹配的已保存 UP；当前分组勾选仍保持不变。</p>
          <div class="local-actions">
            <button type="button" :disabled="busy || !selectedGroup" @click="saveMembers">保存组成员</button>
          </div>
          <p>保存会整组替换该本机分组的成员，且只会提交列表返回的已保存 UP。</p>
        </template>
      </div>
    </template>
    <p v-else>等待真实账号 UID，暂不读写本机分组。</p>
  </section>
</template>

<style scoped>
.local-groups{margin:0 0 24px;padding:24px;border:1px solid #bcd8ff;border-radius:24px;background:#fff;color:#20334f;overflow-wrap:anywhere}.local-groups h2{font-size:21px;margin-bottom:12px}.local-groups h3{font-size:17px;margin:18px 0 8px}.local-groups p{line-height:1.8;margin:12px 0}.local-field{display:flex;flex-direction:column;gap:8px;margin:14px 0}.local-field label{margin:0}.local-groups label{display:block;margin:12px 0}.local-groups input,.local-groups select{border:1px solid #c5dbf8;border-radius:12px;padding:10px 14px;background:#f0f7ff;color:#1455a0;max-width:100%}.local-groups input:focus-visible,.local-groups select:focus-visible{outline:3px solid #1778ff}.local-actions{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}.local-actions button,.local-pagination button{border:1px solid #c5dbf8;border-radius:12px;padding:10px 14px;background:#f0f7ff;color:#1455a0}.local-actions button:disabled,.local-pagination button:disabled{opacity:.45;cursor:not-allowed}.local-actions button:focus-visible,.local-pagination button:focus-visible{outline:3px solid #1778ff}.local-pagination{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;margin:12px 0;padding:10px;border:1px solid #dbebfd;border-radius:16px;background:#f8fbff}.local-pagination span{font-weight:600;color:#31557f}.local-error{background:#fff0ef;color:#9b2922;padding:12px;border-radius:12px}.local-members{border-top:1px solid #dbebfd;padding-top:4px}.source-list{list-style:none;padding:0;margin:8px 0}.source-list li{margin:0}.source-list label{display:flex;align-items:center;gap:10px;margin:6px 0;color:#20334f}.source-list input{margin:0}@media (max-width:560px){.local-pagination{justify-content:center}.local-pagination button{flex:1 1 7rem}.local-pagination span{order:-1;flex:1 0 100%;text-align:center}}
</style>
