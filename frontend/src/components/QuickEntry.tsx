import { useState } from 'react'
import { api, KIND_LABELS, type TransactionKind } from '../api'

export function QuickEntry({ categories, payments, onDone }: { categories: string[]; payments: string[]; onDone: () => void }) {
  const [kind, setKind] = useState<TransactionKind>('expense')
  const [amount, setAmount] = useState('')
  const [own, setOwn] = useState('')
  const [category, setCategory] = useState('餐饮')
  const [payment, setPayment] = useState('')
  const [note, setNote] = useState('')
  const [counterparty, setCounterparty] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const field = 'min-w-0 rounded-lg border border-ink-200 px-2.5 py-2 text-[12px]'
  return <form className="card space-y-3 p-4" onSubmit={async e => {
    e.preventDefault(); setError(''); setBusy(true)
    try {
      if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) throw new Error('请输入大于0的金额')
      await api.createTransaction({ kind, amount: Number(amount), category, payment_method: payment, note, counterparty,
        ...(kind === 'expense' && own !== '' ? { personal_amount: Number(own) } : {}) })
      onDone()
    } catch (err) { setError(err instanceof Error ? err.message : '记账失败') }
    finally { setBusy(false) }
  }}>
    <div className="text-[13px] font-medium">手动记一笔</div>
    <div className="grid grid-cols-2 gap-2">
      <select aria-label="记账类型" value={kind} onChange={e => setKind(e.target.value as TransactionKind)} className={field}>{Object.entries(KIND_LABELS).filter(([key]) => !['refund','collection','loan_repayment'].includes(key)).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select>
      <input aria-label="记账金额" placeholder="金额（元）" inputMode="decimal" required value={amount} onChange={e => setAmount(e.target.value)} className={field} />
      <select aria-label="记账分类" value={category} onChange={e => setCategory(e.target.value)} className={field}>{categories.map(c => <option key={c}>{c}</option>)}</select>
      <select aria-label="记账付款方式" value={payment} onChange={e => setPayment(e.target.value)} className={field}><option value="">未填写，使用默认规则</option>{payments.map(p => <option key={p}>{p}</option>)}</select>
      <input aria-label="记账描述" placeholder="描述，如午饭、工资" value={note} onChange={e => setNote(e.target.value)} className={field} />
      <input aria-label="记账对方" placeholder="对方姓名或公司" value={counterparty} onChange={e => setCounterparty(e.target.value)} className={field} />
      {kind === 'expense' && <input aria-label="记账个人承担" placeholder="个人承担，默认全部" inputMode="decimal" value={own} onChange={e => setOwn(e.target.value)} className={`${field} col-span-2`} />}
    </div>
    {error && <p role="alert" className="text-[12px] text-red-600">{error}</p>}
    <div className="flex items-center justify-between gap-2"><span className="text-[11px] text-ink-400">退款和回款请在原账单上操作。</span><button disabled={busy} className="shrink-0 rounded-lg bg-ink-900 px-3 py-2 text-[12px] text-white disabled:opacity-40">{busy ? '保存中' : '记好了'}</button></div>
  </form>
}
