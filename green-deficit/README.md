# 녹지 부족지수 분석 API (서울, 100m 격자)

지도에서 사용자가 **사각형으로 선택한 영역**의 녹지 부족지수와 녹지 확충이 필요한 구역을 계산해 돌려주는 백엔드.
공개 위성영상·인구·공원 데이터로 서울 전체를 100m 격자로 미리 분석해 두고, 요청이 오면 그 영역만 빠르게(약 0.1초) 계산한다.

```
[사전 준비]  공개 데이터 받기 → 서울 100m 격자(60,585칸) 분석 → output/ 에 저장
                                                   │
[요청마다]   프론트: 사각형 선택 ──(sw, ne)──▶ POST /api/region/analyze ──▶ 부족지수 + 녹지 확충 필요 구역
             모델: 녹지/주택가/도로 폴리곤 ──(landcover, 선택)──┘                    │
                                                                    PostGIS: 유휴 공간과 교차 → 개별 후보지
```

---

## 실행 방법

Python 3.11 이상. `green-deficit` 폴더에서 실행한다.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

> 분석 결과(`output/`)가 레포에 포함되어 있으므로, **API만 쓸 거라면 1)·2)를 건너뛰고 3)부터** 하면 된다.

**1) 데이터 받기** (계정 불필요, 서울 전체 약 13분)

```bash
.venv\Scripts\python scripts\fetch_public_data.py
```

**2) 분석** (약 10초 → `output/`)

```bash
.venv\Scripts\python -m src.pipeline --dir data/raw/서울
```

**3) API 서버**

```bash
.venv\Scripts\uvicorn src.api:app --reload --port 8000
```

API 문서(Swagger): http://localhost:8000/docs

> 분석을 다시 돌리면 **API 서버를 껐다 켜야** 새 결과가 반영된다 (결과를 메모리에 올려 두기 때문).

---

## 데이터

| 데이터 | 출처 | 처리 |
|---|---|---|
| NDVI (식생지수) 10m | Sentinel-2 L2A (ESA) | 2023~2025년 6~9월, 구름 제거 후 89장면 중앙값 |
| 지표면 온도 30m | Landsat 8/9 Collection 2 L2 (USGS) | 같은 기간, 구름 제거 후 40장면 중앙값 (°C) |
| 인구 100m | WorldPop 2020 constrained | 서울 합계 934만 명 (실제 약 940만) |
| 공원 | OpenStreetMap `leisure=park` | 1,000㎡ 미만 조각 제외 → 2,325개 |
| 구 경계 | OpenStreetMap | 25개 구, 605.86㎢ |

위성영상은 Microsoft Planetary Computer에서 필요한 범위만 읽어 온다 (`scripts/fetch_public_data.py`).
여름 영상을 쓰는 이유: 낙엽수가 많아 계절에 따라 NDVI 차이가 크고, 폭염·열섬이 여름 문제이기 때문.

---

## 분석 방법

### 1. 100m 격자 (`src/grid.py`)
서울을 EPSG:5179(미터 단위) 100m 정사각형으로 나눈다 → **60,585칸**.
좌표를 100m 배수로 맞춰 통계청 SGIS 100m 격자와 칸이 일치한다.

### 2. 칸마다 지표 계산 (`src/features.py`)

| 지표 | 계산 |
|---|---|
| `ndvi` | 칸 안 NDVI 픽셀 평균 |
| `lst` | 칸 안 지표면 온도 픽셀 평균 |
| `pop` | 칸 안 인구 합계 |
| `park_dist` | 칸 중심에서 가장 가까운 공원까지 거리 (m) |

### 3. 정규화 (`src/index.py`)
모든 지표를 0~1로 바꾸고 **"클수록 녹지가 더 필요"**한 방향으로 통일한다.
기준은 사람이 사는 칸(인구 1명 이상, 45,378칸)의 5~95 퍼센타일. 한강·산지가 기준을 흐리지 않게 하기 위함.

| 지표 | 계산 |
|---|---|
| 녹지 부족 `green_short_n` | 1 − NDVI (물은 NDVI 0으로 처리) |
| 공원 접근성 부족 `park_far_n` | 공원까지 거리 ÷ 500m (최대 1, 근린공원 서비스 반경) |
| 열 위험 `heat_n` | 지표면 온도 |
| 인구 수요 `pop_n` | log(1 + 인구) (편차가 커서 로그) |

