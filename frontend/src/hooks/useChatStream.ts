import { useCallback, useEffect, useRef, useState } from 'react'
import { streamChatMessage, type ChatStreamEvent } from '../api/chat'
import type { ChatMessage } from '../types/chat'

const welcomeMessage: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  text: '안녕하세요! 먼저 강남구 안에서 기준 위치를 선택하고, 오늘 먹고 싶은 점심을 편하게 이야기해 주세요.',
  status: 'complete',
}

function newConversationId() {
  return crypto.randomUUID()
}

export function useChatStream() {
  const [conversationId, setConversationId] = useState(newConversationId)
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage])
  const [progress, setProgress] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const activeAssistantIdRef = useRef<string | null>(null)

  useEffect(() => {
    return () => abortControllerRef.current?.abort()
  }, [])

  const updateMessage = useCallback(
    (messageId: string, updater: (message: ChatMessage) => ChatMessage) => {
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId ? updater(message) : message,
        ),
      )
    },
    [],
  )

  const handleStreamEvent = useCallback(
    (event: ChatStreamEvent, assistantId: string) => {
      switch (event.event) {
        case 'accepted':
          return
        case 'progress':
          setProgress(event.data.message)
          return
        case 'assistant_delta':
          setProgress(null)
          updateMessage(assistantId, (message) => ({
            ...message,
            text: message.text + event.data.text,
          }))
          return
        case 'completed':
          setProgress(null)
          updateMessage(assistantId, (message) => ({
            ...message,
            status: 'complete',
          }))
          return
        case 'error':
          throw new Error(event.data.message)
      }
    },
    [updateMessage],
  )

  const runStream = useCallback(
    async (assistantId: string, requestText: string) => {
      const controller = new AbortController()
      abortControllerRef.current = controller
      activeAssistantIdRef.current = assistantId
      setProgress('요청을 전송하고 있어요.')
      setIsStreaming(true)

      try {
        await streamChatMessage(
          conversationId,
          requestText,
          (event) => handleStreamEvent(event, assistantId),
          controller.signal,
        )
      } catch (caughtError) {
        if (controller.signal.aborted) {
          return
        }

        const errorMessage =
          caughtError instanceof Error
            ? caughtError.message
            : '답변을 받지 못했습니다.'
        updateMessage(assistantId, (message) => ({
          ...message,
          text: errorMessage,
          status: 'error',
        }))
      } finally {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null
          activeAssistantIdRef.current = null
          setProgress(null)
          setIsStreaming(false)
        }
      }
    },
    [conversationId, handleStreamEvent, updateMessage],
  )

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmedMessage = text.trim()
      if (!trimmedMessage || isStreaming || activeAssistantIdRef.current) {
        return
      }

      const assistantId = crypto.randomUUID()
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'user',
          text: trimmedMessage,
          status: 'complete',
        },
        {
          id: assistantId,
          role: 'assistant',
          text: '',
          status: 'streaming',
          requestText: trimmedMessage,
        },
      ])

      await runStream(assistantId, trimmedMessage)
    },
    [isStreaming, runStream],
  )

  const retryMessage = useCallback(
    async (messageId: string) => {
      if (isStreaming || activeAssistantIdRef.current) {
        return
      }

      const message = messages.find((candidate) => candidate.id === messageId)
      if (!message?.requestText) {
        return
      }

      updateMessage(messageId, (current) => ({
        ...current,
        text: '',
        status: 'streaming',
      }))
      await runStream(messageId, message.requestText)
    },
    [isStreaming, messages, runStream, updateMessage],
  )

  const stopStreaming = useCallback(() => {
    const assistantId = activeAssistantIdRef.current
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    activeAssistantIdRef.current = null
    setProgress(null)
    setIsStreaming(false)

    if (assistantId) {
      updateMessage(assistantId, (message) => ({
        ...message,
        text: message.text || '답변 생성을 중지했어요.',
        status: 'stopped',
      }))
    }
  }, [updateMessage])

  const resetConversation = useCallback(() => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    activeAssistantIdRef.current = null
    setConversationId(newConversationId())
    setMessages([welcomeMessage])
    setProgress(null)
    setIsStreaming(false)
  }, [])

  return {
    messages,
    progress,
    isStreaming,
    sendMessage,
    retryMessage,
    stopStreaming,
    resetConversation,
  }
}
