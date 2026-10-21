import { useState } from 'react'
import { CategoryIcon, IconChevron, IconClose, IconTrash } from '../icons'
import { api, KIND_LABELS, type Transaction, type TransactionKind } from '../api'
import { fmtMoney, fmtTime } from '../utils'

type Props = {
  tx: Transaction
  categories: string[]
  payments: string[]
  onUpdate: (id: number, patch: Partial<Transaction>) => Promise<void>
  onDelete: (id: number) => Promise<void>
  onChanged?: () => void
}

export function TransactionCard({ tx, categories, payments, onUpdate, onDelete, onChanged }: Props) {
  const [editing, setEditing] = useState(false)
  const [amount, setAmount] = useState(String(tx.amount))
  const [category, setCategory] = useState(tx.category)
  const [note, setNote] = useState(tx.note)
  const [payment, setPayment] = useState(tx.paymentMethod)
  const [remark, setRemark] = useState(tx.remark)
  const [busy, setBusy] = useState(false)
  const [removing, setRemoving] = useState(false)
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
    setError(''); setEditing(true); setAction(null)
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
    setRemoving(true)
    setError('')
    try {
      await onDelete(tx.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setRemoving(false)
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

  if (removing) {
    return (
      <div className="rounded-xl border border-dashed border-ink-200 px-3 py-2.5 text-[12px] text-ink-400">
        已删除
      </div>
    )
  }

  return (
    <div className="group relative overflow-hidden rounded-xl border border-ink-100 bg-white transition hover:border-ink-200">
      <div
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ backgroundColor: tx.categoryColor || '#8C8C8C' }}
      />
      {editing ? (
        <div className="space-y-2 px-3 py-2.5">
          <div className="flex flex-wrap gap-1">
            {(Object.entries(KIND_LABELS) as [TransactionKind, string][]).filter(([key]) => !['refund', 'collection', 'loan_repayment'].includes(key) || key === tx.kind).map(([key, label]) => (
              <button key={key} disabled={!!tx.relatedId} onClick={() => setKind(key)} className={`rounded-full px-2 py-1 text-[11px] ${kind === key ? 'bg-ink-900 text-white' : 'bg-ink-50 text-ink-500'}`}>{label}</button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="shrink-0 text-[12px] text-ink-400">金额</span>
            <input
              autoFocus
              inputMode="decimal"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              className="w-20 rounded-lg border border-ink-200 px-2 py-1 text-sm outline-none focus:border-ink-900"
            />
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="描述"
              className="min-w-0 flex-1 rounded-lg border border-ink-200 px-2 py-1 text-sm outline-none focus:border-ink-900"
            />
          </div>

          {kind === 'expense' && <label className="flex items-center gap-2 text-[12px] text-ink-500">个人承担
            <input aria-label="个人承担金额" inputMode="decimal" value={own} onChange={(e) => setOwn(e.target.value)} className="w-24 rounded-lg border border-ink-200 px-2 py-1 text-ink-900" />
            <span>其余记为待收回款</span>
          </label>}
          <div className="grid grid-cols-2 gap-2">
            <input aria-label="商户" placeholder="商户" value={merchant} onChange={(e) => setMerchant(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
            <input aria-label="日期" type="date" value={date} onChange={(e) => setDate(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
            <input aria-label="对方姓名或公司" placeholder="对方姓名或公司" value={counterparty} onChange={(e) => setCounterparty(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
            <input aria-label="事件标签" placeholder="事件标签，如杭州出差" value={event} onChange={(e) => setEvent(e.target.value)} className="min-w-0 rounded-lg border border-ink-200 px-2 py-1 text-[12px]" />
          </div>

          <div className="flex flex-wrap gap-1">
            {categories.map((item) => (
              <button
                key={item}
                onClick={() => setCategory(item)}
                className={`rounded-full px-2 py-0.5 text-[11px] transition ${
                  category === item ? 'bg-ink-900 text-white' : 'bg-ink-50 text-ink-500 hover:bg-ink-100'
                }`}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 shrink-0 text-[11px] text-ink-400">付款</span>
            {payments.map((item) => (
              <button
                key={item}
                onClick={() => setPayment(payment === item ? '' : item)}
                className={`rounded-full px-2 py-0.5 text-[11px] transition ${
                  payment === item ? 'bg-ink-900 text-white' : 'bg-ink-50 text-ink-500 hover:bg-ink-100'
                }`}
              >
                {item}
              </button>
            ))}
          </div>

          <input
            value={remark}
            onChange={(event) => setRemark(event.target.value)}
            placeholder="备注（和谁、是否报销、发票号…）"
            className="w-full rounded-lg border border-ink-200 px-2 py-1 text-[12px] outline-none placeholder:text-ink-300 focus:border-ink-900"
          />

          <div className="flex items-center justify-end gap-2 pt-0.5">
            <button onClick={remove} className="rounded-full p-1.5 text-ink-400 hover:bg-red-50 hover:text-red-500">
              <IconTrash width={15} height={15} />
            </button>
            <button onClick={() => setEditing(false)} className="rounded-full p-1.5 text-ink-400 hover:bg-ink-50">
              <IconClose width={15} height={15} />
            </button>
            <button
              disabled={busy}
              onClick={save}
              className="rounded-full bg-ink-900 px-3 py-1 text-[12px] font-medium text-white disabled:opacity-50"
            >
              {busy ? '保存中' : '保存'}
            </button>
          </div>
        </div>
      ) : (
        <button onClick={startEdit} className="flex w-full items-center gap-3 px-3 py-2.5 text-left">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
            style={{ backgroundColor: `${tx.categoryColor}14`, color: tx.categoryColor }}
          >
            <CategoryIcon name={iconFor(tx.category)} size={16} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-baseline gap-1.5">
              <span className="truncate text-[13px] font-medium text-ink-900">
                {tx.merchant || tx.note || tx.category}
              </span>
              {tx.merchant && tx.note && <span className="truncate text-[11px] text-ink-400">{tx.note}</span>}
            </span>
            <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-400">
              <span>{tx.category}</span>
              <span className="rounded bg-ink-50 px-1 text-ink-600">{KIND_LABELS[tx.kind] || '支出'}</span>
              {tx.counterparty && <span>{tx.counterparty}</span>}
              {tx.transferTo && <span>→ {tx.transferTo}</span>}
              {tx.relatedId && <span>关联 #{tx.relatedId}</span>}
              <span className="text-ink-200">·</span>
              <span>{tx.date.slice(5).replace('-', '/')}</span>
              {fmtTime(tx.occurredAt) && (
                <>
                  <span className="text-ink-200">·</span>
                  <span>{fmtTime(tx.occurredAt)}</span>
                </>
              )}
              {tx.paymentMethod && (
                <>
                  <span className="text-ink-200">·</span>
                  <span
                    className="rounded px-1"
                    style={{ backgroundColor: `${tx.paymentColor}12`, color: tx.paymentColor }}
                  >
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
            {tx.remark && (
              <span className="mt-1 block truncate text-[11px] text-ink-400">
                <span className="text-ink-300">备注 </span>
                {tx.remark}
              </span>
            )}
          </span>
          <span className={`shrink-0 font-num text-[15px] font-semibold tabular-nums ${tx.cashFlow > 0 ? 'text-emerald-600' : 'text-ink-900'}`}>
            {tx.kind === 'transfer' ? '↔' : tx.cashFlow > 0 ? '+' : '−'}{fmtMoney(tx.amount)}
          </span>
          <IconChevron width={14} height={14} className="shrink-0 text-ink-300 opacity-0 transition group-hover:opacity-100" />
        </button>
      )}
      {!editing && (tx.recoverableAmount > 0 || tx.refundedAmount > 0) && ['expense','lend','borrow','deposit'].includes(tx.kind) && <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-ink-50 px-3 py-2 text-[11px] text-ink-500">
        {tx.kind === 'expense' && <span>个人承担 ¥{fmtMoney(tx.personalAmount)}</span>}
        {tx.refundedAmount > 0 && <span>已退款 ¥{fmtMoney(tx.refundedAmount)}</span>}
        {tx.recoverableAmount > 0 && <span className={tx.outstandingAmount > 0 ? 'text-amber-700' : 'text-emerald-600'}>{tx.outstandingAmount > 0 ? (tx.kind === 'borrow' ? '待归还' : '待收回') : '已结清'} ¥{fmtMoney(tx.outstandingAmount)}</span>}
      </div>}
      {!editing && onChanged && <div className="flex justify-end gap-3 px-3 pb-2 text-[11px] text-ink-500">
        {tx.kind === 'expense' && tx.amount > (tx.refundedAmount || 0) && <button disabled={busy} onClick={() => { setAction('refund'); setActionAmount(String(Math.round((tx.amount - (tx.refundedAmount || 0)) * 100) / 100)); setError('') }} className="hover:text-ink-900">记录退款</button>}
        {tx.outstandingAmount > 0 && <button disabled={busy} onClick={() => { setAction('settle'); setActionAmount(String(tx.outstandingAmount)); setError('') }} className="font-medium text-indigo-600">{tx.kind === 'borrow' ? '记录还款' : '记录回款'}</button>}
      </div>}
      {action && <form onSubmit={(e) => { e.preventDefault(); void submitAction() }} className="flex flex-wrap items-center gap-2 border-t border-ink-100 px-3 py-2 text-[12px]">
        <span>{action === 'refund' ? '退款' : tx.kind === 'borrow' ? '还款' : '回款'}金额</span>
        <input aria-label="退款或结算金额" inputMode="decimal" value={actionAmount} onChange={(e) => setActionAmount(e.target.value)} className="w-24 rounded-lg border border-ink-200 px-2 py-1" />
        <button disabled={busy} type="submit" className="rounded-lg bg-ink-900 px-2 py-1 text-white disabled:opacity-50">{busy ? '保存中' : '确认记录'}</button>
        <button type="button" onClick={() => setAction(null)}>取消</button>
      </form>}
      {error && <div role="alert" className="px-3 pb-2 text-[12px] text-red-600">{error}</div>}
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
