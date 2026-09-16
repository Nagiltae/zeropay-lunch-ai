import { useEffect, useState } from 'react'
import { usePreferences } from '../../hooks/usePreferences'
import type {
  RestaurantCategory,
  SpiceLevel,
} from '../../types/preference'
import './PreferencePanel.css'

const categories: Array<{ value: RestaurantCategory; label: string }> = [
  { value: 'KOREAN', label: '한식' },
  { value: 'KOREAN_SOUP', label: '국물·한식' },
  { value: 'SALAD', label: '샐러드' },
]

type PreferencePanelProps = {
  onClose: () => void
}

export function PreferencePanel({ onClose }: PreferencePanelProps) {
  const { preference, isLoading, loadError, save, isSaving, saveError } =
    usePreferences()
  const [budget, setBudget] = useState('')
  const [spiceLevel, setSpiceLevel] = useState<SpiceLevel>('ANY')
  const [preferred, setPreferred] = useState<RestaurantCategory[]>([])
  const [disliked, setDisliked] = useState<RestaurantCategory[]>([])
  const [allergies, setAllergies] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!preference) return
    setBudget(preference.defaultBudget?.toString() ?? '')
    setSpiceLevel(preference.spiceLevel)
    setPreferred(preference.preferredCategories)
    setDisliked(preference.dislikedCategories)
    setAllergies(preference.allergies.join(', '))
  }, [preference])

  const toggleCategory = (
    category: RestaurantCategory,
    target: 'preferred' | 'disliked',
  ) => {
    setSaved(false)
    if (target === 'preferred') {
      setPreferred((current) =>
        current.includes(category)
          ? current.filter((value) => value !== category)
          : [...current, category],
      )
      setDisliked((current) => current.filter((value) => value !== category))
      return
    }
    setDisliked((current) =>
      current.includes(category)
        ? current.filter((value) => value !== category)
        : [...current, category],
    )
    setPreferred((current) => current.filter((value) => value !== category))
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    await save({
      defaultBudget: budget ? Number(budget) : null,
      spiceLevel,
      preferredCategories: preferred,
      dislikedCategories: disliked,
      allergies: allergies
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean),
    })
    setSaved(true)
  }

  return (
    <div className="preference-backdrop" role="presentation">
      <section className="preference-panel" aria-labelledby="preference-title">
        <div className="preference-panel__header">
          <div>
            <p>PERSONALIZATION</p>
            <h2 id="preference-title">내 점심 취향</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="취향 설정 닫기">×</button>
        </div>

        {isLoading && <p>취향 설정을 불러오고 있어요.</p>}
        {loadError && <p className="preference-error">{loadError.message}</p>}
        {preference && (
          <form onSubmit={(event) => void submit(event)}>
            <label>
              기본 점심 예산
              <input
                type="number"
                min="1000"
                max="100000"
                step="1000"
                value={budget}
                onChange={(event) => { setBudget(event.target.value); setSaved(false) }}
                placeholder="예: 12000"
              />
            </label>

            <label>
              매운맛 선호
              <select
                value={spiceLevel}
                onChange={(event) => { setSpiceLevel(event.target.value as SpiceLevel); setSaved(false) }}
              >
                <option value="ANY">상관없음</option>
                <option value="MILD">순한맛</option>
                <option value="MEDIUM">보통</option>
                <option value="HOT">매운맛</option>
              </select>
            </label>

            <fieldset>
              <legend>선호 음식 종류</legend>
              <div className="preference-options">
                {categories.map((category) => (
                  <label key={`preferred-${category.value}`}>
                    <input
                      type="checkbox"
                      checked={preferred.includes(category.value)}
                      onChange={() => toggleCategory(category.value, 'preferred')}
                    />
                    {category.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <fieldset>
              <legend>피하고 싶은 음식 종류</legend>
              <div className="preference-options">
                {categories.map((category) => (
                  <label key={`disliked-${category.value}`}>
                    <input
                      type="checkbox"
                      checked={disliked.includes(category.value)}
                      onChange={() => toggleCategory(category.value, 'disliked')}
                    />
                    {category.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <label>
              알레르기
              <input
                type="text"
                maxLength={300}
                value={allergies}
                onChange={(event) => { setAllergies(event.target.value); setSaved(false) }}
                placeholder="쉼표로 구분해 주세요"
              />
              <small>실제 음식 재료 데이터가 연결되기 전까지 참고 정보로만 저장됩니다.</small>
            </label>

            <p className="zeropay-policy">모든 추천은 제로페이 사용 가능 음식점만 제공합니다.</p>
            {saveError && <p className="preference-error">{saveError.message}</p>}
            {saved && <p className="preference-success">취향을 저장했습니다.</p>}
            <button className="preference-save" type="submit" disabled={isSaving}>
              {isSaving ? '저장 중...' : '저장'}
            </button>
          </form>
        )}
      </section>
    </div>
  )
}
