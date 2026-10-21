export type Category = {
  name: string
  icon: string
  color: string
  desc: string
}

export type PaymentMethod = {
  name: string
  color: string
  desc: string
}

export type TxItem = { name: string; price: number }

export const KIND_LABELS = { expense: '支出', income: '收入', refund: '退款', transfer: '转账', repayment: '信用还款', lend: '借出', borrow: '借入', collection: '收回垫款', loan_repayment: '归还借款', deposit: '押金' } as const
export type TransactionKind = keyof typeof KIND_LABELS
export type Budget = { id: number; month: string; category: string; event: string; label: string; amount: number; spent: number; remaining: number; percent: number }
export type Preference = { payment_method: string; rules: Record<string, string> }

export type Transaction = {
  id: number
  amount: number
  kind: TransactionKind
  personalAmount: number
  recoverableAmount: number
  settledAmount: number
  outstandingAmount: number
  refundedAmount: number
  settlementKind: string
  counterparty: string
  relatedId: number | null
  transferTo: string
  expenseAmount: number
  cashFlow: number
  currency: string
  category: string
  categoryColor: string
  merchant: string
  note: string
  paymentMethod: string
  paymentColor: string
  remark: string
  items: TxItem[]
  occurredAt: string
  date: string
  source: string
  event: string
  hasImage: boolean
}

export type GroupStat = { label: string; value: number }

export type Stats = {
  count: number
  total: number
  income: number
  balance: number
  cash_flow: number
  outstanding: number
  payable: number
  display_total: number
  metric: string
  average: number
  max: number
  first_date: string | null
  last_date: string | null
  by_category: GroupStat[]
  by_event: GroupStat[]
  by_payment: GroupStat[]
  groups: GroupStat[]
  group_by: string
}

export type MessagePayload = {
  kind?: 'record' | 'clarify' | 'query' | 'chat' | 'error' | 'update' | 'delete' | 'undo' | 'duplicate' | 'budget' | 'preference' | 'compare' | 'export'
  related?: Transaction[]
  budgets?: Budget[]
  month?: string
  preference?: Preference
  download?: string
  retry?: { text: string; imageIds: string[] }
  choices?: { label: string; text: string }[]
  comparison?: { start: string; end: string; total: number; delta: number; categories: GroupStat[] }
  transactions?: Transaction[]
  deleted?: Transaction[]
  stats?: Stats
  query?: Record<string, unknown>
  relaxed?: boolean
  missing?: string[]
  images?: string[]
  image?: string
  /** 查询命中的时间范围（服务端解析后的结果），用于卡片标题 */
  range?: { start?: string | null; end?: string | null }
  /** 命中超过 40 笔时，未展示的条数 */
  truncated?: number
  /** 修改/删除没定位到目标时，给出最近几笔供用户点选 */
  candidates?: Transaction[]
  found?: boolean
}

export type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  payload: MessagePayload
  createdAt: string
  pending?: boolean
}

export type PeriodStats = {
  period: string
  label: string
  start: string
  end: string
  current: Stats & { days: number; daily_average: number }
  previous: Stats & { start: string; end: string }
  change_pct: number
  daily: { date: string; value: number }[]
  recent: Transaction[]
  today_total: number
}

export type Report = {
  period: string
  label: string
  start: string
  end: string
  stats: Stats
  previous_total: number
  change_pct: number
  monthly: GroupStat[]
  daily: { date: string; value: number }[]
  top_transactions: Transaction[]
  events: GroupStat[]
}

export type Insight = {
  headline: string
  points: string[]
  tip: string
}

/** 应用可能挂在 /jizhang/ 这类子路径下，接口地址要跟着 base 走 */
export const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '')

