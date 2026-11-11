# RE : GREEN 웹 서비스 (프론트 + 백엔드 연동본)

서울에서 사각형으로 영역을 고르면 **녹지 부족 분석 → 후보지 추천 → 녹지 설계 → 결과 비교 → 리포트(PDF)** 까지 이어지는 화면입니다.

> 이 폴더는 프론트와 백엔드 4개를 **실제로 연결해 끝까지 확인한 버전**입니다.
> 저장소 루트의 `green-deficit/`, `ai/`, `candidate-recommender-v2/`, `green-design-backend/` 를 복사한 뒤
> 연동하면서 고친 내용이 들어 있습니다 (아래 [원본과 다른 점](#원본과-다른-점)).

```
regreen/
├─ frontend/                     화면 (React + Vite + Leaflet)          → 5173
└─ backend/
   ├─ run_backend.py             백엔드 4개를 한 번에 켜는 스크립트
   ├─ green-deficit/             녹지 부족지수 분석                      → 8000
   ├─ candidate-recommender-v2/  후보지 추천 (+ 서울 부지 5,000곳 data/)  → 8001
   ├─ green-design-backend/      녹지 설계 · 환경 효과                   → 8002
   └─ ai/                        AI 토지 피복 (+ 서울 도로 파일)          → 8003
```

---

## 0. 처음 한 번만 설치

필요한 프로그램: **Python 3.11 이상**, **Node.js 20 이상**, Git

```bash
git clone https://github.com/yeonjaeae/2026SWAITHON.git
cd 2026SWAITHON/regreen
```

### 백엔드 (녹지 부족지수 · 후보지 · 설계)

Windows (PowerShell)
```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd ..
```

Mac / Linux
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ..
```

### AI 서버 (선택 · 설치에 10분 이상, 약 2GB)

없어도 화면은 **공공 데이터 기준**으로 끝까지 동작합니다. 있으면 녹지·도로·주거지역 비율이 추가됩니다.

Windows (PowerShell) — GPU 없는 컴퓨터는 가벼운 CPU 버전 torch 를 먼저 설치
```powershell
cd backend\ai
python -m venv .venv
.venv\Scripts\pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\pip install -r requirements.txt
cd ..\..
```

Mac / Linux
```bash
cd backend/ai
python3 -m venv .venv
.venv/bin/pip install torch
.venv/bin/pip install -r requirements.txt
cd ../..
```

AI 모델(Mask2Former, 수백 MB)은 **첫 분석 때** Hugging Face 에서 자동으로 받습니다.

### 프론트

```bash
cd frontend
npm install
cd ..
```

---

## 1. 실행 (매번)

터미널 **2개**를 엽니다.

**터미널 1 — 백엔드** (`regreen/backend` 에서)

Windows
```powershell
.venv\Scripts\python run_backend.py
```
Mac / Linux
```bash
.venv/bin/python run_backend.py
```

아래처럼 나오면 성공입니다. (AI 를 설치하지 않았으면 8003 은 건너뜀)
```
  8000  녹지 부족지수  실행 중   http://localhost:8000/docs
  8001  후보지 추천    실행 중   http://localhost:8001/docs
  8002  녹지 설계      실행 중   http://localhost:8002/docs
  8003  AI 토지 피복   실행 중   http://localhost:8003/docs
```

**터미널 2 — 프론트** (`regreen/frontend` 에서)
```bash
npm run dev
```

## 2. 화면 들어가기

👉 **http://localhost:5173**

1. **01 공간 탐색**: 처음엔 서울 전체 녹지 부족(500m 칸)이 보입니다. 칸을 누르면 지표가 떠요.
   `영역 선택` → 지도에서 드래그(최대 2㎢) → `선택 영역 분석`
   → 녹지 부족지수 · 100m 격자 · 추천 후보지 (AI 가 켜져 있으면 수십 초 뒤 토지 피복 반영)
2. 후보지 카드를 눌러 **추천 이유** 확인 → `선택한 공간 설계하기`
3. **02 공존 설계**: 녹화·보존 영역 그리기, 녹화 비율·식생 조절 → 녹지 면적·탄소·비용이 바로 계산
4. **03 결과 비교** → **04 리포트** (인쇄 / PDF 저장)

> 시연 추천 영역: 숙명여대 ~ 서울역 서쪽 (청파동·남영동). 주차장·학교·공공 옥상·공터가 골고루 나옵니다.

끄기: 각 터미널에서 `Ctrl + C`

---

## 3. 자주 생기는 문제

| 증상 | 원인 · 해결 |
|---|---|
| "서버에 연결할 수 없어요" | 터미널 1 의 백엔드가 꺼져 있음 → `run_backend.py` 다시 실행 |
| "AI 분석을 쓰지 못해 공공 데이터 기준으로…" | AI 서버(8003)가 없거나 실패. 화면은 그대로 진행 가능 |
| "응답 시간이 초과됐어요" (AI) | CPU 로 모델을 돌려 3분을 넘김. 영역을 작게 골라 다시 |
| 추천 후보지가 없어요 | 그 영역에 부지가 없음. 녹지 부족이 진한 곳(주거·상업지)으로 옮겨 보기 |
| 포트가 이미 사용 중 | 다른 서버가 8000~8003 을 쓰는 중 → 그 서버를 끄고 다시 |

각 서버의 API 문서: `http://localhost:8000/docs` (8001, 8002, 8003 도 같은 방식)

---

## 원본과 다른 점

| 폴더 | 바뀐 내용 |
|---|---|
| `green-deficit` | 응답에 100m 격자(`grids`) 추가 · 서울 전체 500m 칸 API `GET /api/seoul/grid` · AI 결과가 있으면 확충 구역 거리 기준 150m → 50m · 서울 유휴 부지 추출 스크립트 `scripts/fetch_idle_sites.py` |
| `ai` | 꼬인 도형 정리(`make_valid`, TopologyException 해결) · 도로를 **서울 도로 파일**(`seoul_roads.gpkg`)에서 읽기 (공용 서버가 바빠 실패하던 문제) · 파일이 없으면 공용 서버 3곳 순서대로 시도 · 도로 파일 만드는 `build_roads.py` · requirements 에 scipy, geopandas 추가 |
| `candidate-recommender-v2` | 미터 좌표로 바꾼 도형 정리(`spatial.py` 의 `metric`, TopologyException 해결) · 서울 부지 파일 `data/idle_sites_seoul.geojson` 추가 |
| `green-design-backend` | 변경 없음 |

## 데이터 출처

- **서울 부지 5,000곳** (`candidate-recommender-v2/data/idle_sites_seoul.geojson`), **서울 도로** (`ai/seoul_roads.gpkg`):
  © OpenStreetMap contributors, [ODbL](https://opendatacommons.org/licenses/odbl/). Geofabrik 한국 파일(2026-11-10 기준)에서 추출
  - 종류: 주차장 · 학교 운동장 · 공공 광장 · 공공 옥상 · 공공기관 부지 · 공터
  - 불투수율은 위성(Sentinel-2) NDVI 로 추정한 값
  - 다시 만들기: [Geofabrik](https://download.geofabrik.de/asia/south-korea-latest.osm.pbf) 파일을 받은 뒤
    `ai/build_roads.py <파일>` (도로) / `green-deficit/scripts/fetch_idle_sites.py --pbf <파일> --boundary <서울 경계> --ndvi <NDVI 래스터> --out <출력>` (부지, 원본 위성 데이터 필요 · `osmium` 설치 필요)
- 녹지 부족지수: Sentinel-2 NDVI, Landsat 8/9 지표면 온도, WorldPop 인구, OSM 공원
- 위성사진: Esri World Imagery
