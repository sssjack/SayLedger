const money = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })

export function fmtMoney(value: number, withSign = false): string {
  const rounded = Math.round(value * 100) / 100
  const body = money.format(Math.abs(rounded))
  if (withSign) return `${rounded < 0 ? '-' : '+'}${body}`
  return `${rounded < 0 ? '-' : ''}${body}`
}

export function fmtDateLabel(iso: string): string {
  const today = new Date()
  const date = new Date(iso + 'T00:00:00')
  const diff = Math.round((new Date(today.toDateString()).getTime() - new Date(date.toDateString()).getTime()) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '昨天'
  if (diff === 2) return '前天'
  if (date.getFullYear() === today.getFullYear()) return `${date.getMonth() + 1}月${date.getDate()}日`
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`
}

export function fmtTime(iso: string): string {
  const parts = iso.split(' ')
  return parts[1] && parts[1] !== '00:00' ? parts[1] : ''
}

export function monthLabel(iso: string): string {
  const [y, m] = iso.split('-')
  return `${y.slice(2)}年${Number(m)}月`
}

export function groupByDate<T extends { occurredAt: string }>(items: T[]): { date: string; items: T[] }[] {
  const map = new Map<string, T[]>()
  for (const item of items) {
    const key = item.occurredAt.slice(0, 10)
    const bucket = map.get(key) ?? []
    bucket.push(item)
    map.set(key, bucket)
  }
  return [...map.entries()].map(([date, list]) => ({ date, items: list }))
}
