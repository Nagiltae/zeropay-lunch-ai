/** Spring 세션 인증 요청의 공통 fetch 경계.
 * 상태 변경 요청에는 Spring Security CSRF 쿠키를 헤더로 전달한다.
 */
function getCsrfToken(): string | undefined {
  if (typeof document === 'undefined') return undefined
  const match = document.cookie.match(new RegExp('(^| )XSRF-TOKEN=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : undefined
}

export async function fetchWithAuth(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = { ...(init?.headers as Record<string, string>) }
  
  // 상태를 변경하는 요청만 CSRF 토큰을 전달해 읽기 요청의 의미를 보존한다.
  const method = init?.method?.toUpperCase() ?? 'GET'
  if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS' && method !== 'TRACE') {
    const csrfToken = getCsrfToken()
    if (csrfToken) {
      headers['X-XSRF-TOKEN'] = csrfToken
    }
  }

  const response = await fetch(input, {
    ...init,
    headers,
  })

  return response
}
