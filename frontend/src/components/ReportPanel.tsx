import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type Insight, type Report } from '../api'
import { Chart, TOOLTIP_STYLE } from './Chart'
import { fmtMoney } from '../utils'
import { CategoryIcon, IconChevron, IconDown, IconSpark, IconUp } from '../icons'
import { CATEGORY_COLORS } from './MessageBubble'
import { ICON_MAP } from './TransactionCard'

type Period = 'day' | 'month' | 'year' | 'custom'

type Props = {
  refreshKey: number
}

const PERIOD_TABS: { key: Period; label: string }[] = [
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

function shiftAnchor(anchor: string, period: Period, delta: number): string {
  if (period === 'custom') return anchor
  const [y, m, d = 1] = anchor.split('-').map(Number)
  if (period === 'day') {
    const date = new Date(y, m - 1, d + delta)
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  }
  if (period === 'year') return `${y + delta}-01-01`
  const date = new Date(y, m - 1 + delta, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-01`
}

function defaultAnchor(period: Period): string {
  const today = todayISO()
  if (period === 'year') return `${today.slice(0, 4)}-01-01`
  if (period === 'month') return `${today.slice(0, 7)}-01`
  return today
}

export function ReportPanel({ refreshKey }: Props) {
  const [period, setPeriod] = useState<Period>('month')
  const [anchor, setAnchor] = useState(() => defaultAnchor('month'))
  const [rangeStart, setRangeStart] = useState(() => {
    const date = new Date()
    date.setDate(1)
    const offset = date.getTimezoneOffset() * 60000
    return new Date(date.getTime() - offset).toISOString().slice(0, 10)
  })
  const [rangeEnd, setRangeEnd] = useState(todayISO)
  const [report, setReport] = useState<Report | null>(null)
  const [insight, setInsight] = useState<Insight | null>(null)
  const [loading, setLoading] = useState(true)
  const [insightLoading, setInsightLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const opts = period === 'custom' ? { start: rangeStart, end: rangeEnd } : { anchor }
      const data = await api.report(period, opts)
      setReport(data)
      setInsight(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [period, anchor, rangeStart, rangeEnd])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  const fetchInsight = useCallback(async () => {
    setInsightLoading(true)
    try {
      const opts = period === 'custom' ? { start: rangeStart, end: rangeEnd } : { anchor }
      const data = await api.insight(period, opts)
      setInsight(data.insight)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 点评暂时不可用')
    } finally {
      setInsightLoading(false)
    }
  }, [period, anchor, rangeStart, rangeEnd])

  const isCurrent = useMemo(() => {
    if (period === 'custom') return rangeEnd >= todayISO()
    return anchor === defaultAnchor(period)
  }, [anchor, period, rangeEnd])

  const trendOption = useMemo(() => {
    if (!report) return {}
    const useDaily = report.daily.length > 0
    const labels = useDaily
      ? report.daily.map((d) => (period === 'day' ? d.date : d.date.slice(8)))
      : report.monthly.map((m) => `${Number(m.label.slice(5))}月`)
    const values = useDaily ? report.daily.map((d) => d.value) : report.monthly.map((m) => m.value)

    return {
      grid: { left: 8, right: 8, top: 24, bottom: 4, containLabel: true },
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: '#d5d9e2', type: 'dashed' } },
        formatter: (params: { axisValue: string; value: number }[]) =>
          `${useDaily && period !== 'day' ? `${params[0].axisValue}日` : params[0].axisValue}&nbsp;&nbsp;<b>¥${fmtMoney(Number(params[0].value))}</b>`,
      },
      xAxis: {
        type: 'category',
        data: labels,
        boundaryGap: !useDaily,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: '#b0b7c6',
          fontSize: 10,
          interval: useDaily ? Math.max(0, Math.floor(labels.length / 7) - 1) : 0,
        },
      },
      yAxis: { type: 'value', show: false, splitLine: { show: false } },
      series: [
        {
          type: useDaily ? 'line' : 'bar',
          data: values,
          smooth: 0.2,
          showSymbol: report.stats.count <= 12,
          symbolSize: 6,
          lineStyle: { width: 2, color: '#4f46e5' },
          itemStyle: { color: '#4f46e5', borderRadius: [6, 6, 0, 0] },
          areaStyle: useDaily
            ? {
                color: {
                  type: 'linear',
                  x: 0, y: 0, x2: 0, y2: 1,
                  colorStops: [
                    { offset: 0, color: 'rgba(79,70,229,.18)' },
                    { offset: 1, color: 'rgba(79,70,229,0)' },
                  ],
                },
              }
            : undefined,
          barMaxWidth: 24,
        },
      ],
    }
  }, [report, period])

  const donutOption = useMemo(() => {
    if (!report) return {}
    const data = report.stats.by_category.filter((item) => item.value > 0)
    return {
      tooltip: {
        ...TOOLTIP_STYLE,
        trigger: 'item',
        formatter: (p: { name: string; value: number; percent: number }) =>
          `${p.name}&nbsp;&nbsp;<b>¥${fmtMoney(p.value)}</b>&nbsp;&nbsp;${p.percent}%`,
      },
      legend: { show: false },
      series: [
        {
          type: 'pie',
          radius: ['62%', '88%'],
          center: ['50%', '50%'],
          padAngle: 2,
          itemStyle: { borderRadius: 6 },
          label: { show: false },
          emphasis: { scale: true, scaleSize: 4 },
          color: data.map((item) => colorFor(item.label)),
          data: data.map((item) => ({ name: item.label, value: item.value })),
        },
      ],
    }
  }, [report])

  if (error && !report) {
    return <div className="py-16 text-center text-[13px] text-ink-400">{error}</div>
  }

  const changePeriod = (next: Period) => {
    setPeriod(next)
    if (next !== 'custom') setAnchor(defaultAnchor(next))
  }

  return (
    <div className="space-y-3.5">
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex shrink-0 rounded-full bg-ink-100 p-0.5">
          {PERIOD_TABS.map((item) => (
            <button
              key={item.key}
              onClick={() => changePeriod(item.key)}
              className={`rounded-full px-3 py-1 text-[12px] font-medium transition ${
                period === item.key ? 'bg-white text-ink-900 shadow-sm' : 'text-ink-500'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {period !== 'custom' && (
          <div className="flex min-w-0 items-center gap-1">
            <button
              onClick={() => setAnchor((a) => shiftAnchor(a, period, -1))}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-400 transition hover:bg-white hover:text-ink-800"
            >
              <IconChevron width={16} height={16} className="rotate-180" />
            </button>
            <span className="min-w-0 truncate text-center text-[12.5px] font-medium text-ink-700">
              {report?.label ?? '…'}
            </span>
            <button
              onClick={() => setAnchor((a) => shiftAnchor(a, period, 1))}
              disabled={isCurrent}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-ink-400 transition hover:bg-white hover:text-ink-800 disabled:opacity-30"
            >
              <IconChevron width={16} height={16} />
            </button>
          </div>
        )}
      </div>

      {period === 'custom' && (
        <div className="card flex flex-wrap items-center gap-2 p-3">
          <input
            type="date"
            value={rangeStart}
            max={rangeEnd}
            onChange={(event) => setRangeStart(event.target.value)}
            className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[12.5px] text-ink-800 outline-none focus:border-ink-900"
          />
          <span className="text-[12px] text-ink-300">至</span>
          <input
            type="date"
            value={rangeEnd}
            min={rangeStart}
            max={todayISO()}
            onChange={(event) => setRangeEnd(event.target.value)}
            className="rounded-lg border border-ink-200 px-2.5 py-1.5 text-[12.5px] text-ink-800 outline-none focus:border-ink-900"
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
                  setRangeStart(iso(start))
                  setRangeEnd(iso(end))
                }}
                className="rounded-full bg-ink-50 px-2.5 py-1 text-[11px] text-ink-500 transition hover:bg-ink-100 hover:text-ink-800"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && !report && <div className="py-16 text-center text-[13px] text-ink-300">正在汇总…</div>}

      {report && (
        <>
          <div className="card overflow-hidden">
            <div className="px-4 pt-4">
              <div className="flex items-baseline justify-between">
                <span className="text-[12px] text-ink-400">个人净支出</span>
                <span className="text-[11px] text-ink-400">{report.label}</span>
              </div>
              <div className="mt-1.5 flex items-end justify-between">
                <div className="flex items-baseline gap-1.5">
                  <span className="font-num text-[32px] font-semibold leading-none tracking-tight tabular-nums">
                    ¥{fmtMoney(report.stats.total)}
                  </span>
                  {report.previous_total > 0 && (
                    <span
                      className={`mb-0.5 inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-medium ${
                        report.change_pct > 0 ? 'bg-red-50 text-red-500' : 'bg-emerald-50 text-emerald-600'
                      }`}
                    >
                      {report.change_pct > 0 ? <IconUp width={11} height={11} /> : <IconDown width={11} height={11} />}
                      {Math.abs(report.change_pct)}%
                    </span>
                  )}
                </div>
                <div className="mb-0.5 text-right text-[11px] leading-relaxed text-ink-400">
                  <div>{report.stats.count} 笔</div>
                  <div>均 ¥{fmtMoney(report.stats.average)}</div>
                </div>
              </div>
            </div>
            {report.stats.count > 0 && <Chart option={trendOption} height={112} />}
            {report.stats.count === 0 && <div className="h-4" />}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="card p-4"><div className="text-[11px] text-ink-400">真实收入</div><div className="mt-1 font-num text-xl font-semibold text-emerald-600">¥{fmtMoney(report.stats.income ?? 0)}</div></div>
            <div className="card p-4"><div className="text-[11px] text-ink-400">收支结余</div><div className="mt-1 font-num text-xl font-semibold text-ink-900">¥{fmtMoney(report.stats.balance ?? 0)}</div></div>
          </div>
          <p className="px-1 text-[11px] leading-relaxed text-ink-400">净支出为个人承担减当期退款；代垫、借还款和账户转账分别记录。结余根据已记流水计算，账户实际余额请以银行为准。对比采用前一个等长周期。</p>

          {report.stats.count > 0 && (
            <div className="card p-4">
              <div className="mb-1 text-[12px] font-medium text-ink-700">分类构成</div>
              <div className="flex items-center gap-4">
                <div className="relative w-[116px] shrink-0">
                  <Chart option={donutOption} height={116} />
                  <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-[10px] text-ink-400">分类</span>
                    <span className="font-num text-[17px] font-semibold leading-tight">
                      {report.stats.by_category.filter((c) => c.value > 0).length}
                    </span>
                  </div>
                </div>
                <div className="min-w-0 flex-1 space-y-2">
                  {report.stats.by_category.filter((c) => c.value > 0).slice(0, 4).map((item) => {
                    const percent = (item.value / (report.stats.total || 1)) * 100
                    return (
                      <div key={item.label}>
                        <div className="flex items-center justify-between text-[11.5px]">
                          <span className="flex items-center gap-1.5 text-ink-600">
                            <CategoryIcon name={ICON_MAP[item.label] ?? 'dots'} size={12} style={{ color: colorFor(item.label) }} />
                            {item.label}
                          </span>
                          <span className="font-num tabular-nums text-ink-800">¥{fmtMoney(item.value)}</span>
                        </div>
                        <div className="mt-1 h-1 overflow-hidden rounded-full bg-ink-100">
                          <div
                            className="h-full rounded-full transition-all duration-500"
                            style={{ width: `${Math.max(percent, 3)}%`, backgroundColor: colorFor(item.label) }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {report.stats.by_category.length > 4 && (
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 border-t border-ink-50 pt-3">
                  {report.stats.by_category.slice(4).map((item) => (
                    <div key={item.label} className="flex items-center justify-between text-[11.5px]">
                      <span className="flex items-center gap-1.5 text-ink-500">
                        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: colorFor(item.label) }} />
                        {item.label}
                      </span>
                      <span className="font-num tabular-nums text-ink-700">¥{fmtMoney(item.value)}</span>
                    </div>
                  ))}
                </div>
              )}

              {report.stats.by_payment.filter((p) => p.label !== '未记录').length > 0 && (
                <div className="mt-3 border-t border-ink-50 pt-3">
                  <div className="mb-2 text-[11px] text-ink-400">付款方式</div>
                  <div className="flex flex-wrap gap-1.5">
                    {report.stats.by_payment
                      .filter((p) => p.label !== '未记录')
                      .map((item) => (
                        <span
                          key={item.label}
                          className="flex items-center gap-1.5 rounded-full bg-ink-50 py-1 pl-2 pr-2.5 text-[11.5px]"
                        >
                          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: paymentColor(item.label) }} />
                          <span className="text-ink-600">{item.label}</span>
                          <span className="font-num font-medium tabular-nums text-ink-900">¥{fmtMoney(item.value)}</span>
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {report.events.length > 0 && (
            <div className="card p-4">
              <div className="mb-2.5 text-[12px] font-medium text-ink-700">事件开销</div>
              <div className="flex flex-wrap gap-1.5">
                {report.events.map((event) => (
                  <div
                    key={event.label}
                    className="flex items-center gap-2 rounded-full bg-ink-50 py-1 pl-2.5 pr-1.5"
                  >
                    <span className="text-[12px] text-ink-700">{event.label}</span>
                    <span className="rounded-full bg-white px-2 py-0.5 font-num text-[11.5px] font-medium tabular-nums text-ink-900">
                      ¥{fmtMoney(event.value)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card overflow-hidden">
            <div className="flex items-start gap-2.5 p-4">
              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
                <IconSpark width={13} height={13} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-medium text-ink-700">AI 消费诊断</span>
                  {!insightLoading && (
                    <button
                      onClick={() => void fetchInsight()}
                      className="rounded-full bg-ink-900 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-ink-800"
                    >
                      {insight ? '重新生成' : '生成'}
                    </button>
                  )}
                </div>
                {insightLoading && (
                  <div className="mt-2 space-y-1.5">
                    <div className="h-2.5 w-2/3 animate-pulseSoft rounded bg-ink-100" />
                    <div className="h-2.5 w-full animate-pulseSoft rounded bg-ink-100" />
                    <div className="h-2.5 w-4/5 animate-pulseSoft rounded bg-ink-100" />
                  </div>
                )}
                {!insightLoading && !insight && (
                  <div className="mt-1 text-[11.5px] leading-relaxed text-ink-400">
                    让 AI 读一遍这{period === 'year' ? '一年' : period === 'day' ? '一天' : '段时间'}的账，给几句具体建议。
                  </div>
                )}
                {insight && (
                  <div className="mt-1.5 space-y-2 animate-rise">
                    <div className="text-[13px] font-medium text-ink-900">{insight.headline}</div>
                    <ul className="space-y-1">
                      {insight.points.map((point, index) => (
                        <li key={index} className="flex gap-1.5 text-[12px] leading-relaxed text-ink-600">
                          <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-300" />
                          {point}
                        </li>
                      ))}
                    </ul>
                    {insight.tip && (
                      <div className="rounded-lg bg-indigo-50/70 px-2.5 py-2 text-[12px] leading-relaxed text-indigo-900">
                        {insight.tip}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          {report.top_transactions.length > 0 && (
            <div className="card p-4">
              <div className="mb-2.5 text-[12px] font-medium text-ink-700">最大几笔</div>
              <div className="space-y-2">
                {report.top_transactions.map((tx, index) => (
                  <div key={tx.id} className="flex items-center gap-2.5">
                    <span className="w-3 shrink-0 font-num text-[11px] text-ink-300">{index + 1}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] text-ink-800">
                        {tx.merchant || tx.note || tx.category}
                      </span>
                      <span className="text-[10.5px] text-ink-400">
                        {tx.category} · {tx.date.slice(5).replace('-', '/')}
                        {tx.paymentMethod && ` · ${tx.paymentMethod}`}
                      </span>
                    </span>
                    <span className="font-num text-[13px] font-medium tabular-nums text-ink-900">
                      ¥{fmtMoney(tx.expenseAmount)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {report.stats.count === 0 && (
            <div className="py-10 text-center">
              <div className="text-[13px] text-ink-400">这段时间还没有记录</div>
              <div className="mt-1 text-[12px] text-ink-300">记几笔之后回来看看</div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function colorFor(name: string): string {
  const order = ['餐饮', '交通', '购物', '服饰', '居住', '娱乐', '医疗', '教育', '数码', '旅行', '人情', '其他']
  const index = order.indexOf(name)
  return CATEGORY_COLORS[index >= 0 ? index : 11]
}

function paymentColor(name: string): string {
  const table: Record<string, string> = {
    支付宝: '#1677FF',
    微信: '#07C160',
    银行卡: '#FA8C16',
    信用卡: '#722ED1',
    现金: '#8C8C8C',
    其他: '#595959',
  }
  return table[name] ?? '#8C8C8C'
}
