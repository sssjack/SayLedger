import { useEffect, useState } from 'react'
import { api } from '../api'
import { Amount } from './Amount'

/**
 * 待结清摘要条。
 * 以前只有「我的 → 待结清」能看到，用户不知道外面还有多少钱没收回来。
 * 这里只放一条，点一下直接筛出这部分流水。
 */
export function SettlementBar({ refreshKey, onShow }: { refreshKey: number; onShow: () => void }) {
  const [data, setData] = useState<{ outstanding: number; payable: number; count: number } | null>(null)

  useEffect(() => {
    let alive = true
    api
      .transactions({ pending: true, limit: 1 })
      .then((result) => {
        if (!alive) return
        setData({
          outstanding: result.stats.outstanding ?? 0,
          payable: result.stats.payable ?? 0,
          count: result.total ?? 0,
        })
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [refreshKey])

  if (!data || data.count === 0) return null

  return (
    <button
      onClick={onShow}
      className="flex w-full items-center justify-between gap-2 rounded-xl bg-amber-50 px-3 py-2 text-left text-[12px] text-amber-900 transition hover:bg-amber-100/70"
    >
      <span className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="text-amber-700">待收回</span>
        <Amount value={data.outstanding} size={13} className="text-amber-900" />
        {data.payable > 0 && (
          <>
            <span className="ml-1 text-amber-700/80">待归还</span>
            <Amount value={data.payable} size={13} className="text-amber-900" />
          </>
        )}
      </span>
      <span className="shrink-0 text-amber-700/90">{data.count} 笔 ›</span>
    </button>
  )
}
