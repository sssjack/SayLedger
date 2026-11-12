/**
 * 把视图状态写进地址栏。
 * 三个面板各写各的参数，用 merge 的方式合并，避免互相覆盖；
 * replaceState 而不是 pushState，切筛选不该产生一串 History 记录。
 */
export function readQuery(): URLSearchParams {
  return new URLSearchParams(window.location.search)
}

export function updateQuery(patch: Record<string, string | null | undefined>): void {
  const params = new URLSearchParams(window.location.search)
  for (const [key, value] of Object.entries(patch)) {
    if (value === null || value === undefined || value === '') params.delete(key)
    else params.set(key, value)
  }
  const search = params.toString()
  const next = `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (next !== current) window.history.replaceState(null, '', next)
}
