import { useCallback, useEffect, useState } from 'react'
import { api, type Memo } from '../api'

type Props = { refreshKey: number; onChanged: () => void }
const input = 'min-w-0 rounded-lg border border-ink-200 bg-white px-2.5 py-2 text-[12px] text-ink-800 outline-none focus:border-ink-700'

const PUSH_LABELS: Record<string, string> = {
  wechat_queued: '已排队发微信',
  web_only_no_binding: '仅网页提醒（未绑微信）',
  web_only_no_context: '仅网页提醒（微信会话已过期，先在微信里发条消息）',
  wechat_failed: '微信发送失败',
}

function defaultTrigger(): string {
  const next = new Date(Date.now() + 60 * 60 * 1000)
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}T${pad(next.getHours())}:${pad(next.getMinutes())}`
}

export function MemosPanel({ refreshKey, onChanged }: Props) {
  const [items, setItems] = useState<Memo[]>([])
  const [content, setContent] = useState('')
  const [triggerAt, setTriggerAt] = useState(defaultTrigger)
  const [recurrence, setRecurrence] = useState('none')
  const [intervalDays, setIntervalDays] = useState(4)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setError('')
    setLoading(true)
    try {
      const result = await api.memos()
      setItems(result.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { void load() }, [load, refreshKey])

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await operation()
      await load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const active = items.filter((item) => item.status === 'active')
  const finished = items.filter((item) => item.status !== 'active')

  const renderItem = (memo: Memo) => (
    <div key={memo.id} className="flex items-start gap-3 rounded-xl bg-ink-50 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[13px] font-medium text-ink-900">{memo.content}</span>
          {!!memo.stageDay && <span className="text-[10.5px] text-ink-400">计划第{memo.stageDay}天</span>}
          {memo.recurrenceLabel && (
            <span className="rounded-full bg-indigo-50 px-1.5 py-0.5 text-[10.5px] text-indigo-600">{memo.recurrenceLabel}</span>
          )}
          {memo.status === 'done' && <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10.5px] text-emerald-600">已提醒</span>}
          {memo.status === 'cancelled' && <span className="rounded-full bg-ink-100 px-1.5 py-0.5 text-[10.5px] text-ink-400">已取消</span>}
        </div>
        <div className="mt-0.5 text-[11.5px] text-ink-400">
          {memo.status === 'active' ? `下一次提醒：${memo.nextTriggerAt}` : `提醒时间：${memo.nextTriggerAt}`}
          {memo.pushStatus && PUSH_LABELS[memo.pushStatus] ? ` · ${PUSH_LABELS[memo.pushStatus]}` : ''}
        </div>
      </div>
      {memo.status === 'active' && (
        <div className="flex shrink-0 gap-1.5">
          <button disabled={busy} onClick={() => void run(() => api.updateMemo(memo.id, { status: 'done' }))} className="rounded-lg bg-white px-2 py-1 text-[11px] text-emerald-600 ring-1 ring-ink-100 disabled:opacity-40">完成</button>
          <button disabled={busy} onClick={() => void run(() => api.updateMemo(memo.id, { status: 'cancelled' }))} className="rounded-lg bg-white px-2 py-1 text-[11px] text-ink-500 ring-1 ring-ink-100 disabled:opacity-40">取消</button>
        </div>
      )}
      {memo.status !== 'active' && (
        <button disabled={busy} onClick={() => void run(() => api.deleteMemo(memo.id))} className="shrink-0 rounded-lg bg-white px-2 py-1 text-[11px] text-ink-400 ring-1 ring-ink-100 disabled:opacity-40">删除</button>
      )}
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="px-1">
        <h1 className="text-lg font-semibold text-ink-900">备忘录</h1>
        <p className="mt-1 text-[12px] leading-relaxed text-ink-400">
          也可以直接在对话里说「下周三提醒我交房租」「每周三下午3点提醒我交水电费」，到点我会来喊你；绑了微信还会在微信里提醒。
        </p>
      </div>
      {error && <div role="alert" className="rounded-xl bg-red-50 p-3 text-[12px] text-red-600">{error}<button onClick={() => void load()} className="ml-3 underline">重新加载</button></div>}
      {loading && <div className="text-[12px] text-ink-400">正在同步…</div>}
      <section className="card space-y-3 p-4">
        <h2 className="text-[14px] font-medium">待提醒</h2>
        {active.map(renderItem)}
        {!loading && active.length === 0 && <p className="text-[12px] text-ink-400">还没有待提醒的备忘，去对话里说一句，或者在下面手动加一条。</p>}
        <form
          className="grid grid-cols-2 gap-2 border-t border-ink-50 pt-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!content.trim()) { setError('备忘内容不能为空'); return }
            void run(async () => {
              await api.createMemo({ content: content.trim(), trigger_at: triggerAt.replace('T', ' '), recurrence,
                interval_days: recurrence === 'interval' ? intervalDays : undefined })
              setContent('')
            })
          }}
        >
          <input aria-label="备忘内容" required maxLength={200} placeholder="要提醒的事，如交房租" value={content} onChange={(e) => setContent(e.target.value)} className={`${input} col-span-2`} />
          <input aria-label="提醒时间" type="datetime-local" required value={triggerAt} onChange={(e) => setTriggerAt(e.target.value)} className={input} />
          <div className="flex gap-2">
            <select aria-label="重复方式" value={recurrence} onChange={(e) => setRecurrence(e.target.value)} className={`${input} flex-1`}>
              <option value="none">不重复</option>
              <option value="daily">每天</option>
              <option value="weekly">每周</option>
              <option value="interval">每隔几天</option>
            </select>
            <button disabled={busy} className="rounded-lg bg-ink-900 px-3 py-2 text-[12px] text-white disabled:opacity-40">添加</button>
          </div>
          {recurrence === 'interval' && <label className="col-span-2 flex items-center gap-2 text-[12px] text-ink-600">
            每 <input aria-label="循环间隔天数" type="number" min={1} max={365} required value={intervalDays}
              onChange={(event) => setIntervalDays(Number(event.target.value))} className={`${input} w-20`} /> 天重复一次
          </label>}
        </form>
        <p className="text-[11px] text-ink-400">每隔几天会从首次提醒日期开始循环；也可以在聊天中查询或修改整份计划。</p>
      </section>
      {finished.length > 0 && (
        <section className="card space-y-3 p-4">
          <h2 className="text-[14px] font-medium">已结束</h2>
          {finished.map(renderItem)}
        </section>
      )}
    </div>
  )
}
