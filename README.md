# RE : GREEN

2026 SWAITHON · 도시에 자연의 자리를 되돌리다

서울에서 사각형으로 고른 영역의 녹지 부족을 분석하고, 녹화할 후보지를 추천받아 설계·효과까지 확인하는 서비스입니다.

## 폴더

| 폴더 | 내용 |
|---|---|
| `green-deficit/` | 녹지 부족지수 분석 API (NDVI · 지표면 온도 · 인구 · 공원 거리 → 100m 격자) |
| `ai/` | AI 토지 피복 API (Mask2Former 녹지 + OSM 도로 + 서울시 주거지역) |
| `candidate-recommender-v2/` | 녹지 확충 후보지 추천 API |
| `green-design-backend/` | 녹지 설계 · 환경 효과 계산 API |
| `swaithon-unified-backend/` | 위 서버들을 포트 하나(8080)로 묶는 통합 백엔드 |
| `html-prototype/` | API 연결 전 HTML 화면 양식 |

각 폴더의 README 에 실행 방법이 있습니다.