### 4. 점수

```
녹지 부족지수  = 0.6 × 녹지 부족 + 0.4 × 공원 접근성 부족
우선순위 점수  = 0.4 × 녹지 부족지수 + 0.3 × 열 위험 + 0.3 × 인구 수요
```

가중치와 기준값(500m, 1,000㎡ 등)은 모두 `src/config.py` 에 있다.

### 5. 선택 영역 분석 (`src/region.py`)
요청이 오면 미리 계산한 격자 값으로 그 영역만 계산한다.

1. **토지 피복 면적**: 모델 폴리곤(녹지/주택가/도로)을 영역으로 잘라 분류별 면적·비율
2. **영역 평균**: 영역에 걸친 칸들을 겹친 면적 비율로 가중해 평균 NDVI·온도, 인구 합계
3. **녹지까지 거리**: 주택가에 20m 간격으로 점을 찍고 가장 가까운 녹지(모델 녹지 + 주변 1km 공공 공원)까지 평균 거리. 모델 결과가 없으면 칸의 공원 거리로 대신
4. **점수**: 격자와 **같은 정규화 기준**으로 부족지수·우선순위 계산 → 서울 전체와 비교 가능
5. **녹지 확충 필요 구역**: 기존 녹지를 뺀 영역 중 **녹지에서 250m 이상 떨어지고 열 위험 0.6 이상**인 곳

---

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 서버 확인 (`{"status":"ok","cells":60585,"parks":2325}`) |
| POST | `/api/region/analyze` | 선택한 사각형 영역 분석 |

### 요청

| 필드 | 필수 | 설명 |
|---|:---:|---|
| `sw` | ✓ | **S**outh-**W**est(남서쪽) = 사각형 왼쪽 아래 꼭짓점 `{lat, lng}` |
| `ne` | ✓ | **N**orth-**E**ast(북동쪽) = 사각형 오른쪽 위 꼭짓점 `{lat, lng}` |
| `landcover` | | 모델 결과. `class`(green / residential / road) + `geometry`(GeoJSON) 목록 |
| `weights` | | 우선순위 가중치. 기본 `{"deficit":0.4,"heat":0.3,"pop":0.3}` |

```json
{
  "sw": { "lat": 37.5440, "lng": 126.9615 },
  "ne": { "lat": 37.5485, "lng": 126.9680 }
}
```

- 꼭짓점을 반대로 보내도 알아서 정리한다.
- `landcover` 의 GeoJSON 좌표는 **[경도, 위도]** 순서 (EPSG:4326).
- 사각형이 아닌 영역은 `sw`/`ne` 대신 `region` 에 GeoJSON Polygon 으로 보낼 수 있다.

카카오맵에서 요청 만들기:

```javascript
const b = rectangle.getBounds();
const res = await fetch('http://localhost:8000/api/region/analyze', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    sw: { lat: b.getSouthWest().getLat(), lng: b.getSouthWest().getLng() },
    ne: { lat: b.getNorthEast().getLat(), lng: b.getNorthEast().getLng() },
  }),
});
```

### 응답 (숙명여대 일대, 모델 결과 없이)

```json
{
  "deficit_index": 0.513,
  "priority_score": 0.524,
  "total_area_m2": 286673.2,
  "population": 3218,
  "avg_ndvi": 0.301,
  "avg_lst": 40.11,
  "avg_dist_to_green_m": 113.0,
  "candidate_area_m2": 27212.2,
  "candidates": { "type": "MultiPolygon", "coordinates": [...] },
  ...
}
```

