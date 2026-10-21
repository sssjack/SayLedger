import { useEffect, useState } from 'react'
import { api, type WechatStatus } from '../api'

const loginLabels: Record<string, string> = {
  creating: '正在生成二维码，请稍候',
  wait: '用手机微信扫一扫，连接当前账本',
  scaned: '已扫码，请在手机微信完成确认',
  scaned_but_redirect: '正在继续验证，请稍候',
  need_verifycode: '请输入手机微信显示的验证数字',
  expired: '二维码已过期，请重新生成',
  error: '连接未完成，请重新尝试',
  confirmed: '扫码完成，正在连接微信',
}

function localTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function WechatPanel() {
  const [status, setStatus] = useState<WechatStatus | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [code, setCode] = useState('')
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const next = await api.wechatStatus()
        if (active) setStatus(next)
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : '连接状态加载失败')
      } finally {
        if (active) timer = setTimeout(() => void poll(), 3000)
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [refresh])

  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try { await operation(); setRefresh(value => value + 1) }
    catch (err) { setError(err instanceof Error ? err.message : '连接未完成，请稍后重试') }
    finally { setBusy(false) }
  }
  const login = status?.login
  const ready = status?.connected && status.state === 'connected' && status.worker_running && !!status.last_poll_at
  const label = !status ? '正在读取' : !status.enabled ? '尚未启用' : status.state === 'expired' ? '需要重新连接'
    : ready ? '已连接' : status.connected ? '正在连接' : login?.qr_available ? '等待扫码' : '未连接'

  return <section className="card overflow-hidden" aria-labelledby="wechat-heading">
    <div className="flex items-center gap-3 border-b border-ink-50 p-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
        <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H8l-4 2v-5a7.5 7.5 0 1 1 16-4.5Z" /><path d="M8 10h.01M12 10h.01M16 10h.01" strokeWidth="3" strokeLinecap="round" /></svg>
      </span>
      <div className="min-w-0 flex-1"><h2 id="wechat-heading" className="text-[14px] font-medium">微信记账</h2><p className="mt-0.5 text-[11px] text-ink-400">发一句话，和网页记到同一本账里</p></div>
      <span aria-live="polite" className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${ready ? 'bg-emerald-50 text-emerald-700' : 'bg-ink-50 text-ink-500'}`}>{label}</span>
    </div>
    <div className="space-y-3 p-4">
      {error && <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-[12px] text-red-600">{error === 'unauthorized' ? '登录已过期，请刷新页面重新登录。' : error}</p>}
      {status && !status.enabled && <p className="text-[12px] leading-relaxed text-ink-500">服务器尚未启用微信入口，请联系管理员启用后再连接。</p>}
      {status?.enabled && !status.worker_running && <p role="status" className="rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800">微信后台服务尚未就绪。请稍候，持续未恢复时检查服务器是否正在运行。</p>}
      {status?.connected ? <>
        <p className="text-[12px] leading-relaxed text-ink-500">{status.state === 'expired' ? '登录凭证已失效，请断开后重新扫码连接。' : '在微信 ClawBot 对话里发送记账说明，即可记账、查账、修改和撤销。'}</p>
        {status.last_error && <p role="status" className="text-[12px] text-amber-700">{status.last_error}</p>}
        <div className="rounded-xl bg-ink-50 px-3 py-2.5 text-[12px] leading-6 text-ink-600"><p>“午饭花了28，微信付的”</p><p>“这个月餐饮花了多少”</p><p>“撤销上一步”</p></div>
        {status.last_message_at && <p className="text-[11px] text-ink-400">最近收到消息：{localTime(status.last_message_at)}</p>}
        {status.pending_replies > 0 && <p className="text-[12px] text-ink-500">有{status.pending_replies}条回复正在等待发送，请勿重复记账。</p>}
        {status.failed_replies > 0 && <div className="rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800"><p>有{status.failed_replies}条回复未送达，账本中的处理结果已保存。</p><button disabled={busy || status.state !== 'connected'} onClick={() => void run(() => api.retryWechatReplies())} className="mt-1 underline underline-offset-2 disabled:opacity-40">重新发送回复</button></div>}
        {confirmDisconnect ? <div className="rounded-xl border border-ink-100 p-3"><p className="text-[12px] text-ink-600">断开后停止接收消息，已有账单会保留。</p><div className="mt-2 flex gap-3"><button disabled={busy} onClick={() => void run(async () => { await api.disconnectWechat(); setStatus(null); setConfirmDisconnect(false) })} className="text-[12px] text-red-600 disabled:opacity-40">确认断开</button><button disabled={busy} onClick={() => setConfirmDisconnect(false)} className="text-[12px] text-ink-500">取消</button></div></div>
          : <button onClick={() => setConfirmDisconnect(true)} className="text-[12px] text-ink-400 underline underline-offset-2">断开连接</button>}
      </> : status?.enabled && <>
        {login?.qr_available ? <div className="rounded-2xl border border-ink-100 bg-ink-50/50 p-4 text-center">
          <img key={login.id} src={api.wechatQrUrl(login.id)} alt="使用手机微信扫描此二维码，将微信连接到当前账本" width="224" height="224" className="mx-auto h-auto w-56 max-w-full rounded-xl bg-white" onError={() => setError('二维码加载失败，请重新生成后扫码。')} />
          <p aria-live="polite" className="mt-3 text-[12px] font-medium text-ink-700">{loginLabels[login.state]}</p>
          <p className="mt-1 text-[11px] text-ink-400">有效至 {localTime(login.expires_at)} · 请使用自己的微信扫码</p>
          {login.state === 'need_verifycode' && <form className="mx-auto mt-3 flex max-w-xs gap-2" onSubmit={event => { event.preventDefault(); void run(async () => { await api.verifyWechat(login.id, code); setCode(''); setStatus(previous => previous?.login?.id === login.id ? { ...previous, login: { ...previous.login, verify_pending: true, error: '' } } : previous) }) }}><input aria-label="手机微信显示的验证数字" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]+" maxLength={12} required value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ''))} placeholder="手机上显示的数字" className="min-w-0 flex-1 rounded-lg border border-ink-200 bg-white px-3 py-2 text-[12px] outline-none focus:border-ink-700" /><button disabled={busy || login.verify_pending} className="shrink-0 rounded-lg bg-ink-900 px-3 py-2 text-[12px] text-white disabled:opacity-40">{login.verify_pending ? '验证中…' : '确认'}</button></form>}
          {login.error && <p role="status" className="mt-2 text-[12px] text-amber-700">{login.error}</p>}
          <button disabled={busy} onClick={() => void run(() => api.disconnectWechat())} className="mt-3 text-[11px] text-ink-400 underline underline-offset-2 disabled:opacity-40">取消本次连接</button>
        </div> : <>
          <p className="text-[12px] leading-relaxed text-ink-500">连接后，在微信 ClawBot 对话里直接记账。文字消息会同步到当前账本，输入“帮助”可查看用法。</p>
          {login && login.state !== 'confirmed' && <p role="status" className="text-[12px] text-amber-700">{login.error || loginLabels[login.state]}</p>}
          <button disabled={busy || !status.worker_running || login?.state === 'creating'} onClick={() => void run(async () => { const next = await api.connectWechat(); setStatus(previous => previous ? { ...previous, login: next } : previous) })} className="rounded-xl bg-ink-900 px-4 py-2.5 text-[12px] font-medium text-white transition hover:bg-ink-800 disabled:opacity-40">{busy || login?.state === 'creating' ? '正在生成…' : login ? '重新生成二维码' : '扫码连接微信'}</button>
          {login?.state === 'creating' && <button disabled={busy} onClick={() => void run(() => api.disconnectWechat())} className="ml-3 text-[11px] text-ink-400 underline disabled:opacity-40">取消本次连接</button>}
        </>}
      </>}
      <p className="border-t border-ink-50 pt-3 text-[11px] leading-relaxed text-ink-400">第一版支持文字对话。图片、小票和语音请在网页记录。连接服务需持续运行，微信可用性以客户端扫码授权结果为准。</p>
    </div>
  </section>
}
