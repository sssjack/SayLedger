import { useEffect, useState } from 'react'
import { api, type PeriodStats } from '../api'
import { Amount } from './Amount'
import { IconChart, IconClose } from '../icons'

/** 本周一的日期，用作「这周已经看过回顾」的键。 */
function weekKey(): string {
  const now = new Date()
  const date = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  date.setDate(date.getDate() - ((date.getDay() + 6) % 7))
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 10)
}

/**
 * 每周首次打开时，在对话顶部给一条回顾。
 * 没有定时任务，也不新增接口：读的是已有的 /api/stats?period=week，
 * 一周只出现一次，关掉就不再打扰。
 */
export function WeeklyDigest({ onOpenReport, onShown }: { onOpenReport: () => void; onShown?: () => void }) {
  const [stats, setStats] = useState<PeriodStats | null>(null)
  const [visible, setVisible] = useState(false)
  const storageKey = `sayledger.digest.${weekKey()}`

  useEffect(() => {
    let seen = false
    try {
      seen = window.localStorage.getItem(storageKey) === '1'
    } catch {
      seen = false
    }
    if (seen) return
    void api
      .stats('week')
      .then((data) => {
        if (data.current.count === 0) return
        setStats(data)
        setVisible(true)
        // 回顾卡是异步出现的，比首屏滚动晚一拍；出现后再把视口带到底部
        window.requestAnimationFrame(() => onShown?.())
        try {
          window.localStorage.setItem(storageKey, '1')
        } catch {
          /* 隐私模式下写不进去就算了，最多多看一次 */
        }
      })
      .catch(() => undefined)
  }, [storageKey])

  if (!visible || !stats) return null

  const change = stats.change_pct ?? 0
  const previousTotal = stats.previous?.total ?? 0
  const changeText =
    previousTotal === 0
      ? '上周还没有记录'
      : change === 0
        ? '和上周基本持平'
        : `比上周${change > 0 ? '多花' : '少花'} ${Math.abs(change)}%`

  return (
    <section className="animate-rise rounded-2xl border border-accent-100 bg-accent-50/50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-1.5 text-[12px] font-medium text-accent-700">
          <IconChart width={14} height={14} />
          本周回顾
        </div>
        <button
          onClick={() => setVisible(false)}
          aria-label="关闭本周回顾"
          className="-mr-1 -mt-1 flex h-6 w-6 items-center justify-center rounded-full text-accent-700/70 transition hover:bg-white/60"
        >
          <IconClose width={12} height={12} />
        </button>
      </div>

      <div className="mt-1.5 flex items-baseline gap-2">
        <Amount value={stats.current.total} size={26} className="text-ink-900" />
        <span className="text-[12px] text-ink-500">{stats.current.count} 笔</span>
      </div>

      <p className="mt-1 text-[12px] text-ink-600">
        {changeText}，日均 <Amount value={stats.current.daily_average ?? 0} size={12} className="text-ink-600" />
      </p>

      <button
        onClick={onOpenReport}
        className="mt-3 text-[12px] font-medium text-accent-700 underline-offset-2 hover:underline"
      >
        看看这周的钱花在哪 →
      </button>
    </section>
  )
}
