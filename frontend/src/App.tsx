import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Category, type ChatMessage, type PaymentMethod } from './api'
import { Composer } from './components/Composer'
import { MessageBubble } from './components/MessageBubble'
import { BillsPage } from './components/BillsPage'
import { MoneyPanel } from './components/MoneyPanel'
import { MemosPanel } from './components/MemosPanel'
import { UsersPanel } from './components/UsersPanel'
import { UndoToast } from './components/UndoToast'
import { Amount } from './components/Amount'
import { readQuery, updateQuery } from './urlState'
import { mute, tint } from './utils'
import { CategoryIcon, IconBell, IconList, IconLogout, IconPlus, IconSearch, IconSpark, IconUser } from './icons'
import { ICON_MAP } from './components/TransactionCard'
import { WeeklyDigest } from './components/WeeklyDigest'
import { APP_NAME, APP_TAGLINE } from './brand'
import assistantAvatar from './assets/assistant-avatar.webp'

type Tab = 'chat' | 'bills' | 'memos' | 'me'

/**
 * 导航 4 个入口。账单/日历/分析已经合成一页（回答的是同一个问题：这段时间钱去哪了），
 * 预算、往来、账号与退出登录在「我的」。
 */
const NAV: { key: Tab; label: string; icon: (props: { width?: number; height?: number }) => JSX.Element }[] = [
  { key: 'chat', label: '对话', icon: IconSpark },
  { key: 'bills', label: '账单', icon: IconList },
  { key: 'memos', label: '备忘', icon: IconBell },
  { key: 'me', label: '我的', icon: IconUser },
]

