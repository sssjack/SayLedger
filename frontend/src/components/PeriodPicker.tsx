import { IconChevron } from '../icons'

export type PeriodMode = 'day' | 'month' | 'year' | 'custom'

/** 一个周期 = 模式 + 锚点 + 自定义区间。账单/日历/分析三个视图共用同一份，避免各算各的。 */
export type Period = { mode: PeriodMode; anchor: string; start: string; end: string }

const MODE_LABELS: { key: PeriodMode; label: string }[] = [
  { key: 'day', label: '日' },
  { key: 'month', label: '月' },
  { key: 'year', label: '年' },
  { key: 'custom', label: '区间' },
]

const pad = (value: number) => String(value).padStart(2, '0')

export function todayISO(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function lastDayOfMonth(anchor: string): string {
  const [year, month] = anchor.split('-').map(Number)
  return `${anchor.slice(0, 7)}-${pad(new Date(year, month, 0).getDate())}`
}

export function defaultAnchor(mode: PeriodMode, base = todayISO()): string {
  if (mode === 'month') return `${base.slice(0, 7)}-01`
  if (mode === 'year') return `${base.slice(0, 4)}-01-01`
  return base
}

export function makePeriod(mode: PeriodMode = 'month', base = todayISO()): Period {
  return { mode, anchor: defaultAnchor(mode, base), start: `${base.slice(0, 7)}-01`, end: base }
}

/** 切换模式时把锚点重置到当前周期的起点，和之前两处实现的行为保持一致 */
export function changeMode(period: Period, mode: PeriodMode): Period {
  if (mode === period.mode) return period
  if (mode === 'custom') return { ...period, mode }
  return { ...period, mode, anchor: defaultAnchor(mode) }
}

export function shiftPeriod(period: Period, delta: number): Period {
  const [year, month, day = 1] = period.anchor.split('-').map(Number)
  if (period.mode === 'day') {
    const date = new Date(year, month - 1, day + delta)
    return { ...period, anchor: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` }
  }
  if (period.mode === 'year') return { ...period, anchor: `${year + delta}-01-01` }
  if (period.mode === 'month') {
    const date = new Date(year, month - 1 + delta, 1)
    return { ...period, anchor: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-01` }
  }
  return period
}

export function rangeOf(period: Period): { start: string; end: string } {
  if (period.mode === 'day') return { start: period.anchor, end: period.anchor }
  if (period.mode === 'month') return { start: `${period.anchor.slice(0, 7)}-01`, end: lastDayOfMonth(period.anchor) }
  if (period.mode === 'year') return { start: `${period.anchor.slice(0, 4)}-01-01`, end: `${period.anchor.slice(0, 4)}-12-31` }
  return { start: period.start, end: period.end }
}

export function periodOptions(period: Period): { period: string; anchor?: string; start?: string; end?: string } {
  if (period.mode === 'custom') return { period: 'custom', start: period.start, end: period.end }
  return { period: period.mode, anchor: period.anchor }
}

export function isCurrentPeriod(period: Period): boolean {
  if (period.mode === 'custom') return period.end >= todayISO()
  return period.anchor === defaultAnchor(period.mode)
}

export function periodLabel(period: Period): string {
  const [year, month, day] = period.anchor.split('-').map(Number)
  if (period.mode === 'day') return `${year}年${month}月${day}日`
  if (period.mode === 'year') return `${year}年`
  if (period.mode === 'month') return `${year}年${month}月`
  return `${period.start.slice(5).replace('-', '/')} 至 ${period.end.slice(5).replace('-', '/')}`
}

type Props = {
  period: Period
  onChange: (period: Period) => void
  /** 服务端返回的标签（报告页用它，口径以服务端为准） */
  label?: string
  /** 日历只能按月看，传 ['month'] 就只渲染翻页，不出现日/年/区间 */
  modes?: PeriodMode[]
  className?: string
}

export function PeriodPicker({ period, onChange, label, modes, className = '' }: Props) {
  const tabs = MODE_LABELS.filter((item) => !modes || modes.includes(item.key))
  const single = tabs.length === 1

  return (
    <div className={`space-y-2 ${className}`}>
      <div className="flex items-center justify-between gap-2">
        {!single && (
          <div className="inline-flex shrink-0 rounded-full bg-ink-100 p-0.5" role="tablist" aria-label="统计周期">
            {tabs.map((item) => (
              <button
                key={item.key}
                role="tab"
                aria-selected={period.mode === item.key}
                onClick={() => onChange(changeMode(period, item.key))}
                className={`rounded-full px-3 py-1 text-[12px] font-medium transition ${
                  period.mode === item.key ? 'bg-white text-accent-700 shadow-sm' : 'text-ink-500 hover:text-ink-700'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}

        {period.mode !== 'custom' && (
          <div className={`flex min-w-0 items-center gap-1 ${single ? 'w-full justify-center gap-4' : ''}`}>
            <button
              onClick={() => onChange(shiftPeriod(period, -1))}
              aria-label="上一个周期"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-500 transition hover:bg-white hover:text-ink-800"
            >
              <IconChevron width={16} height={16} className="rotate-180" />
            </button>
            <span className="min-w-0 truncate text-center text-[13px] font-medium text-ink-700">
              {label ?? periodLabel(period)}
            </span>
            <button
              onClick={() => onChange(shiftPeriod(period, 1))}
              disabled={isCurrentPeriod(period)}
              aria-label="下一个周期"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-500 transition hover:bg-white hover:text-ink-800 disabled:opacity-30"
            >
              <IconChevron width={16} height={16} />
            </button>
          </div>
        )}
      </div>

      {period.mode === 'custom' && (
        <div className="card flex flex-wrap items-center gap-2 p-3">
          <input
            type="date"
            aria-label="开始日期"
            value={period.start}
            max={period.end}
            onChange={(event) => onChange({ ...period, start: event.target.value })}
            className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[13px] text-ink-800 focus:border-ink-900"
          />
          <span className="text-[12px] text-ink-500">至</span>
          <input
            type="date"
            aria-label="结束日期"
            value={period.end}
            min={period.start}
            max={todayISO()}
            onChange={(event) => onChange({ ...period, end: event.target.value })}
            className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[13px] text-ink-800 focus:border-ink-900"
          />
          <div className="ml-auto flex gap-1">
            {[
              { label: '近7天', days: 7 },
              { label: '近30天', days: 30 },
              { label: '近90天', days: 90 },
            ].map((preset) => (
              <button
                key={preset.label}
                onClick={() => {
                  const end = new Date()
                  const start = new Date()
                  start.setDate(end.getDate() - (preset.days - 1))
                  const iso = (date: Date) => {
                    const offset = date.getTimezoneOffset() * 60000
                    return new Date(date.getTime() - offset).toISOString().slice(0, 10)
                  }
                  onChange({ ...period, start: iso(start), end: iso(end) })
                }}
                className="rounded-full bg-ink-50 px-2.5 py-1 text-[11px] text-ink-500 transition hover:bg-ink-100 hover:text-ink-800"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
