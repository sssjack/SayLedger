import { useState } from 'react'
import { BASE, type ChatMessage, type Stats, type Transaction } from '../api'
import { TransactionCard } from './TransactionCard'
import { Chart, TOOLTIP_STYLE } from './Chart'
import { fmtDateLabel, fmtMoney, groupByDate } from '../utils'
import { IconChevron, IconSpark } from '../icons'
import { BudgetProgress } from './BudgetProgress'

type Props = {
  message: ChatMessage
  categories: string[]
  payments: string[]
  onUpdate: (id: number, patch: Record<string, unknown>) => Promise<void>
  onDelete: (id: number) => Promise<void>
  onLedgerChange: () => void
  onSend: (text: string, images?: string[], confirmDuplicate?: boolean) => void
  disabled?: boolean
}

export function MessageBubble({ message, categories, payments, onUpdate, onDelete, onLedgerChange, onSend, disabled }: Props) {
  const isUser = message.role === 'user'
  const { payload } = message

  if (isUser) {
    return (
      <div className="flex animate-rise justify-end gap-2.5">
        <div className="max-w-[86%] sm:max-w-[72%]">
          {payload.images && payload.images.length > 0 && (
            <div className="mb-1.5 flex justify-end gap-1.5">
              {payload.images.map((src) => (
                <img
                  key={src}
                  src={`${BASE}${src}`}
                  alt=""
                  className="h-20 w-20 rounded-xl object-cover ring-1 ring-ink-100"
                />
              ))}
            </div>
          )}
          <div className="rounded-2xl rounded-br-md bg-ink-900 px-3.5 py-2.5 text-[14px] leading-relaxed text-white">
            {message.content}
          </div>
        </div>
      </div>
    )
  }

  const renderCards = (list: Transaction[]) => (
    <div className="space-y-1.5 pt-0.5">
      {list.map((tx) => (
        <TransactionCard
          key={tx.id}
          tx={tx}
          categories={categories}
          payments={payments}
          onUpdate={(id, patch) => onUpdate(id, patch)}
          onDelete={onDelete}
          onChanged={onLedgerChange}
        />
      ))}
    </div>
  )

  return (
    <div className="flex animate-rise gap-2.5">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-ink-800 to-ink-950 text-white">
        <IconSpark width={14} height={14} />
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        {message.content && (
          <div className="whitespace-pre-wrap text-[14.5px] leading-relaxed text-ink-900">
            {message.content}
          </div>
        )}

        {['record', 'undo'].includes(payload.kind || '') && payload.transactions && payload.transactions.length > 0 && (
          <>
            {renderCards(payload.transactions)}
            {payload.transactions.length > 1 && (
              <div className="flex items-center justify-end gap-1 pt-0.5 text-[12px] text-ink-400">
                流水金额合计
                <span className="font-num font-semibold text-ink-900">
                  ¥{fmtMoney(payload.transactions.reduce((sum, t) => sum + t.amount, 0))}
                </span>
              </div>
            )}
          </>
        )}

        {payload.kind === 'update' && payload.transactions && payload.transactions.length > 0 && renderCards(payload.transactions)}
        {payload.related && payload.related.length > 0 && renderCards(payload.related)}

        {['delete', 'undo'].includes(payload.kind || '') && payload.deleted && payload.deleted.length > 0 && (
          <div className="space-y-1 pt-0.5">
            {payload.deleted.map((tx) => (
              <div
                key={tx.id}
                className="flex items-center gap-2 rounded-xl border border-dashed border-ink-200 bg-ink-50/40 px-3 py-2 text-[12px] text-ink-400"
              >
                <span className="line-through">
                  {tx.merchant || tx.note || tx.category} ¥{fmtMoney(tx.amount)}
                </span>
                <span className="ml-auto rounded bg-white px-1.5 py-0.5 text-[10.5px] text-ink-400">已删除</span>
              </div>
            ))}
          </div>
        )}

        {/* 改/删没定位到目标时，把最近几笔直接摆出来让用户点，而不是干问一句 */}
        {['clarify', 'duplicate'].includes(payload.kind || '') && payload.candidates && payload.candidates.length > 0 && (
          <div className="space-y-1.5 pt-0.5">
            <div className="text-[11.5px] text-ink-400">点任意一条就能改金额、分类或直接删掉</div>
            {renderCards(payload.candidates)}
          </div>
        )}
        {payload.kind === 'duplicate' && payload.retry && <button disabled={disabled} onClick={() => onSend(payload.retry!.text, payload.retry!.imageIds, true)} className="rounded-full border border-ink-200 px-3 py-1.5 text-[12px] text-ink-700 disabled:opacity-40">这是另一笔，仍然记入</button>}
        {payload.choices && <div className="flex flex-wrap gap-2">{payload.choices.map(choice => <button key={choice.text} disabled={disabled} onClick={() => onSend(choice.text)} className="rounded-lg border border-ink-200 px-2 py-1 text-[12px] disabled:opacity-40">{choice.label}</button>)}</div>}
        {payload.kind === 'memo' && (payload.memos?.length ? payload.memos : payload.memo ? [payload.memo] : []).map(memo => (
          <div key={memo.id} className="rounded-xl bg-indigo-50/60 p-3 text-[12px] text-ink-600 ring-1 ring-indigo-100">
            <div className="font-medium text-ink-800">⏰ {memo.content}</div>
            <div className="mt-1 text-ink-400">
              {memo.status === 'active' ? `下一次提醒：${memo.nextTriggerAt}` : `提醒时间：${memo.nextTriggerAt}`}
              {memo.recurrenceLabel ? ` · ${memo.recurrenceLabel}` : ''}
            </div>
          </div>
        ))}
        {payload.budgets && <div className="space-y-2">{payload.budgets.map(b => <BudgetProgress key={b.id} budget={b} />)}{payload.budgets.length === 0 && <div className="text-[12px] text-ink-400">还没有预算，可以说“这个月餐饮预算1500”。</div>}</div>}
        {payload.preference && <div className="rounded-xl bg-ink-50 p-3 text-[12px] text-ink-600">默认付款：{payload.preference.payment_method || '不设置'}{Object.entries(payload.preference.rules).map(([merchant, category]) => <div key={merchant} className="mt-1">{merchant} → {category}</div>)}<div className="mt-1 text-ink-400">可以到“管理”查看和取消规则。</div></div>}
        {payload.download && <a href={`${BASE}${payload.download}`} download className="inline-block rounded-full bg-ink-900 px-3 py-1.5 text-[12px] text-white">下载账单 CSV</a>}
        {payload.comparison && <div className="rounded-xl bg-ink-50 p-3 text-[12px] text-ink-600"><div>对比前一等长周期：{payload.comparison.start} 至 {payload.comparison.end}，¥{fmtMoney(payload.comparison.total)}</div>{payload.comparison.categories.slice(0, 5).map(g => <div key={g.label} className="mt-1 flex justify-between"><span>{g.label}</span><span className={g.value > 0 ? 'text-red-500' : 'text-emerald-600'}>{g.value > 0 ? '+' : '−'}¥{fmtMoney(Math.abs(g.value))}</span></div>)}</div>}

        {['query', 'compare', 'export'].includes(payload.kind || '') && payload.stats && payload.stats.count > 0 && (
          <QueryResult
            stats={payload.stats}
            transactions={payload.transactions ?? []}
            range={payload.range}
            truncated={payload.truncated ?? 0}
            relaxed={payload.relaxed}
            sortBy={typeof payload.query?.sort_by === 'string' ? payload.query.sort_by : undefined}
            renderCards={renderCards}
          />
        )}
      </div>
    </div>
  )
}

