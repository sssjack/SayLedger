import { useCallback, useEffect, useState } from 'react'
import { api, type Budget, type Preference, type Transaction } from '../api'
import { BudgetProgress } from './BudgetProgress'
import { TransactionCard } from './TransactionCard'
import { fmtMoney } from '../utils'

type Props = { categories: string[]; payments: string[]; refreshKey: number; onChanged: () => void }
const input = 'min-w-0 rounded-lg border border-ink-200 bg-white px-2.5 py-2 text-[12px] text-ink-800 outline-none focus:border-ink-700'

export function MoneyPanel({ categories, payments, refreshKey, onChanged }: Props) {
  const [month, setMonth] = useState(() => { const now = new Date(); return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2, '0')}` })
  const [budgets, setBudgets] = useState<Budget[]>([])
  const [pending, setPending] = useState<Transaction[]>([])
  const [pendingCount, setPendingCount] = useState(0)
  const [total, setTotal] = useState(0)
  const [payable, setPayable] = useState(0)
  const [preference, setPreference] = useState<Preference>({ payment_method: '', rules: {} })
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('')
  const [event, setEvent] = useState('')
  const [merchant, setMerchant] = useState('')
  const [ruleCategory, setRuleCategory] = useState('餐饮')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')
  const load = useCallback(async () => {
    setError(''); setLoading(true)
    try {
      const [budgetResult, preferences, transactions] = await Promise.all([api.budgets(month), api.preferences(), api.transactions({ pending: true, limit: 500 })])
      setBudgets(budgetResult.items); setPreference(preferences); setPending(transactions.items); setPendingCount(transactions.total)
      setTotal(transactions.stats.outstanding); setPayable(transactions.stats.payable)
    } catch (err) { setError(err instanceof Error ? err.message : '加载失败') }
    finally { setLoading(false) }
  }, [month])
  useEffect(() => { void load() }, [load, refreshKey])
  const changed = () => { void load(); onChanged() }
  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError('')
    try { await operation(); changed() }
    catch (err) { setError(err instanceof Error ? err.message : '操作失败') }
    finally { setBusy(false) }
  }
  const filtered = pending.filter(row => filter === 'borrow' ? row.kind === 'borrow' : filter === 'reimbursement' ? row.settlementKind === 'reimbursement' : filter === 'receive' ? row.kind !== 'borrow' : true)

  return <div className="space-y-4">
    <div className="px-1"><h1 className="text-lg font-semibold text-ink-900">预算与资金往来</h1><p className="mt-1 text-[12px] leading-relaxed text-ink-400">预算按个人承担的净支出计算；回款和账户转账不会重复计入收入。</p></div>
    {error && <div role="alert" className="rounded-xl bg-red-50 p-3 text-[12px] text-red-600">{error}<button onClick={() => void load()} className="ml-3 underline">重新加载</button></div>}
    {loading && <div className="text-[12px] text-ink-400">正在同步…</div>}
    <section className="card space-y-3 p-4">
      <div className="flex items-center justify-between gap-3"><h2 className="text-[14px] font-medium">月预算</h2><input aria-label="预算月份" type="month" value={month} onChange={e => { if (e.target.value) setMonth(e.target.value) }} className={input} /></div>
      {budgets.map(budget => <BudgetProgress key={budget.id} budget={budget} onDelete={() => { if (!busy) void run(() => api.deleteBudget(budget.id)) }} />)}
      {!loading && budgets.length === 0 && <p className="text-[12px] text-ink-400">给这个月设一个可执行的花钱计划。</p>}
      <form className="grid grid-cols-2 gap-2" onSubmit={e => { e.preventDefault(); if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) { setError('预算金额需要大于0'); return } void run(async () => { await api.saveBudget({ month, amount: Number(amount), category, event }); setAmount('') }) }}>
        <select aria-label="预算分类" value={category} onChange={e => setCategory(e.target.value)} className={input}><option value="">全部分类</option>{categories.map(c => <option key={c}>{c}</option>)}</select>
        <input aria-label="预算事件" placeholder="事件，可不填" value={event} maxLength={64} onChange={e => setEvent(e.target.value)} className={input} />
        <input aria-label="预算金额" placeholder="预算金额（元）" inputMode="decimal" required value={amount} onChange={e => setAmount(e.target.value)} className={input} />
        <button disabled={busy} className="rounded-lg bg-ink-900 px-3 py-2 text-[12px] text-white disabled:opacity-40">保存预算</button>
      </form>
      <p className="text-[11px] text-ink-400">同一月份、分类和事件再次保存会更新金额。总预算与分类预算分别展示。</p>
    </section>
    <section className="card space-y-3 p-4">
      <h2 className="text-[14px] font-medium">待结清</h2>
      <div className="grid grid-cols-2 gap-3"><div className="rounded-xl bg-amber-50 p-3 text-[11px] text-amber-800">待收回<div className="mt-1 font-num text-xl font-semibold">¥{fmtMoney(total)}</div></div><div className="rounded-xl bg-ink-50 p-3 text-[11px] text-ink-500">待归还<div className="mt-1 font-num text-xl font-semibold text-ink-900">¥{fmtMoney(payable)}</div></div></div>
      <div className="flex flex-wrap gap-1.5">{[['all', '全部'], ['receive', '待收回'], ['borrow', '待归还'], ['reimbursement', '待报销']].map(([key,label]) => <button key={key} onClick={() => setFilter(key)} className={`rounded-full px-2.5 py-1 text-[11px] ${filter === key ? 'bg-ink-900 text-white' : 'bg-ink-50 text-ink-500'}`}>{label}</button>)}</div>
      {filtered.map(tx => <TransactionCard key={tx.id} tx={tx} categories={categories} payments={payments} onChanged={changed} onUpdate={async (id, patch) => { await api.updateTransaction(id, patch); changed() }} onDelete={async id => { await api.deleteTransaction(id); changed() }} />)}
      {!loading && filtered.length === 0 && <p className="py-2 text-[12px] text-ink-400">这部分已经全部结清。</p>}
      {pendingCount > pending.length && <p className="text-[12px] text-ink-400">还有{pendingCount - pending.length}笔，可在账单页勾选“只看待结清”继续查看。上方统计已包含全部记录。</p>}
    </section>
    <section className="card space-y-3 p-4">
      <h2 className="text-[14px] font-medium">记账习惯</h2>
      <label className="flex items-center justify-between gap-3 text-[12px] text-ink-500">默认付款方式<select aria-label="默认付款方式" value={preference.payment_method} disabled={busy} onChange={e => void run(() => api.savePreferences({ ...preference, payment_method: e.target.value }))} className={input}><option value="">不设置</option>{payments.map(p => <option key={p}>{p}</option>)}</select></label>
      <p className="text-[11px] text-ink-400">明确说出的付款方式优先；规则仅影响之后的新账单。</p>
      <h3 className="text-[12px] text-ink-600">商户分类规则</h3>
      {Object.entries(preference.rules).map(([name, value]) => <div key={name} className="flex justify-between gap-2 rounded-lg bg-ink-50 px-3 py-2 text-[12px]"><span>{name} → {value}</span><button disabled={busy} onClick={() => void run(() => { const rules = { ...preference.rules }; delete rules[name]; return api.savePreferences({ ...preference, rules }) })} className="text-ink-400 hover:text-red-600">删除规则</button></div>)}
      <form className="flex flex-wrap gap-2" onSubmit={e => { e.preventDefault(); if (!merchant.trim()) return; void run(async () => { await api.savePreferences({ ...preference, rules: { ...preference.rules, [merchant.trim()]: ruleCategory } }); setMerchant('') }) }}>
        <input aria-label="商户关键词" required maxLength={128} placeholder="商户关键词，如瑞幸" value={merchant} onChange={e => setMerchant(e.target.value)} className={`${input} flex-1`} />
        <select aria-label="规则分类" value={ruleCategory} onChange={e => setRuleCategory(e.target.value)} className={input}>{categories.map(c => <option key={c}>{c}</option>)}</select>
        <button disabled={busy} className="rounded-lg bg-ink-900 px-3 py-2 text-[12px] text-white disabled:opacity-40">记住</button>
      </form>
    </section>
  </div>
}
