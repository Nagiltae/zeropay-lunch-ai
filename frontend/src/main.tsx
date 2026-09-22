/**
 * React 애플리케이션 진입점.
 * React Query를 전역으로 제공하고 App이 인증·채팅·취향 화면을 조합하도록 연결한다.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

// 인증·채팅·환경설정 화면은 Spring API를 통해서만 데이터를 주고받는다.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
