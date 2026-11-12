import type { Budget } from '../api'
import { Amount } from './Amount'

export function BudgetProgress({ budget, onDelete }: { budget: Budget; onDelete?: () => void }) {
  const over = budget.remaining < 0
  return <div className="rounded-xl border border-ink-100 bg-white p-3">
    <div className="flex items-center justify-between gap-3 text-[12px]">
      <span className="font-medium text-ink-800">{budget.label}</span>
      <span className={`flex items-baseline gap-1 ${over ? 'text-red-600' : 'text-ink-500'}`}>{over ? '超出' : '剩余'}<Amount value={Math.abs(budget.remaining)} size={13} className={over ? 'text-red-600' : 'text-ink-800'} /></span>
    </div>
    <div className="my-2 h-1.5 overflow-hidden rounded-full bg-ink-100" role="progressbar" aria-label={budget.label} aria-valuenow={budget.percent} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full ${over ? 'bg-red-400' : budget.percent > 80 ? 'bg-amber-400' : 'bg-accent-600'}`} style={{ width: `${Math.min(100, Math.max(0, budget.percent))}%` }} />
    </div>
    <div className="flex items-center justify-between text-[12px] text-ink-500"><span className="flex items-baseline gap-1">已用<Amount value={budget.spent} size={11} className="text-ink-600" /><span>/</span><Amount value={budget.amount} size={11} className="text-ink-400" /></span>{onDelete && <button onClick={onDelete} className="hover:text-red-600">取消预算</button>}</div>
  </div>
}
