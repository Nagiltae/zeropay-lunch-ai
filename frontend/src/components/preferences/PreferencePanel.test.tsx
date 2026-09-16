// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PreferencePanel } from './PreferencePanel'

const preferenceMocks = vi.hoisted(() => ({
  save: vi.fn(),
  preference: {
    defaultBudget: 12_000,
    spiceLevel: 'MEDIUM' as const,
    preferredCategories: ['KOREAN'] as const,
    dislikedCategories: ['SALAD'] as const,
    allergies: ['땅콩'],
    zeroPayRequired: true as const,
  },
}))

vi.mock('../../hooks/usePreferences', () => ({
  usePreferences: () => ({
    preference: preferenceMocks.preference,
    isLoading: false,
    loadError: null,
    save: preferenceMocks.save,
    isSaving: false,
    saveError: null,
  }),
}))

afterEach(() => {
  cleanup()
  preferenceMocks.save.mockReset()
})

describe('PreferencePanel', () => {
  it('keeps preferred and disliked categories exclusive and saves the form', async () => {
    preferenceMocks.save.mockResolvedValue(undefined)
    const user = userEvent.setup()

    render(<PreferencePanel onClose={vi.fn()} />)

    const budget = await screen.findByLabelText('기본 점심 예산')
    await waitFor(() => expect(budget).toHaveProperty('value', '12000'))

    const koreanChoices = screen.getAllByLabelText('한식')
    expect(koreanChoices).toHaveLength(2)
    expect(koreanChoices[0]).toHaveProperty('checked', true)

    await user.click(koreanChoices[1])
    expect(koreanChoices[0]).toHaveProperty('checked', false)
    expect(koreanChoices[1]).toHaveProperty('checked', true)
    await user.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => {
      expect(preferenceMocks.save).toHaveBeenCalledWith({
        defaultBudget: 12_000,
        spiceLevel: 'MEDIUM',
        preferredCategories: [],
        dislikedCategories: ['SALAD', 'KOREAN'],
        allergies: ['땅콩'],
      })
    })
    expect(await screen.findByText('취향을 저장했습니다.')).toBeTruthy()
  })
})
