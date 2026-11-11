# RE : GREEN 프론트 (React + Vite + Leaflet)

01 공간 탐색 → 02 공존 설계 → 03 결과 비교 → 04 리포트 (순서대로만 이동, 새로고침하면 처음부터)

## 실행

```bash
npm install
npm run dev
```

→ http://localhost:5173

백엔드는 각자 아래 포트로 켜 둔다. Vite 가 `/svc/...` 주소를 대신 전달하므로 CORS 설정이 필요 없다 (`vite.config.js`).

| 프론트 주소 | 백엔드 | 포트 |
|---|---|---|
| `/svc/deficit` | 녹지 부족지수 (green-deficit) | 8000 |
| `/svc/candidate` | 후보지 추천 (candidate-recommender-v2) | 8001 |
| `/svc/design` | 녹지 설계 (green-design-backend) | 8002 |
| `/svc/ai` | AI 토지 피복 (ai) | 8003 |
| `/esri` | Esri 위성사진 내보내기 (AI 입력용) | - |

## 화면별 연결

- **01 공간 탐색**: 사각형 선택 → `POST /api/region/analyze` (부족지수 + 100m 격자, 먼저 표시)
  → Esri 위성사진 + 좌표 파일(.pgw, EPSG:3857) 생성 → `POST /ai/landcover` → 토지 피복 표시 후 부족지수 재계산
  → `POST /recommendations/from-region-analysis` (0개면 "추천할 후보지가 없어요", 실패하면 오류 사유 표시)
- **02 공존 설계**: 다각형으로 녹화·보존 영역 → (녹화 − 보존)을 계산해 `POST /api/design/spatial`, 값이 바뀔 때마다 재계산
- **03 결과 비교**: 위성사진 Before / After (녹화 영역 + 교목·관목 점은 예시 배치)
- **04 리포트**: 인쇄 / PDF 저장

AI 서버가 없어도 공공 데이터 기준으로 분석된다. 후보지가 없으면 02 단계로 넘어갈 수 없다.

## 파일

```
src/App.jsx            헤더 · 단계 · 잠금
src/state.jsx          앱 상태 (저장 안 함)
src/api.js             백엔드 호출
src/geo.js             좌표 · 면적 · 위성사진 내보내기 · 색
src/components/        BaseMap(위성/일반 전환), PlanMap(결과 지도)
src/pages/             Explore, Design, Compare, Report
```
