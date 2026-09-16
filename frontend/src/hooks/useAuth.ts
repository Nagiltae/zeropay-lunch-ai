import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchCsrfToken, getCurrentUser, login, signup, logout } from '../api/auth'
import type { LoginRequest, SignupRequest, User } from '../types/auth'

export function useCurrentUser() {
  const {
    data: user,
    isPending: isUserLoading,
    error: userError,
  } = useQuery<User | null, Error>({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
    retry: false, // Don't retry on 401
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  return {
    user,
    isUserLoading,
    isAuthenticated: !!user && !userError,
  }
}

export function useAuthMutations() {
  const queryClient = useQueryClient()

  const loginMutation = useMutation({
    mutationFn: async (request: LoginRequest) => {
      await fetchCsrfToken()
      return login(request)
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['currentUser'], data)
    },
  })

  const signupMutation = useMutation({
    mutationFn: async (request: SignupRequest) => {
      await fetchCsrfToken()
      return signup(request)
    },
  })

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.setQueryData(['currentUser'], null)
    },
  })

  return {
    login: loginMutation.mutateAsync,
    isLoginPending: loginMutation.isPending,
    loginError: loginMutation.error,
    signup: signupMutation.mutateAsync,
    isSignupPending: signupMutation.isPending,
    signupError: signupMutation.error,
    logout: logoutMutation.mutateAsync,
  }
}
