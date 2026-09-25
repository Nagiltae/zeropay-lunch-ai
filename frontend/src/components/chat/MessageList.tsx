import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../../types/chat'
import { useMealHistory } from '../../hooks/useMealHistory'

const starterPrompts = [
  '만원 이하로 든든한 점심 추천해줘',
  '비 오는 날 먹기 좋은 국물 음식',
  '가볍게 먹을 수 있는 메뉴가 좋아',
]

type MessageListProps = {
  messages: ChatMessage[]
  progress: string | null
  onPromptSelect: (prompt: string) => void
  onRetry: (messageId: string) => void
}

export function MessageList({
  messages,
  progress,
  onPromptSelect,
  onRetry,
}: MessageListProps) {
  const { recentMeals, markEaten, markingRequest, isMarking, markError } =
    useMealHistory()
  const containerRef = useRef<HTMLDivElement | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const shouldFollowRef = useRef(true)

  useEffect(() => {
    if (shouldFollowRef.current) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, progress])

  return (
    <div
      className="message-list"
      role="log"
      aria-live="polite"
      ref={containerRef}
      onScroll={() => {
        const container = containerRef.current
        if (!container) {
          return
        }
        const distanceFromBottom =
          container.scrollHeight - container.scrollTop - container.clientHeight
        shouldFollowRef.current = distanceFromBottom < 96
      }}
    >
      {messages.map((message) => (
        <article
          className={`message-row message-row--${message.role}`}
          key={message.id}
        >
          {message.role === 'assistant' && (
            <div className="assistant-avatar" aria-hidden="true">
              Z
            </div>
          )}
          <div className="message-content">
            <div className={`message-bubble message-bubble--${message.role}`}>
              {message.text || (
                <span className="typing-dots" aria-label="답변 작성 중">
                  <i />
                  <i />
                  <i />
                </span>
              )}
              {message.status === 'streaming' && message.text && (
                <span className="stream-cursor" aria-hidden="true" />
              )}
            </div>
            {message.recommendations && message.recommendations.length > 0 && (
              <div className="recommendation-list" aria-label="추천 음식점">
                <p className="meal-guidance">
                  실제로 드셨다면 <strong>먹었어요</strong>를 눌러 주세요. 최근 3일 기록은 다음 추천에 반영됩니다.
                </p>
                {message.recommendations.map((restaurant) => (
                  <article
                    className="recommendation-card"
                    key={restaurant.restaurantId}
                  >
                    <div className="recommendation-card__heading">
                      <div>
                        <strong>{restaurant.name}</strong>
                        <span>
                          {restaurant.category} · 강남구 논현동
                        </span>
                      </div>
                      {restaurant.sampleData && <em>샘플 데이터</em>}
                    </div>
                    <dl>
                      <div>
                        <dt>대표 메뉴</dt>
                        <dd>{restaurant.representativeMenu}</dd>
                      </div>
                      <div>
                        <dt>예상 가격</dt>
                        <dd>{restaurant.averagePrice.toLocaleString()}원</dd>
                      </div>
                      <div>
                        <dt>제로페이</dt>
                        <dd>{restaurant.zeroPayAvailable ? '가능' : '불가'}</dd>
                      </div>
                    </dl>
                    {restaurant.reason?.trim() && <p>{restaurant.reason}</p>}
                    <small>{restaurant.address}</small>
                    {message.serverMessageId && (
                      <button
                        className="meal-button"
                        type="button"
                        disabled={
                          recentMeals.some(
                            (meal) =>
                              meal.sourceMessageId === message.serverMessageId &&
                              meal.restaurantId === restaurant.restaurantId,
                          ) ||
                          (isMarking &&
                            markingRequest?.sourceMessageId === message.serverMessageId &&
                            markingRequest.restaurantId === restaurant.restaurantId)
                        }
                        onClick={() =>
                          void markEaten({
                            sourceMessageId: message.serverMessageId!,
                            restaurantId: restaurant.restaurantId,
                          })
                        }
                      >
                        {recentMeals.some(
                          (meal) =>
                            meal.sourceMessageId === message.serverMessageId &&
                            meal.restaurantId === restaurant.restaurantId,
                        )
                          ? '먹었다고 기록했어요'
                          : '먹었어요'}
                      </button>
                    )}
                  </article>
                ))}
                {markError && <p className="meal-error">{markError.message}</p>}
              </div>
            )}
            {message.status === 'error' && (
              <button
                className="message-action"
                type="button"
                onClick={() => onRetry(message.id)}
              >
                다시 시도
              </button>
            )}
            {message.status === 'stopped' && (
              <span className="message-status">생성 중지됨</span>
            )}
          </div>
        </article>
      ))}

      {messages.length === 1 && (
        <div className="starter-prompts" aria-label="추천 질문">
          <p>
            이렇게 물어보세요
          </p>
          {starterPrompts.map((prompt) => (
            <button
              type="button"
              key={prompt}
              onClick={() => onPromptSelect(prompt)}
            >
              {prompt}
              <span aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}

      {progress && (
        <p className="progress-message" role="status">
          <span className="progress-pulse" aria-hidden="true" />
          {progress}
        </p>
      )}
      <div ref={endRef} />
    </div>
  )
}
