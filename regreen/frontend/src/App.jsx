import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useApp } from './state.jsx'
import Explore from './pages/Explore.jsx'
import Design from './pages/Design.jsx'
import Compare from './pages/Compare.jsx'
import Report from './pages/Report.jsx'

const STEPS = [
  { key: 'explore', path: '/explore', no: '01', label: '공간 탐색' },
  { key: 'design', path: '/design', no: '02', label: '공존 설계' },
  { key: 'compare', path: '/compare', no: '03', label: '결과 비교' },
  { key: 'report', path: '/report', no: '04', label: '리포트' },
]

function Header() {
  const { unlocked, candidate } = useApp()
  return (
    <header className="app-header no-print">
      <div className="brand">
        <span className="brand-name">RE : GREEN</span>
      </div>
      <nav className="steps" aria-label="진행 단계">
        {STEPS.map((s) =>
          unlocked[s.key] ? (
            <NavLink key={s.key} to={s.path} className={({ isActive }) => `step${isActive ? ' active' : ''}`}>
              <small>{s.no}</small> {s.label}
            </NavLink>
          ) : (
            <span key={s.key} className="step locked" aria-disabled="true" title="이전 단계를 먼저 마쳐 주세요">
              <small>{s.no}</small> {s.label}
            </span>
          ),
        )}
      </nav>
      <div className="project">{candidate ? <><i className="dot" /> {candidate.feature?.properties?.name ?? '선택한 후보지'}</> : <span className="muted">후보지 선택 전</span>}</div>
    </header>
  )
}

// 잠긴 단계로 주소를 직접 쳐서 들어오면 마지막으로 열린 단계로 보낸다
function Guard({ step, children }) {
  const { unlocked } = useApp()
  if (unlocked[step]) return children
  const last = [...STEPS].reverse().find((s) => unlocked[s.key])
  return <Navigate to={last.path} replace />
}

export default function App() {
  return (
    <div className="app">
      <Header />
      <Routes>
        <Route path="/" element={<Navigate to="/explore" replace />} />
        <Route path="/explore" element={<Explore />} />
        <Route path="/design" element={<Guard step="design"><Design /></Guard>} />
        <Route path="/compare" element={<Guard step="compare"><Compare /></Guard>} />
        <Route path="/report" element={<Guard step="report"><Report /></Guard>} />
        <Route path="*" element={<Navigate to="/explore" replace />} />
      </Routes>
      <footer className="app-footer no-print">RE : GREEN · 공간과 일상이 함께하는 녹지 설계</footer>
    </div>
  )
}
