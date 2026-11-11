// 좌표·면적·도형 계산 도우미
import * as turf from '@turf/turf'

export const SEOUL_BOUNDS = [[37.413, 126.734], [37.715, 127.27]]
export const MAX_AREA_KM2 = 2

export function regionPolygon({ sw, ne }) {
  return {
    type: 'Polygon',
    coordinates: [[[sw.lng, sw.lat], [ne.lng, sw.lat], [ne.lng, ne.lat], [sw.lng, ne.lat], [sw.lng, sw.lat]]],
  }
}

export const areaM2 = (geometry) => turf.area(geometry)
export const regionAreaKm2 = (region) => areaM2(regionPolygon(region)) / 1e6

// 위경도 → 웹 지도 좌표(EPSG:3857, 미터)
const R = 6378137
export function toMerc(lng, lat) {
  const x = (lng * Math.PI / 180) * R
  const y = Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2)) * R
  return [x, y]
}

// AI 에 보낼 Esri 위성사진 요청 주소와 좌표 파일(.pgw) 만들기 (EPSG:3857)
export function esriExport({ sw, ne }, maxPx = 2048, bestRes = 0.5) {
  const [x0, y0] = toMerc(sw.lng, sw.lat)
  const [x1, y1] = toMerc(ne.lng, ne.lat)
  const w = x1 - x0, h = y1 - y0
  const res = Math.max(bestRes, Math.max(w, h) / maxPx)       // 픽셀 하나 = res 미터
  const W = Math.max(1, Math.round(w / res)), H = Math.max(1, Math.round(h / res))
  const px = w / W, py = h / H
  const url = '/esri/ArcGIS/rest/services/World_Imagery/MapServer/export'
    + `?bbox=${x0},${y0},${x1},${y1}&bboxSR=3857&imageSR=3857&size=${W},${H}`
    + '&format=png&transparent=false&f=image'
  // PGW: A, D, B, E, C, F  (C, F = 왼쪽 위 픽셀의 중심)
  const pgw = [px, 0, 0, -py, x0 + px / 2, y1 - py / 2].join('\n')
  return { url, pgw, width: W, height: H }
}

// AI FeatureCollection → 후보지 추천 API 의 [{class, geometry}] 목록
export const landcoverList = (fc) =>
  (fc?.features ?? [])
    .filter((f) => f?.properties?.class && f.geometry)
    .map((f) => ({ class: f.properties.class, geometry: f.geometry }))

// 녹화 영역 합집합 − 보존 영역 합집합 (녹화가 없으면 후보지 전체에서 보존만 뺌)
export function editableGeometry(candidateGeom, green, protect) {
  const asFeature = (g) => turf.feature(g)
  const unionAll = (geoms) => {
    if (!geoms.length) return null
    if (geoms.length === 1) return asFeature(geoms[0])
    return turf.union(turf.featureCollection(geoms.map(asFeature)))
  }
  let base = unionAll(green) ?? asFeature(candidateGeom)
  const cut = unionAll(protect)
  if (cut) base = turf.difference(turf.featureCollection([base, cut]))
  return base?.geometry ?? null
}

// 녹지 부족지수(0~1) → 색 (낮음: 연녹 → 높음: 주황)
export function deficitColor(d) {
  const stops = [[0, [255, 244, 176]], [0.5, [240, 138, 60]], [1, [140, 30, 40]]]
  const v = Math.min(1, Math.max(0, d ?? 0))
  for (let i = 1; i < stops.length; i++) {
    const [a, ca] = stops[i - 1], [b, cb] = stops[i]
    if (v <= b) {
      const t = (v - a) / (b - a)
      const c = ca.map((x, k) => Math.round(x + (cb[k] - x) * t))
      return `rgb(${c.join(',')})`
    }
  }
  return 'rgb(140,30,40)'
}

export const deficitLabel = (d) => (d == null ? '—' : d >= 0.65 ? '높음' : d >= 0.4 ? '보통' : '낮음')

