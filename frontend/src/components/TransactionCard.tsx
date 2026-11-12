import { useState } from 'react'
import { CategoryIcon, IconChevron } from '../icons'
import { api, KIND_LABELS, type Transaction, type TransactionKind } from '../api'
import { fmtMoney, fmtTime, mute, tint } from '../utils'
import { Amount } from './Amount'

type Props = {
  tx: Transaction
  categories: string[]
  payments: string[]
  onUpdate: (id: number, patch: Partial<Transaction>) => Promise<void>
  onDelete: (id: number) => Promise<void>
  onChanged?: () => void
}

/**
 * 一笔流水。
 * 点卡片只展开「只读详情」，编辑要再点一次「编辑」——之前整张卡就是编辑按钮，
 * 手机上滚动时手指落点直接进编辑态，面板高度瞬间翻倍。
 */
export function TransactionCard({ tx, categories, payments, onUpdate, onDelete, onChanged }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [more, setMore] = useState(false)
  const [amount, setAmount] = useState(String(tx.amount))
  const [category, setCategory] = useState(tx.category)
  const [note, setNote] = useState(tx.note)
  const [payment, setPayment] = useState(tx.paymentMethod)
  const [remark, setRemark] = useState(tx.remark)
  const [busy, setBusy] = useState(false)
  const [kind, setKind] = useState<TransactionKind>(tx.kind || 'expense')
  const [own, setOwn] = useState(String(tx.personalAmount ?? tx.amount))
  const [counterparty, setCounterparty] = useState(tx.counterparty || '')
  const [event, setEvent] = useState(tx.event)
  const [merchant, setMerchant] = useState(tx.merchant)
  const [date, setDate] = useState(tx.date)
  const [error, setError] = useState('')
  const [action, setAction] = useState<'refund' | 'settle' | null>(null)
  const [actionAmount, setActionAmount] = useState('')

  const startEdit = () => {
    setAmount(String(tx.amount)); setCategory(tx.category); setNote(tx.note)
    setPayment(tx.paymentMethod); setRemark(tx.remark); setKind(tx.kind || 'expense')
    setOwn(String(tx.personalAmount ?? tx.amount)); setCounterparty(tx.counterparty || '')
    setEvent(tx.event); setMerchant(tx.merchant); setDate(tx.date)
    setError(''); setEditing(true); setMore(false); setAction(null)
  }

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) throw new Error('金额需要大于0')
      const patch: Partial<Transaction> = {
        amount: Number(amount),
        category,
        note,
        paymentMethod: payment,
        remark,
        kind, counterparty, event, merchant,
      }
      if (kind === 'expense' && (own !== String(tx.personalAmount ?? tx.amount) || Number(amount) !== tx.amount)) {
        patch.personalAmount = own === String(tx.personalAmount ?? tx.amount) && !tx.recoverableAmount ? Number(amount) : Number(own)
      }
      if (date !== tx.date) (patch as Record<string, unknown>).occurred_at = date
      await onUpdate(tx.id, patch)
      setEditing(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setError('')
    try {
      await onDelete(tx.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
      setBusy(false)
    }
  }

  const submitAction = async () => {
    if (!action) return
    setBusy(true); setError('')
    try {
      const value = Number(actionAmount)
      if (!Number.isFinite(value) || value <= 0) throw new Error('请输入大于0的金额')
      await api.relatedTransaction(tx.id, action, value)
      setAction(null)
      onChanged?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally { setBusy(false) }
  }

  const title = tx.merchant || tx.note || tx.category
  const time = fmtTime(tx.occurredAt) || tx.occurredAt.slice(11, 16)
  const canRefund = tx.kind === 'expense' && tx.amount > (tx.refundedAmount || 0)

  return (
    <div className="overflow-hidden rounded-xl border border-ink-100 bg-white transition hover:border-ink-200">
      <div className="relative">
        <span
          className="absolute inset-y-0 left-0 w-[3px]"
          style={{ backgroundColor: mute(tx.categoryColor || '#8C8C8C', 0.12) }}
        />
        {editing ? (
          <div className="space-y-2 px-3 py-2.5">
            <div className="flex flex-wrap gap-1">
              {(Object.entries(KIND_LABELS) as [TransactionKind, string][]).filter(([key]) => !['refund', 'collection', 'loan_repayment'].includes(key) || key === tx.kind).map(([key, label]) => (
                <button key={key} disabled={!!tx.relatedId} onClick={() => setKind(key)} className={`rounded-full px-2 py-1 text-[11px] transition ${kind === key ? 'bg-accent-600 text-white' : 'bg-ink-50 text-ink-500 hover:bg-ink-100'}`}>{label}</button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <span className="shrink-0 text-[12px] text-ink-500">金额</span>
              <input
                autoFocus
                inputMode="decimal"
                aria-label="金额"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                className="w-20 rounded-lg border border-ink-200 px-2 py-1 text-sm focus:border-ink-900"
              />
              <input
                value={note}
                onChange={(event) => setNote(event.target.value)}
                aria-label="描述"
                placeholder="描述"
                className="min-w-0 flex-1 rounded-lg border border-ink-200 px-2 py-1 text-sm focus:border-ink-900"
              />
            </div>

            <div className="flex flex-wrap gap-1">
              {categories.map((item) => (
                <button
                  key={item}
                  onClick={() => setCategory(item)}
                  className={`rounded-full px-2 py-0.5 text-[11px] transition ${
                    category === item ? 'bg-accent-600 text-white' : 'bg-ink-50 text-ink-500 hover:bg-ink-100'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-1">
              <span className="mr-1 shrink-0 text-[11px] text-ink-500">付款</span>
              {payments.map((item) => (
                <button
                  key={item}
                  onClick={() => setPayment(payment === item ? '' : item)}
                  className={`rounded-full px-2 py-0.5 text-[11px] transition ${
                    payment === item ? 'bg-accent-600 text-white' : 'bg-ink-50 text-ink-500 hover:bg-ink-100'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>

            <button onClick={() => setMore((value) => !value)} className="flex items-center gap-1 text-[11px] text-ink-500 hover:text-ink-700">
              <IconChevron width={12} height={12} className={`transition ${more ? 'rotate-90' : ''}`} />
              {more ? '收起更多字段' : '商户、日期、对方、事件、备注'}
            </button>

            {more && (
              <div className="space-y-2 rounded-xl bg-ink-50 p-2.5">
                {kind === 'expense' && (
                  <label className="flex items-center gap-2 text-[12px] text-ink-500">
                    个人承担
                    <input aria-label="个人承担金额" inputMode="decimal" value={own} onChange={(e) => setOwn(e.target.value)} className="w-24 rounded-lg border border-ink-200 px-2 py-1 text-ink-900" />
                    <span>其余记为待收回款</span>
                  </label>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <input aria-label="商户" placeholder="商户" value={merchant} onChange={(e) => setMerchant(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
                  <input aria-label="日期" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
                  <input aria-label="对方姓名或公司" placeholder="对方姓名或公司" value={counterparty} onChange={(e) => setCounterparty(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
                  <input aria-label="事件标签" placeholder="事件标签，如杭州出差" value={event} onChange={(e) => setEvent(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
                </div>
                <input
                  value={remark}
                  onChange={(event) => setRemark(event.target.value)}
                  aria-label="备注"
                  placeholder="备注（和谁、是否报销、发票号…）"
                  className="w-full rounded-lg border border-ink-200 px-2 py-1 text-[12px] placeholder:text-ink-400 focus:border-ink-900"
                />
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-0.5">
              <button onClick={() => setEditing(false)} className="rounded-full px-2 py-1.5 text-[12px] text-ink-500 hover:bg-ink-50">
                取消
              </button>
              <button
                disabled={busy}
                onClick={save}
                className="rounded-full bg-accent-600 px-3.5 py-1.5 text-[12px] font-medium text-white hover:bg-accent-700 disabled:opacity-50"
              >
                {busy ? '保存中' : '保存'}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
          >
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
              style={{ backgroundColor: tint(tx.categoryColor, 0.92), color: mute(tx.categoryColor, 0.18) }}
            >
              <CategoryIcon name={iconFor(tx.category)} size={16} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline gap-1.5">
                <span className="truncate text-[13px] font-medium text-ink-900">{title}</span>
                {tx.merchant && tx.note && <span className="truncate text-[11px] text-ink-500">{tx.note}</span>}
              </span>
              <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500">
                <span>{tx.category}</span>
                <span className="rounded bg-ink-50 px-1 text-ink-600">{KIND_LABELS[tx.kind] || '支出'}</span>
                {tx.counterparty && <span>{tx.counterparty}</span>}
                {tx.transferTo && <span>→ {tx.transferTo}</span>}
                {tx.relatedId && <span>关联 #{tx.relatedId}</span>}
                <span className="text-ink-200">·</span>
                <span>{tx.date.slice(5).replace('-', '/')}</span>
                {time && (
                  <>
                    <span className="text-ink-200">·</span>
                    <span>{time}</span>
                  </>
                )}
                {tx.paymentMethod && (
                  <>
                    <span className="text-ink-200">·</span>
                    <span className="rounded px-1" style={{ backgroundColor: `${tx.paymentColor}12`, color: tx.paymentColor }}>
                      {tx.paymentMethod}
                    </span>
                  </>
                )}
                {tx.event && (
                  <>
                    <span className="text-ink-200">·</span>
                    <span className="rounded bg-ink-50 px-1 text-ink-500">{tx.event}</span>
                  </>
                )}
              </span>
            </span>
            <Amount
              value={tx.amount}
              size={15}
              prefix={tx.kind === 'transfer' ? '↔' : tx.cashFlow > 0 ? '+' : '−'}
              className={`shrink-0 ${tx.cashFlow > 0 ? 'text-emerald-600' : 'text-ink-900'}`}
            />
            <IconChevron
              width={14}
              height={14}
              className={`shrink-0 text-ink-300 transition ${expanded ? 'rotate-90' : ''}`}
            />
          </button>
        )}
      </div>

      {!editing && expanded && (
        <div className="animate-rise border-t border-ink-50 px-3 py-2.5">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[12px]">
            <Field label="时间" value={`${tx.date.slice(5).replace('-', '/')} ${time || ''}`.trim()} />
            <Field label="分类" value={tx.category} />
            <Field label="付款" value={tx.paymentMethod || '未记录'} />
            <Field label="类型" value={KIND_LABELS[tx.kind] || '支出'} />
            {tx.merchant && <Field label="商户" value={tx.merchant} />}
            {tx.event && <Field label="事件" value={tx.event} />}
            {tx.counterparty && <Field label="对方" value={tx.counterparty} />}
            {tx.kind === 'expense' && <Field label="个人承担" value={`¥${fmtMoney(tx.personalAmount)}`} />}
            {tx.remark && <Field label="备注" value={tx.remark} className="col-span-2" />}
          </dl>

          {(tx.recoverableAmount > 0 || tx.refundedAmount > 0) && (
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-500">
              {tx.refundedAmount > 0 && <span>已退款 ¥{fmtMoney(tx.refundedAmount)}</span>}
              {tx.recoverableAmount > 0 && (
                <span className={tx.outstandingAmount > 0 ? 'text-amber-700' : 'text-emerald-600'}>
                  {tx.outstandingAmount > 0 ? (tx.kind === 'borrow' ? '待归还' : '待收回') : '已结清'} ¥{fmtMoney(tx.outstandingAmount)}
                </span>
              )}
            </div>
          )}

          {action && (
            <form
              onSubmit={(event) => { event.preventDefault(); void submitAction() }}
              className="mt-2 flex flex-wrap items-center gap-2 rounded-xl bg-ink-50 p-2 text-[12px]"
            >
              <span>{action === 'refund' ? '退款' : tx.kind === 'borrow' ? '还款' : '回款'}金额</span>
              <input aria-label="退款或结算金额" inputMode="decimal" value={actionAmount} onChange={(event) => setActionAmount(event.target.value)} className="w-24 rounded-lg border border-ink-200 px-2 py-1" />
              <button disabled={busy} type="submit" className="rounded-lg bg-accent-600 px-2.5 py-1 text-white disabled:opacity-50">{busy ? '保存中' : '确认'}</button>
              <button type="button" onClick={() => setAction(null)} className="text-ink-500">取消</button>
            </form>
          )}

          <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-ink-50 pt-2">
            <div className="flex gap-3 text-[12px]">
              {canRefund && (
                <button
                  disabled={busy}
                  onClick={() => { setAction('refund'); setActionAmount(String(Math.round((tx.amount - (tx.refundedAmount || 0)) * 100) / 100)); setError('') }}
                  className="text-ink-500 hover:text-ink-900"
                >
                  记录退款
                </button>
              )}
              {tx.outstandingAmount > 0 && (
                <button
                  disabled={busy}
                  onClick={() => { setAction('settle'); setActionAmount(String(tx.outstandingAmount)); setError('') }}
                  className="font-medium text-accent-700"
                >
                  {tx.kind === 'borrow' ? '记录还款' : '记录回款'}
                </button>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={startEdit} className="rounded-full px-2.5 py-1 text-[12px] text-ink-600 ring-1 ring-ink-200 hover:text-ink-900">
                编辑
              </button>
              <button
                disabled={busy}
                onClick={() => void remove()}
                className="rounded-full px-2.5 py-1 text-[12px] text-red-600 ring-1 ring-red-100 hover:bg-red-50 disabled:opacity-50"
              >
                删除
              </button>
            </div>
          </div>
          {error && <div role="alert" className="mt-1.5 text-[12px] text-red-600">{error}</div>}
        </div>
      )}

      {editing && error && <div role="alert" className="px-3 pb-2 text-[12px] text-red-600">{error}</div>}
    </div>
  )
}

function Field({ label, value, className = '' }: { label: string; value: string; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-[11px] text-ink-400">{label}</dt>
      <dd className="mt-0.5 break-words text-ink-800">{value}</dd>
    </div>
  )
}

function iconFor(category: string): string {
  return ICON_MAP[category] ?? 'dots'
}

export const ICON_MAP: Record<string, string> = {
  餐饮: 'coffee',
  交通: 'car',
  购物: 'bag',
  服饰: 'shirt',
  居住: 'home',
  娱乐: 'game',
  医疗: 'heart',
  教育: 'book',
  数码: 'device',
  旅行: 'plane',
  人情: 'gift',
  其他: 'dots',
}
