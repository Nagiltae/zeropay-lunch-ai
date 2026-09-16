import type { RestaurantCategory } from './preference'

export type MealRecord = {
  mealId: string
  restaurantId: number
  restaurantName: string
  category: RestaurantCategory
  sourceMessageId: string
  eatenAt: string
}

export type MarkMealRequest = {
  restaurantId: number
  sourceMessageId: string
}