| 구분 | 필드 | 설명 |
|---|---|---|
| 점수 | `deficit_index` | 녹지 부족지수 (0~1, 높을수록 부족) |
| | `priority_score` | 우선순위 점수 (0~1) |
| | `components` | 점수 세부 항목 `green_short_n`, `park_far_n`, `heat_n`, `pop_n` (각 0~1) |
| 영역 | `total_area_m2` | 선택 영역 면적 (㎡) |
| | `population`, `pop_density_per_ha` | 인구 (명), 인구밀도 (명/ha) |
| | `avg_ndvi`, `avg_lst` | 평균 NDVI, 평균 지표면 온도 (°C) |
| | `grid_cells` | 계산에 쓴 100m 칸 수 |
| 녹지 | `landcover` | 분류별 `area_m2`, `ratio` (모델 결과가 있을 때) |
| | `green_area_m2` | 녹지 면적 (㎡) |
| | `green_per_capita_m2` | 1인당 녹지 면적 (㎡). 모델 결과가 없으면 `null` |
| | `green_per_capita_target_m2` | 비교 기준 9㎡ (WHO 권장) |
| | `avg_dist_to_green_m` | 녹지까지 평균 거리 (m) |
| | `dist_source` | 거리 기준: `model_residential`(모델 주택가) / `grid_park_dist`(격자) |
| 확충 | `candidates` | 녹지 확충 필요 구역 (GeoJSON MultiPolygon, 없으면 `null`) |
| | `candidate_area_m2` | 그 면적 (㎡) |

### 오류 (422)

| 상황 | 메시지 |
|---|---|
| `sw`/`ne` 중 하나만 보냄 | 사각형은 sw 와 ne 를 둘 다 보내야 합니다 |
| 영역 없음 | 영역이 없습니다. sw + ne (사각형) 또는 region (GeoJSON) 을 보내세요 |
| 위도·경도를 바꿔 넣음 | lat 은 90 이하여야 함 (검증 오류) |
| 서울 밖 | 영역이 분석 대상 지역(격자) 밖에 있습니다 |

---

## 팀 연동

- **프론트**: `sw`/`ne` 만 보내면 된다. CORS 는 모두 허용되어 있다.
- **모델**: 결과 폴리곤을 `landcover` 로 넘긴다. 좌표는 GeoJSON EPSG:4326 ([경도, 위도]). 없어도 동작한다.
- **PostGIS**: `candidates` 는 녹지가 필요한 **범위**다. 주택가로 자르지 않았으므로 주차장·학교·공공시설 등 유휴 공간 데이터와 교차(`ST_Intersection`)해 개별 후보지를 뽑는다. 면적은 `ST_Transform(geom, 5179)` 후 계산.
- **DB 적재**: 격자 결과는 `output/grid_index.gpkg` (레이어 `grid`, EPSG:5179) 한 파일.

  ```bash
  ogr2ogr -f PostgreSQL PG:"host=... dbname=... user=..." output/grid_index.gpkg -nln grid_cell
  ```

  API는 지금 이 파일을 메모리에 올려 쓴다. DB로 바꾸려면 `src/store.py` 의 `GridStore` 만 고치면 된다.

---

## 한계

- **상대 지표**: 부족지수는 서울 안에서 비교하는 값이며, 가중치·기준(500m, 250m 등)은 우리가 정한 것이다.
- **지표면 온도 ≠ 기온**: 위성이 오전 10시 반쯤 측정한 땅 표면 온도라 아스팔트는 40°C 이상으로 나온다.
- **인구**: WorldPop 2020 모델 추정치. 서울 합계는 맞지만 칸 단위로는 오차가 있다.
- **공원**: OSM 기준이라 실제 지정 공원과 다를 수 있다. 공공데이터포털 공원 데이터로 교체 가능.

---

## 파일 구조

```
scripts/fetch_public_data.py  공개 데이터 받기 (경계·공원·NDVI·온도·인구)
src/config.py                 가중치 · 기준값
src/grid.py                   100m 격자 생성
src/features.py               칸별 NDVI·온도 평균, 인구 합계, 공원 거리
src/index.py                  정규화 · 부족지수 · 우선순위
src/pipeline.py               전체 분석 실행 → output/
src/store.py                  분석 결과 읽기 (나중에 PostGIS로 교체)
src/region.py                 선택 영역 분석
src/api.py                    FastAPI 서버
gee/export_seoul.js           (대안) Google Earth Engine 으로 위성 데이터 받기
output/                       분석 결과 (격자 · 공원 · 정규화 기준값)
```

직접 받은 데이터 파일로 분석하려면:

```bash
.venv\Scripts\python -m src.pipeline --boundary 경계.shp --name-col 구이름컬럼 --ndvi ndvi.tif --lst lst.tif --pop pop.tif --parks parks.gpkg
```
