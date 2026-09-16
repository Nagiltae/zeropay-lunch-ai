import { fetchWithAuth } from './client'
import type { MarkMealRequest, MealRecord } from '../types/meal'

async function readError(response: Response) {
  const body = (await response.json().catch(() => ({}))) as {
    detail?: string
    message?: string
  }
  return body.detail ?? body.message
}

export async function getRecentMeals(): Promise<MealRecord[]> {
  const response = await fetchWithAuth('/api/meals/recent')
  if (!response.ok) {
    throw new Error((await readError(response)) ?? '최근 식사 기록을 불러오지 못했습니다.')
  }
  return response.json()
}

export async function markMealEaten(request: MarkMealRequest): Promise<MealRecord> {
  const response = await fetchWithAuth('/api/meals', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error((await readError(response)) ?? '식사 기록을 저장하지 못했습니다.')
  }
  return response.json()
}
