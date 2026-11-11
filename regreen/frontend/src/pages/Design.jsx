// 02 공존 설계: 후보지 위에 녹화·보존 영역을 다각형으로 그리고, 비율을 정하면 바로 계산
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { GeoJSON, useMap } from 'react-leaflet'
import '@geoman-io/leaflet-geoman-free'
import * as turf from '@turf/turf'
import BaseMap from '../components/BaseMap.jsx'
import { useApp } from '../state.jsx'
import { designSpatial } from '../api.js'
import { areaM2, editableGeometry, fmt } from '../geo.js'

const CONDITIONS = ['보행로 보존', '출입구 확보', '주차 공간 유지', '휴식 공간 확보']
const VEG = [['grass', '잔디'], ['shrub', '관목'], ['tree', '교목']]
const STYLE = {
  green: { color: '#1F6B43', weight: 2, fillColor: '#3E9B5F', fillOpacity: 0.45 },
  protect: { color: '#A06A10', weight: 2, fillColor: '#E4B34D', fillOpacity: 0.5 },
}

// 하나를 바꾸면 나머지 둘이 비율대로 줄거나 늘어 합이 항상 100
function rebalance(veg, key, value) {
  const others = VEG.map(([k]) => k).filter((k) => k !== key)
  const rest = 100 - value
  const sum = veg[others[0]] + veg[others[1]]
  const a = Math.round(rest * (sum ? veg[others[0]] / sum : 0.5))
  return { ...veg, [key]: value, [others[0]]: a, [others[1]]: rest - a }
}

function Draw({ kind, onCreate, onDone }) {
  const map = useMap()
  useEffect(() => {
    map.pm.setGlobalOptions({ snappable: true })
    try { map.pm.setLang('ko') } catch { /* 한국어 번역이 없으면 기본(영어) */ }
    const created = (e) => {
      onCreate(e.layer.toGeoJSON().geometry)
      e.layer.remove()
    }
    map.on('pm:create', created)
    return () => { map.off('pm:create', created) }
  }, [map, onCreate])
  useEffect(() => {
    if (!kind) { map.pm.disableDraw(); return }
    map.pm.enableDraw('Polygon', { pathOptions: STYLE[kind], templineStyle: { color: STYLE[kind].color }, hintlineStyle: { color: STYLE[kind].color, dashArray: '5 5' }, finishOn: 'dblclick' })
    const end = () => onDone()
    map.on('pm:drawend', end)
    return () => { map.off('pm:drawend', end); map.pm.disableDraw() }
  }, [kind, map, onDone])
  return null
}

function FitCandidate({ geometry }) {
  const map = useMap()
  useEffect(() => {
    const [w, s, e, n] = turf.bbox(geometry)
    map.fitBounds([[s, w], [n, e]], { padding: [60, 60], maxZoom: 19 })
  }, [geometry, map])
  return null
}

