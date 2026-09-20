export type MessageStatus = 'complete' | 'streaming' | 'error' | 'stopped'

export type ChatMessage = {
  id: string
  role: 'assistant' | 'user'
  text: string
  status: MessageStatus
  requestText?: string
  serverMessageId?: string
  recommendations?: RestaurantRecommendation[]
}

export type RestaurantRecommendation = {
  restaurantId: number
  name: string
  category: string
  representativeMenu: string
  averagePrice: number
  address: string
  zeroPayAvailable: boolean
  sampleData: boolean
  reason: string
}

export type GangnamLocation = {
  id: string
  label: string
  description: string
}