/** 本地日期（不要用 toISOString，那个是 UTC，跨零点会差一天） */
function localDate(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: init?.body && !(init.body instanceof FormData) ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  })
  if (res.status === 401) {
    throw Object.assign(new Error('unauthorized'), { code: 401 })
  }
  if (!res.ok) {
    let detail = '请求失败'
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  login: (password: string) =>
    request<{ ok: boolean }>('/api/login', {
      method: 'POST',
      body: JSON.stringify({ username: 'me', password }),
    }),
  logout: () => request<{ ok: boolean }>('/api/logout', { method: 'POST' }),
  me: () => request<{ id: number; username: string }>('/api/me'),
  meta: () =>
    request<{
      categories: Category[]
      payments: PaymentMethod[]
      today: string
      app: string
      appName: string
      appNameEn: string
      tagline: string
      description: string
    }>('/api/meta'),

  messages: () => request<{ messages: ChatMessage[] }>('/api/messages'),
  clearMessages: () => request<{ ok: boolean }>('/api/messages', { method: 'DELETE' }),
  chat: (text: string, imageIds: string[] = [], confirmDuplicate = false) =>
    request<{ reply: string; payload: MessagePayload }>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        text,
        image_ids: imageIds,
        local_date: localDate(),
        confirm_duplicate: confirmDuplicate,
      }),
    }),

  upload: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ image_id: string; url: string }>('/api/upload', { method: 'POST', body: form })
  },

  stats: (period: string, opts: { anchor?: string; start?: string; end?: string } = {}) => {
    const q = new URLSearchParams({ period })
    if (opts.anchor) q.set('anchor', opts.anchor)
    if (opts.start) q.set('start', opts.start)
    if (opts.end) q.set('end', opts.end)
    return request<PeriodStats>(`/api/stats?${q.toString()}`)
  },
  report: (period: string, opts: { anchor?: string; start?: string; end?: string } = {}) => {
    const q = new URLSearchParams({ period })
    if (opts.anchor) q.set('anchor', opts.anchor)
    if (opts.start) q.set('start', opts.start)
    if (opts.end) q.set('end', opts.end)
    return request<Report>(`/api/report?${q.toString()}`)
  },
  insight: (period: string, opts: { anchor?: string; start?: string; end?: string } = {}) =>
    request<{ insight: Insight }>('/api/insight', {
      method: 'POST',
      body: JSON.stringify({ period, anchor: opts.anchor, start: opts.start, end: opts.end }),
    }),

  transactions: (params: {
    limit?: number
    month?: string
    keyword?: string
    event?: string
    start?: string
    end?: string
    payment?: string
    offset?: number
    kind?: string
    pending?: boolean
  } = {}) => {
    const q = new URLSearchParams()
    if (params.limit) q.set('limit', String(params.limit))
    if (params.month) q.set('month', params.month)
    if (params.keyword) q.set('keyword', params.keyword)
    if (params.event) q.set('event', params.event)
    if (params.start) q.set('start', params.start)
    if (params.end) q.set('end', params.end)
    if (params.payment) q.set('payment', params.payment)
    if (params.offset) q.set('offset', String(params.offset))
    if (params.kind) q.set('kind', params.kind)
    if (params.pending) q.set('pending', 'true')
    return request<{ items: Transaction[]; total: number; stats: Stats }>(`/api/transactions?${q.toString()}`)
  },
  updateTransaction: (id: number, patch: Partial<Transaction>) =>
    request<{ item: Transaction }>(`/api/transactions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(
        Object.fromEntries(
          Object.entries(patch).map(([key, value]) => [{ paymentMethod: 'payment_method', personalAmount: 'personal_amount', recoverableAmount: 'recoverable_amount', settlementKind: 'settlement_kind', transferTo: 'transfer_to' }[key] || key, value]),
        ),
      ),
    }),
  deleteTransaction: (id: number) =>
    request<{ ok: boolean }>(`/api/transactions/${id}`, { method: 'DELETE' }),
  createTransaction: (input: {
    amount: number
    category: string
    merchant?: string
    note?: string
    payment_method?: string
    remark?: string
    occurred_at?: string
    kind?: TransactionKind
    personal_amount?: number
    recoverable_amount?: number
    counterparty?: string
  }) =>
    request<{ item: Transaction }>('/api/transactions', { method: 'POST', body: JSON.stringify(input) }),
  undo: () => request<{ items: Transaction[]; deleted_ids: number[] }>('/api/undo', { method: 'POST' }),
  relatedTransaction: (id: number, action: 'refund' | 'settle', amount?: number) => request<{ reply: string; payload: MessagePayload }>(`/api/transactions/${id}/${action}`, { method: 'POST', body: JSON.stringify({ amount }) }),
  budgets: (month: string) => request<{ items: Budget[]; month: string }>(`/api/budgets?month=${month}`),
  saveBudget: (input: { month: string; category: string; event: string; amount: number }) => request<{ items: Budget[] }>('/api/budgets', { method: 'PUT', body: JSON.stringify(input) }),
  deleteBudget: (id: number) => request('/api/budgets/' + id, { method: 'DELETE' }),
  preferences: () => request<Preference>('/api/preferences'),
  savePreferences: (preference: Preference) => request<Preference>('/api/preferences', { method: 'PUT', body: JSON.stringify(preference) }),
}
