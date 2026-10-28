export interface ApiErrorBody { error: { code: string; message: string } }
export interface Page<T> {
  mode: 'demo'
  items: T[]
  pagination: { offset: number; limit: number; total: number; has_more: boolean }
  partial: boolean
  warnings: string[]
}
export interface Account {
  uid: string
  name: string
  auth_state: 'demo'
  following_count: number
  group_count: number
}
export interface Group { id: string; name: string; member_count: number; origin: 'bilibili_demo' }
export interface Source {
  uid: string
  name: string
  bio: string
  initials: string
  color: string
  group_ids: string[]
  video_count: number
  dynamic_count: number
}
export interface Video {
  id: string
  title: string
  published_at: string
  duration_seconds: number
  description: string
  url: null
}
export interface Dynamic {
  id: string
  text: string
  published_at: string
  kind: 'text' | 'video'
  url: null
}

export class ApiFailure extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message)
    this.name = 'ApiFailure'
  }
}

export async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const url = new URL(`/api/${path}`, window.location.origin)
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) url.searchParams.set(key, String(value))
  }
  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' })
  } catch {
    throw new ApiFailure('NETWORK_ERROR', '本地服务暂时无法连接。请确认 FastAPI 已启动。', 0)
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiFailure('INVALID_RESPONSE', '服务返回了无法识别的数据。', response.status)
  }
  if (!response.ok) {
    const error = (body as Partial<ApiErrorBody>)?.error
    throw new ApiFailure(error?.code ?? 'API_ERROR', error?.message ?? '请求失败，请稍后重试。', response.status)
  }
  return body as T
}

export function friendlyError(error: unknown): string {
  return error instanceof ApiFailure ? error.message : '发生了未知错误，请重试。'
}
