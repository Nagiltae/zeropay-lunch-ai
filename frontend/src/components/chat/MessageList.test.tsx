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

describe('MessageList recommendations', () => {
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
    expect(screen.getByText('요청 조건과 일치해요.')).toBeTruthy()
    expect(screen.getByText(/최근 3일 기록은 다음 추천에 반영됩니다/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '먹었어요' }))

    await waitFor(() => {
      expect(mealMocks.markEaten).toHaveBeenCalledWith({
        sourceMessageId: 'assistant-server-id',
        restaurantId: 1001,
      })
    })
  })

  it('renders up to three recommendation reasons and tolerates a legacy item without reason', () => {
    const messages: ChatMessage[] = [{
      id: 'assistant', role: 'assistant', text: '추천 결과예요.', status: 'complete',
      recommendations: [1, 2, 3].map((id) => ({
        restaurantId: id, name: `식당 ${id}`, category: '한식', representativeMenu: '메뉴',
        averagePrice: 9000, address: '논현동', zeroPayAvailable: true, sampleData: false,
        ...(id === 1 ? { reason: '안전한 결정론 사유' } : {}),
      })),
    }]
    render(<MessageList messages={messages} progress={null} onPromptSelect={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByLabelText('추천 음식점').querySelectorAll('.recommendation-card')).toHaveLength(3)
    expect(screen.getByText('식당 3')).toBeTruthy()
    expect(screen.getByText('안전한 결정론 사유')).toBeTruthy()
    expect(screen.queryByText('undefined')).toBeNull()
  })

  it('renders an empty recommendation list without breaking the chat message', () => {
    render(<MessageList messages={[{
      id: 'assistant', role: 'assistant', text: '조건에 맞는 음식점을 찾지 못했어요.',
      status: 'complete', recommendations: [],
    }]} progress={null} onPromptSelect={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText('조건에 맞는 음식점을 찾지 못했어요.')).toBeTruthy()
    expect(screen.queryByLabelText('추천 음식점')).toBeNull()
  })

  it('renders source menu examples without presenting them as representative menus or prices', () => {
    render(<MessageList messages={[{
      id: 'assistant', role: 'assistant', text: '추천 결과예요.', status: 'complete',
      recommendations: [{
        restaurantId: 77, name: '검증 식당', category: null, representativeMenu: null,
        averagePrice: null, address: '논현동', zeroPayAvailable: true, sampleData: false,
        menuExamples: [{ name: '짜장면', price: 9000 }], reason: '요청과 맞아요.',
      }],
    }]} progress={null} onPromptSelect={vi.fn()} onRetry={vi.fn()} />)

    expect(screen.getByText('메뉴 예시')).toBeTruthy()
    expect(screen.getByText('짜장면 · 9,000원')).toBeTruthy()
    expect(screen.queryByText('대표 메뉴')).toBeNull()
    expect(screen.queryByText('예상 가격')).toBeNull()
  })
})
