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
  category: string | null
  representativeMenu: string | null
  averagePrice: number | null
  menuExamples?: { name: string; price: number | null }[]
  address: string
  zeroPayAvailable: boolean
  sampleData: boolean
  reason?: string
}

export type GangnamLocation = {
  id: string
  label: string
  description: string
}
