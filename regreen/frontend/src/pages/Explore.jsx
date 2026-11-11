// 01 공간 탐색: 서울 지도에서 사각형 선택 → 녹지 부족 분석 → AI 토지 피복 → 후보지 추천
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GeoJSON, Rectangle, useMap, useMapEvents } from 'react-leaflet'
import BaseMap from '../components/BaseMap.jsx'
import { useApp } from '../state.jsx'
import { analyzeRegion, recommend, requestLandcover, seoulGrid, selectCandidate } from '../api.js'
import {
  LANDCOVER, MAX_AREA_KM2, SEOUL_BOUNDS, SITE_TYPE, deficitColor, deficitLabel, explainCandidate, fmt, pickDiverse, regionAreaKm2,
} from '../geo.js'

const toRegion = (a, b) => ({
  sw: { lat: Math.min(a.lat, b.lat), lng: Math.min(a.lng, b.lng) },
  ne: { lat: Math.max(a.lat, b.lat), lng: Math.max(a.lng, b.lng) },
})
const rectBounds = (r) => [[r.sw.lat, r.sw.lng], [r.ne.lat, r.ne.lng]]

// 후보지 추천 API 의 이유 중 사용자에게 의미 있는 것만 (내부 계산 설명은 뺌)
const friendlyReasons = (reasons = []) =>
  reasons
    .filter((r) => !/가중치|실현 가능성 점수/.test(r))
    .map((r) => r.replace(/\s*\(출처:[^)]*\)/, '').replace('후보지 교차 면적', '녹화 가능 면적').replace('입력 데이터의 ', ''))
    .slice(0, 2)
    .join(' · ')

// 영역 선택 모드에서 드래그로 사각형 그리기
function RectSelect({ enabled, onDraft, onCommit }) {
  const start = useRef(null)
  const map = useMap()
  useEffect(() => {
    if (enabled) { map.dragging.disable(); map.getContainer().style.cursor = 'crosshair' }
    else { map.dragging.enable(); map.getContainer().style.cursor = '' }
  }, [enabled, map])
  useMapEvents({
    mousedown(e) { if (enabled) { start.current = e.latlng; onDraft(null) } },
    mousemove(e) { if (enabled && start.current) onDraft(toRegion(start.current, e.latlng)) },
    mouseup(e) {
      if (!enabled || !start.current) return
      const r = toRegion(start.current, e.latlng)
      start.current = null
      onDraft(null)
      const a = map.latLngToContainerPoint([r.sw.lat, r.sw.lng]), b = map.latLngToContainerPoint([r.ne.lat, r.ne.lng])
      if (Math.abs(a.x - b.x) > 8 && Math.abs(a.y - b.y) > 8) onCommit(r)
    },
  })
  return null
}

function MapTools() {
  const map = useMap()
  if (import.meta.env.DEV) window.__exploreMap = map   // 개발 중 테스트용 (배포 빌드엔 없음)
  return (
    <div className="map-tools" role="group" aria-label="지도 도구">
      <button type="button" title="확대" onClick={() => map.zoomIn()}>＋</button>
      <button type="button" title="축소" onClick={() => map.zoomOut()}>－</button>
      <button type="button" className="wide" onClick={() => map.fitBounds(SEOUL_BOUNDS)}>서울 전체</button>
    </div>
  )
}

// AI 서버 오류 메시지는 길어서 사용자에게는 짧게
const aiReason = (msg = '') => {
  if (/overpass|Gateway|capacity/i.test(msg)) return '도로 데이터 서버가 바빠요. 잠시 후 다시 분석해 보세요'
  if (/Topology|invalid/i.test(msg)) return 'AI 결과 도형을 합치지 못했어요'
  return msg.length > 60 ? `${msg.slice(0, 60)}…` : msg
}

// 서울 전체 칸을 누르면 보이는 지표
const seoulPopup = (p) => `
  <div class="cell-pop">
    <b>녹지 부족지수 ${fmt(p.deficit_index, 2)}</b> <span>${deficitLabel(p.deficit_index)}</span>
    <dl>
      <dt>녹지 정도 (NDVI)</dt><dd>${fmt(p.avg_ndvi, 2)}</dd>
      <dt>지표면 온도</dt><dd>${fmt(p.avg_lst, 1)}°C</dd>
      <dt>인구</dt><dd>${fmt(p.population, 0)}명</dd>
      <dt>공원까지 평균</dt><dd>${fmt(p.avg_dist_to_park_m, 0)}m</dd>
    </dl>
    <small>500m 칸 평균 · 이 근처를 사각형으로 골라 자세히 분석해 보세요</small>
  </div>`

function FitTo({ bounds }) {
  const map = useMap()
  useEffect(() => { if (bounds) map.fitBounds(bounds, { padding: [40, 40] }) }, [bounds, map])
  return null
}

