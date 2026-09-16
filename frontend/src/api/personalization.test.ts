import { afterEach, describe, expect, it, vi } from 'vitest'
import { markMealEaten } from './meals'
import { updatePreferences } from './preferences'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('personalization APIs', () => {
  it('updates user preferences through the authenticated API client', async () => {
    vi.stubGlobal('document', { cookie: 'XSRF-TOKEN=preference-token' })
    const preference = {
      defaultBudget: 12000,
      spiceLevel: 'MEDIUM' as const,
      preferredCategories: ['KOREAN' as const],
      dislikedCategories: ['SALAD' as const],
      allergies: ['땅콩'],
    }
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ...preference, zeroPayRequired: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await updatePreferences(preference)

    expect(result.zeroPayRequired).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/preferences/me', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-XSRF-TOKEN': 'preference-token',
      },
      body: JSON.stringify(preference),
    })
  })

  it('records a meal only through the explicit mark-eaten request', async () => {
    vi.stubGlobal('document', { cookie: 'XSRF-TOKEN=meal-token' })
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          mealId: 'meal-id',
          restaurantId: 1001,
          restaurantName: '강남 샘플 한식당',
          category: 'KOREAN',
          sourceMessageId: 'message-id',
          eatenAt: '2026-09-17T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await markMealEaten({ restaurantId: 1001, sourceMessageId: 'message-id' })

    expect(fetchMock).toHaveBeenCalledWith('/api/meals', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-XSRF-TOKEN': 'meal-token',
      },
      body: JSON.stringify({ restaurantId: 1001, sourceMessageId: 'message-id' }),
    })
  })
})
