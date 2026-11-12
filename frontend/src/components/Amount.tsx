import { fmtMoney } from '../utils'

type Props = {
  value: number
  /** 字号（px）。¥ 会自动用 0.64 倍，不再和数字同大抢视觉。 */
  size?: number
  prefix?: string
  className?: string
}

/** 金额排版：符号缩小、数字等宽。财务产品的「专业感」几乎全在这一处。 */
export function Amount({ value, size = 17, prefix, className = '' }: Props) {
  return (
    <span className={`font-num font-semibold tabular-nums ${className}`} style={{ fontSize: size, lineHeight: 1.1 }}>
      {prefix && <span className="mr-[0.04em]">{prefix}</span>}
      <span className="mr-[0.06em] font-medium" style={{ fontSize: '0.64em' }}>
        ¥
      </span>
      {fmtMoney(Math.abs(value))}
    </span>
  )
}
