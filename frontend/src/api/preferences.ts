import { fetchWithAuth } from './client'
import type {
  UpdatePreferenceRequest,
  UserPreference,
} from '../types/preference'

async function readError(response: Response) {
  const body = (await response.json().catch(() => ({}))) as {
    detail?: string
    message?: string
  }
  return body.detail ?? body.message
}

export async function getPreferences(): Promise<UserPreference> {
  const response = await fetchWithAuth('/api/preferences/me')
  if (!response.ok) {
    throw new Error((await readError(response)) ?? '취향 설정을 불러오지 못했습니다.')
  }
  return response.json()
}

export async function updatePreferences(
  request: UpdatePreferenceRequest,
): Promise<UserPreference> {
  const response = await fetchWithAuth('/api/preferences/me', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    throw new Error((await readError(response)) ?? '취향 설정을 저장하지 못했습니다.')
  }
  return response.json()
}
