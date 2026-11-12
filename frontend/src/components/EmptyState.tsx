import type { ReactNode } from 'react'

type Props = {
  icon?: ReactNode
  title: string
  hint?: string
  action?: { label: string; onClick: () => void }
  className?: string
}

/** 全站统一空状态：图标 + 一句话 + 一个可执行动作。之前各地只有两行灰字。 */
export function EmptyState({ icon, title, hint, action, className = '' }: Props) {
  return (
    <div className={`flex flex-col items-center px-6 py-12 text-center ${className}`}>
      {icon && (
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-ink-100 text-ink-500">{icon}</span>
      )}
      <p className="mt-3 text-[13px] font-medium text-ink-700">{title}</p>
      {hint && <p className="mt-1 max-w-[280px] text-[12px] leading-relaxed text-ink-500">{hint}</p>}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 rounded-full bg-white px-3.5 py-1.5 text-[12px] font-medium text-accent-700 ring-1 ring-ink-200 transition hover:ring-ink-300"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
