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

function parseHex(hex: string): [number, number, number] | null {
  const raw = hex.replace('#', '').trim()
  const full = raw.length === 3 ? raw.split('').map((char) => char + char).join('') : raw
  if (full.length !== 6 || !/^[0-9a-f]{6}$/i.test(full)) return null
  return [parseInt(full.slice(0, 2), 16), parseInt(full.slice(2, 4), 16), parseInt(full.slice(4, 6), 16)]
}

/** 向自身灰度混合，降低饱和度。12 个分类色同屏时不再像调色板；小圆点仍用原色。 */
export function mute(hex: string, amount = 0.16): string {
  const rgb = parseHex(hex)
  if (!rgb) return hex
  const gray = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
  const mix = (value: number) => Math.round(value + (gray - value) * amount)
  return `rgb(${mix(rgb[0])} ${mix(rgb[1])} ${mix(rgb[2])})`
}

/** 混白，用于分类图标的浅色底 */
export function tint(hex: string, amount = 0.9): string {
  const rgb = parseHex(hex)
  if (!rgb) return hex
  const mix = (value: number) => Math.round(value + (255 - value) * amount)
  return `rgb(${mix(rgb[0])} ${mix(rgb[1])} ${mix(rgb[2])})`
}
