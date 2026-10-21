import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, BASE, KIND_LABELS, type Stats, type PaymentMethod, type Transaction } from '../api'
import { TransactionCard } from './TransactionCard'
import { fmtDateLabel, fmtMoney, groupByDate } from '../utils'
import { IconChevron } from '../icons'
import { QuickEntry } from './QuickEntry'

type Props = {
  categories: string[]
  payments: PaymentMethod[]
  refreshKey: number
  onChanged: () => void
}

type Mode = 'day' | 'month' | 'year' | 'custom'

const MODES: { key: Mode; label: string }[] = [
  { key: 'day', label: '日' },
  { key: 'month', label: '月' },
  { key: 'year', label: '年' },
  { key: 'custom', label: '区间' },
]

function todayISO(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function shift(date: string, mode: Mode, delta: number): string {
  const [y, m, d = 1] = date.split('-').map(Number)
  if (mode === 'day') {
    const next = new Date(y, m - 1, d + delta)
    return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-${String(next.getDate()).padStart(2, '0')}`
  }
  if (mode === 'year') return `${y + delta}-01-01`
  const next = new Date(y, m - 1 + delta, 1)
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}-01`
}

function defaultAnchor(mode: Mode): string {
  const today = todayISO()
  if (mode === 'year') return `${today.slice(0, 4)}-01-01`
  if (mode === 'month') return `${today.slice(0, 7)}-01`
  return today
}

function labelFor(anchor: string, mode: Mode): string {
  const [y, m, d] = anchor.split('-')
  if (mode === 'year') return `${y}年`
  if (mode === 'month') return `${y}年${Number(m)}月`
  return `${Number(m)}月${Number(d)}日`
}

export function BillsPanel({ categories, payments, refreshKey, onChanged }: Props) {
  const [mode, setMode] = useState<Mode>('month')
  const [anchor, setAnchor] = useState(() => defaultAnchor('month'))
  const [rangeStart, setRangeStart] = useState(() => `${todayISO().slice(0, 7)}-01`)
  const [rangeEnd, setRangeEnd] = useState(todayISO)
  const [items, setItems] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [keyword, setKeyword] = useState('')
  const [paymentFilter, setPaymentFilter] = useState('')

  const [kindFilter, setKindFilter] = useState('')
  const [pendingOnly, setPendingOnly] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [count, setCount] = useState(0)
  const [error, setError] = useState('')
  const [showEntry, setShowEntry] = useState(false)
  const version = useRef(0)
  const params = useMemo<NonNullable<Parameters<typeof api.transactions>[0]>>(() => ({
    ...(mode === 'custom' ? { start: rangeStart, end: rangeEnd } : mode === 'year' ? { start: `${anchor.slice(0, 4)}-01-01`, end: `${anchor.slice(0, 4)}-12-31` } : mode === 'day' ? { start: anchor, end: anchor } : { month: anchor.slice(0, 7) }),
    keyword, payment: paymentFilter, kind: kindFilter, pending: pendingOnly, limit: 100,
  }), [mode, anchor, rangeStart, rangeEnd, keyword, paymentFilter, kindFilter, pendingOnly])
  const load = useCallback(async () => {
    const id = ++version.current
    setLoading(true); setError('')
    try {
      const result = await api.transactions(params)
      if (id !== version.current) return
      setItems(result.items); setStats(result.stats); setCount(result.total)
    } catch (err) { if (id === version.current) setError(err instanceof Error ? err.message : '加载失败') }
    finally { if (id === version.current) setLoading(false) }
  }, [params])
  useEffect(() => { void load(); return () => { version.current++ } }, [load, refreshKey])
  const more = async () => {
    const id = version.current
    setLoading(true)
    try { const result = await api.transactions({ ...params, offset: items.length }); if (id === version.current) setItems(prev => [...prev, ...result.items]) }
    catch (err) { setError(err instanceof Error ? err.message : '加载失败') }
    finally { if (id === version.current) setLoading(false) }
  }
  const filtered = items
  const groups = groupByDate(filtered)
  const total = stats?.total ?? 0
  const isCurrent = mode === 'custom' ? rangeEnd >= todayISO() : anchor === defaultAnchor(mode)
  const exportParams = new URLSearchParams()
  if (params.month) { const [y,m] = params.month.split('-').map(Number); const last = new Date(y,m,0).getDate(); exportParams.set('start', `${params.month}-01`); exportParams.set('end', `${params.month}-${last}`) }
  if (params.start) exportParams.set('start', params.start)
  if (params.end) exportParams.set('end', params.end)
  if (keyword) exportParams.set('keyword', keyword)
  if (paymentFilter) exportParams.set('payment_method', paymentFilter)
  if (kindFilter) exportParams.set('kinds', kindFilter)
  if (pendingOnly) exportParams.set('pending', 'true')
  const update = async (id: number, patch: Record<string, unknown>) => {
    const result = await api.updateTransaction(id, patch as never)
    setItems((prev) => prev.map((item) => (item.id === id ? result.item : item)))
    void load()
    onChanged()
  }

  const remove = async (id: number) => {
    await api.deleteTransaction(id)
    setItems((prev) => prev.filter((item) => item.id !== id))
    void load()
    onChanged()
  }

  const changeMode = (next: Mode) => {
    setMode(next)
    if (next !== 'custom') setAnchor(defaultAnchor(next))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between px-1"><span className="text-[14px] font-medium">收支账单</span><div className="flex gap-3 text-[12px] text-ink-500"><a href={`${BASE}/api/export?${exportParams}`} download>导出 CSV</a><button onClick={() => setShowEntry(v => !v)}>{showEntry ? '收起' : '手动记一笔'}</button></div></div>
      {showEntry && <QuickEntry categories={categories} payments={payments.map(p => p.name)} onDone={() => { setShowEntry(false); void load(); onChanged() }} />}
      {error && <div role="alert" className="rounded-xl bg-red-50 p-3 text-[12px] text-red-600">{error}</div>}
      <div className="card p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 text-[12px] text-ink-400">
              <span className="truncate">
                {mode === 'custom' ? `${rangeStart.slice(5)} 至 ${rangeEnd.slice(5)}` : labelFor(anchor, mode)}
              </span>
              <span>个人净支出</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="font-num text-3xl font-semibold tracking-tight tabular-nums">¥{fmtMoney(total)}</span>
              <span className="text-[12px] text-ink-400">{count} 笔</span>
            </div>
          </div>
          <div className="inline-flex shrink-0 rounded-full bg-ink-100 p-0.5">
            {MODES.map((item) => (
              <button
                key={item.key}
                onClick={() => changeMode(item.key)}
                className={`rounded-full px-2 py-1 text-[11.5px] font-medium transition ${
                  mode === item.key ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {mode !== 'custom' ? (
          <div className="mt-2 flex items-center justify-end gap-1">
            <button
              onClick={() => setAnchor((value) => shift(value, mode, -1))}
              className="flex h-7 w-7 items-center justify-center rounded-full text-ink-400 hover:bg-ink-50 hover:text-ink-800"
            >
              <IconChevron width={15} height={15} className="rotate-180" />
            </button>
            <button
              onClick={() => setAnchor((value) => shift(value, mode, 1))}
              disabled={isCurrent}
              className="flex h-7 w-7 items-center justify-center rounded-full text-ink-400 hover:bg-ink-50 hover:text-ink-800 disabled:opacity-30"
            >
              <IconChevron width={15} height={15} />
            </button>
          </div>
        ) : (
          <div className="mt-3 flex items-center gap-1.5">
            <input
              type="date"
              value={rangeStart}
              max={rangeEnd}
              onChange={(event) => setRangeStart(event.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-ink-200 px-2 py-1.5 text-[12px] text-ink-800 outline-none focus:border-ink-900"
            />
            <span className="shrink-0 text-[11px] text-ink-300">至</span>
            <input
              type="date"
              value={rangeEnd}
              min={rangeStart}
              max={todayISO()}
              onChange={(event) => setRangeEnd(event.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-ink-200 px-2 py-1.5 text-[12px] text-ink-800 outline-none focus:border-ink-900"
            />
          </div>
        )}

        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜商户、备注、商品名"
          className="mt-3 w-full rounded-xl bg-ink-50 px-3 py-2 text-[13px] text-ink-800 outline-none placeholder:text-ink-300 focus:bg-ink-100/70"
        />

        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-ink-50 pt-3 text-[12px]"><div className="text-ink-400">收入 <span className="ml-1 font-num text-emerald-600">¥{fmtMoney(stats?.income ?? 0)}</span></div><div className="text-ink-400">收支结余 <span className="ml-1 font-num text-ink-800">¥{fmtMoney(stats?.balance ?? 0)}</span></div></div>
        <div className="mt-3 flex flex-wrap gap-2">
          <select aria-label="账务类型筛选" value={kindFilter} onChange={e => setKindFilter(e.target.value)} className="rounded-lg bg-ink-50 px-2 py-1.5 text-[12px]"><option value="">全部类型</option>{Object.entries(KIND_LABELS).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select>
          <select aria-label="付款方式筛选" value={paymentFilter} onChange={e => setPaymentFilter(e.target.value)} className="rounded-lg bg-ink-50 px-2 py-1.5 text-[12px]"><option value="">全部付款方式</option>{payments.map(p => <option key={p.name}>{p.name}</option>)}</select>
          <label className="flex items-center gap-1 text-[12px] text-ink-500"><input type="checkbox" checked={pendingOnly} onChange={e => setPendingOnly(e.target.checked)} />只看待结清</label>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-ink-400">净支出按个人承担减退款计算；转账、借还款及回款分别记录。统计包含筛选范围内全部账单。</p>
      </div>

      {loading && <div className="py-10 text-center text-[13px] text-ink-300">加载中…</div>}

      {!loading && groups.length === 0 && (
        <div className="py-14 text-center">
          <div className="text-[13px] text-ink-400">这段时间还没有记录</div>
          <div className="mt-1 text-[12px] text-ink-300">回到对话说一句「午饭 28」试试</div>
        </div>
      )}

      {groups.map((group) => (
        <div key={group.date} className="space-y-2">
          <div className="flex items-baseline justify-between px-1">
            <span className="text-[12px] font-medium text-ink-500">{fmtDateLabel(group.date)}</span>
            <span className="font-num text-[11px] tabular-nums text-ink-300">
              ¥{fmtMoney(group.items.reduce((sum, item) => sum + item.expenseAmount, 0))}
            </span>
          </div>
          <div className="space-y-1.5">
            {group.items.map((tx) => (
              <TransactionCard
                key={tx.id}
                tx={tx}
                categories={categories}
                payments={payments.map((item) => item.name)}
                onUpdate={update}
                onDelete={remove}
                onChanged={() => { void load(); onChanged() }}
              />
            ))}
          </div>
        </div>
      ))}
      {items.length < count && <button disabled={loading} onClick={() => void more()} className="w-full rounded-xl border border-ink-100 py-3 text-[12px] text-ink-500 disabled:opacity-40">{loading ? '加载中…' : `加载更多（已显示${items.length}/${count}笔）`}</button>}
    </div>
  )
}
