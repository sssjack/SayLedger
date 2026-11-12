import { useEffect, useState } from 'react'
import { api, type Budget } from '../api'
import { Amount } from './Amount'

function currentMonth(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

/**
 * 本月预算条。
 * 预算以前只存在于「我的」里，设完就再也没出现过；这里把最紧张的那一项放回账单页，
 * 让「设预算」和「看进度」在同一个地方闭环。
 */
export function BudgetStrip({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<Budget[]>([])

  useEffect(() => {
    let alive = true
    api
      .budgets(currentMonth())
      .then((result) => {
        if (alive) setItems(result.items)
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [refreshKey])

  if (items.length === 0) return null

  const urgent = [...items].sort((a, b) => b.percent - a.percent)[0]
  const over = urgent.remaining < 0
  const width = Math.min(100, Math.max(3, urgent.percent))

  return (
    <div className="rounded-xl border border-ink-100 bg-white px-3 py-2">
      <div className="flex items-baseline justify-between gap-2 text-[12px]">
        <span className="truncate text-ink-600">
          {over && <span className="font-medium text-red-600">已超支 · </span>}
          本月预算{urgent.label && urgent.label !== '总预算' ? ` · ${urgent.label}` : ''}
        </span>
        <span className={`flex shrink-0 items-baseline gap-1 ${over ? 'text-red-600' : 'text-ink-500'}`}>
          {over ? '超' : '剩'}
          <Amount value={Math.abs(urgent.remaining)} size={13} className={over ? 'text-red-600' : 'text-ink-800'} />
        </span>
      </div>
      <div
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-100"
        role="progressbar"
        aria-label={`${urgent.label}预算使用进度`}
        aria-valuenow={urgent.percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-full ${over ? 'bg-red-400' : urgent.percent >= 80 ? 'bg-amber-400' : 'bg-accent-600'}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <div className="mt-1 flex items-baseline justify-between text-[12px] text-ink-400">
        <span className="flex items-baseline gap-1">
          已用 <Amount value={urgent.spent} size={11} className="text-ink-500" />
          <span>/</span>
          <Amount value={urgent.amount} size={11} className="text-ink-400" />
        </span>
        {items.length > 1 && <span>另有 {items.length - 1} 项</span>}
      </div>
    </div>
  )
}
