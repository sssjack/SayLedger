type Props = {
  message: string
  onUndo: () => void
}

/**
 * 删除后的撤销条。
 * 删除本身延迟 5 秒提交（父组件负责计时），这段时间点「撤销」等于什么都没发生，
 * 不依赖后端 undo，也就不存在「撤销错一步」的风险。
 */
export function UndoToast({ message, onUndo }: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-[74px] z-40 flex justify-center px-4 lg:bottom-6"
    >
      <div className="pointer-events-auto relative flex items-center gap-2 overflow-hidden rounded-full bg-ink-900 py-1 pl-4 pr-1 text-[13px] text-white shadow-float animate-rise">
        <span className="py-1">{message}</span>
        <button
          onClick={onUndo}
          className="rounded-full bg-white/15 px-3 py-1.5 text-[12px] font-medium text-white transition hover:bg-white/25"
        >
          撤销
        </button>
        <span className="absolute inset-x-0 bottom-0 h-[2px] origin-left animate-drain bg-accent-400" />
      </div>
    </div>
  )
}
