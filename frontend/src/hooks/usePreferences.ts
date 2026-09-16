import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getPreferences, updatePreferences } from '../api/preferences'

export function usePreferences() {
  const queryClient = useQueryClient()
  const preferenceQuery = useQuery({
    queryKey: ['preferences'],
    queryFn: getPreferences,
  })
  const updateMutation = useMutation({
    mutationFn: updatePreferences,
    onSuccess: (preference) => {
      queryClient.setQueryData(['preferences'], preference)
    },
  })

  return {
    preference: preferenceQuery.data,
    isLoading: preferenceQuery.isLoading,
    loadError: preferenceQuery.error,
    save: updateMutation.mutateAsync,
    isSaving: updateMutation.isPending,
    saveError: updateMutation.error,
  }
}
