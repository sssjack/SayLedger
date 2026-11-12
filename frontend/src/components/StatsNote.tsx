import { useState } from 'react'
import { IconChevron, IconInfo } from '../icons'

type Props = {
  items: string[]
  label?: string
  defaultOpen?: boolean
}

/**
 * 统计口径说明。
 * 原先是两段 11px 的常驻文字，既难读又占位；现在默认收起，需要核对数字时再展开。
 */
export function StatsNote({ items, label = '统计口径', defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  if (items.length === 0) return null

  return (
    <div className="px-1">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-1 rounded-xl py-0.5 text-[12px] text-ink-500 transition hover:text-ink-700"
      >
        <IconInfo width={13} height={13} />
        {label}
        <IconChevron width={12} height={12} className={`transition ${open ? 'rotate-90' : ''}`} />
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1 rounded-xl bg-ink-50 px-3 py-2.5">
          {items.map((item) => (
            <li key={item} className="prose-note flex gap-1.5">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-300" />
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
