import { useEffect, useRef, useState } from 'react'
import { IconChevron } from '../icons'

type Option = { value: string; label: string }

type Props = {
  label: string
  value: string
  options: Option[]
  onChange: (value: string) => void
}

/**
 * 筛选 chip + 弹层。
 * 原来三个原生 <select> 用浏览器默认样式，和全站胶囊语言完全断裂。
 */
export function FilterChip({ label, value, options, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const active = value !== ''
  const current = options.find((option) => option.value === value)

  const item = (optionValue: string, optionLabel: string) => (
    <button
      key={optionValue || 'all'}
      role="option"
      aria-selected={value === optionValue}
      onClick={() => {
        onChange(optionValue)
        setOpen(false)
      }}
      className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-[12px] transition ${
        value === optionValue ? 'bg-accent-50 text-accent-700' : 'text-ink-700 hover:bg-ink-50'
      }`}
    >
      {optionLabel}
      {value === optionValue && <span className="h-1.5 w-1.5 rounded-full bg-accent-600" />}
    </button>
  )

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`flex items-center gap-1 rounded-full px-2.5 py-1.5 text-[12px] font-medium transition ${
          active
            ? 'bg-accent-50 text-accent-700 ring-1 ring-accent-200'
            : 'bg-ink-50 text-ink-600 hover:bg-ink-100'
        }`}
      >
        {current?.label ?? label}
        <IconChevron width={12} height={12} className={`rotate-90 transition ${open ? '-rotate-90' : ''}`} />
      </button>
      {open && (
        <div
          role="listbox"
          aria-label={label}
          className="absolute left-0 top-full z-30 mt-1 max-h-64 w-44 overflow-auto rounded-xl border border-ink-100 bg-white p-1 shadow-float animate-rise"
        >
          {item('', label)}
          {options.map((option) => item(option.value, option.label))}
        </div>
      )}
    </div>
  )
}
