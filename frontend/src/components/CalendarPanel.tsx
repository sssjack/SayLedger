import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, KIND_LABELS, type CalendarDay, type CalendarDayDetail } from '../api'
import { holidayOf, isHolidayStart } from '../holidays'
import { fmtMoney } from '../utils'

type Props = { refreshKey: number }

const pad = (value: number) => String(value).padStart(2, '0')
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
const thisMonth = () => today().slice(0, 7)
const shiftMonth = (month: string, delta: number) => {
  const [y, m] = month.split('-').map(Number)
  const d = new Date(y, m - 1 + delta, 1)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

/** 某天的两行数字：支出为净支出（支出 − 退款），退款大于支出时折进收入行。 */
function dayLines(day: CalendarDay | undefined): { spend: number; earn: number } {
  if (!day) return { spend: 0, earn: 0 }
  const spend = day.expense > 0 ? day.expense : 0
  const earn = day.income + (day.expense < 0 ? -day.expense : 0)
  return { spend, earn }
}

function txSignedAmount(tx: { kind: string; personalAmount: number; amount: number }): number {
  const value = tx.personalAmount ?? tx.amount
  if (tx.kind === 'expense') return -value
  if (tx.kind === 'income' || tx.kind === 'refund') return value
  return 0
}

function memoFired(memo: { status: string; lastSentAt: string | null }, date: string): boolean {
  return memo.status === 'done' || (memo.lastSentAt?.startsWith(date) ?? false)
}

function memoTime(memo: { nextTriggerAt: string; lastSentAt: string | null }, date: string): string {
  const fired = memo.lastSentAt?.startsWith(date) ?? false
  const raw = fired ? (memo.lastSentAt ?? '') : memo.nextTriggerAt
  return raw.slice(11, 16)
}

export function CalendarPanel({ refreshKey }: Props) {
  const [month, setMonth] = useState(thisMonth)
  const [days, setDays] = useState<CalendarDay[]>([])
  const [selected, setSelected] = useState(today())
  const [detail, setDetail] = useState<CalendarDayDetail | null>(null)
  const [loadingMonth, setLoadingMonth] = useState(true)
  const [loadingDay, setLoadingDay] = useState(false)
  const [error, setError] = useState('')

  const loadMonth = useCallback(async () => {
    setError('')
    setLoadingMonth(true)
    try {
      const result = await api.calendar(month)
      setDays(result.days)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoadingMonth(false)
    }
  }, [month])
  useEffect(() => { void loadMonth() }, [loadMonth, refreshKey])

  const loadDay = useCallback(async (date: string) => {
    setLoadingDay(true)
    try {
      setDetail(await api.calendarDay(date))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoadingDay(false)
    }
  }, [])
  useEffect(() => {
    if (selected) void loadDay(selected)
    else setDetail(null)
  }, [selected, loadDay])

  const goMonth = (delta: number) => {
    const next = shiftMonth(month, delta)
    setMonth(next)
    // 切到当月默认选中今天，切到别的月先不选，等用户点某一天
    setSelected(next === thisMonth() ? today() : '')
  }

  const dayMap = useMemo(() => new Map(days.map((d) => [d.date, d])), [days])

  const weeks = useMemo(() => {
    const [y, m] = month.split('-').map(Number)
    const offset = (new Date(y, m - 1, 1).getDay() + 6) % 7 // 周一起算
    const count = new Date(y, m, 0).getDate()
    const cells: (number | null)[] = [...Array(offset).fill(null), ...Array.from({ length: count }, (_, i) => i + 1)]
    while (cells.length % 7 !== 0) cells.push(null)
    const out: (number | null)[][] = []
    for (let i = 0; i < cells.length; i += 7) out.push(cells.slice(i, i + 7))
    return out
  }, [month])

  const monthTotals = useMemo(() => {
    let spend = 0
    let earn = 0
    for (const day of days) {
      const lines = dayLines(day)
      spend += lines.spend
      earn += lines.earn
    }
    return { spend, earn }
  }, [days])

  const [year, monthNum] = month.split('-').map(Number)
  const todayStr = today()
  const selectedHoliday = selected ? holidayOf(selected) : undefined

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="flex items-center justify-between">
          <button
            onClick={() => goMonth(-1)}
            className="rounded-lg px-3 py-1.5 text-[13px] font-medium text-ink-600 hover:bg-ink-50"
          >
            ‹ 上月
          </button>
          <div className="text-[15px] font-semibold text-ink-900">{year}年{monthNum}月</div>
          <button
            onClick={() => goMonth(1)}
            className="rounded-lg px-3 py-1.5 text-[13px] font-medium text-ink-600 hover:bg-ink-50"
          >
            下月 ›
          </button>
        </div>
        <div className="mt-1 flex items-center justify-center gap-3 text-[12px] text-ink-500">
          <span>支出 <span className="font-num font-semibold text-red-500">-{fmtMoney(monthTotals.spend)}</span></span>
          <span>收入 <span className="font-num font-semibold text-emerald-600">+{fmtMoney(monthTotals.earn)}</span></span>
          {month !== thisMonth() && (
            <button
              onClick={() => { setMonth(thisMonth()); setSelected(today()) }}
              className="font-medium text-ink-700 underline underline-offset-2"
            >
              回到本月
            </button>
          )}
        </div>
        <div className="mt-1 text-center text-[11px] text-ink-500">
          <span className="mr-1 rounded bg-red-100 px-1 py-px font-medium text-red-600">春节</span>
          法定节假日
          <span className="ml-3 mr-1 rounded bg-ink-100 px-1 py-px text-ink-500">班</span>
          调休上班
        </div>

        <div className="mt-3 grid grid-cols-7 gap-1 text-center text-[11px] text-ink-500">
          {['一', '二', '三', '四', '五', '六', '日'].map((w) => <div key={w}>{w}</div>)}
        </div>
        {loadingMonth ? (
          <div className="py-8 text-center text-[12px] text-ink-500">加载中…</div>
        ) : (
          <div className="mt-1 space-y-1">
            {weeks.map((week, wi) => (
              <div key={wi} className="grid grid-cols-7 gap-1">
                {week.map((day, di) => {
                  if (day === null) return <div key={di} />
                  const date = `${month}-${pad(day)}`
                  const lines = dayLines(dayMap.get(date))
                  const isToday = date === todayStr
                  const isSelected = date === selected
                  const holiday = holidayOf(date)
                  const holidayLabel = holiday
                    ? holiday.kind === 'workday'
                      ? '班'
                      : isHolidayStart(date)
                        ? holiday.name
                        : '休'
                    : ''
                  return (
                    <button
                      key={di}
                      onClick={() => setSelected(date)}
                      className={`flex min-h-[52px] flex-col items-center rounded-xl px-1 py-1.5 transition ${
                        isSelected ? 'bg-white shadow-card ring-1 ring-ink-900/10' : 'hover:bg-white/70'
                      }`}
                    >
                      <span
                        className={`flex h-5 w-5 items-center justify-center rounded-full text-[13px] ${
                          isToday ? 'bg-ink-900 font-semibold text-white' : 'text-ink-800'
                        }`}
                      >
                        {day}
                      </span>
                      {holiday && (
                        <span
                          className={`mt-0.5 rounded px-1 text-[11px] leading-tight ${
                            holiday.kind === 'holiday'
                              ? 'bg-red-100 font-medium text-red-600'
                              : 'bg-ink-100 text-ink-500'
                          }`}
                        >
                          {holidayLabel}
                        </span>
                      )}
                      {lines.spend > 0 && (
                        <span className="mt-0.5 truncate font-num text-[11px] leading-tight text-red-500">
                          -{fmtMoney(lines.spend)}
                        </span>
                      )}
                      {lines.earn > 0 && (
                        <span className="truncate font-num text-[11px] leading-tight text-emerald-600">
                          +{fmtMoney(lines.earn)}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        )}
        {error && <div className="mt-2 text-[12px] text-red-600">{error}</div>}
      </div>

      {selected ? (
        <div className="card p-4">
          <div className="text-[14px] font-semibold text-ink-900">
            {selected === todayStr ? '今天' : selected} · 账单与提醒
            {selectedHoliday && (
              <span
                className={`ml-2 rounded px-1.5 py-px text-[12px] font-medium ${
                  selectedHoliday.kind === 'holiday'
                    ? 'bg-red-100 text-red-600'
                    : 'bg-ink-100 text-ink-500'
                }`}
              >
                {selectedHoliday.name}
                {selectedHoliday.kind === 'holiday' ? ' · 放假' : ''}
              </span>
            )}
          </div>
          {loadingDay ? (
            <div className="py-4 text-center text-[12px] text-ink-500">加载中…</div>
          ) : detail ? (
            <div className="mt-3 space-y-4">
              <div>
                <div className="text-[12px] font-medium text-ink-500">当天账单</div>
                {detail.transactions.length === 0 ? (
                  <div className="mt-1 text-[13px] text-ink-500">这天还没有账单</div>
                ) : (
                  <ul className="mt-1.5 divide-y divide-ink-100">
                    {detail.transactions.map((tx) => {
                      const signed = txSignedAmount(tx)
                      return (
                        <li key={tx.id} className="flex items-baseline justify-between gap-3 py-1.5">
                          <div className="min-w-0">
                            <div className="truncate text-[13px] text-ink-800">
                              {tx.merchant || tx.note || tx.category}
                            </div>
                            <div className="truncate text-[11px] text-ink-500">
                              {tx.category}
                              {tx.paymentMethod ? ` · ${tx.paymentMethod}` : ''}
                              {tx.occurredAt ? ` · ${tx.occurredAt.slice(11, 16)}` : ''}
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <span
                              className={`font-num text-[13px] font-semibold ${
                                signed < 0 ? 'text-red-500' : signed > 0 ? 'text-emerald-600' : 'text-ink-700'
                              }`}
                            >
                              {signed !== 0 ? fmtMoney(signed, true) : fmtMoney(tx.personalAmount ?? tx.amount)}
                            </span>
                            <div className="text-[11px] text-ink-500">{KIND_LABELS[tx.kind] ?? tx.kind}</div>
                          </div>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
              <div>
                <div className="text-[12px] font-medium text-ink-500">当天提醒</div>
                {detail.memos.length === 0 ? (
                  <div className="mt-1 text-[13px] text-ink-500">这天没有提醒</div>
                ) : (
                  <ul className="mt-1.5 divide-y divide-ink-100">
                    {detail.memos.map((memo) => {
                      const fired = memoFired(memo, selected)
                      return (
                        <li key={memo.id} className="flex items-baseline justify-between gap-3 py-1.5">
                          <div className="min-w-0">
                            <div className="truncate text-[13px] text-ink-800">{memo.content}</div>
                            <div className="truncate text-[11px] text-ink-500">
                              {memoTime(memo, selected)} · {memo.recurrenceLabel}
                            </div>
                          </div>
                          <span
                            className={`shrink-0 text-[12px] font-medium ${
                              fired ? 'text-ink-500' : 'text-amber-600'
                            }`}
                          >
                            {fired ? '已提醒' : '待提醒'}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="card p-4 text-center text-[13px] text-ink-500">
          点一下某一天，下面会列出当天的账单和提醒
        </div>
      )}
    </div>
  )
}
