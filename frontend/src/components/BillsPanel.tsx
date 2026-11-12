import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, BASE, KIND_LABELS, type PaymentMethod, type PeriodStats, type Stats, type Transaction } from '../api'
import { TransactionCard } from './TransactionCard'
import { QuickEntry } from './QuickEntry'
import { FilterChip } from './FilterChip'
import { EmptyState } from './EmptyState'
import { StatsNote } from './StatsNote'
import { UndoToast } from './UndoToast'
import { Amount } from './Amount'
import { periodLabel, rangeOf, type Period } from './PeriodPicker'
import { readQuery, updateQuery } from '../urlState'
import { fmtDateLabel, fmtMoney, groupByDate } from '../utils'
import { IconClose, IconInbox } from '../icons'

type Props = {
  period: Period
  categories: string[]
  payments: PaymentMethod[]
  refreshKey: number
  onChanged: () => void
}

const KIND_OPTIONS = Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }))

/**
 * 流水视图。
 * 顶部大数字是「整个周期的净支出」，来自 /api/stats，不随筛选变化；
 * 筛选命中的小计单独一行——之前两者混用同一个数字，搜个关键词总额就缩水。
 */
export function BillsPanel({ period, categories, payments, refreshKey, onChanged }: Props) {
  const [initialQuery] = useState(readQuery)
  const [items, setItems] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [keywordInput, setKeywordInput] = useState(initialQuery.get('q') ?? '')
  const [keyword, setKeyword] = useState(initialQuery.get('q') ?? '')
  const [paymentFilter, setPaymentFilter] = useState(initialQuery.get('pay') ?? '')
  const [kindFilter, setKindFilter] = useState(initialQuery.get('kind') ?? '')
  const [pendingOnly, setPendingOnly] = useState(initialQuery.get('pending') === '1')
  const [categoryFilter, setCategoryFilter] = useState(initialQuery.get('cat') ?? '')
  const [stats, setStats] = useState<Stats | null>(null)
  const [overview, setOverview] = useState<PeriodStats | null>(null)
  const [count, setCount] = useState(0)
  const [error, setError] = useState('')
  const [showEntry, setShowEntry] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<{ id: number } | null>(null)
  const version = useRef(0)
  const timerRef = useRef<number | null>(null)
  const pendingRef = useRef<{ id: number } | null>(null)
  pendingRef.current = pendingDelete

  const range = rangeOf(period)
  const params = useMemo(
    () => ({
      start: range.start,
      end: range.end,
      keyword,
      category: categoryFilter,
      payment: paymentFilter,
      kind: kindFilter,
      pending: pendingOnly,
      limit: 100,
    }),
    [range.start, range.end, keyword, categoryFilter, paymentFilter, kindFilter, pendingOnly],
  )

  const load = useCallback(async () => {
    const id = ++version.current
    setLoading(true)
    setError('')
    try {
      const result = await api.transactions(params)
      if (id !== version.current) return
      setItems(result.items)
      setStats(result.stats)
      setCount(result.total)
    } catch (err) {
      if (id === version.current) setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      if (id === version.current) setLoading(false)
    }
  }, [params])

  useEffect(() => {
    void load()
    return () => {
      version.current++
    }
  }, [load, refreshKey])

  // 周期总额单独取一次 /api/stats：它不看搜索和筛选，是页面上唯一「稳定的那个数」
  useEffect(() => {
    let alive = true
    api
      .stats(period.mode, period.mode === 'custom' ? { start: period.start, end: period.end } : { anchor: period.anchor })
      .then((data) => {
        if (alive) setOverview(data)
      })
      .catch(() => {
        /* 总额取不到不影响列表 */
      })
    return () => {
      alive = false
    }
  }, [period.mode, period.anchor, period.start, period.end, refreshKey])

  // 搜索防抖：之前每敲一个字都会打一次接口
  useEffect(() => {
    const timer = window.setTimeout(() => setKeyword(keywordInput.trim()), 320)
    return () => window.clearTimeout(timer)
  }, [keywordInput])

  // 筛选与视图写进地址栏，刷新/分享都能回到同一屏
  useEffect(() => {
    updateQuery({
      q: keyword || null,
      kind: kindFilter || null,
      pay: paymentFilter || null,
      cat: categoryFilter || null,
      pending: pendingOnly ? '1' : null,
    })
  }, [keyword, kindFilter, paymentFilter, categoryFilter, pendingOnly])

  const commitDelete = useCallback(async () => {
    const target = pendingRef.current
    if (!target) return
    pendingRef.current = null
    setPendingDelete(null)
    if (timerRef.current) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    try {
      await api.deleteTransaction(target.id)
    } catch {
      /* 删除失败时刷新列表，这一笔会重新出现 */
    }
    void load()
    onChanged()
  }, [load, onChanged])

  // 删除延迟 5 秒提交：这段时间点「撤销」等于什么都没发生
  const remove = useCallback(
    async (id: number) => {
      if (pendingRef.current) await commitDelete()
      setItems((prev) => prev.filter((item) => item.id !== id))
      pendingRef.current = { id }
      setPendingDelete({ id })
      timerRef.current = window.setTimeout(() => void commitDelete(), 5000)
    },
    [commitDelete],
  )

  const undo = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = null
    pendingRef.current = null
    setPendingDelete(null)
    void load()
  }, [load])

  // 离开页面时把未到期的删除落地，避免「看着删了其实还在」
  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current)
      if (pendingRef.current) void api.deleteTransaction(pendingRef.current.id)
    },
    [],
  )

  const more = async () => {
    const id = version.current
    setLoading(true)
    try {
      const result = await api.transactions({ ...params, offset: items.length })
      if (id === version.current) setItems((prev) => [...prev, ...result.items])
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      if (id === version.current) setLoading(false)
    }
  }

  const update = async (id: number, patch: Record<string, unknown>) => {
    const result = await api.updateTransaction(id, patch as never)
    setItems((prev) => prev.map((item) => (item.id === id ? result.item : item)))
    void load()
    onChanged()
  }

  const groups = groupByDate(items)
  const filtersActive = Boolean(keyword || kindFilter || paymentFilter || pendingOnly || categoryFilter)

  const clearFilters = () => {
    setKeywordInput('')
    setKeyword('')
    setKindFilter('')
    setPaymentFilter('')
    setCategoryFilter('')
    setPendingOnly(false)
  }

  const exportParams = new URLSearchParams({ start: range.start, end: range.end })
  if (keyword) exportParams.set('keyword', keyword)
  if (categoryFilter) exportParams.set('category', categoryFilter)
  if (paymentFilter) exportParams.set('payment_method', paymentFilter)
  if (kindFilter) exportParams.set('kinds', kindFilter)
  if (pendingOnly) exportParams.set('pending', 'true')

  const change = overview?.change_pct ?? 0

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 px-1 text-[12px]">
        <span className="text-ink-500">{filtersActive ? `筛选命中 ${count} 笔` : ''}</span>
        <div className="flex items-center gap-3">
          <a href={`${BASE}/api/export?${exportParams}`} download className="text-ink-500 hover:text-ink-800">
            导出 CSV
          </a>
          <button onClick={() => setShowEntry((value) => !value)} className="font-medium text-accent-700">
            {showEntry ? '收起' : '手动记一笔'}
          </button>
        </div>
      </div>

      {showEntry && (
        <QuickEntry
          categories={categories}
          payments={payments.map((item) => item.name)}
          onDone={() => {
            setShowEntry(false)
            void load()
            onChanged()
          }}
        />
      )}

      {error && <div role="alert" className="rounded-xl bg-red-50 p-3 text-[12px] text-red-600">{error}</div>}

      <div className="card p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[12px] text-ink-500">{periodLabel(period)}净支出</div>
            <div className="mt-1 flex items-baseline gap-2">
              <Amount value={overview?.current.total ?? 0} size={30} />
              <span className="text-[12px] text-ink-500">{overview?.current.count ?? 0} 笔</span>
            </div>
            {overview && overview.current.count > 0 && (
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[12px] text-ink-500">
                <span>均 ¥{fmtMoney(overview.current.average)}</span>
                {change !== 0 && (
                  <span
                    className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-medium ${
                      change > 0 ? 'bg-red-50 text-red-500' : 'bg-emerald-50 text-emerald-600'
                    }`}
                  >
                    {change > 0 ? '较上期 +' : '较上期 −'}
                    {Math.abs(change)}%
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="shrink-0 space-y-0.5 text-right text-[12px]">
            <div className="text-ink-500">
              收入 <span className="font-num font-medium text-emerald-600">¥{fmtMoney(overview?.current.income ?? 0)}</span>
            </div>
            <div className="text-ink-500">
              结余 <span className="font-num font-medium text-ink-900">¥{fmtMoney(overview?.current.balance ?? 0)}</span>
            </div>
          </div>
        </div>

        <div className="relative mt-3">
          <input
            value={keywordInput}
            onChange={(event) => setKeywordInput(event.target.value)}
            placeholder="搜商户、备注、商品名"
            aria-label="搜索流水"
            className="w-full rounded-xl bg-ink-50 py-2 pl-3 pr-8 text-[13px] text-ink-800 placeholder:text-ink-400 focus:bg-white focus:ring-1 focus:ring-ink-200"
          />
          {keywordInput && (
            <button
              onClick={() => setKeywordInput('')}
              aria-label="清空搜索"
              className="absolute right-2 top-1/2 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full text-ink-400 hover:bg-ink-100"
            >
              <IconClose width={12} height={12} />
            </button>
          )}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {categoryFilter && (
            <button
              onClick={() => setCategoryFilter('')}
              className="flex items-center gap-1 rounded-full bg-accent-50 px-2.5 py-1.5 text-[12px] font-medium text-accent-700 ring-1 ring-accent-200"
            >
              {categoryFilter}
              <IconClose width={11} height={11} />
            </button>
          )}
          <FilterChip label="全部类型" value={kindFilter} options={KIND_OPTIONS} onChange={setKindFilter} />
          <FilterChip
            label="全部付款方式"
            value={paymentFilter}
            options={payments.map((item) => ({ value: item.name, label: item.name }))}
            onChange={setPaymentFilter}
          />
          <button
            onClick={() => setPendingOnly((value) => !value)}
            aria-pressed={pendingOnly}
            className={`rounded-full px-2.5 py-1.5 text-[12px] font-medium transition ${
              pendingOnly ? 'bg-accent-50 text-accent-700 ring-1 ring-accent-200' : 'bg-ink-50 text-ink-600 hover:bg-ink-100'
            }`}
          >
            只看待结清
          </button>
          {filtersActive && (
            <button onClick={clearFilters} className="ml-auto text-[11px] text-ink-500 hover:text-ink-800">
              清空筛选
            </button>
          )}
        </div>

        {filtersActive && (
          <div className="mt-2 flex items-center justify-between rounded-lg bg-ink-50 px-2.5 py-1.5 text-[12px]">
            <span className="text-ink-600">
              筛选结果合计 <b className="font-num text-ink-900">¥{fmtMoney(stats?.total ?? 0)}</b>
            </span>
            <span className="text-ink-500">{stats?.count ?? 0} 笔</span>
          </div>
        )}

        <div className="mt-2 border-t border-ink-50 pt-2">
          <StatsNote
            items={[
              '净支出 = 个人承担 − 当期退款；代垫、借还款与账户转账不计入。',
              '顶部数字按整个周期统计，不随搜索和筛选变化；筛选命中另算「筛选结果合计」。',
              '环比对比前一个等长周期。',
            ]}
          />
        </div>
      </div>

      {loading && items.length === 0 && <div className="py-10 text-center text-[13px] text-ink-500">加载中…</div>}

      {!loading && groups.length === 0 && (
        filtersActive ? (
          <EmptyState
            icon={<IconInbox width={20} height={20} />}
            title="没有匹配的记录"
            hint="换个关键词，或清空筛选看看这个周期的全部流水"
            action={{ label: '清空筛选', onClick: clearFilters }}
          />
        ) : (
          <EmptyState
            icon={<IconInbox width={20} height={20} />}
            title="这段时间还没有记录"
            hint="回到对话说一句「午饭 28」，或者点上面的手动记一笔"
          />
        )
      )}

      {groups.map((group) => (
        <div key={group.date} className="space-y-1.5">
          <div className="flex items-baseline justify-between px-1">
            <span className="text-[12px] font-medium text-ink-500">{fmtDateLabel(group.date)}</span>
            <span className="font-num text-[11px] tabular-nums text-ink-400">
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
                onChanged={() => {
                  void load()
                  onChanged()
                }}
              />
            ))}
          </div>
        </div>
      ))}

      {items.length < count && (
        <button
          disabled={loading}
          onClick={() => void more()}
          className="w-full rounded-xl border border-ink-100 py-3 text-[12px] text-ink-500 disabled:opacity-40"
        >
          {loading ? '加载中…' : `加载更多（已显示 ${items.length}/${count} 笔）`}
        </button>
      )}

      {pendingDelete && <UndoToast message="已删除 1 笔流水" onUndo={undo} />}
    </div>
  )
}
