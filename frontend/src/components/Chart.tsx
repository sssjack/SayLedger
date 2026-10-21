import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  GraphicComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  GraphicComponent,
  CanvasRenderer,
])

type Props = {
  option: echarts.EChartsCoreOption
  height?: number
  className?: string
}

export function Chart({ option, height = 220, className = '' }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const instance = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!ref.current) return
    instance.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const onResize = () => instance.current?.resize()
    window.addEventListener('resize', onResize)
    const observer = new ResizeObserver(onResize)
    observer.observe(ref.current)
    return () => {
      window.removeEventListener('resize', onResize)
      observer.disconnect()
      instance.current?.dispose()
      instance.current = null
    }
  }, [])

  useEffect(() => {
    instance.current?.setOption(option, true)
  }, [option])

  return <div ref={ref} className={className} style={{ height }} />
}

export const TOOLTIP_STYLE = {
  backgroundColor: 'rgba(28,31,39,.94)',
  borderWidth: 0,
  padding: [8, 12] as [number, number],
  textStyle: { color: '#fff', fontSize: 12 },
  extraCssText: 'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);',
}