/** 示例按「记一笔 / 查一下 / 提醒我」分组，各组的动词不同，用户一眼能对上自己的目的。 */
const SUGGESTION_GROUPS: { title: string; items: string[] }[] = [
  { title: '记一笔', items: ['午饭花了 28', '今天工资到账 8500', '聚餐300，3人AA'] },
  { title: '查一下', items: ['我昨天花了哪些钱', '这个月餐饮花了多少', '还有谁没还我'] },
  { title: '提醒我', items: ['明天下午3点提醒我开会', '每周三提醒交水电费'] },
]

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)
  const [me, setMe] = useState<{ id: number; username: string } | null>(null)
  const [categories, setCategories] = useState<Category[]>([])
  const [payments, setPayments] = useState<PaymentMethod[]>([])
  const [tab, setTab] = useState<Tab>(() => {
    const raw = readQuery().get('tab')
    return raw === 'bills' || raw === 'memos' || raw === 'me' ? raw : 'chat'
  })
  const [billsKey, setBillsKey] = useState(0)
  const [pendingDelete, setPendingDelete] = useState<{ id: number } | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [searchResults, setSearchResults] = useState<ChatMessage[] | null>(null)
  const [pendingCount, setPendingCount] = useState(0)
  const [sending, setSending] = useState(false)
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [voiceTapUrl, setVoiceTapUrl] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [todayTotal, setTodayTotal] = useState(0)
  const [weekTotal, setWeekTotal] = useState(0)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const deleteTimer = useRef<number | null>(null)
  const deleteRef = useRef<{ id: number } | null>(null)
  const loadedCountRef = useRef(120)
  deleteRef.current = pendingDelete

  const changeTab = useCallback((next: Tab) => {
    setTab(next)
    updateQuery({ tab: next === 'chat' ? null : next })
  }, [])

  const bootstrap = useCallback(async () => {
    try {
      const meData = await api.me()
      setMe(meData)
      const [meta, history, stats, voice, pending] = await Promise.all([
        api.meta(),
        api.messages(),
        api.stats('week'),
        api.voice().catch(() => ({ enabled: false, voice: 'xiaoyi' })),
        // 只要个数，用来在导航上给「待结清」一个提醒点
        api.transactions({ pending: true, limit: 1 }).catch(() => ({ total: 0 })),
      ])
      setCategories(meta.categories)
      setPayments(meta.payments)
      setMessages(history.messages)
      setHasMore(Boolean(history.has_more))
      setPendingCount(pending.total ?? 0)
      setVoiceEnabled(voice.enabled)
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

  const playVoice = useCallback(async (text: string) => {
    try {
      const url = await api.tts(text)
      if (audioRef.current) {
        audioRef.current.pause()
        if (audioRef.current.src.startsWith('blob:')) URL.revokeObjectURL(audioRef.current.src)
      }
      const audio = new Audio(url)
      audioRef.current = audio
      setVoiceTapUrl(null)
      try {
        await audio.play()
      } catch {
        // 浏览器拦截自动播放时留一个手动播放按钮，点一下就能听。
        setVoiceTapUrl(url)
      }
    } catch {
      /* 合成失败就不出声，文字回复还在 */
    }
  }, [])

  const toggleVoice = useCallback(async () => {
    try {
      const result = await api.setVoice(!voiceEnabled)
      setVoiceEnabled(result.enabled)
      if (!result.enabled && audioRef.current) audioRef.current.pause()
    } catch (err) {
      setError(err instanceof Error ? err.message : '切换失败')
    }
  }, [voiceEnabled])

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
        if (typeof result.voice_enabled === 'boolean') setVoiceEnabled(result.voice_enabled)
        if (result.voice_enabled) void playVoice(result.reply)
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
    [refreshNumbers, sending, playVoice],
  )

  const syncLedger = useCallback(async () => {
    try {
      const history = await api.messages({ limit: loadedCountRef.current })
      setMessages(history.messages)
      await refreshNumbers()
    } catch (err) {
      setError(err instanceof Error ? err.message : '同步失败')
    }
  }, [refreshNumbers])

  /** 往上翻：用当前最早一条的 id 作为游标，只补更早的，不动已经渲染的。 */
  const loadOlder = useCallback(async () => {
    const oldest = messages.find((message) => message.id > 0)
    if (!oldest || loadingMore) return
    setLoadingMore(true)
    try {
      const result = await api.messages({ beforeId: oldest.id, limit: 50 })
      setMessages((prev) => {
        const seen = new Set(prev.map((message) => message.id))
        return [...result.messages.filter((message) => !seen.has(message.id)), ...prev]
      })
      setHasMore(Boolean(result.has_more))
      loadedCountRef.current = Math.min(200, loadedCountRef.current + result.messages.length)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载更早的对话失败')
    } finally {
      setLoadingMore(false)
    }
  }, [messages, loadingMore])

  /** 对话内搜索：只在关键词变化时打接口，300ms 防抖。 */
  useEffect(() => {
    if (!searchOpen) return
    const keyword = searchTerm.trim()
    if (!keyword) {
      setSearchResults(null)
      return
    }
    const timer = window.setTimeout(() => {
      void api
        .messages({ q: keyword, limit: 50 })
        .then((result) => setSearchResults(result.messages))
        .catch(() => setSearchResults([]))
    }, 300)
    return () => window.clearTimeout(timer)
  }, [searchOpen, searchTerm])

  useEffect(() => {
    if (!authed) return
    const sync = () => { if (document.visibilityState === 'visible' && !sending) void syncLedger() }
    window.addEventListener('focus', sync)
    document.addEventListener('visibilitychange', sync)
    return () => { window.removeEventListener('focus', sync); document.removeEventListener('visibilitychange', sync) }
  }, [authed, sending, syncLedger])

  const commitDelete = useCallback(async () => {
    const target = deleteRef.current
    if (!target) return
    deleteRef.current = null
    setPendingDelete(null)
    if (deleteTimer.current) {
      window.clearTimeout(deleteTimer.current)
      deleteTimer.current = null
    }
    try {
      await api.deleteTransaction(target.id)
    } catch {
      /* 删除失败时重拉对话，这一笔会重新出现 */
    }
    await syncLedger()
  }, [syncLedger])

  // 对话里的删除同样延迟 5 秒提交，撤销等于什么都没发生
  const deleteTx = useCallback(
    async (id: number) => {
      if (deleteRef.current) await commitDelete()
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
      deleteRef.current = { id }
      setPendingDelete({ id })
      deleteTimer.current = window.setTimeout(() => void commitDelete(), 5000)
    },
    [commitDelete],
  )

  const undoDelete = useCallback(() => {
    if (deleteTimer.current) window.clearTimeout(deleteTimer.current)
    deleteTimer.current = null
    deleteRef.current = null
    setPendingDelete(null)
    void syncLedger()
  }, [syncLedger])

  useEffect(
    () => () => {
      if (deleteTimer.current) window.clearTimeout(deleteTimer.current)
      if (deleteRef.current) void api.deleteTransaction(deleteRef.current.id)
    },
    [],
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

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // 服务端没响应也要让用户退回登录页，否则会卡在账本里出不去
    }
    setAuthed(false)
  }, [])

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
            <div className="text-[12px] text-ink-500">{APP_TAGLINE}</div>
          </div>
        </div>

        <nav aria-label="主导航" className="mt-7 space-y-1">
          {NAV.map((item) => {
            const active = tab === item.key
            const Icon = item.icon
            return (
              <button
                key={item.key}
                onClick={() => changeTab(item.key)}
                className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[14px] font-medium transition ${
                  active
                    ? 'bg-white text-accent-700 shadow-card'
                    : 'text-ink-500 hover:bg-white/60 hover:text-ink-800'
                }`}
              >
                <span className="relative">
                  <Icon width={18} height={18} />
                  {item.key === 'bills' && pendingCount > 0 && (
                    <span className="absolute -right-1.5 -top-1 flex h-3 min-w-3 items-center justify-center rounded-full bg-accent-600 px-0.5 text-[9px] font-medium leading-none text-white">
                      {pendingCount > 9 ? '9+' : pendingCount}
                    </span>
                  )}
                </span>
                {item.label}
              </button>
            )
          })}
        </nav>

        <div className="mt-6 space-y-3">
          <div className="card p-4">
            <div className="text-[12px] text-ink-500">今天个人净支出</div>
            <div className="mt-0.5 text-ink-900">
              <Amount value={todayTotal} size={22} />
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-ink-50 pt-2.5 text-[12px]">
              <span className="text-ink-500">近 7 天</span>
              <Amount value={weekTotal} size={13} className="text-ink-700" />
            </div>
          </div>

          <div className="card p-4">
            <div className="mb-2.5 text-[12px] text-ink-500">按分类看</div>
            <div className="flex flex-wrap gap-1.5">
              {categories.slice(0, 8).map((item) => (
                <button
                  key={item.name}
                  title={`看${item.name}的流水`}
                  onClick={() => {
                    changeTab('bills')
                    updateQuery({ cat: item.name, view: null })
                    setBillsKey((key) => key + 1)
                  }}
                  className="flex h-7 w-7 items-center justify-center rounded-xl transition hover:scale-105"
                  style={{ backgroundColor: tint(item.color, 0.92), color: mute(item.color, 0.18) }}
                >
                  <CategoryIcon name={ICON_MAP[item.name] ?? item.icon} size={14} />
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-auto pt-4">
          <button
            onClick={() => changeTab('me')}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-[12px] text-ink-500 transition hover:bg-white hover:text-ink-800"
          >
            <IconUser width={14} height={14} />
            <span className="truncate">{me?.username ?? '我的账号'}</span>
          </button>
        </div>
      </aside>

      {/* 主区域 */}
      <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden bg-white lg:rounded-3xl lg:shadow-card">
        <header className="z-10 flex shrink-0 items-center gap-3 border-b border-ink-50 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
          <Logo size={26} />
          <div className="min-w-0 flex-1">
            <div className="text-[14px] font-semibold leading-tight tracking-tight">{APP_NAME}</div>
            <div className="flex items-baseline gap-1 text-[12px] text-ink-500">
              今天 <Amount value={todayTotal} size={12} className="text-ink-700" />
            </div>
          </div>
        </header>

        {tab === 'chat' && (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto w-full max-w-2xl px-4 pb-2 pt-5">
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="truncate text-[12px] text-ink-500">
                  {searchResults ? `找到 ${searchResults.length} 条对话` : '收支 · 退款 · AA · 报销 · 预算 · 提醒'}
                </span>
                <button
                  onClick={() => {
                    setSearchOpen((value) => !value)
                    setSearchTerm('')
                    setSearchResults(null)
                  }}
                  aria-expanded={searchOpen}
                  aria-label={searchOpen ? '关闭对话搜索' : '搜索对话'}
                  className="flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1.5 text-[12px] text-ink-500 transition hover:bg-ink-50 hover:text-ink-800"
                >
                  <IconSearch width={14} height={14} />
                  {searchOpen ? '关闭' : '搜索'}
                </button>
              </div>

              {searchOpen && (
                <input
                  autoFocus
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="搜对话内容，比如「海底捞」「报销」"
                  aria-label="搜索对话内容"
                  className="mb-3 w-full rounded-xl bg-ink-50 px-3 py-2 text-[13px] text-ink-800 outline-none placeholder:text-ink-400 focus:bg-white focus:ring-1 focus:ring-ink-200"
                />
              )}

              {searchResults === null && messages.length === 0 ? (
                <EmptyState onPick={(text) => void send(text, [])} onStart={() => composerRef.current?.focus()} />
              ) : (
                <div className="space-y-5">
                  {searchResults === null && hasMore && (
                    <div className="text-center">
                      <button
                        onClick={() => void loadOlder()}
                        disabled={loadingMore}
                        className="rounded-full bg-ink-50 px-3 py-1.5 text-[12px] text-ink-500 transition hover:bg-ink-100 disabled:opacity-50"
                      >
                        {loadingMore ? '正在加载…' : '加载更早的对话'}
                      </button>
                    </div>
                  )}

                  {(searchResults ?? messages).map((message) => (
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

                  {/* 放在最新一条之后：进对话默认滚到底，放顶部等于永远看不到 */}
                  {searchResults === null && (
                    <WeeklyDigest
                      onShown={() => bottomRef.current?.scrollIntoView({ block: 'end' })}
                      onOpenReport={() => {
                        changeTab('bills')
                        updateQuery({ view: 'report' })
                        setBillsKey((key) => key + 1)
                      }}
                    />
                  )}

                  {searchResults !== null && searchResults.length === 0 && (
                    <p className="py-10 text-center text-[13px] text-ink-500">
                      {searchTerm.trim() ? '没有找到包含这个词的对话' : '输入关键词，搜你说过的话'}
                    </p>
                  )}

                  {searchResults === null && sending && (
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
            <div className="mx-auto flex min-h-full max-w-2xl flex-col px-4 py-4">
              <BillsPage
                key={billsKey}
                categories={categories}
                payments={payments}
                refreshKey={refreshKey}
                onChanged={() => void refreshNumbers()}
              />
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

        {tab === 'me' && (
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
            <div className="mx-auto max-w-2xl space-y-4 px-4 py-4">
              <div className="px-1 text-[12px] font-medium tracking-wide text-ink-400">账号</div>
              <AccountCard username={me?.username ?? ''} onLogout={() => void logout()} />
              <MoneyPanel
                categories={categoryNames}
                payments={paymentNames}
                refreshKey={refreshKey}
                onChanged={() => void syncLedger()}
                voiceEnabled={voiceEnabled}
                onToggleVoice={() => void toggleVoice()}
              />
              {/* 账号管理只给 admin；预算与记账习惯是每个租户自己的 */}
              {me?.username === 'admin' && (
                <>
                  <div className="px-1 text-[12px] font-medium tracking-wide text-ink-400">系统</div>
                  <UsersPanel />
                </>
              )}
            </div>
          </div>
        )}

        {tab === 'chat' && (
          <div className="shrink-0">
            {error && (
              <div className="mx-auto mb-1 w-full max-w-2xl px-4">
                <div className="rounded-xl bg-red-50 px-3 py-1.5 text-[12px] text-red-600">{error}</div>
              </div>
            )}
            {voiceTapUrl && (
              <div className="mx-auto flex w-full max-w-2xl justify-end px-4 pb-1">
                <button
                  onClick={() => {
                    const audio = new Audio(voiceTapUrl)
                    audioRef.current = audio
                    setVoiceTapUrl(null)
                    void audio.play()
                  }}
                  className="rounded-full bg-accent-600 px-2.5 py-1.5 text-[12px] font-medium text-white"
                >
                  播放语音
                </button>
              </div>
            )}
            <Composer onSend={send} disabled={sending} inputRef={composerRef} />
          </div>
        )}
      </main>

      {/* 移动端底部导航 */}
      <nav aria-label="底部导航" className="z-20 flex shrink-0 items-center justify-around border-t border-ink-100 bg-white/95 px-2 pb-[max(6px,env(safe-area-inset-bottom))] pt-1.5 backdrop-blur lg:hidden">
        {NAV.map((item) => {
          const active = tab === item.key
          const Icon = item.icon
          return (
            <button
              key={item.key}
              onClick={() => changeTab(item.key)}
              aria-current={active ? 'page' : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 py-1.5 text-[12px] font-medium transition ${
                active ? 'text-accent-700' : 'text-ink-500'
              }`}
            >
              <span className="relative">
                <Icon width={20} height={20} />
                {item.key === 'bills' && pendingCount > 0 && (
                  <span className="absolute -right-1.5 -top-1 flex h-3 min-w-3 items-center justify-center rounded-full bg-accent-600 px-0.5 text-[9px] font-medium leading-none text-white">
                    {pendingCount > 9 ? '9+' : pendingCount}
                  </span>
                )}
              </span>
              {item.label}
            </button>
          )
        })}
      </nav>

      {pendingDelete && <UndoToast message="已删除 1 笔流水" onUndo={undoDelete} />}
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

