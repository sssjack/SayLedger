export type HolidayKind = 'holiday' | 'workday'

export interface HolidayInfo {
  /** 节日名，如“春节”；调休上班日为“调休上班”。 */
  name: string
  kind: HolidayKind
}

const pad = (value: number) => String(value).padStart(2, '0')

/**
 * 法定节假日与调休上班日（按“YYYY-MM-DD”查）。
 * 来源：国务院办公厅《关于2026年部分节假日安排的通知》（2025-11-04 发布）、
 * 《关于2027年部分节假日安排的通知》（2026-11-05 发布）。
 * 静态数据，不随账单变化；后续年份按同样格式在 buildHolidays 里追加即可。
 */
function buildHolidays(): Record<string, HolidayInfo> {
  const map: Record<string, HolidayInfo> = {}
  const holiday = (name: string, start: string, end: string = start) => {
    const [y, m, d] = start.split('-').map(Number)
    const cur = new Date(y, m - 1, d)
    const [ey, em, ed] = end.split('-').map(Number)
    const last = new Date(ey, em - 1, ed)
    while (cur <= last) {
      const key = `${cur.getFullYear()}-${pad(cur.getMonth() + 1)}-${pad(cur.getDate())}`
      map[key] = { name, kind: 'holiday' }
      cur.setDate(cur.getDate() + 1)
    }
  }
  const workday = (date: string) => {
    map[date] = { name: '调休上班', kind: 'workday' }
  }

  // 2026 年
  holiday('元旦', '2026-01-01', '2026-01-03')
  workday('2026-01-04')
  holiday('春节', '2026-02-15', '2026-02-23')
  workday('2026-02-14')
  workday('2026-02-28')
  holiday('清明节', '2026-04-04', '2026-04-06')
  holiday('劳动节', '2026-05-01', '2026-05-05')
  workday('2026-05-09')
  holiday('端午节', '2026-06-19', '2026-06-21')
  holiday('中秋节', '2026-09-25', '2026-09-27')
  holiday('国庆节', '2026-10-01', '2026-10-07')
  workday('2026-09-20')
  workday('2026-10-10')

  // 2027 年
  holiday('元旦', '2027-01-01', '2027-01-03')
  holiday('春节', '2027-02-05', '2027-02-13')
  workday('2027-01-31')
  workday('2027-02-14')
  holiday('清明节', '2027-04-03', '2027-04-05')
  holiday('劳动节', '2027-05-01', '2027-05-05')
  workday('2027-05-08')
  holiday('端午节', '2027-06-09')
  holiday('中秋节', '2027-09-15')
  holiday('国庆节', '2027-10-01', '2027-10-07')
  workday('2027-09-26')
  workday('2027-10-09')

  return map
}

export const HOLIDAYS: Record<string, HolidayInfo> = buildHolidays()

export function holidayOf(date: string): HolidayInfo | undefined {
  return HOLIDAYS[date]
}

/** 是否为该假期的第一天：格子里只在首日写节日名，其余放假日写“休”。 */
export function isHolidayStart(date: string): boolean {
  const info = HOLIDAYS[date]
  if (!info || info.kind !== 'holiday') return false
  const [y, m, d] = date.split('-').map(Number)
  const prev = new Date(y, m - 1, d - 1)
  const prevKey = `${prev.getFullYear()}-${pad(prev.getMonth() + 1)}-${pad(prev.getDate())}`
  return HOLIDAYS[prevKey]?.name !== info.name
}
