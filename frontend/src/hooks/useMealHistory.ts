import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getRecentMeals, markMealEaten } from '../api/meals'

export function useMealHistory() {
  const queryClient = useQueryClient()
  const recentQuery = useQuery({
    queryKey: ['meals', 'recent'],
    queryFn: getRecentMeals,
  })
  const markMutation = useMutation({
    mutationFn: markMealEaten,
    onSuccess: (meal) => {
      queryClient.setQueryData(
        ['meals', 'recent'],
        (current: typeof recentQuery.data = []) => [
          meal,
          ...(current ?? []).filter((item) => item.mealId !== meal.mealId),
        ],
      )
    },
  })

  return {
    recentMeals: recentQuery.data ?? [],
    markEaten: markMutation.mutateAsync,
    markingRequest: markMutation.variables,
    isMarking: markMutation.isPending,
    markError: markMutation.error,
  }
}