export default function Design() {
  const { candidate, design, setDesign, designResult, setDesignResult } = useApp()
  const navigate = useNavigate()
  const [drawing, setDrawing] = useState(null)
  const [calc, setCalc] = useState({ loading: false, error: '' })
  const seq = useRef(0)
  const geom = candidate.feature.geometry
  const props = candidate.feature.properties ?? {}

  const drawingRef = useRef(null)
  drawingRef.current = drawing
  const order = useRef([])        // 그린 순서 (되돌리기용)
  const addShape = useRef((g) => {
    const kind = drawingRef.current
    if (!kind) return
    order.current.push(kind)
    setDesign((d) => ({ ...d, [kind]: [...d[kind], g] }))
  })
  const stopDrawing = useRef(() => setDrawing(null))

  // 값이 바뀔 때마다 (0.3초 쉬었다가) 설계 API 계산
  useEffect(() => {
    const id = ++seq.current
    const t = setTimeout(async () => {
      const editable = editableGeometry(geom, design.green, design.protect)
      if (!editable) { setDesignResult(null); setCalc({ loading: false, error: '녹화할 수 있는 영역이 없어요. 보존 영역을 줄여 주세요.' }); return }
      setCalc((c) => ({ ...c, loading: true }))
      try {
        const r = await designSpatial(candidate, editable, design.greenRatio, design.veg)
        if (id === seq.current) { setDesignResult(r); setCalc({ loading: false, error: '' }) }
      } catch (e) {
        if (id === seq.current) { setDesignResult(null); setCalc({ loading: false, error: `설계 계산에 실패했어요: ${e.message}` }) }
      }
    }, 300)
    return () => clearTimeout(t)
  }, [geom, candidate, design.green, design.protect, design.greenRatio, design.veg, setDesignResult])

  const r = designResult
  const env = r?.environmental_effect
  const shapes = [...design.green.map((g, i) => ({ kind: 'green', g, i })), ...design.protect.map((g, i) => ({ kind: 'protect', g, i }))]

  function removeShape(kind, i) {
    const idx = order.current.lastIndexOf(kind)
    if (idx >= 0) order.current.splice(idx, 1)
    setDesign((d) => ({ ...d, [kind]: d[kind].filter((_, j) => j !== i) }))
  }
  function undo() {
    const kind = order.current.pop() ?? (design.green.length ? 'green' : 'protect')
    setDesign((d) => ({ ...d, [kind]: d[kind].slice(0, -1) }))
  }
  function clearShapes() {
    order.current = []
    setDesign((d) => ({ ...d, green: [], protect: [] }))
  }

  return (
    <main className="page">
      <div className="page-heading">
        <span className="page-no">02</span>
        <div>
          <h1>남길 공간은 남기고, 초록은 직접 그려요.</h1>
          <p>{props.name ?? '선택한 후보지'} · {fmt(candidate.area_m2)}㎡{props.is_demo ? ' · 예시 후보지' : ''}</p>
        </div>
      </div>

      <div className="layout">
        <section className="panel map-panel">
          <BaseMap center={[37.55, 126.97]} zoom={17} maxZoom={20}>
            <FitCandidate geometry={geom} />
            <Draw kind={drawing} onCreate={addShape.current} onDone={stopDrawing.current} />
            <GeoJSON data={geom} interactive={false} style={{ color: '#F5F3EC', weight: 3, dashArray: '8 6', fillOpacity: 0.05 }} />
            {r?.editable_geometry && (
              <GeoJSON key={`e-${r.editable_area_m2}`} data={r.editable_geometry} interactive={false} style={{ color: '#2E7D57', weight: 0, fillColor: '#2E7D57', fillOpacity: 0.12 }} />
            )}
            {shapes.map(({ kind, g, i }) => <GeoJSON key={`${kind}-${i}-${JSON.stringify(g).length}`} data={g} interactive={false} style={STYLE[kind]} />)}
          </BaseMap>
          <div className="map-hint">
            {drawing ? '점을 찍어 영역을 그리고, 마지막 점에서 더블클릭하면 끝나요 (Esc 취소)' : '흰 점선이 후보지 경계예요. 아무것도 안 그리면 후보지 전체를 녹화 가능 영역으로 봐요.'}
          </div>
          <div className="map-legend">
            <div className="legend-row"><span><i style={{ background: STYLE.green.fillColor }} />녹화 영역</span><span><i style={{ background: STYLE.protect.fillColor }} />보존 영역 · 겹치면 보존 우선</span></div>
          </div>
        </section>

        <aside className="panel side">
          <h2>영역 그리기</h2>
          <div className="seg">
            <button type="button" className={drawing === 'green' ? 'on' : ''} onClick={() => setDrawing(drawing === 'green' ? null : 'green')}>🟩 녹화 영역</button>
            <button type="button" className={drawing === 'protect' ? 'on' : ''} onClick={() => setDrawing(drawing === 'protect' ? null : 'protect')}>🟨 보존 영역</button>
          </div>
          <div className="seg">
            <button type="button" disabled={!shapes.length} onClick={undo}>되돌리기</button>
            <button type="button" disabled={!shapes.length} onClick={clearShapes}>전체 지우기</button>
          </div>
          {shapes.length > 0 && (
            <ul className="shape-list">
              {shapes.map(({ kind, g, i }) => (
                <li key={`${kind}-${i}`}>
                  <i style={{ background: STYLE[kind].fillColor }} />
                  {kind === 'green' ? '녹화' : '보존'} {i + 1} · {fmt(areaM2(g))}㎡
                  <button type="button" className="link" onClick={() => removeShape(kind, i)} aria-label="삭제">삭제</button>
                </li>
              ))}
            </ul>
          )}

          <hr />
          <h3>녹화 비율 <span className="muted small">후보지 면적 대비</span></h3>
          <div className="slider-row">
            <input type="range" min="0" max="100" step="1" value={design.greenRatio} onChange={(e) => setDesign((d) => ({ ...d, greenRatio: Number(e.target.value) }))} aria-label="녹화 비율" />
            <b>{design.greenRatio}%</b>
          </div>

          <h3>식생 구성 <span className="muted small">합계 100%</span></h3>
          {VEG.map(([k, label]) => (
            <div key={k} className="slider-row">
              <span className="slider-label">{label}</span>
              <input type="range" min="0" max="100" step="1" value={design.veg[k]} onChange={(e) => setDesign((d) => ({ ...d, veg: rebalance(d.veg, k, Number(e.target.value)) }))} aria-label={label} />
              <b>{design.veg[k]}%</b>
            </div>
          ))}

          <h3>공존 조건 <span className="muted small">리포트에 표시</span></h3>
          <div className="checks">
            {CONDITIONS.map((c) => (
              <label key={c} className="check">
                <input type="checkbox" checked={design.conditions.includes(c)} onChange={(e) => setDesign((d) => ({ ...d, conditions: e.target.checked ? [...d.conditions, c] : d.conditions.filter((x) => x !== c) }))} /> {c}
              </label>
            ))}
          </div>
          <label className="field">설계 메모
            <textarea rows="2" value={design.memo} onChange={(e) => setDesign((d) => ({ ...d, memo: e.target.value }))} placeholder="추가로 반영할 내용" />
          </label>

          <hr />
          <div className="row-between"><h3>설계 결과</h3>{calc.loading && <span className="spinner" />}</div>
          {calc.error && <p className="warn-text">{calc.error}</p>}
          {r && (
            <>
              <div className="metrics">
                <div><span>녹지 면적</span><strong>{fmt(r.green_area_m2)}<small>㎡</small></strong></div>
                <div><span>교목 · 관목</span><strong>{fmt(r.plant_count?.tree)}<small>주</small> · {fmt(r.plant_count?.shrub)}<small>주</small></strong></div>
                <div><span>연간 탄소 흡수</span><strong>{fmt(env?.carbon_absorption?.total)}<small>kg</small></strong></div>
                <div><span>예상 조성 비용</span><strong>{fmt((env?.estimated_cost?.total ?? 0) / 10000)}<small>만원</small></strong></div>
              </div>
              <p className="muted small">녹화 가능 영역 {fmt(r.editable_area_m2)}㎡ 중 실제 녹화 {fmt(r.actual_green_ratio, 1)}%</p>
              {r.warnings?.map((w) => <p key={w} className="warn-text">{w}</p>)}
            </>
          )}
          <button type="button" className="primary big" disabled={!r} onClick={() => navigate('/compare')}>설계 결과 확인 →</button>
        </aside>
      </div>
    </main>
  )
}
