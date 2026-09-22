/**
 * 로그인 상태에 따라 인증 화면 또는 채팅 중심의 서비스 화면을 선택한다.
 * 실제 데이터 요청은 하위 hook과 Spring API client가 담당한다.
 */
import { useState } from 'react'
import './App.css'
import { ChatHeader } from './components/chat/ChatHeader'
import { MessageComposer } from './components/chat/MessageComposer'
import { MessageList } from './components/chat/MessageList'
import { AuthScreen } from './components/auth/AuthScreen'
import { PreferencePanel } from './components/preferences/PreferencePanel'
import { useChatStream } from './hooks/useChatStream'
import { useCurrentUser, useAuthMutations } from './hooks/useAuth'

function App() {
  const { isAuthenticated, isUserLoading } = useCurrentUser()
  const { logout } = useAuthMutations()
  const [preferencesOpen, setPreferencesOpen] = useState(false)
  const {
    conversationId,
    messages,
    progress,
    isStreaming,
    isRestoring,
    sendMessage,
    retryMessage,
    stopStreaming,
    resetConversation,
    clearLocalConversation,
  } = useChatStream(isAuthenticated)

  const logoutAndClearChat = async () => {
    await logout()
    clearLocalConversation()
  }

  const resetWithConfirmation = async () => {
    if (
      messages.length > 1 &&
      !window.confirm(
        '현재 대화 내용을 초기화할까요?',
      )
    ) {
      return
    }
    try {
      await resetConversation()
    } catch {
      window.alert('대화를 초기화하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    }
  }

  // 인증이 끝나기 전에는 화면을 노출하지 않고, 인증 후에만 대화와 개인화 기능을 연결한다.
  if (isUserLoading) {
    return <div className="loading-screen">로딩 중...</div>
  }

  if (!isAuthenticated) {
    return <AuthScreen />
  }

  return (
    <main className="app-shell">
      <section className="chat-app" aria-labelledby="page-title">
        <ChatHeader
          hasConversation={conversationId !== null || messages.length > 1}
          onReset={() => void resetWithConfirmation()}
          onOpenPreferences={() => setPreferencesOpen(true)}
          onLogout={() => void logoutAndClearChat()}
        />
        <MessageList
          messages={messages}
          progress={isRestoring ? '이전 대화를 불러오고 있어요.' : progress}
          onPromptSelect={(prompt) => void sendMessage(prompt)}
          onRetry={(messageId) => void retryMessage(messageId)}
        />
        <MessageComposer
          disabled={false}
          isStreaming={isStreaming}
          onSend={(message) => void sendMessage(message)}
          onStop={stopStreaming}
        />
      </section>
      {preferencesOpen && (
        <PreferencePanel onClose={() => setPreferencesOpen(false)} />
      )}
    </main>
  )
}

export default App
