/**
 * 현재 대화의 복원, 메시지 전송, SSE 이벤트 반영을 한 곳에서 관리한다.
 * 브라우저는 FastAPI가 아니라 Spring의 스트림 endpoint만 호출한다.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createConversation,
  deactivateConversation,
  getConversation,
  streamChatMessage,
  type ChatStreamEvent,
  type ConversationHistory,
} from '../api/chat'
import type { ChatMessage, MessageStatus } from '../types/chat'

const conversationStorageKey = 'zeropay-lunch-active-conversation'

const welcomeMessage: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  text: '안녕하세요! 강남구 논현동에서 오늘 먹고 싶은 점심을 편하게 이야기해 주세요.',
  status: 'complete',
}

function restoredMessageStatus(
  status: ConversationHistory['messages'][number]['status'],
): MessageStatus {
  if (status === 'COMPLETED') return 'complete'
  if (status === 'FAILED') return 'error'
  return 'stopped'
}

function restoreMessages(history: ConversationHistory): ChatMessage[] {
  return [
    welcomeMessage,
    ...history.messages.map((message) => ({
      id: message.messageId,
      role: message.role === 'USER' ? ('user' as const) : ('assistant' as const),
      text:
        message.content ||
        (message.status === 'PENDING'
          ? '이전 답변이 완료되지 않았어요.'
          : message.content),
      status: restoredMessageStatus(message.status),
      serverMessageId: message.messageId,
      recommendations: message.recommendations,
    })),
  ]
}

export function useChatStream(isAuthenticated: boolean) {
  const [conversationId, setConversationId] = useState<string | null>(() =>
    window.localStorage.getItem(conversationStorageKey),
  )
  const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage])
  const [progress, setProgress] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const activeAssistantIdRef = useRef<string | null>(null)
  const restoredConversationRef = useRef<string | null>(null)

  const historyQuery = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => getConversation(conversationId!),
    enabled: isAuthenticated && conversationId !== null,
    staleTime: Number.POSITIVE_INFINITY,
  })
  const createMutation = useMutation({ mutationFn: createConversation })
  const deactivateMutation = useMutation({ mutationFn: deactivateConversation })

  // SSE 연결은 컴포넌트가 사라질 때 취소해 서버의 진행 중인 교환과 화면 상태가 어긋나지 않게 한다.
  useEffect(() => {
    const history = historyQuery.data
    if (!history || restoredConversationRef.current === history.conversationId) {
      return
    }
    restoredConversationRef.current = history.conversationId
    if (!history.active) {
      window.localStorage.removeItem(conversationStorageKey)
      setConversationId(null)
      setMessages([welcomeMessage])
      return
    }
    setMessages(restoreMessages(history))
  }, [historyQuery.data])

  useEffect(() => {
    if (!historyQuery.isError || !conversationId) {
      return
    }
    window.localStorage.removeItem(conversationStorageKey)
    setConversationId(null)
    setMessages([welcomeMessage])
  }, [conversationId, historyQuery.isError])

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
          updateMessage(assistantId, (message) => ({
            ...message,
            serverMessageId: event.data.assistantMessageId,
          }))
          return
        case 'progress':
          setProgress(event.data.message)
          return
        case 'recommendations':
          updateMessage(assistantId, (message) => ({
            ...message,
            recommendations: event.data.items,
          }))
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

  const ensureConversation = useCallback(async () => {
    if (conversationId) {
      return conversationId
    }
    const created = await createMutation.mutateAsync()
    window.localStorage.setItem(conversationStorageKey, created.conversationId)
    setConversationId(created.conversationId)
    restoredConversationRef.current = created.conversationId
    return created.conversationId
  }, [conversationId, createMutation])

  const runStream = useCallback(
    async (assistantId: string, requestText: string) => {
      const controller = new AbortController()
      abortControllerRef.current = controller
      activeAssistantIdRef.current = assistantId
      setProgress('요청을 전송하고 있어요.')
      setIsStreaming(true)

      try {
        const activeConversationId = await ensureConversation()
        await streamChatMessage(
          activeConversationId,
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
    [ensureConversation, handleStreamEvent, updateMessage],
  )

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmedMessage = text.trim()
      if (
        !trimmedMessage ||
        isStreaming ||
        activeAssistantIdRef.current
      ) {
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
        recommendations: [],
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

  const resetConversation = useCallback(async () => {
    abortControllerRef.current?.abort()
    if (conversationId) {
      await deactivateMutation.mutateAsync(conversationId)
    }
    abortControllerRef.current = null
    activeAssistantIdRef.current = null
    restoredConversationRef.current = null
    window.localStorage.removeItem(conversationStorageKey)
    setConversationId(null)
    setMessages([welcomeMessage])
    setProgress(null)
    setIsStreaming(false)
  }, [conversationId, deactivateMutation])

  const clearLocalConversation = useCallback(() => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    activeAssistantIdRef.current = null
    restoredConversationRef.current = null
    window.localStorage.removeItem(conversationStorageKey)
    setConversationId(null)
    setMessages([welcomeMessage])
    setProgress(null)
    setIsStreaming(false)
  }, [])

  return {
    conversationId,
    messages,
    progress,
    isStreaming,
    isRestoring: historyQuery.isLoading,
    sendMessage,
    retryMessage,
    stopStreaming,
    resetConversation,
    clearLocalConversation,
  }
}
