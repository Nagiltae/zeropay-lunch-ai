import { useState } from 'react'
import './App.css'
import { ChatHeader } from './components/chat/ChatHeader'
import { LocationSelector } from './components/chat/LocationSelector'
import { MessageComposer } from './components/chat/MessageComposer'
import { MessageList } from './components/chat/MessageList'
import { useChatStream } from './hooks/useChatStream'
import type { GangnamLocation } from './types/chat'

function App() {
  const [selectedLocation, setSelectedLocation] =
    useState<GangnamLocation | null>(null)
  const {
    messages,
    progress,
    isStreaming,
    sendMessage,
    retryMessage,
    stopStreaming,
    resetConversation,
  } = useChatStream()

  const resetWithConfirmation = () => {
    if (
      messages.length > 1 &&
      !window.confirm(
        '현재 대화 내용을 초기화할까요? 선택한 기준 위치는 유지됩니다.',
      )
    ) {
      return
    }
    resetConversation()
  }

  return (
    <main className="app-shell">
      <section className="chat-app" aria-labelledby="page-title">
        <ChatHeader
          hasConversation={messages.length > 1 || isStreaming}
          onReset={resetWithConfirmation}
        />
        <LocationSelector
          selectedLocation={selectedLocation}
          onSelect={setSelectedLocation}
        />
        <MessageList
          messages={messages}
          progress={progress}
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