export default function Explore() {
  const app = useApp()
  const { region, analysis, landcover, ai, recs, selectedId } = app
  const navigate = useNavigate()
  const [mode, setMode] = useState('pan')
  const [draft, setDraft] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [show, setShow] = useState({ green: false, road: false, residential: false, grid: false, need: false, seoul: true })
  const [fitBounds, setFitBounds] = useState(null)
  const [seoul, setSeoul] = useState(null)       // 서울 전체 부족지수 (500m 칸)
  const run = useRef(0)

  useEffect(() => {
    let alive = true
    seoulGrid().then((fc) => alive && setSeoul(fc)).catch(() => {})   // 없으면 지도만 보여줌
    return () => { alive = false }
  }, [])

  const area = region ? regionAreaKm2(region) : 0
  const tooBig = area > MAX_AREA_KM2

  function commitRegion(r) {
    app.setRegion(r); app.resetFromRegion(); setError(''); setMode('pan')
  }

  // 후보지 추천 API 결과만 보여준다. 없으면 없다고, 실패하면 실패했다고 표시
  async function loadRecs(token, a, fc) {
    app.setRecs({ status: 'loading', items: [] })
    try {
      const r = await recommend(a, fc)
      if (token !== run.current) return
      app.setRecs({ status: r.count > 0 ? 'ok' : 'empty', items: pickDiverse(r.recommendations ?? []), recommendationId: r.recommendation_id, weights: r.scoring_weights })
    } catch (e) {
      if (token !== run.current) return
      app.setRecs({ status: 'error', items: [], message: e.message })
    }
  }

  async function analyze() {
    if (!region || tooBig) return
    const token = ++run.current
    setBusy(true); setError(''); app.resetFromRegion()
    try {
      // ① 공공 데이터로 먼저 (1초 안팎)
      const a = await analyzeRegion(region)
      if (token !== run.current) return
      app.setAnalysis(a)
      setShow((s) => ({ ...s, seoul: false, grid: true }))   // 분석하면 서울 전체는 끄고 100m 격자만 켜기
      setFitBounds(rectBounds(region))
      loadRecs(token, a, null)
    } catch (e) {
      if (token === run.current) setError(`녹지 부족 분석에 실패했어요: ${e.message}`)
      setBusy(false)
      return
    }
    setBusy(false)
    // ② AI 토지 피복은 뒤에서 (수십 초) → 오면 다시 계산
    app.setAi({ status: 'loading', message: '항공사진을 분석하는 중이에요 (수십 초 걸릴 수 있어요)' })
    try {
      const fc = await requestLandcover(region)
      if (token !== run.current) return
      app.setLandcover(fc)
      const a2 = await analyzeRegion(region, fc)
      if (token !== run.current) return
      app.setAnalysis(a2)
      app.setAi({ status: 'done', message: '항공사진 분석을 반영했어요' })
      loadRecs(token, a2, fc)
    } catch (e) {
      if (token !== run.current) return
      app.setAi({ status: 'error', message: `AI 분석을 쓰지 못해 공공 데이터 기준으로 보여드려요 (${aiReason(e.message)})` })
    }
  }

  function clearAll() {
    run.current++
    app.setRegion(null); app.resetFromRegion(); setError(''); setBusy(false)
    setShow((s) => ({ ...s, seoul: true }))   // 선택을 지우면 다시 서울 전체 보기
  }

  async function goDesign() {
    const item = recs?.items.find((x) => x.candidate_id === selectedId)
    if (!item) return
    setError('')
    try {
      const cand = await selectCandidate(item.candidate_id, recs.recommendationId)
      cand.feature.properties = {
        ...cand.feature.properties, name: item.name, site_type: item.site_type,
        rank: item.rank, total_score: item.total_score, reasons: explainCandidate(item, recs.weights),
      }
      app.setCandidate(cand); app.resetFromCandidate()
      navigate('/design')
    } catch (e) {
      setError(`후보지를 불러오지 못했어요: ${e.message}`)
    }
  }

  const gridStyle = (f) => ({ color: '#ffffff', weight: 0.6, fillColor: deficitColor(f.properties.deficit_index), fillOpacity: 0.55 })
  const lcStyle = (f) => ({ color: LANDCOVER[f.properties.class]?.color, weight: 1, fillColor: LANDCOVER[f.properties.class]?.color, fillOpacity: 0.45 })
  const gridFc = analysis?.grids ? {
    type: 'FeatureCollection',
    features: analysis.grids.map((g) => ({ type: 'Feature', geometry: g.geometry, properties: { deficit_index: g.deficit_index } })),
  } : null
  const lcFc = landcover ? { ...landcover, features: landcover.features.filter((f) => show[f.properties?.class]) } : null
  const lcRatio = analysis?.landcover
  const hasLc = lcRatio && Object.values(lcRatio).some((v) => v.area_m2 > 0)

  return (
    <main className="page">
      <div className="page-heading">
        <span className="page-no">01</span>
        <div>
          <h1>어디에 녹지를 더할까요?</h1>
          <p>서울 지도에서 범위를 사각형으로 골라 녹지가 얼마나 부족한지 살펴보세요.</p>
        </div>
      </div>

      <div className="layout">
        <section className="panel map-panel">
          <BaseMap bounds={SEOUL_BOUNDS} minZoom={10} maxBounds={[[37.2, 126.5], [37.95, 127.5]]}>
            <MapTools />
            <RectSelect enabled={mode === 'select'} onDraft={setDraft} onCommit={commitRegion} />
            <FitTo bounds={fitBounds} />
            {/* 분석 전에는 서울 전체 500m 칸, 분석하면 선택 영역의 100m 격자로 바뀜 */}
            {show.seoul && seoul && !analysis && (
              <GeoJSON key={`s-${mode}`} data={seoul} interactive={mode === 'pan'}
                style={(f) => ({ color: '#ffffff', weight: 0.4, opacity: 0.6, fillColor: deficitColor(f.properties.deficit_index), fillOpacity: 0.62 })}
                onEachFeature={(f, layer) => layer.bindPopup(seoulPopup(f.properties), { maxWidth: 260 })} />
            )}
            {show.grid && gridFc && <GeoJSON key={`g-${analysis.grids.length}-${analysis.deficit_index}`} data={gridFc} style={gridStyle} interactive={false} />}
            {lcFc && <GeoJSON key={`lc-${JSON.stringify(show)}-${lcFc.features.length}`} data={lcFc} style={lcStyle} interactive={false} />}
            {show.need && analysis?.candidates && (
              <GeoJSON key={`n-${analysis.candidate_area_m2}`} data={analysis.candidates} interactive={false}
                style={{ color: '#2B6CB0', weight: 2, dashArray: '6 4', fillColor: '#2B6CB0', fillOpacity: 0.15 }} />
            )}
            {recs?.items.map((it) => (
              <GeoJSON key={`r-${it.candidate_id}-${selectedId === it.candidate_id}`} data={it.geometry} interactive={false}
                style={selectedId === it.candidate_id
                  ? { color: '#15302A', weight: 3, fillColor: '#2E7D57', fillOpacity: 0.55 }
                  : { color: '#F5F3EC', weight: 2, fillColor: '#2E7D57', fillOpacity: 0.25 }} />
            ))}
            {region && <Rectangle bounds={rectBounds(region)} pathOptions={{ color: tooBig ? '#FF8A4C' : '#FFFFFF', weight: 3, dashArray: '10 6', fill: false }} interactive={false} />}
            {draft && <Rectangle bounds={rectBounds(draft)} pathOptions={{ color: '#F5F3EC', weight: 2, fillOpacity: 0.1 }} interactive={false} />}
          </BaseMap>
          {mode === 'select' && <div className="map-hint">지도 위를 대각선으로 드래그해 범위를 고르세요</div>}
          {mode === 'pan' && !analysis && seoul && show.seoul && <div className="map-hint">색이 진할수록 녹지가 부족해요 · 칸을 누르면 지표를 볼 수 있어요</div>}
          <div className="map-legend">
            <div className="legend-row">
              {Object.entries(LANDCOVER).map(([k, v]) => <span key={k}><i style={{ background: v.color }} />{v.label}</span>)}
            </div>
            <div className="legend-row">녹지 부족 낮음 <b className="ramp" /> 높음</div>
          </div>
        </section>

        <aside className="panel side">
          <h2>탐색 조건</h2>
          <div className="seg" role="group" aria-label="지도 모드">
            <button type="button" className={mode === 'pan' ? 'on' : ''} aria-pressed={mode === 'pan'} onClick={() => setMode('pan')}>↖ 지도 이동</button>
            <button type="button" className={mode === 'select' ? 'on' : ''} aria-pressed={mode === 'select'} onClick={() => setMode('select')}>⛶ 영역 선택</button>
          </div>

          <div className="row-between">
            <div><b>선택 면적</b><p className="muted small">최대 {MAX_AREA_KM2}㎢</p></div>
            <div className={`area-box${tooBig ? ' warn' : ''}`}>{region ? fmt(area, 2) : '—'} <small>㎢</small></div>
          </div>
          {tooBig && <p className="warn-text">범위가 {MAX_AREA_KM2}㎢를 넘어요. 범위를 줄여 다시 골라 주세요.</p>}

          <div className="seg">
            <button type="button" className="primary" disabled={!region || tooBig || busy} onClick={analyze}>{busy ? '분석 중…' : '선택 영역 분석'}</button>
            <button type="button" disabled={!region} onClick={clearAll}>선택 해제</button>
          </div>
          {!region && <p className="muted small">'영역 선택'을 누른 뒤 지도에서 범위를 드래그하세요.</p>}
          {error && <p className="warn-text">{error}</p>}

          <hr />
          <div className="row-between"><h3>지도 표시</h3></div>
          <div className="chips">
            {Object.entries(LANDCOVER).map(([k, v]) => (
              <label key={k} className={`chip${show[k] ? ' on' : ''}`}>
                <input type="checkbox" checked={show[k]} onChange={(e) => setShow({ ...show, [k]: e.target.checked })} /> {v.label}
              </label>
            ))}
          </div>
          <label className="check"><input type="checkbox" checked={show.seoul} onChange={(e) => setShow({ ...show, seoul: e.target.checked })} /> 서울 전체 녹지 부족 <span className="muted small">500m 칸 · 분석 전</span></label>
          <label className="check"><input type="checkbox" checked={show.grid} onChange={(e) => setShow({ ...show, grid: e.target.checked })} /> 녹지 부족 분포 <span className="muted small">100m 격자</span></label>
          <label className="check"><input type="checkbox" checked={show.need} onChange={(e) => setShow({ ...show, need: e.target.checked })} /> 녹지 확충 필요 구역</label>

          {analysis && (
            <>
              <hr />
              <h3>분석 결과</h3>
              <div className="score">
                <div>
                  <span className="muted small">녹지 부족지수</span>
                  <strong>{fmt(analysis.deficit_index, 2)}</strong>
                </div>
                <span className={`badge level-${deficitLabel(analysis.deficit_index)}`}>{deficitLabel(analysis.deficit_index)}</span>
              </div>
              <div className="bar"><i style={{ width: `${(analysis.deficit_index ?? 0) * 100}%` }} /></div>
              <p className={`ai-status ${ai.status}`}>{ai.status === 'loading' && <span className="spinner" />}{ai.message}</p>
              {hasLc ? (
                <div className="lc-bars">
                  {Object.entries(LANDCOVER).map(([k, v]) => (
                    <div key={k} className="lc-row">
                      <span>{v.label}</span>
                      <div className="bar thin"><i style={{ width: `${(lcRatio[k]?.ratio ?? 0) * 100}%`, background: v.color }} /></div>
                      <b>{fmt((lcRatio[k]?.ratio ?? 0) * 100, 0)}%</b>
                    </div>
                  ))}
                </div>
              ) : <p className="muted small">토지 피복 비율은 항공사진 분석이 끝나면 표시돼요.</p>}
            </>
          )}

          {recs && (
            <>
              <hr />
              <div className="row-between">
                <h3>추천 후보지 {recs.status === 'ok' && <span className="pill">{recs.items.length}곳</span>}</h3>
                {recs.status === 'loading' && <span className="spinner" />}
              </div>
              {recs.status === 'empty' && <div className="empty">이 영역에는 추천할 후보지가 없어요.<br /><span className="muted small">범위를 옮기거나 넓혀서 다시 분석해 보세요.</span></div>}
              {recs.status === 'error' && <div className="empty error">후보지를 불러오지 못했어요.<br /><span className="small">{recs.message}</span></div>}
              <ol className="cards">
                {recs.items.map((it) => (
                  <li key={it.candidate_id}>
                    <button type="button" className={`card${selectedId === it.candidate_id ? ' on' : ''}`} aria-pressed={selectedId === it.candidate_id} onClick={() => app.setSelectedId(it.candidate_id)}>
                      <span className="rank">{String(it.rank).padStart(2, '0')}</span>
                      <span className="card-body">
                        <b>{it.name}</b>
                        <small>{SITE_TYPE[it.site_type] ?? it.site_type}{it.is_demo ? ' · 예시' : ''}</small>
                        <small className="reason">{friendlyReasons(it.reasons)}</small>
                      </span>
                      <span className="total"><small>종합</small>{fmt((it.total_score ?? 0) * 100, 0)}</span>
                    </button>
                    {selectedId === it.candidate_id && (
                      <div className="why">
                        <b>추천 이유</b>
                        <ul>{explainCandidate(it, recs.weights).map((t) => <li key={t}>{t}</li>)}</ul>
                      </div>
                    )}
                  </li>
                ))}
              </ol>
              {recs.status === 'ok' && <button type="button" className="primary big" disabled={!selectedId} onClick={goDesign}>선택한 공간 설계하기 →</button>}
            </>
          )}
        </aside>
      </div>
    </main>
  )
}
