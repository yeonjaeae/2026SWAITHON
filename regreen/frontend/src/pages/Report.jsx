// 04 리포트: 영역 → 후보지 → 설계 조건 → 환경 효과를 한 장으로, 인쇄 / PDF 저장
import { Link } from 'react-router-dom'
import PlanMap from '../components/PlanMap.jsx'
import { useApp } from '../state.jsx'
import { LANDCOVER, SITE_TYPE, deficitLabel, fmt, regionAreaKm2 } from '../geo.js'

export default function Report() {
  const { region, analysis, candidate, design, designResult: r } = useApp()
  const env = r.environmental_effect
  const props = candidate.feature.properties ?? {}
  const lc = analysis?.landcover ?? {}
  const today = new Date().toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' })

  return (
    <main className="page report-page">
      <div className="page-heading no-print">
        <span className="page-no">04</span>
        <div>
          <h1>설계 내용을 한눈에.</h1>
          <p>인쇄하거나 PDF로 저장할 수 있어요.</p>
        </div>
      </div>

      <article className="panel padded report">
        <header className="report-head">
          <small>RE : GREEN · 녹지 설계 리포트</small>
          <h1>{props.name ?? '선택한 후보지'}</h1>
          <p className="muted">{today}{props.is_demo ? ' · 예시 후보지' : ''}</p>
        </header>

        <div className="report-grid">
          <PlanMap candidate={candidate} result={r} after protect={design.protect} className="map-report" />
          <div>
            <h2>1. 분석 영역</h2>
            <dl className="kv">
              <dt>범위</dt><dd>{fmt(region.sw.lat, 4)}, {fmt(region.sw.lng, 4)} ~ {fmt(region.ne.lat, 4)}, {fmt(region.ne.lng, 4)}</dd>
              <dt>면적</dt><dd>{fmt(regionAreaKm2(region), 2)}㎢</dd>
              <dt>녹지 부족지수</dt><dd>{fmt(analysis?.deficit_index, 2)} ({deficitLabel(analysis?.deficit_index)})</dd>
              <dt>토지 피복</dt><dd>{Object.values(lc).some((v) => v.area_m2 > 0)
                ? Object.entries(LANDCOVER).map(([k, v]) => `${v.label} ${fmt((lc[k]?.ratio ?? 0) * 100, 0)}%`).join(' · ')
                : '항공사진 분석 없음 (공공 데이터 기준)'}</dd>
            </dl>
            <h2>2. 후보지</h2>
            <dl className="kv">
              <dt>유형</dt><dd>{SITE_TYPE[props.site_type] ?? props.site_type ?? '—'}</dd>
              <dt>면적</dt><dd>{fmt(candidate.area_m2)}㎡</dd>
              {props.rank != null && <><dt>추천 순위</dt><dd>{props.rank}위 · 종합 {fmt((props.total_score ?? 0) * 100, 0)}점</dd></>}
            </dl>
            {props.reasons?.length > 0 && (
              <>
                <h3>추천 이유</h3>
                <ul className="report-why">{props.reasons.map((t) => <li key={t}>{t}</li>)}</ul>
              </>
            )}
          </div>
        </div>

        <h2>3. 설계 조건</h2>
        <dl className="kv">
          <dt>녹화 비율</dt><dd>{design.greenRatio}% (실제 {fmt(r.actual_green_ratio, 1)}%)</dd>
          <dt>식생 구성</dt><dd>잔디 {design.veg.grass}% · 관목 {design.veg.shrub}% · 교목 {design.veg.tree}%</dd>
          <dt>그린 영역</dt><dd>녹화 {design.green.length}곳 · 보존 {design.protect.length}곳 (녹화 가능 {fmt(r.editable_area_m2)}㎡)</dd>
          <dt>공존 조건</dt><dd>{design.conditions.length ? design.conditions.join(' · ') : '선택 안 함'}</dd>
          {design.memo && <><dt>메모</dt><dd>{design.memo}</dd></>}
        </dl>

        <h2>4. 환경 효과</h2>
        <div className="metrics four">
          <div><span>녹지 면적</span><strong>{fmt(r.green_area_m2)}<small>㎡</small></strong></div>
          <div><span>식재 수목</span><strong>{fmt(r.plant_count?.tree)}<small>주</small></strong><em>관목 {fmt(r.plant_count?.shrub)}주</em></div>
          <div><span>연간 탄소 흡수</span><strong>{fmt(env?.carbon_absorption?.total)}<small>kg CO₂</small></strong></div>
          <div><span>예상 조성 비용</span><strong>{fmt((env?.estimated_cost?.total ?? 0) / 10000)}<small>만원</small></strong></div>
        </div>
        <p className="muted small">환경 효과와 비용은 설계 API의 임시 가정(관목 1주/㎡, 교목 1주/16㎡ 등)에 따른 추정치이며, 실제 시공 가능 여부는 별도 확인이 필요합니다.</p>

        <div className="actions no-print">
          <Link className="button" to="/design">설계 수정</Link>
          <button type="button" className="primary" onClick={() => window.print()}>인쇄 / PDF 저장</button>
        </div>
      </article>
    </main>
  )
}
