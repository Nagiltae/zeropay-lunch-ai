import { afterEach, describe, expect, it, vi } from 'vitest'
import { createConversation, streamChatMessage } from './chat'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('chat API', () => {
  it('creates a conversation without location parameters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          conversationId: 'conversation-id',
          active: true,
          createdAt: '2026-09-16T00:00:00Z',
        }),
        { status: 201, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await createConversation()

    expect(result.conversationId).toBe('conversation-id')
    expect(fetchMock).toHaveBeenCalledWith('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  })

  it('parses recommendations and completion from a chunked SSE response', async () => {
    const encoder = new TextEncoder()
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            'event:recommendations\ndata:{"items":[{"restaurantId":1001,',
          ),
        )
        controller.enqueue(
          encoder.encode(
            '"name":"강남 샘플 한식당"}]}\n\nevent:completed\ndata:{"assistantMessageId":"assistant-id"}\n\n',
          ),
        )
        controller.close()
      },
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(body, {
          status: 200,
          headers: { 'Content-Type': 'text/event-stream' },
        }),
      ),
    )
    const receivedEvents: string[] = []

    await streamChatMessage(
      'conversation-id',
      '점심 추천해줘',
      (event) => receivedEvents.push(event.event),
      new AbortController().signal,
    )

    expect(receivedEvents).toEqual(['recommendations', 'completed'])
  })
})