function EmptyState({ onPick, onStart }: { onPick: (text: string) => void; onStart: () => void }) {
  return (
    <div className="pb-6 pt-1 sm:pt-6">
      <img src={assistantAvatar} alt={APP_NAME} className="mx-auto h-12 w-12 rounded-full object-cover shadow-float" />
      <h1 className="mt-4 text-center text-[19px] font-semibold tracking-tight text-ink-900">今天花了多少？</h1>
      <p className="mx-auto mt-1.5 max-w-[300px] text-center text-[13px] leading-relaxed text-ink-500">
        说一句话、发一张小票照片，我来帮你记、帮你分类、帮你算清楚。
      </p>

      <div className="mt-5 flex justify-center">
        <button
          onClick={onStart}
          className="flex items-center gap-1.5 rounded-full bg-accent-600 px-4 py-2.5 text-[13px] font-medium text-white transition hover:bg-accent-700"
        >
          <IconPlus width={15} height={15} />
          记第一笔
        </button>
      </div>

      <div className="mt-7 grid gap-4 sm:grid-cols-3 sm:gap-5">
        {SUGGESTION_GROUPS.map((group) => (
          <div key={group.title}>
            <div className="mb-1 px-2 text-[12px] font-medium tracking-wide text-ink-400">{group.title}</div>
            <div className="space-y-0.5">
              {group.items.map((text) => (
                <button
                  key={text}
                  onClick={() => onPick(text)}
                  className="w-full truncate rounded-xl px-2 py-2 text-left text-[12px] text-ink-600 transition hover:bg-ink-50 hover:text-ink-900"
                >
                  {text}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** 「我的」页顶部：当前账号 + 退出登录。移动端以前没有这个入口，只能清缓存。 */
function AccountCard({ username, onLogout }: { username: string; onLogout: () => void }) {
  return (
    <section className="card flex items-center gap-3 p-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ink-100 text-ink-600">
        <IconUser width={20} height={20} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-medium text-ink-900">{username || '未登录'}</div>
        <div className="mt-0.5 text-[12px] text-ink-500">每个账号只能看到自己的账单、备忘与微信绑定</div>
      </div>
      <button
        onClick={onLogout}
        className="flex shrink-0 items-center gap-1.5 rounded-full border border-ink-200 px-3 py-1.5 text-[12px] font-medium text-ink-600 transition hover:border-ink-300 hover:text-ink-900"
      >
        <IconLogout width={14} height={14} />
        退出登录
      </button>
    </section>
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
        <p className="mt-1.5 text-center text-[13px] text-ink-500">
          {mode === 'register' ? '只需要账号和密码，账号不重复就能注册' : '输入账号和密码，进入你的账本'}
        </p>

        <input
          type="text"
          autoFocus
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="账号"
          className="mt-6 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-center text-[14px] outline-none transition placeholder:text-ink-400 focus:border-ink-900"
        />
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="密码"
          className="mt-3 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-center text-[14px] tracking-widest outline-none transition placeholder:tracking-normal placeholder:text-ink-400 focus:border-ink-900"
        />
        {error && <div className="mt-2 text-center text-[12px] text-red-500">{error}</div>}
        <button
          type="submit"
          disabled={busy || !username.trim() || !password.trim()}
          className="mt-3 w-full rounded-xl bg-accent-600 py-2.5 text-[14px] font-medium text-white transition hover:bg-accent-700 disabled:opacity-40"
        >
          {busy ? '验证中…' : mode === 'register' ? '注册并进入' : '进入'}
        </button>
        <button
          type="button"
          onClick={() => switchMode(mode === 'register' ? 'login' : 'register')}
          className="mt-3 w-full text-center text-[13px] text-ink-500 underline-offset-2 hover:text-ink-900 hover:underline"
        >
          {mode === 'register' ? '已有账号？去登录' : '没有账号？注册一个'}
        </button>
      </form>
    </div>
  )
}
