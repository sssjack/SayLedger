import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

type TenantUser = { id: number; username: string; created_at: string | null }

/** 管理页里的账号管理：只渲染给 admin（App 侧已判断），普通租户看不到。 */
export function UsersPanel() {
  const [users, setUsers] = useState<TenantUser[]>([])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const data = await api.listUsers()
      setUsers(data.users)
    } catch {
      // 加载失败时静默，不阻塞管理页其余内容
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const created = await api.createUser(username.trim(), password)
      setNotice(`已创建账号 ${created.username}，把账号和密码发给对方即可登录，各自账本互不相通。`)
      setUsername('')
      setPassword('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card p-4">
      <div className="text-[13.5px] font-semibold">账号管理</div>
      <p className="mt-1 text-[12px] leading-relaxed text-ink-500">
        只有管理员能建号，不开放公开注册。每个账号登录后只能看到自己的账单、备忘和微信绑定。
      </p>
      <form onSubmit={create} className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={username}
          onChange={(event) => setUsername(event.target.value)}
          placeholder="新账号，字母数字下划线横线"
          className="min-w-0 flex-1 rounded-xl border border-ink-200 bg-white px-3 py-2 text-[13px] outline-none placeholder:text-ink-300 focus:border-ink-900"
        />
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="密码，至少 6 位"
          className="min-w-0 flex-1 rounded-xl border border-ink-200 bg-white px-3 py-2 text-[13px] outline-none placeholder:text-ink-300 focus:border-ink-900"
        />
        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="rounded-xl bg-ink-900 px-4 py-2 text-[13px] font-medium text-white transition hover:bg-ink-800 disabled:opacity-40"
        >
          {busy ? '创建中…' : '创建账号'}
        </button>
      </form>
      {error && <div className="mt-2 text-[12px] text-red-500">{error}</div>}
      {notice && <div className="mt-2 text-[12px] text-emerald-600">{notice}</div>}
      <ul className="mt-3 space-y-1.5">
        {users.map((user) => (
          <li key={user.id} className="flex items-center justify-between text-[13px] text-ink-700">
            <span>
              {user.username}
              {user.username === 'admin' && <span className="ml-1.5 text-[11px] text-ink-400">管理员</span>}
            </span>
            <span className="text-[11.5px] text-ink-400">{user.created_at ? user.created_at.slice(0, 10) : ''}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
