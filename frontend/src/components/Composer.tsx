import { useEffect, useRef, useState } from 'react'
import { IconClose, IconImage, IconMic, IconSend, IconStop } from '../icons'
import { api, BASE } from '../api'

type Props = {
  onSend: (text: string, imageIds: string[]) => Promise<void>
  disabled?: boolean
}

type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((event: any) => void) | null
  onerror: ((event: any) => void) | null
  onend: (() => void) | null
}

function getRecognition(): Recognition | null {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition }
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition
  if (!Ctor) return null
  const instance = new Ctor()
  instance.lang = 'zh-CN'
  instance.continuous = true
  instance.interimResults = true
  return instance
}

export function Composer({ onSend, disabled }: Props) {
  const [text, setText] = useState('')
  const [images, setImages] = useState<{ id: string; url: string }[]>([])
  const [uploading, setUploading] = useState(false)
  const [listening, setListening] = useState(false)
  const [hint, setHint] = useState('')
  const [focused, setFocused] = useState(false)

  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<Recognition | null>(null)
  const baseTextRef = useRef('')

  useEffect(() => {
    if (!hint) return
    const timer = window.setTimeout(() => setHint(''), 3200)
    return () => window.clearTimeout(timer)
  }, [hint])

  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`
  }, [text])

  const stopListening = () => {
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setListening(false)
  }

  const toggleMic = () => {
    if (listening) {
      stopListening()
      return
    }
    const recognition = getRecognition()
    if (!recognition) {
      setHint('当前浏览器不支持语音识别，试试用 Chrome 或系统语音输入')
      return
    }
    baseTextRef.current = text ? `${text}${text.endsWith('，') || text.endsWith('。') ? '' : '，'}` : ''
    recognition.onresult = (event: any) => {
      let final = ''
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i]
        if (result.isFinal) final += result[0].transcript
        else interim += result[0].transcript
      }
      if (final) baseTextRef.current += final
      setText(baseTextRef.current + interim)
    }
    recognition.onerror = (event: any) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        setHint('麦克风权限被拒绝，请在浏览器设置里允许')
      } else if (event.error === 'no-speech') {
        setHint('没听到声音，再说一次？')
      }
      setListening(false)
    }
    recognition.onend = () => setListening(false)
    try {
      recognition.start()
      recognitionRef.current = recognition
      setListening(true)
      setHint('正在听…说完点一下麦克风结束')
    } catch {
      setHint('语音启动失败，请重试')
    }
  }

  const upload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      for (const file of Array.from(files).slice(0, 3)) {
        const result = await api.upload(file)
        setImages((prev) => [...prev, { id: result.image_id, url: result.url }].slice(0, 3))
      }
    } catch (error) {
      setHint(error instanceof Error ? error.message : '图片上传失败')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const submit = async () => {
    const value = text.trim()
    if ((!value && images.length === 0) || disabled || uploading) return
    if (listening) stopListening()
    const ids = images.map((item) => item.id)
    setText('')
    setImages([])
    await onSend(value, ids)
  }

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void submit()
    }
  }

  const canSend = (text.trim().length > 0 || images.length > 0) && !disabled && !uploading

  return (
    <div className="sticky bottom-0 z-20 bg-gradient-to-t from-ink-50 via-ink-50 to-transparent pb-3 pt-4 sm:pb-5">
      <div className="mx-auto w-full max-w-2xl px-3 sm:px-4">
        {hint && (
          <div className="mb-2 animate-rise rounded-lg bg-ink-900/90 px-3 py-1.5 text-[12px] text-white backdrop-blur">
            {hint}
          </div>
        )}

        {images.length > 0 && (
          <div className="mb-2 flex gap-2">
            {images.map((image) => (
              <div key={image.id} className="group relative">
                <img src={`${BASE}${image.url}`} alt="" className="h-16 w-16 rounded-xl object-cover ring-1 ring-ink-200" />
                <button
                  onClick={() => setImages((prev) => prev.filter((item) => item.id !== image.id))}
                  className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-ink-900 text-white shadow-sm"
                >
                  <IconClose width={11} height={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div
          className={`flex items-end gap-1 rounded-[22px] border bg-white px-1.5 py-1.5 shadow-card transition ${
            focused ? 'border-ink-300 shadow-float' : 'border-ink-100'
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={(event) => void upload(event.target.files)}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            title="发小票图片"
            className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-ink-400 transition hover:bg-ink-50 hover:text-ink-700 disabled:opacity-40"
          >
            {uploading ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-200 border-t-ink-700" />
            ) : (
              <IconImage width={19} height={19} />
            )}
          </button>

          <textarea
            ref={inputRef}
            rows={1}
            value={text}
            disabled={disabled}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onKeyDown}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder={listening ? '正在听你说…' : '说一句，比如「午饭花了28」'}
            className="max-h-[132px] min-h-[34px] flex-1 resize-none bg-transparent px-1 py-[7px] text-[14.5px] leading-snug text-ink-900 outline-none placeholder:text-ink-300"
          />

          <button
            onClick={toggleMic}
            title="语音记账"
            className={`relative mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition ${
              listening ? 'bg-red-500 text-white' : 'text-ink-400 hover:bg-ink-50 hover:text-ink-700'
            }`}
          >
            {listening ? <IconStop width={16} height={16} /> : <IconMic width={19} height={19} />}
            {listening && <span className="absolute inset-0 animate-ping rounded-full bg-red-400/40" />}
          </button>

          <button
            onClick={() => void submit()}
            disabled={!canSend}
            title="发送"
            className={`mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition ${
              canSend ? 'bg-ink-900 text-white hover:bg-ink-800' : 'bg-ink-100 text-ink-300'
            }`}
          >
            {disabled ? (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <IconSend width={17} height={17} />
            )}
          </button>
        </div>

        <div className="mt-1.5 hidden items-center justify-center gap-3 text-[11px] text-ink-300 sm:flex">
          <span>Enter 发送 · Shift+Enter 换行</span>
          <span className="text-ink-200">|</span>
          <span>支持语音、小票照片</span>
        </div>
      </div>
    </div>
  )
}
