type ChatHeaderProps = {
  hasConversation: boolean
  onReset: () => void
}

export function ChatHeader({ hasConversation, onReset }: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div className="brand-mark" aria-hidden="true">
        Z
      </div>
      <div className="brand-copy">
        <p className="eyebrow">ZeroPay Lunch AI</p>
        <h1 id="page-title">오늘의 점심 대화</h1>
      </div>
      <button
        className="new-chat-button"
        type="button"
        onClick={onReset}
        disabled={!hasConversation}
      >
        초기화
      </button>
    </header>
  )
}
