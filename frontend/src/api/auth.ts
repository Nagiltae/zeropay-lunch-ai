import { fetchWithAuth } from './client'
import type { User, LoginRequest, SignupRequest } from '../types/auth'

export async function fetchCsrfToken(): Promise<void> {
  const response = await fetchWithAuth('/api/auth/csrf')
  if (!response.ok) {
    throw new Error('CSRF 토큰을 가져오지 못했습니다.')
  }
}

export async function getCurrentUser(): Promise<User> {
  const response = await fetchWithAuth('/api/auth/me')
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('UNAUTHORIZED')
    }
    throw new Error('사용자 정보를 가져오지 못했습니다.')
  }
  return response.json()
}

export async function login(request: LoginRequest): Promise<User> {
  const response = await fetchWithAuth('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.message || '로그인에 실패했습니다.')
  }
  return response.json()
}

export async function signup(request: SignupRequest): Promise<void> {
  const response = await fetchWithAuth('/api/auth/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.message || '회원가입에 실패했습니다.')
  }
}

export async function logout(): Promise<void> {
  const response = await fetchWithAuth('/api/auth/logout', {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error('로그아웃에 실패했습니다.')
  }
}
