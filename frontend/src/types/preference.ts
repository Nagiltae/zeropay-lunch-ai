export type RestaurantCategory = 'KOREAN' | 'KOREAN_SOUP' | 'SALAD'

export type SpiceLevel = 'ANY' | 'MILD' | 'MEDIUM' | 'HOT'

export type UserPreference = {
  defaultBudget: number | null
  spiceLevel: SpiceLevel
  preferredCategories: RestaurantCategory[]
  dislikedCategories: RestaurantCategory[]
  allergies: string[]
  zeroPayRequired: true
}

export type UpdatePreferenceRequest = Omit<UserPreference, 'zeroPayRequired'>
