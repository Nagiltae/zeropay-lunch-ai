// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import type { ChatMessage } from '../../types/chat'
import { MessageList } from './MessageList'

const mealMocks = vi.hoisted(() => ({
  markEaten: vi.fn(),
}))

vi.mock('../../hooks/useMealHistory', () => ({
  useMealHistory: () => ({
    recentMeals: [],
    markEaten: mealMocks.markEaten,
    markingRequest: undefined,
    isMarking: false,
    markError: null,
  }),
}))

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  cleanup()
  mealMocks.markEaten.mockReset()
})

describe('MessageList meal recording', () => {
  it('records a meal only when the user clicks the explicit button', async () => {
    mealMocks.markEaten.mockResolvedValue(undefined)
    const user = userEvent.setup()
    const messages: ChatMessage[] = [
      {
        id: 'assistant-local-id',
        serverMessageId: 'assistant-server-id',
        role: 'assistant',
        text: '한 곳을 추천했어요.',
        status: 'complete',
        recommendations: [
          {
            restaurantId: 1001,
            name: '강남 샘플 한식당',
            category: '한식',
            representativeMenu: '제육볶음',
            averagePrice: 9000,
            address: '서울특별시 강남구 강남대로 샘플 101',
            zeroPayAvailable: true,
            sampleData: true,
            reason: '요청 조건과 일치해요.',
          },
        ],
      },
    ]

    render(
      <MessageList
        messages={messages}
        progress={null}
        onPromptSelect={vi.fn()}
        onRetry={vi.fn()}
      />,
    )

    expect(mealMocks.markEaten).not.toHaveBeenCalled()
    expect(screen.getByText(/최근 3일 기록은 다음 추천에 반영됩니다/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '먹었어요' }))

    await waitFor(() => {
      expect(mealMocks.markEaten).toHaveBeenCalledWith({
        sourceMessageId: 'assistant-server-id',
        restaurantId: 1001,
      })
    })
  })
})
