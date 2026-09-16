import './App.css'

function App() {
  return (
    <main className="app-shell">
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">ZeroPay Lunch AI</p>
        <h1 id="page-title">오늘 점심, 상황에 맞게 골라드릴게요.</h1>
        <p className="description">
          자연어 요청과 취향, 예산, 최근 식사 기록을 함께 고려하는 추천 서비스를 준비하고 있습니다.
        </p>
        <span className="status">Phase 1 · Project skeleton</span>
      </section>
    </main>
  )
}

export default App

