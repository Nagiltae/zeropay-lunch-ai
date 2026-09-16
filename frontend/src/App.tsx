import { useState } from 'react'
import './App.css'
import { ChatHeader } from './components/chat/ChatHeader'
import { LocationSelector } from './components/chat/LocationSelector'
import { MessageComposer } from './components/chat/MessageComposer'
import { MessageList } from './components/chat/MessageList'
import { AuthScreen } from './components/auth/AuthScreen'
import { gangnamLocations } from './data/gangnamLocations'
import { useChatStream } from './hooks/useChatStream'
import { useCurrentUser, useAuthMutations } from './hooks/useAuth'
import type { GangnamLocation } from './types/chat'

const locationStorageKey = 'zeropay-lunch-selected-location'

function restoreLocation() {
  const storedId = window.localStorage.getItem(locationStorageKey)
  return gangnamLocations.find((location) => location.id === storedId) ?? null
}

function App() {
  const { isAuthenticated, isUserLoading } = useCurrentUser()
  const { logout } = useAuthMutations()
  const [selectedLocation, setSelectedLocation] =
    useState<GangnamLocation | null>(restoreLocation)
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
  } = useChatStream(selectedLocation?.id ?? null, isAuthenticated)

  const logoutAndClearChat = async () => {
    await logout()
    clearLocalConversation()
  }

  const resetWithConfirmation = async () => {
    if (
      messages.length > 1 &&
      !window.confirm(
        '현재 대화 내용을 초기화할까요? 선택한 기준 위치는 유지됩니다.',
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

  const selectLocation = async (location: GangnamLocation) => {
    if (location.id === selectedLocation?.id) {
      return
    }
    if (
      conversationId &&
      !window.confirm(
        '기준 위치를 변경하면 현재 대화를 종료하고 새 대화를 시작합니다. 변경할까요?',
      )
    ) {
      return
    }
    try {
      if (conversationId) {
        await resetConversation()
      }
      window.localStorage.setItem(locationStorageKey, location.id)
      setSelectedLocation(location)
    } catch {
      window.alert('기준 위치를 변경하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    }
  }

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
          onLogout={() => void logoutAndClearChat()}
        />
        <LocationSelector
          selectedLocation={selectedLocation}
          onSelect={(location) => void selectLocation(location)}
        />
        <MessageList
          messages={messages}
          progress={isRestoring ? '이전 대화를 불러오고 있어요.' : progress}
          locationSelected={selectedLocation !== null}
          onPromptSelect={(prompt) => void sendMessage(prompt)}
          onRetry={(messageId) => void retryMessage(messageId)}
        />
        <MessageComposer
          disabled={selectedLocation === null}
          isStreaming={isStreaming}
          onSend={(message) => void sendMessage(message)}
          onStop={stopStreaming}
        />
      </section>
    </main>
  )
}

export default App
