// 앱 전체 상태 (새로고침하면 처음부터: 저장하지 않음)
import { createContext, useContext, useMemo, useState } from 'react'

const Ctx = createContext(null)

export const DEFAULT_DESIGN = {
  green: [],            // 녹화 영역 다각형들 (GeoJSON Polygon geometry)
  protect: [],          // 보존 영역 다각형들
  greenRatio: 60,       // 그린 영역 중 실제로 녹화할 비율 (%)
  veg: { grass: 50, shrub: 30, tree: 20 },
  conditions: [],       // 공존 조건 (리포트 표시용)
  memo: '',
}

export function AppStateProvider({ children }) {
  // 01 공간 탐색
  const [region, setRegion] = useState(null)          // { sw:{lat,lng}, ne:{lat,lng} }
  const [analysis, setAnalysis] = useState(null)      // 녹지 부족지수 API 응답
  const [landcover, setLandcover] = useState(null)    // AI 토지 피복 FeatureCollection
  const [ai, setAi] = useState({ status: 'idle', message: '' })
  const [recs, setRecs] = useState(null)              // { status: loading/ok/empty/error, items, recommendationId, message }
  const [selectedId, setSelectedId] = useState(null)
  const [candidate, setCandidate] = useState(null)    // 후보지 선택 결과 (설계 API 입력 형식)
  // 02 공존 설계
  const [design, setDesign] = useState(DEFAULT_DESIGN)
  const [designResult, setDesignResult] = useState(null)
  // 03 을 본 적 있는지 (04 잠금 해제용)
  const [visitedCompare, setVisitedCompare] = useState(false)

  const value = useMemo(() => ({
    region, setRegion, analysis, setAnalysis, landcover, setLandcover, ai, setAi,
    recs, setRecs, selectedId, setSelectedId, candidate, setCandidate,
    design, setDesign, designResult, setDesignResult, visitedCompare, setVisitedCompare,
    // 영역을 새로 고르면 뒤 단계는 모두 초기화
    resetFromRegion() {
      setAnalysis(null); setLandcover(null); setAi({ status: 'idle', message: '' })
      setRecs(null); setSelectedId(null); setCandidate(null)
      setDesign(DEFAULT_DESIGN); setDesignResult(null); setVisitedCompare(false)
    },
    resetFromCandidate() {
      setDesign(DEFAULT_DESIGN); setDesignResult(null); setVisitedCompare(false)
    },
    unlocked: {
      explore: true,
      design: !!candidate,
      compare: !!candidate && !!designResult,
      report: !!candidate && !!designResult && visitedCompare,
    },
  }), [region, analysis, landcover, ai, recs, selectedId, candidate, design, designResult, visitedCompare])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useApp = () => useContext(Ctx)
