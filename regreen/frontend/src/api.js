// 백엔드 호출 (주소는 vite.config.js 의 프록시를 거친다)
import { SITE_TYPE, esriExport, regionPolygon, landcoverList } from './geo.js'

async function json(url, options = {}, timeoutMs = 60000) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(url, { ...options, signal: ctrl.signal })
    const body = await res.json().catch(() => null)
    if (!res.ok) {
      const d = body?.detail
      throw new Error(typeof d === 'string' ? d : d ? JSON.stringify(d) : `HTTP ${res.status}`)
    }
    return body
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('응답 시간이 초과됐어요')
    if (e instanceof TypeError) throw new Error('서버에 연결할 수 없어요')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

const post = (url, body, timeoutMs) =>
  json(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, timeoutMs)

// ① 녹지 부족지수 (내 API)
// 서울 전체 부족지수 (500m 칸, 사각형 고르기 전에 지도에 깔아 둠)
export const seoulGrid = () => json('/svc/deficit/api/seoul/grid')

export const analyzeRegion = (region, landcover) =>
  post('/svc/deficit/api/region/analyze', { sw: region.sw, ne: region.ne, ...(landcover ? { landcover } : {}) })

// ② AI 토지 피복 (연재님 API): Esri 위성사진 + 좌표 파일 + 영역을 보냄
export async function requestLandcover(region) {
  const { url, pgw } = esriExport(region)
  const img = await fetch(url)
  if (!img.ok) throw new Error(`위성사진을 받지 못했어요 (HTTP ${img.status})`)
  const form = new FormData()
  form.append('image', await img.blob(), 'aerial.png')
  form.append('world_file', new Blob([pgw], { type: 'text/plain' }), 'aerial.pgw')
  form.append('region', JSON.stringify(regionPolygon(region)))
  return json('/svc/ai/ai/landcover', { method: 'POST', body: form }, 180000)
}

// ③ 후보지 추천 (후보지 서버)
export const recommend = (analysis, landcoverFc) =>
  post('/svc/candidate/recommendations/from-region-analysis', {
    region_analysis: analysis,
    grids: (analysis.grids ?? []).slice(0, 5000),
    landcover: landcoverList(landcoverFc),
    allowed_site_types: Object.keys(SITE_TYPE),   // 후보지 서버 기본값은 4종류라 공터·공공기관 부지도 허용
    limit: 50,   // 넉넉히 받아서 화면에서 종류가 골고루 섞이게 10곳을 고름 (pickDiverse)
  })

export const selectCandidate = (candidateId, recommendationId) =>
  post('/svc/candidate/recommendations/select', { candidate_id: candidateId, recommendation_id: recommendationId })

// ④ 녹지 설계 (설계 서버)
export const designSpatial = (candidate, editableGeometry, greenRatio, veg) =>
  post('/svc/design/api/design/spatial', {
    candidate, editable_geometry: editableGeometry, green_ratio: greenRatio, vegetation: veg,
  })
