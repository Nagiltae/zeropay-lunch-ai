import { FormEvent, useEffect, useRef, useState } from 'react'

const maxMessageLength = 2000

type MessageComposerProps = {
  disabled: boolean
  isStreaming: boolean
  onSend: (message: string) => void
  onStop: () => void
}

export function MessageComposer({
  disabled,
  isStreaming,
  onSend,
  onStop,
}: MessageComposerProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) {
      return
    }
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 128)}px`
  }, [input])

  useEffect(() => {
    if (!disabled && !isStreaming) {
      textareaRef.current?.focus()
    }
  }, [disabled, isStreaming])

  const submit = () => {
    const message = input.trim()
    if (!message || disabled || isStreaming) {
      return
    }
    onSend(message)
    setInput('')
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    submit()
  }

  return (
    <div className="composer-area">
      <form className="message-composer" onSubmit={handleSubmit}>
        <label className="sr-only" htmlFor="chat-input">
          점심 추천 요청
        </label>
        <textarea
          id="chat-input"
          ref={textareaRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder={
            disabled
              ? '먼저 강남구 내 기준 위치를 선택해 주세요'
              : '먹고 싶은 메뉴나 상황을 이야기해 주세요'
          }
          rows={1}
          maxLength={maxMessageLength}
          disabled={disabled || isStreaming}
        />
        {isStreaming ? (
          <button
            className="stop-button"
            type="button"
            onClick={onStop}
            aria-label="답변 생성 중지"
          >
            <span aria-hidden="true" />
            중지
          </button>
        ) : (
          <button
            className="send-button"
            type="submit"
            disabled={disabled || !input.trim()}
            aria-label="메시지 전송"
          >
            <span>전송</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m4 12 15-7-4.5 14-3.1-5.3L4 12Zm7.4 1.7L19 5" />
            </svg>
          </button>
        )}
      </form>
      <div className="composer-meta">
        <span>Enter로 전송 · Shift + Enter로 줄바꿈</span>
        <span>{input.length.toLocaleString()} / 2,000</span>
      </div>
    </div>
  )
}
