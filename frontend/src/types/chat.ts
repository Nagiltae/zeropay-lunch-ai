export type MessageStatus = 'complete' | 'streaming' | 'error' | 'stopped'

export type ChatMessage = {
  id: string
  role: 'assistant' | 'user'
  text: string
  status: MessageStatus
  requestText?: string
}

export type GangnamLocation = {
  id: string
  label: string
  description: string
}
