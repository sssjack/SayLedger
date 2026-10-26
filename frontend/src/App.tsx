import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Category, type ChatMessage, type PaymentMethod } from './api'
import { Composer } from './components/Composer'
import { MessageBubble } from './components/MessageBubble'
import { BillsPanel } from './components/BillsPanel'
import { ReportPanel } from './components/ReportPanel'
import { MoneyPanel } from './components/MoneyPanel'
import { MemosPanel } from './components/MemosPanel'
import { UsersPanel } from './components/UsersPanel'
import { Chart, TOOLTIP_STYLE } from './components/Chart'
import { fmtMoney } from './utils'
import {
  CategoryIcon,
  IconChart,
  IconList,
  IconLogout,
  IconSpark,
} from './icons'
import { ICON_MAP } from './components/TransactionCard'
import { APP_NAME, APP_TAGLINE } from './brand'
import assistantAvatar from './assets/assistant-avatar.webp'

type Tab = 'chat' | 'bills' | 'report' | 'plan' | 'memos'

const SUGGESTIONS = [
  '午饭花了 28',
  '今天工资到账 8500',
  '聚餐付了300，含我3个人AA',
  '这个月餐饮预算1500',
  '还有谁没还我',
  '我昨天花了哪些钱',
  '明天下午3点提醒我开会',
  '每周三下午3点提醒我交水电费',
]

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [me, setMe] = useState<{ id: number; username: string } | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [payments, setPayments] = useState<PaymentMethod[]>([])
  const [tab, setTab] = useState<Tab>('chat')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [todayTotal, setTodayTotal] = useState(0)
  const [weekTotal, setWeekTotal] = useState(0)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const bootstrap = useCallback(async () => {
    try {
      const meData = await api.me()
      setMe(meData)
      const [meta, history, stats] = await Promise.all([api.meta(), api.messages(), api.stats('week')])
      setCategories(meta.categories)
      setPayments(meta.payments)
      setMessages(history.messages)
      setTodayTotal(stats.today_total)
      setWeekTotal(stats.current.total)
      setAuthed(true)
    } catch {
      setAuthed(false)
    }
  }, [])

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  useEffect(() => {
    if (tab !== 'chat') return
    bottomRef.current?.scrollIntoView({ behavior: messages.length > 2 ? 'smooth' : 'auto' })
  }, [messages, tab])

  const refreshNumbers = useCallback(async () => {
    setRefreshKey((key) => key + 1)
    try {
      const stats = await api.stats('week')
      setTodayTotal(stats.today_total)
      setWeekTotal(stats.current.total)
    } catch {
      /* ignore */
    }
  }, [])

  const send = useCallback(
    async (text: string, imageIds: string[] = [], confirmDuplicate = false) => {
      if (sending) return
      setError('')
      const localId = Date.now()
      const optimistic: ChatMessage = {
        id: -localId,
        role: 'user',
        content: text || '（发送了一张图片）',
        payload: { images: [] },
        createdAt: '',
      }
      setMessages((prev) => [...prev, optimistic])
      setSending(true)
      try {
        const result = await api.chat(text, imageIds, confirmDuplicate)
        setMessages((prev) => [
          ...prev,
          {
            id: localId,
            role: 'assistant',
            content: result.reply,
            payload: result.payload,
            createdAt: '',
          },
        ])
        const history = await api.messages()
        setMessages(history.messages)
        void refreshNumbers()
      } catch (err) {
        const message = err instanceof Error ? err.message : '出了点问题'
        if (message === 'unauthorized') {
          setAuthed(false)
        } else {
          setError(message)
          setMessages((prev) => [
            ...prev,
            {
              id: localId + 1,
              role: 'assistant',
              content: `抱歉，${message}`,
              payload: { kind: 'error' },
              createdAt: '',
            },
          ])
        }
      } finally {
        setSending(false)
      }
    },
    [refreshNumbers, sending],
  )

  const syncLedger = useCallback(async () => {
    try { const history = await api.messages(); setMessages(history.messages); await refreshNumbers() }
    catch (err) { setError(err instanceof Error ? err.message : '同步失败') }
  }, [refreshNumbers])

  useEffect(() => {
    if (!authed) return
    const sync = () => { if (document.visibilityState === 'visible' && !sending) void syncLedger() }
    window.addEventListener('focus', sync)
    document.addEventListener('visibilitychange', sync)
    return () => { window.removeEventListener('focus', sync); document.removeEventListener('visibilitychange', sync) }
  }, [authed, sending, syncLedger])

  const deleteTx = useCallback(
    async (id: number) => {
      await api.deleteTransaction(id)
      // 记录可能同时出现在「刚记的账」和「改删候选」里，两处都要移除
      setMessages((prev) =>
        prev.map((message) => ({
          ...message,
          payload: {
            ...message.payload,
            transactions: message.payload.transactions?.filter((tx) => tx.id !== id),
            candidates: message.payload.candidates?.filter((tx) => tx.id !== id),
          },
        })),
      )
      void syncLedger()
    },
    [syncLedger],
  )

  const updateTx = useCallback(
    async (id: number, patch: Record<string, unknown>) => {
      const result = await api.updateTransaction(id, patch as never)
      // 用户改完后，卡片立刻显示新值，不用重新拉一遍对话
      setMessages((prev) =>
        prev.map((message) => ({
          ...message,
          payload: {
            ...message.payload,
            transactions: message.payload.transactions?.map((tx) => (tx.id === id ? result.item : tx)),
            candidates: message.payload.candidates?.map((tx) => (tx.id === id ? result.item : tx)),
          },
        })),
      )
      void syncLedger()
    },
    [syncLedger],
  )

  if (authed === null) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-ink-200 border-t-ink-800" />
      </div>
    )
  }

  if (!authed) return <Login onDone={() => void bootstrap()} />

  const categoryNames = categories.map((item) => item.name)
  const paymentNames = payments.map((item) => item.name)

  return (
    <div className="mx-auto flex h-full w-full max-w-[1180px] flex-col bg-ink-50 lg:flex-row lg:gap-6 lg:px-6 lg:py-5">
      {/* 侧边栏：桌面端导航；移动端收进底部 tab */}
      <aside className="hidden w-[236px] shrink-0 flex-col lg:flex">
        <div className="flex items-center gap-2.5 px-1.5">
          <Logo />
          <div>
            <div className="text-[14px] font-semibold tracking-tight text-ink-900">{APP_NAME}</div>
            <div className="text-[11px] text-ink-400">{APP_TAGLINE}</div>
          </div>
        </div>

        <nav className="mt-7 space-y-1">
          {(
            [
              { key: 'chat', label: '对话', icon: IconSpark },
              { key: 'bills', label: '账单', icon: IconList },
              { key: 'report', label: '报告', icon: IconChart },
              { key: 'memos', label: '备忘', icon: IconList },
              { key: 'plan', label: '管理', icon: IconList },
            ] as const
          ).map((item) => {
            const active = tab === item.key
            const Icon = item.icon
            return (
              <button
                key={item.key}
                onClick={() => setTab(item.key)}
                className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13.5px] font-medium transition ${
                  active ? 'bg-white text-ink-900 shadow-card' : 'text-ink-500 hover:bg-white/60 hover:text-ink-800'
                }`}
              >
                <Icon width={17} height={17} />
                {item.label}
              </button>
            )
          })}
        </nav>

        <div className="mt-6 space-y-3">
          <div className="card p-4">
            <div className="text-[11.5px] text-ink-400">今天个人净支出</div>
            <div className="mt-0.5 font-num text-[22px] font-semibold tracking-tight tabular-nums">
              ¥{fmtMoney(todayTotal)}
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-ink-50 pt-2.5 text-[11.5px]">
              <span className="text-ink-400">近 7 天</span>
              <span className="font-num font-medium tabular-nums text-ink-700">¥{fmtMoney(weekTotal)}</span>
            </div>
          </div>

          <div className="card p-4">
            <div className="mb-2.5 text-[11.5px] text-ink-400">分类</div>
            <div className="flex flex-wrap gap-1.5">
              {categories.slice(0, 8).map((item) => (
                <span
                  key={item.name}
                  title={item.desc}
                  className="flex h-7 w-7 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${item.color}12`, color: item.color }}
                >
                  <CategoryIcon name={ICON_MAP[item.name] ?? item.icon} size={14} />
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-auto pt-4">
          <button
            onClick={async () => {
              await api.logout()
              setAuthed(false)
            }}
            className="flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] text-ink-400 transition hover:bg-white hover:text-ink-700"
          >
            <IconLogout width={14} height={14} />
            退出登录
          </button>
        </div>
      </aside>

      {/* 主区域 */}
      <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-white lg:rounded-3xl lg:shadow-card">
        <header className="z-10 flex shrink-0 items-center gap-3 border-b border-ink-50 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
          <Logo size={26} />
          <div className="min-w-0 flex-1">
            <div className="text-[13.5px] font-semibold leading-tight tracking-tight">{APP_NAME}</div>
            <div className="text-[10.5px] text-ink-400">今天 ¥{fmtMoney(todayTotal)}</div>
          </div>
        </header>

        {tab === 'chat' && (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto w-full max-w-2xl px-4 pb-2 pt-5">
              <div className="mb-4 flex items-center justify-between gap-2 text-[11px] text-ink-400"><span>收支 · 退款 · AA · 报销 · 预算 · 备忘提醒</span><button disabled={sending} onClick={() => void send('撤销上一步', [])} className="rounded-full bg-ink-50 px-2.5 py-1.5 text-ink-500 hover:bg-ink-100 disabled:opacity-40">撤销上一步</button></div>
              {messages.length === 0 ? (
                <EmptyState
                  todayTotal={todayTotal}
                  onPick={(text) => void send(text, [])}
                />
              ) : (
                <div className="space-y-5">
                  {messages.map((message) => (
                    <MessageBubble
                      key={message.id}
                      message={message}
                      categories={categoryNames}
                      payments={paymentNames}
                      onUpdate={updateTx}
                      onDelete={deleteTx}
                      onLedgerChange={() => void syncLedger()}
                      onSend={(text, images, confirm) => void send(text, images, confirm)}
                      disabled={sending}
                    />
                  ))}
                  {sending && (
                    <div className="flex animate-rise gap-2.5">
                      <img src={assistantAvatar} alt="小助手" className="mt-0.5 h-7 w-7 shrink-0 rounded-full object-cover" />
                      <div className="flex items-center gap-1 pt-1.5">
                        {[0, 1, 2].map((index) => (
                          <span
                            key={index}
                            className="h-1.5 w-1.5 animate-pulseSoft rounded-full bg-ink-300"
                            style={{ animationDelay: `${index * 0.16}s` }}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              )}
            </div>
          </div>
        )}

        {tab === 'bills' && (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto max-w-2xl px-4 py-4">
              <BillsPanel
                categories={categoryNames}
                payments={payments}
                refreshKey={refreshKey}
                onChanged={() => void refreshNumbers()}
              />
            </div>
          </div>
        )}

        {tab === 'report' && (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto max-w-2xl px-4 py-4">
              <ReportPanel refreshKey={refreshKey} />
            </div>
          </div>
        )}

        {tab === 'memos' && (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto max-w-2xl px-4 py-4">
              <MemosPanel refreshKey={refreshKey} onChanged={() => void refreshNumbers()} />
            </div>
          </div>
        )}

        {tab === 'plan' && <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain"><div className="mx-auto max-w-2xl space-y-4 px-4 py-4">{me?.username === 'admin' && <UsersPanel />}{/* 管理页：预算与偏好是每个租户自己的，账号管理只给 admin */}<MoneyPanel categories={categoryNames} payments={paymentNames} refreshKey={refreshKey} onChanged={() => void syncLedger()} /></div></div>}

        {tab === 'chat' && (
          <div className="shrink-0">
            {error && (
              <div className="mx-auto mb-1 w-full max-w-2xl px-4">
                <div className="rounded-lg bg-red-50 px-3 py-1.5 text-[11.5px] text-red-600">{error}</div>
              </div>
            )}
            <Composer onSend={send} disabled={sending} />
          </div>
        )}
      </main>

      {/* 移动端底部导航 */}
      <nav className="z-20 flex shrink-0 items-center justify-around border-t border-ink-100 bg-white/95 px-2 pb-[max(6px,env(safe-area-inset-bottom))] pt-1.5 backdrop-blur lg:hidden">
        {(
          [
            { key: 'chat', label: '对话', icon: IconSpark },
            { key: 'bills', label: '账单', icon: IconList },
            { key: 'report', label: '报告', icon: IconChart },
            { key: 'memos', label: '备忘', icon: IconList },
            { key: 'plan', label: '管理', icon: IconList },
          ] as const
        ).map((item) => {
          const active = tab === item.key
          const Icon = item.icon
          return (
            <button
              key={item.key}
              onClick={() => setTab(item.key)}
              className={`flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[10.5px] font-medium transition ${
                active ? 'text-ink-900' : 'text-ink-400'
              }`}
            >
              <Icon width={19} height={19} />
              {item.label}
            </button>
          )
        })}
      </nav>
    </div>
  )
}

function Logo({ size = 30 }: { size?: number }) {
  return (
    <img
      src={assistantAvatar}
      alt={APP_NAME}
      className="shrink-0 rounded-full object-cover"
      style={{ width: size, height: size }}
    />
  )
}

function EmptyState({ todayTotal, onPick }: { todayTotal: number; onPick: (text: string) => void }) {
  return (
    <div className="pt-6 sm:pt-14">
      <img src={assistantAvatar} alt={APP_NAME} className="mx-auto h-12 w-12 rounded-full object-cover shadow-float" />
      <h1 className="mt-4 text-center text-[19px] font-semibold tracking-tight text-ink-900">
        今天花了多少？
      </h1>
      <p className="mx-auto mt-1.5 max-w-[300px] text-center text-[13px] leading-relaxed text-ink-400">
        说一句话、发一张小票照片，我来帮你记、帮你分类、帮你算清楚。
      </p>

      {todayTotal > 0 && (
        <div className="mx-auto mt-5 w-fit rounded-full bg-ink-50 px-3.5 py-1.5 text-[12px] text-ink-500">
          今天已记 <b className="font-num font-semibold text-ink-900">¥{fmtMoney(todayTotal)}</b>
        </div>
      )}

      <div className="mx-auto mt-7 grid max-w-[420px] grid-cols-1 gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => onPick(text)}
            className="group flex items-center gap-2.5 rounded-xl border border-ink-100 bg-white px-3.5 py-3 text-left transition hover:border-ink-200 hover:shadow-card"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-ink-50 text-ink-400 transition group-hover:bg-ink-900 group-hover:text-white">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </span>
            <span className="truncate text-[13px] text-ink-700">{text}</span>
          </button>
        ))}
      </div>

      <MiniWeekly />
    </div>
  )
}

function MiniWeekly() {
  const [series, setSeries] = useState<{ date: string; value: number }[]>([])
  useEffect(() => {
    void api
      .stats('week')
      .then((data) => setSeries(data.daily))
      .catch(() => undefined)
  }, [])
  const total = series.reduce((sum, item) => sum + item.value, 0)
  if (series.length === 0 || total === 0) return null

  const max = Math.max(...series.map((item) => item.value), 1)
  const option = {
    grid: { left: 0, right: 0, top: 6, bottom: 0 },
    tooltip: {
      ...TOOLTIP_STYLE,
      trigger: 'item',
      formatter: (p: { name: string; value: number }) => `${p.name}&nbsp;&nbsp;<b>¥${fmtMoney(p.value)}</b>`,
    },
    xAxis: { type: 'category', show: false, data: series.map((item) => item.date.slice(5)) },
    yAxis: { type: 'value', show: false, max: max * 1.15 },
    series: [
      {
        type: 'bar',
        data: series.map((item) => item.value),
        itemStyle: { color: '#d5d9e2', borderRadius: [4, 4, 0, 0] },
        emphasis: { itemStyle: { color: '#4f46e5' } },
        barWidth: '46%',
      },
    ],
  }

  return (
    <div className="mx-auto mt-8 max-w-[420px] rounded-2xl border border-ink-100 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <span className="text-[11.5px] text-ink-400">近 7 天</span>
        <span className="font-num text-[13px] font-semibold tabular-nums">¥{fmtMoney(total)}</span>
      </div>
      <Chart option={option} height={54} className="mt-2" />
    </div>
  )
}

function Login({ onDone }: { onDone: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password.trim()) return
    setBusy(true)
    setError('')
    try {
      if (mode === 'register') {
        await api.register(username.trim(), password)
      } else {
        await api.login(username.trim(), password)
      }
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : mode === 'register' ? '注册失败' : '登录失败')
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (next: 'login' | 'register') => {
    setMode(next)
    setError('')
  }

  return (
    <div className="flex h-full items-center justify-center px-6">
      <form onSubmit={submit} className="w-full max-w-[340px] animate-rise">
        <img src={assistantAvatar} alt={APP_NAME} className="mx-auto h-12 w-12 rounded-full object-cover shadow-float" />
        <h1 className="mt-5 text-center text-[19px] font-semibold tracking-tight">{APP_NAME}</h1>
        <p className="mt-1.5 text-center text-[12.5px] text-ink-400">
          {mode === 'register' ? '只需要账号和密码，账号不重复就能注册' : '输入账号和密码，进入你的账本'}
        </p>

        <input
          type="text"
          autoFocus
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="账号"
          className="mt-6 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-center text-[14px] outline-none transition placeholder:text-ink-300 focus:border-ink-900"
        />
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="密码"
          className="mt-3 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-center text-[14px] tracking-widest outline-none transition placeholder:tracking-normal placeholder:text-ink-300 focus:border-ink-900"
        />
        {error && <div className="mt-2 text-center text-[12px] text-red-500">{error}</div>}
        <button
          type="submit"
          disabled={busy || !username.trim() || !password.trim()}
          className="mt-3 w-full rounded-xl bg-ink-900 py-2.5 text-[13.5px] font-medium text-white transition hover:bg-ink-800 disabled:opacity-40"
        >
          {busy ? '验证中…' : mode === 'register' ? '注册并进入' : '进入'}
        </button>
        <button
          type="button"
          onClick={() => switchMode(mode === 'register' ? 'login' : 'register')}
          className="mt-3 w-full text-center text-[12.5px] text-ink-500 underline-offset-2 hover:text-ink-900 hover:underline"
        >
          {mode === 'register' ? '已有账号？去登录' : '没有账号？注册一个'}
        </button>
      </form>
    </div>
  )
}
