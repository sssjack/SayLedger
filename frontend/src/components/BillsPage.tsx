import { lazy, Suspense, useEffect, useState } from 'react'
import { BillsPanel } from './BillsPanel'
import { CalendarPanel } from './CalendarPanel'
import { IconCalendar, IconChart, IconList } from '../icons'
import { makePeriod, isCurrentPeriod, PeriodPicker, type Period, type PeriodMode } from './PeriodPicker'
import { readQuery, updateQuery } from '../urlState'
import type { PaymentMethod, Category } from '../api'

const ReportPanel = lazy(() => import('./ReportPanel').then((mod) => ({ default: mod.ReportPanel })))

type View = 'list' | 'calendar' | 'report'

const VIEWS: { key: View; label: string; icon: (props: { width?: number; height?: number }) => JSX.Element }[] = [
  { key: 'list', label: '流水', icon: IconList },
  { key: 'calendar', label: '日历', icon: IconCalendar },
  { key: 'report', label: '分析', icon: IconChart },
]

type Props = {
  categories: Category[]
  payments: PaymentMethod[]
  refreshKey: number
  onChanged: () => void
}

function initialView(query: URLSearchParams): View {
  const raw = query.get('view')
  return raw === 'calendar' || raw === 'report' ? raw : 'list'
}

function initialPeriod(query: URLSearchParams): Period {
  const raw = query.get('period')
  const mode: PeriodMode = raw === 'day' || raw === 'year' || raw === 'custom' ? raw : 'month'
  const base = makePeriod(mode)
  const anchor = query.get('anchor')
  const start = query.get('start')
  const end = query.get('end')
  return {
    mode,
    anchor: anchor || base.anchor,
    start: mode === 'custom' && start ? start : base.start,
    end: mode === 'custom' && end ? end : base.end,
  }
}

/**
 * 账单页：流水 / 日历 / 分析三段。
 * 之前这三个是独立 tab，各自一套时间选择器和统计口径；现在共用一份 period，
 * 「看哪段时间」只需要选一次。
 */
export function BillsPage({ categories, payments, refreshKey, onChanged }: Props) {
  const [initial] = useState(readQuery)
  const [view, setView] = useState<View>(() => initialView(initial))
  const [period, setPeriod] = useState<Period>(() => initialPeriod(initial))

  useEffect(() => {
    const current = isCurrentPeriod(period)
    updateQuery({
      view: view === 'list' ? null : view,
      period: period.mode === 'month' ? null : period.mode,
      anchor: current ? null : period.anchor,
      start: period.mode === 'custom' ? period.start : null,
      end: period.mode === 'custom' ? period.end : null,
    })
  }, [view, period])

  const changeView = (next: View) => {
    setView(next)
    // 日历按月展示，切过去时把周期对齐到当前月，避免出现「选了日却看整月」的错觉
    if (next === 'calendar' && period.mode !== 'month') {
      setPeriod({ ...period, mode: 'month', anchor: `${period.anchor.slice(0, 7)}-01` })
    }
  }

  const month = period.anchor.slice(0, 7)

  return (
    <div className="min-h-0 flex-1">
      <div className="mb-3 flex items-center justify-between gap-2 px-1">
        <h1 className="text-[15px] font-semibold text-ink-900">账单</h1>
        <div className="inline-flex shrink-0 rounded-full bg-ink-100 p-0.5" role="tablist" aria-label="账单视图">
          {VIEWS.map((item) => {
            const Icon = item.icon
            const active = view === item.key
            return (
              <button
                key={item.key}
                role="tab"
                aria-selected={active}
                onClick={() => changeView(item.key)}
                className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-[12px] font-medium transition ${
                  active ? 'bg-white text-accent-700 shadow-sm' : 'text-ink-500 hover:text-ink-700'
                }`}
              >
                <Icon width={13} height={13} />
                {item.label}
              </button>
            )
          })}
        </div>
      </div>

      <PeriodPicker
        period={period}
        onChange={setPeriod}
        modes={view === 'calendar' ? ['month'] : undefined}
        className="mb-3 px-1"
      />

      {view === 'list' && (
        <BillsPanel
          period={period}
          categories={categories.map((item) => item.name)}
          payments={payments}
          refreshKey={refreshKey}
          onChanged={onChanged}
        />
      )}

      {view === 'calendar' && <CalendarPanel month={month} onMonthChange={(next) => setPeriod({ ...period, mode: 'month', anchor: `${next}-01` })} refreshKey={refreshKey} />}

      {view === 'report' && (
        <Suspense fallback={<div className="py-16 text-center text-[13px] text-ink-500">正在加载分析…</div>}>
          <ReportPanel period={period} refreshKey={refreshKey} />
        </Suspense>
      )}
    </div>
  )
}
