import type { RestaurantRecommendation } from '../types/chat'

type AcceptedEvent = {
  event: 'accepted'
  data: {
    conversationId: string
    userMessageId: string
    assistantMessageId: string
  }
}

type RecommendationsEvent = {
  event: 'recommendations'
  data: {
    items: RestaurantRecommendation[]
  }
}

type ProgressEvent = {
  event: 'progress'
  data: {
    stage: 'ANALYZING' | 'PREPARING'
    message: string
  }
}

type AssistantDeltaEvent = {
  event: 'assistant_delta'
  data: {
    text: string
  }
}

type CompletedEvent = {
  event: 'completed'
  data: {
    assistantMessageId: string
  }
}

type ErrorEvent = {
  event: 'error'
  data: {
    code: string
    message: string
  }
}

export type ChatStreamEvent =
  | AcceptedEvent
  | ProgressEvent
  | RecommendationsEvent
  | AssistantDeltaEvent
  | CompletedEvent
  | ErrorEvent

const eventNames = new Set([
  'accepted',
  'progress',
  'recommendations',
  'assistant_delta',
  'completed',
  'error',
])

export type ConversationResponse = {
  conversationId: string
  locationId: string
  active: boolean
  createdAt: string
}

export type ConversationHistory = ConversationResponse & {
  messages: Array<{
    messageId: string
    role: 'USER' | 'ASSISTANT'
    status: 'PENDING' | 'COMPLETED' | 'FAILED' | 'STOPPED'
    content: string
    createdAt: string
    recommendations: RestaurantRecommendation[]
  }>
}

async function readError(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string; message?: string }
    return body.detail ?? body.message
  } catch {
    return undefined
  }
}

export async function createConversation(locationId: string) {
  const response = await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ locationId }),
  })
  if (!response.ok) {
    throw new Error(
      (await readError(response)) ?? '새 대화를 시작하지 못했습니다.',
    )
  }
  return (await response.json()) as ConversationResponse
}

export async function deactivateConversation(conversationId: string) {
  const response = await fetch(
    `/api/conversations/${encodeURIComponent(conversationId)}/deactivate`,
    { method: 'POST' },
  )
  if (!response.ok) {
    throw new Error(
      (await readError(response)) ?? '대화를 초기화하지 못했습니다.',
    )
  }
}

export async function getConversation(conversationId: string) {
  const response = await fetch(
    `/api/conversations/${encodeURIComponent(conversationId)}`,
  )
  if (!response.ok) {
    throw new Error(
      (await readError(response)) ?? '대화 기록을 불러오지 못했습니다.',
    )
  }
  return (await response.json()) as ConversationHistory
}

function parseEventBlock(block: string): ChatStreamEvent | null {
  let eventName = ''
  const dataLines: string[] = []

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith('event:')) {
      eventName = line.slice('event:'.length).trim()
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).trimStart())
    }
  }

  if (!eventNames.has(eventName) || dataLines.length === 0) {
    return null
  }

  return {
    event: eventName,
    data: JSON.parse(dataLines.join('\n')),
  } as ChatStreamEvent
}

function findEventBoundary(buffer: string) {
  const lineFeedBoundary = buffer.indexOf('\n\n')
  const carriageReturnBoundary = buffer.indexOf('\r\n\r\n')

  if (lineFeedBoundary === -1) {
    return carriageReturnBoundary === -1
      ? null
      : { index: carriageReturnBoundary, length: 4 }
  }
  if (carriageReturnBoundary === -1 || lineFeedBoundary < carriageReturnBoundary) {
    return { index: lineFeedBoundary, length: 2 }
  }
  return { index: carriageReturnBoundary, length: 4 }
}

export async function streamChatMessage(
  conversationId: string,
  message: string,
  onEvent: (event: ChatStreamEvent) => void,
  signal: AbortSignal,
) {
  const response = await fetch(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages`,
    {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message }),
      signal,
    },
  )

  if (!response.ok) {
    throw new Error('채팅 서버가 요청을 처리하지 못했습니다.')
  }
  if (!response.body) {
    throw new Error('이 브라우저에서는 스트리밍 응답을 읽을 수 없습니다.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false

  const dispatchEvent = (event: ChatStreamEvent) => {
    if (event.event === 'completed') {
      completed = true
    }
    onEvent(event)
  }

  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })

    let boundary = findEventBoundary(buffer)
    while (boundary) {
      const block = buffer.slice(0, boundary.index)
      buffer = buffer.slice(boundary.index + boundary.length)
      const event = parseEventBlock(block)
      if (event) {
        dispatchEvent(event)
      }
      boundary = findEventBoundary(buffer)
    }

    if (done) {
      const finalEvent = parseEventBlock(buffer)
      if (finalEvent) {
        dispatchEvent(finalEvent)
      }
      if (!completed) {
        throw new Error('답변 스트림이 완료되기 전에 종료되었습니다.')
      }
      break
    }
  }
}
