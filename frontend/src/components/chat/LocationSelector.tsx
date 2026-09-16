import { useEffect, useRef, useState } from 'react'
import { gangnamLocations } from '../../data/gangnamLocations'
import type { GangnamLocation } from '../../types/chat'

type LocationSelectorProps = {
  selectedLocation: GangnamLocation | null
  onSelect: (location: GangnamLocation) => void
}

export function LocationSelector({
  selectedLocation,
  onSelect,
}: LocationSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selectorRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!selectorRef.current?.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [isOpen])

  return (
    <div className="location-selector" ref={selectorRef}>
      <div className="location-scope">
        <span className="scope-badge">강남구 전용</span>
        <span>강남구 음식점만 추천해요</span>
      </div>
      <button
        className={`location-trigger${selectedLocation ? ' is-selected' : ''}`}
        type="button"
        aria-expanded={isOpen}
        aria-controls="gangnam-location-options"
        onClick={() => setIsOpen((current) => !current)}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" />
          <circle cx="12" cy="10" r="2.5" />
        </svg>
        <span>
          <small>기준 위치</small>
          <strong>{selectedLocation?.label ?? '위치를 선택해 주세요'}</strong>
        </span>
        <span className="location-chevron" aria-hidden="true">
          {isOpen ? '−' : '+'}
        </span>
      </button>

      {isOpen && (
        <div
          className="location-options"
          id="gangnam-location-options"
          aria-label="강남구 기준 위치"
        >
          <div className="location-options__heading">
            <strong>어디에서 점심을 찾을까요?</strong>
            <span>현재는 강남구 주요 지역을 기준으로 선택할 수 있어요.</span>
          </div>
          <div className="location-grid">
            {gangnamLocations.map((location) => (
              <button
                className={
                  selectedLocation?.id === location.id ? 'is-active' : ''
                }
                type="button"
                key={location.id}
                aria-pressed={selectedLocation?.id === location.id}
                onClick={() => {
                  onSelect(location)
                  setIsOpen(false)
                }}
              >
                <strong>{location.label}</strong>
                <span>{location.description}</span>
              </button>
            ))}
          </div>
          <p className="location-disclaimer">
            실제 좌표와 강남구 경계 검증은 위치 API 연결 후 적용됩니다.
          </p>
        </div>
      )}
    </div>
  )
}
