type ChatHeaderProps = {
  hasConversation: boolean
  onReset: () => void
  onOpenPreferences: () => void
  onLogout: () => void
}

export function ChatHeader({
  hasConversation,
  onReset,
  onOpenPreferences,
  onLogout,
}: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div className="brand-mark" aria-hidden="true">
        Z
      </div>
      <div className="brand-copy">
        <p className="eyebrow">ZeroPay Lunch AI</p>
        <h1 id="page-title">오늘의 점심 대화</h1>
      </div>
      <div className="header-actions">
        <button
          className="preference-button"
          type="button"
          onClick={onOpenPreferences}
        >
          취향 설정
        </button>
        <button
          className="new-chat-button"
          type="button"
          onClick={onReset}
          disabled={!hasConversation}
        >
          초기화
        </button>
        <button
          className="logout-button"
          type="button"
          onClick={onLogout}
        >
          로그아웃
        </button>
      </div>
    </header>
  )
}