type QueryResultProps = {
  stats: Stats
  transactions: Transaction[]
  range?: { start?: string | null; end?: string | null }
  truncated: number
  relaxed?: boolean
  sortBy?: string
  renderCards: (list: Transaction[]) => JSX.Element
}

function QueryResult({ stats, transactions, range, truncated, relaxed, sortBy, renderCards }: QueryResultProps) {
  // 按金额排序时不能再按日期分组，否则跨天的金额顺序会被分组打散；
  // 直接按服务端排好的顺序平铺，每张卡片本身带日期。
  const isAmountSorted = sortBy === 'amount_desc' || sortBy === 'amount_asc'
  const [open, setOpen] = useState(true)
  const total = stats.display_total ?? stats.total
  const top = stats.by_category.filter(item => item.value > 0).slice(0, 6)
  const groups = groupByDate(transactions).map((group) => ({
    ...group,
    total: group.items.reduce((sum, item) => sum + (stats.metric === 'income' ? (item.kind === 'income' ? item.amount : 0) : stats.metric === 'outstanding' ? item.outstandingAmount : stats.metric === 'flow' ? item.amount : item.expenseAmount), 0),
  }))

  const option = {
    tooltip: { ...TOOLTIP_STYLE, trigger: 'item', formatter: (p: { name: string; value: number; percent: number }) =>
      `${p.name}&nbsp;&nbsp;<b>¥${fmtMoney(p.value)}</b>&nbsp;&nbsp;${p.percent}%` },
    series: [
      {
        type: 'pie',
        radius: ['58%', '84%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        padAngle: 2,
        itemStyle: { borderRadius: 4 },
        label: { show: false },
        data: top.map((item) => ({ name: item.label, value: item.value })),
        color: CATEGORY_COLORS,
      },
    ],
    graphic: [
      {
        type: 'text',
        left: 'center',
        top: '43%',
        style: {
          text: `¥${fmtMoney(total)}`,
          fontSize: 18,
          fontWeight: 600,
          fill: '#101218',
          fontFamily: 'system-ui, sans-serif',
        },
      },
      {
        type: 'text',
        left: 'center',
        top: '58%',
        style: { text: `${stats.count} 笔`, fontSize: 11, fill: '#848ea4' },
      },
    ],
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-ink-50 px-3.5 py-2">
        <span className="truncate text-[11.5px] text-ink-500">{rangeLabel(range, stats)}</span>
        <span className="shrink-0 text-[11.5px] text-ink-400">
          <b className="font-num text-ink-800">{stats.count}</b> 笔
          <span className="mx-1 text-ink-200">·</span>
          合计 <b className="font-num text-ink-900">¥{fmtMoney(total)}</b>
        </span>
      </div>

      <div className="flex items-stretch">
        <div className="w-[132px] shrink-0 border-r border-ink-50 p-1">
          <Chart option={option} height={132} />
        </div>
        <div className="min-w-0 flex-1 space-y-1.5 px-3.5 py-3">
          {top.map((item) => (
            <div key={item.label} className="flex items-center gap-2 text-[12px]">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: colorFor(item.label) }}
              />
              <span className="w-10 shrink-0 text-ink-500">{item.label}</span>
              <span className="min-w-0 flex-1 border-b border-dashed border-ink-100" />
              <span className="font-num tabular-nums text-ink-800">¥{fmtMoney(item.value)}</span>
              <span className="w-9 text-right tabular-nums text-ink-300">
                {Math.round((item.value / (total || 1)) * 100)}%
              </span>
            </div>
          ))}
          {top.length === 0 && <div className="text-[12px] text-ink-400">暂无分类数据</div>}
        </div>
      </div>
      {stats.by_payment && stats.by_payment.filter((p) => p.label !== '未记录').length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-ink-50 px-3.5 py-2">
          {stats.by_payment
            .filter((p) => p.label !== '未记录')
            .map((item) => (
              <span key={item.label} className="flex items-center gap-1 rounded-full bg-ink-50 px-2 py-0.5 text-[10.5px] text-ink-500">
                {item.label}
                <span className="font-num font-medium text-ink-800">¥{fmtMoney(item.value)}</span>
              </span>
            ))}
        </div>
      )}
      <div className="flex items-center justify-between gap-3 border-t border-ink-50 px-3.5 py-2 text-[11px] text-ink-400">
        {/* 单日查询的日期已经写在标题了，这里只在跨天时补上区间 */}
        {stats.first_date && stats.last_date && stats.first_date !== stats.last_date ? (
          <span>
            {stats.first_date.slice(5).replace('-', '/')} – {stats.last_date.slice(5).replace('-', '/')}
          </span>
        ) : (
          <span>共 {stats.count} 笔</span>
        )}
        <span>
          笔均 <b className="font-num font-medium text-ink-700">¥{fmtMoney(stats.average)}</b>
          <span className="mx-1.5 text-ink-200">|</span>
          最高 <b className="font-num font-medium text-ink-700">¥{fmtMoney(stats.max)}</b>
        </span>
      </div>

      {relaxed && (
        <div className="border-t border-amber-100 bg-amber-50/60 px-3.5 py-1.5 text-[11px] text-amber-700">
          这段时间没有记录，下面是全部时间里匹配到的结果
        </div>
      )}

      {transactions.length > 0 && (
        <>
          <button
            onClick={() => setOpen((value) => !value)}
            className="flex w-full items-center justify-between border-t border-ink-50 px-3.5 py-2 text-[11.5px] font-medium text-ink-600 transition hover:bg-ink-50/60"
          >
            <span>
              {open ? '收起明细' : '展开明细'}
              <span className="ml-1 font-normal text-ink-400">逐笔</span>
            </span>
            <IconChevron width={14} height={14} className={`text-ink-300 transition ${open ? '-rotate-90' : 'rotate-90'}`} />
          </button>

          {open && (
            <div className="space-y-3 border-t border-ink-50 bg-ink-50/30 px-3 py-3">
              {isAmountSorted ? (
                <>
                  <div className="px-0.5 text-[11.5px] font-medium text-ink-500">
                    {sortBy === 'amount_desc' ? '按金额从大到小排列' : '按金额从小到大排列'}
                  </div>
                  {renderCards(transactions)}
                </>
              ) : (
                groups.map((group) => (
                  <div key={group.date} className="space-y-1.5">
                    <div className="flex items-baseline justify-between px-0.5">
                      <span className="text-[11.5px] font-medium text-ink-500">{fmtDateLabel(group.date)}</span>
                      <span className="font-num text-[11px] tabular-nums text-ink-400">¥{fmtMoney(group.total)}</span>
                    </div>
                    {renderCards(group.items)}
                  </div>
                ))
              )}
              {truncated > 0 && (
                <div className="text-center text-[11px] text-ink-400">
                  还有 {truncated} 笔没列出，去账单页看全部
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** 卡片标题里的时间范围：单日直接说「昨天」，跨天说「9月1日 – 9月30日」 */
function rangeLabel(range: { start?: string | null; end?: string | null } | undefined, stats: Stats): string {
  const start = range?.start || stats.first_date
  const end = range?.end || stats.last_date
  if (!start || !end) return '全部记录'
  if (start === end) return fmtDateLabel(start)
  const md = (iso: string) => `${Number(iso.slice(5, 7))}月${Number(iso.slice(8, 10))}日`
  const left = start.slice(0, 4) === end.slice(0, 4) ? md(start) : start
  return `${left} – ${md(end)}`
}

export const CATEGORY_COLORS = [
  '#FF7A45',
  '#36A3F7',
  '#F759AB',
  '#9254DE',
  '#13C2C2',
  '#EB2F96',
  '#F5222D',
  '#2F54EB',
  '#595959',
  '#52C41A',
  '#FAAD14',
  '#8C8C8C',
]

const ORDER = ['餐饮', '交通', '购物', '服饰', '居住', '娱乐', '医疗', '教育', '数码', '旅行', '人情', '其他']

function colorFor(name: string): string {
  const index = ORDER.indexOf(name)
  return CATEGORY_COLORS[index >= 0 ? index : 11]
}
