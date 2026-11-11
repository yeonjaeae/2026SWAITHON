// 03 결과 비교: 위성사진 Before / After(녹화 영역 + 식생 표시)
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import PlanMap from '../components/PlanMap.jsx'
import { useApp } from '../state.jsx'
import { fmt } from '../geo.js'

export default function Compare() {
  const { candidate, designResult: r, design, setVisitedCompare } = useApp()
  useEffect(() => { setVisitedCompare(true) }, [setVisitedCompare])
  const env = r.environmental_effect
  const props = candidate.feature.properties ?? {}

  return (
    <main className="page">
      <div className="page-heading">
        <span className="page-no">03</span>
        <div>
          <h1>내가 그린 녹지 계획을 확인하세요.</h1>
          <p>{props.name ?? '선택한 후보지'} · 위성사진 위에 녹화 영역과 식생을 표시했어요.</p>
        </div>
      </div>

      <div className="compare">
        <figure className="panel">
          <figcaption>Before · 현재</figcaption>
          <PlanMap candidate={candidate} result={r} className="map-compare" />
        </figure>
        <figure className="panel">
          <figcaption>After · 설계안</figcaption>
          <PlanMap candidate={candidate} result={r} after protect={design.protect} className="map-compare" />
        </figure>
      </div>
      <div className="legend-row compare-legend">
        <span><i style={{ background: '#7CC47F' }} />녹화 영역 (잔디)</span>
        <span><i className="round" style={{ background: '#A3C93A' }} />관목</span>
        <span><i className="round" style={{ background: '#1F5A33' }} />교목</span>
        <span><i style={{ background: '#E4B34D' }} />보존 영역</span>
        <span className="muted">점 위치는 예시 배치예요</span>
      </div>

      <section className="panel padded">
        <h2>환경 효과</h2>
        <div className="metrics four">
          <div><span>녹지 면적</span><strong>{fmt(r.green_area_m2)}<small>㎡</small></strong><em>후보지의 {fmt(r.actual_green_ratio, 1)}%</em></div>
          <div><span>식재 수목</span><strong>{fmt(r.plant_count?.tree)}<small>주</small></strong><em>관목 {fmt(r.plant_count?.shrub)}주</em></div>
          <div><span>연간 탄소 흡수</span><strong>{fmt(env?.carbon_absorption?.total)}<small>kg CO₂</small></strong></div>
          <div><span>예상 조성 비용</span><strong>{fmt((env?.estimated_cost?.total ?? 0) / 10000)}<small>만원</small></strong></div>
        </div>
        <div className="veg-bar" aria-label="식생 면적 구성">
          <i style={{ width: `${design.veg.grass}%`, background: '#7CC47F' }}>잔디 {design.veg.grass}%</i>
          <i style={{ width: `${design.veg.shrub}%`, background: '#4E8F3A' }}>관목 {design.veg.shrub}%</i>
          <i style={{ width: `${design.veg.tree}%`, background: '#1F5A33' }}>교목 {design.veg.tree}%</i>
        </div>
        {env?.estimate_note && <p className="muted small">{env.estimate_note}</p>}
      </section>

      <p className="actions">
        <Link className="button" to="/design">설계 수정</Link>
        <Link className="button primary" to="/report">최종 리포트 보기 →</Link>
      </p>
    </main>
  )
}