export const LANDCOVER = {
  green: { label: '녹지', color: '#3E9B5F' },
  road: { label: '도로', color: '#C9B48A' },
  residential: { label: '주거지역', color: '#8E8E8E' },
}

// 다각형 안에 무작위 점 (03 결과 비교의 나무·관목 표시용)
export function randomPointsIn(geometry, n) {
  if (!geometry || n <= 0) return []
  const bbox = turf.bbox(geometry)
  const out = []
  let guard = 0
  while (out.length < n && guard++ < n * 30) {
    const p = turf.randomPosition(bbox)
    if (turf.booleanPointInPolygon(p, geometry)) out.push(p)
  }
  return out
}

export const SITE_TYPE = {
  parking_lot: '주차장', schoolyard: '학교 운동장', public_plaza: '공공 광장', public_rooftop: '공공 옥상',
  vacant_lot: '공터', public_facility: '공공기관 부지',
}

// 종류가 골고루 나오게: 점수 순서는 그대로, 한 종류는 최대 perType 곳까지.
// 다른 종류가 모자라 칸이 남으면 남은 후보로 점수 순서대로 채운다.
export function pickDiverse(items, total = 10, perType = 4) {
  const sorted = [...items].sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0))
  const count = {}
  const picked = []
  const rest = []
  for (const it of sorted) {
    if (picked.length < total && (count[it.site_type] ?? 0) < perType) {
      picked.push(it); count[it.site_type] = (count[it.site_type] ?? 0) + 1
    } else rest.push(it)
  }
  for (const it of rest) if (picked.length < total) picked.push(it)
  return picked
    .sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0))
    .map((it, i) => ({ ...it, rank: i + 1 }))
}

// 후보지 추천 API 응답(점수 구성·면적·부족지수)으로 "왜 추천됐는지" 를 쉬운 문장으로
const SCORE_PARTS = { deficit: '녹지 부족', area: '면적', impervious: '불투수율', feasibility: '실현 가능성' }
export function explainCandidate(it, weights) {
  const out = []
  const d = it.green_deficit_score
  if (d != null) out.push(`녹지 부족지수 ${fmt(d, 2)}(${deficitLabel(d)}): 주변에 녹지가 ${d >= 0.65 ? '많이 ' : ''}부족한 곳이에요.`)
  if (it.area_m2 != null) {
    out.push(it.area_m2 >= 500
      ? `녹화할 수 있는 면적이 ${fmt(it.area_m2)}㎡로 넓어요.`
      : `녹화할 수 있는 면적은 ${fmt(it.area_m2)}㎡로 작은 편이에요.`)
    out.push('녹화 가능 면적은 부지 중 녹지에서 멀고 더운 "녹지 확충 필요 구역"과 겹치는 부분이에요.')
  }
  if (it.impervious_ratio != null) out.push(`위성으로 본 불투수(포장) 비율이 약 ${fmt(it.impervious_ratio * 100, 0)}%예요${it.impervious_ratio >= 0.5 ? '. 포장이 많아 녹화 효과가 커요' : ''}. (추정치)`)
  const parts = it.score_components ?? {}
  const used = Object.entries(parts).filter(([, v]) => v != null)
  const missing = Object.entries(parts).filter(([, v]) => v == null).map(([k]) => SCORE_PARTS[k] ?? k)
  if (used.length && weights) {
    out.push(`종합 ${fmt((it.total_score ?? 0) * 100, 0)}점은 ${used.map(([k]) => `${SCORE_PARTS[k] ?? k} ${fmt(weights[k] * 100, 0)}%`).join(' · ')} 비중으로 계산했어요`
      + (missing.length ? ` (${missing.join('·')} 자료는 없어서 제외).` : '.'))
  }
  out.push('실제 이용 현황과 녹화 가능 여부는 현장 확인이 필요해요.')
  return out
}

export const fmt =(n, d = 0) => (n == null || Number.isNaN(n) ? '—' : Number(n).toLocaleString('ko-KR', { maximumFractionDigits: d, minimumFractionDigits: d }))
