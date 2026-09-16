import { useState } from 'react'
import { useAuthMutations } from '../../hooks/useAuth'
import './AuthScreen.css'

export function AuthScreen() {
  const [isLogin, setIsLogin] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  
  const { login, signup, isLoginPending, isSignupPending, loginError, signupError } = useAuthMutations()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      if (isLogin) {
        await login({ email, password })
      } else {
        await signup({ email, password, displayName })
        setIsLogin(true)
        alert('회원가입이 완료되었습니다. 로그인해주세요.')
      }
    } catch {
      // React Query exposes the request error below the form.
    }
  }

  const toggleMode = () => {
    setIsLogin(!isLogin)
    setEmail('')
    setPassword('')
    setDisplayName('')
  }

  const currentError = isLogin ? loginError : signupError
  const isPending = isLogin ? isLoginPending : isSignupPending

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h2>{isLogin ? '로그인' : '회원가입'}</h2>
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              maxLength={255}
              disabled={isPending}
            />
          </div>
          {!isLogin && (
            <div className="form-group">
              <label htmlFor="displayName">이름</label>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                maxLength={100}
                disabled={isPending}
              />
            </div>
          )}
          <div className="form-group">
            <label htmlFor="password">비밀번호</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              maxLength={72}
              disabled={isPending}
            />
          </div>
          
          {currentError && (
            <div className="error-message">
              {currentError.message}
            </div>
          )}

          <button type="submit" className="submit-button" disabled={isPending}>
            {isPending ? '처리 중...' : (isLogin ? '로그인' : '회원가입')}
          </button>
        </form>

        <p className="toggle-mode">
          {isLogin ? '계정이 없으신가요?' : '이미 계정이 있으신가요?'}
          <button type="button" onClick={toggleMode} className="text-button">
            {isLogin ? '회원가입' : '로그인'}
          </button>
        </p>
      </div>
    </div>
  )
}
