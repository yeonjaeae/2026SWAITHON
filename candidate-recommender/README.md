# 후보지 추천 API

## 1. 빠른 실행 — Mac

Python 3.11 이상을 권장합니다. 실제 검증 환경은 Python 3.15입니다. ZIP을 풀고 터미널에서 `regreen_candidate_recommender` 폴더를 연 뒤 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8001
```

브라우저: http://127.0.0.1:8001/docs

첫 테스트는 `GET /recommendations/demo` → **Try it out → Execute**입니다. 기본으로 가상 시설 3개가 반환됩니다. DB·API 키·AI 모델이 없어도 됩니다.

서버를 켜둔 상태에서 새 터미널을 열고 같은 폴더에서 실행하면 테스트 파일이 자동 저장됩니다.

```bash
source .venv/bin/activate
python demo_flow.py
```

`demo_output/`에 추천 목록, 선택 후보지 JSON·GeoJSON, 가상 editable, 환경 효과 API 요청이 저장됩니다. 가상 editable은 연동 시연을 위해 후보지 전체를 복사한 것입니다. **AI 결과 또는 실제 녹지화 허용 면적으로 쓰면 안 됩니다.**

## 2. API 네 가지

| 호출 | 입력 | 출력·사용 시점 |
|---|---|---|
| `GET /recommendations/demo` | limit, min_area_m2 | DB 없는 테스트 |
| `POST /recommendations/from-region-analysis` | region_analysis, sites 또는 설정된 파일/DB, 선택 grids·landcover | 시설별 추천 목록 |
| `POST /recommendations/select` | candidate_id, recommendations | 환경 효과 API가 바로 받는 CandidateData |
| `POST /recommendations/design-handoff` | candidate, editable, green_ratio, vegetation | 호출할 환경 효과 endpoint와 payload |

`GET /health`, `GET /api/health`는 서버 생존 여부입니다. DB 연결 성공 여부를 의미하지 않습니다.

### A. 후보지 추천

`examples/recommend_request.json`은 생략 없는 실행 가능한 입력입니다.

```bash
curl -X POST http://127.0.0.1:8001/recommendations/from-region-analysis \
  -H 'Content-Type: application/json' \
  --data-binary @examples/recommend_request.json
```

`region_analysis`에는 동희 API **응답 전체**를 넣을 수 있습니다. `candidates`와 선택적인 `deficit_index`를 사용하며 나머지 분석 필드도 허용합니다.

- `candidates: null` → HTTP 200, `count: 0`. 시설 DB 조회도 하지 않습니다.
- `sites: []` → 빈 시설 자료이므로 `count: 0`.
- `sites` 생략 → `IDLE_SITES_FILE`, 없으면 `DATABASE_URL`에서 조회합니다.
- 파일·DB 설정도 없으면 503. 가상 데이터로 몰래 대체하지 않습니다.
- 기본 최소 후보지 면적은 80㎡. 잘라낸 후 면적이 기준보다 작으면 제외합니다.
- 기본 유형: `parking_lot`, `schoolyard`, `public_plaza`, `public_rooftop`.

GeoJSON은 EPSG:4326의 **[경도, 위도]**입니다. 이 API는 한국 범위를 지원하고, 미터 계산은 EPSG:5179에서 수행합니다. 폴리곤 구멍과 MultiPolygon을 보존하며, 면적이 없는 점·선 접촉은 후보지로 내보내지 않습니다. 면적·교차와 좌표 변환 개념은 [Shapely 공식 설명](https://shapely.readthedocs.io/en/2.1.2/reference/shapely.intersection.html), [PostGIS 좌표 변환 설명](https://postgis.net/docs/manual-dev/en/ST_Transform.html)을 참고했습니다.

### B. 후보지 선택

추천 응답의 `recommendations` 배열과 선택한 `candidate_id`를 넘깁니다. `examples/select_request.json`을 그대로 테스트할 수 있습니다.

결과는 `examples/selected_candidate.json`에 있으며 구조는 다음과 같습니다.

- `candidate_id`: 문자열 고유 ID
- `area_m2`: 해당 후보지 geometry에서 다시 계산한 면적
- `geometry_crs`: `EPSG:4326`
- `feature.type`: `Feature`
- `feature.id`: candidate_id와 동일
- `feature.geometry`: 선택된 후보지 Polygon/MultiPolygon
- `feature.properties`: 원본 site_id, 출처, 가상 여부, 면적 등

이 결과 전체는 기존 환경 효과 API의 `/api/design/candidate`에 바로 보낼 수 있습니다. AI에는 `candidate_id`와 `feature.geometry`를 전달합니다.

후보지 ID는 원본 site_id와 잘라진 경계에서 생성합니다. 동일 시설·동일 경계는 같은 ID이고, 분석 지역 또는 제외 녹지가 달라져 경계가 바뀌면 새 ID가 됩니다. 시설 자체의 지속 식별에는 `site_id`를 사용합니다. 생성 순서나 순위로 ID를 만들지 않습니다.

선택 API는 기존 방식처럼 **요청의 추천 목록을 사용하는 무상태 API**입니다. 서버 저장이나 인증을 제공하지 않습니다. geometry와 ID 일치·면적 재계산은 하지만, 데이터 출처의 진위나 사용자의 접근 권한을 증명하는 기능은 아닙니다. 외부 서비스 배포 시 서버에 추천 결과를 저장하고 로그인/권한 체계를 연결하세요.

### C. editable 수신 및 환경 효과 API 연결

`examples/handoff_request.json`을 참고합니다. `editable`은 다음 필드를 받습니다.

```json
{
  "candidate_id": "선택 후보지와 동일한 ID",
  "geometry_crs": "EPSG:4326",
  "editable_geometry": null,
  "source": "AI 분석 실행 ID 또는 담당자 검토 자료"
}
```

위 null은 명시적으로 편집 가능 영역이 없다는 뜻입니다. 분석이 아직 안 끝난 상태를 null로 대신 제출하지 마세요. 분석 완료 전에는 handoff를 호출하지 않습니다. 실제 영역이 있으면 null 대신 Polygon/MultiPolygon을 넣습니다.

동작:

1. 후보지 ID와 Feature ID, AI editable의 candidate_id를 대조합니다.
2. 후보지 면적을 geometry로 재계산합니다. 외부에서 입력한 면적은 믿지 않습니다.
3. 후보지 ∩ editable을 EPSG:5179에서 구합니다.
4. 면적이 있으면 `/api/design/spatial` 요청을 만듭니다.
5. 면적이 0이면 기존 spatial 코드가 빈 geometry를 거부하므로 `/api/design/from-candidate`에 `protected_area = 전체 면적`을 넣도록 만듭니다.

`design-handoff`는 다른 서버를 자동 호출하지 않습니다. 반환한 `target_endpoint`와 `payload`를 프론트/통합 서버가 실제 환경 효과 API로 보내면 됩니다. 환경 효과를 중복 구현하거나 AI 영역을 임의 생성하지 않습니다.

환경 효과 서버를 8002에서 실행했다면 전체 연동 시연:

```bash
python demo_flow.py --design-url http://127.0.0.1:8002
```

기존 환경 효과 서버는 해당 폴더에서 `python -m uvicorn main:app --reload --port 8002`로 실행합니다. 그 서버의 FastAPI, Pydantic, Shapely, PyProj 환경이 필요합니다. 녹지 부족 API는 8000, 후보지 추천은 8001, 환경 효과는 8002로 분리하면 포트 충돌을 피할 수 있습니다.

## 3. 점수가 계산되는 방식

| 항목 | 가중치 | 값의 근거 |
|---|---:|---|
| 녹지 부족도 | 0.45 | 격자별 deficit_index, 없으면 지역 평균이라고 표시 |
| 면적 적합성 | 0.25 | min(교차 면적 / 500㎡, 1) |
| 불투수율 | 0.20 | 시설 자료의 impervious_ratio |
| 실현 가능성 | 0.10 | 시설 자료의 feasibility_score |

500㎡와 가중치는 프로젝트 정책 가정이며 검증된 도시계획 기준이 아닙니다. 실현 가능성을 시설 종류만 보고 0.9처럼 자동 지정하지 않습니다. 모르는 불투수율·실현 가능성은 null로 둡니다.

사용 가능한 항목만 가중합한 후 **사용한 가중치 합으로 나누어** 0~1 점수를 만듭니다. `score_data_coverage`는 사용한 가중치 합이며 통계적 신뢰도는 아닙니다. 누락된 항목이 많은 후보지는 점수가 높아도 근거가 약할 수 있으므로 같이 표시하세요.

격자가 있으면 후보지와 격자가 겹친 면적으로 가중평균합니다. 격자가 일부만 덮고 지역 평균이 있으면 나머지는 지역 평균으로 채워 출처를 `grid_plus_region_fallback`으로 표시합니다. 지역 평균도 없으면 격자가 덮는 부분만 계산하고 `covered_grid_only`, `grid_coverage_ratio`를 반환합니다. 서로 중첩되는 격자는 이중 계산을 막기 위해 오류로 처리합니다.

추천 이유는 이번 전달본에서 **계산된 수치와 출처를 직접 조합하는 규칙 기반 문장**입니다. 외부 LLM 호출, API 키, 호출 비용은 필요하지 않습니다. 이전 코드의 선택적 LLM 문장 생성 기능은 이 버전에서 제외했습니다. 추천 순위의 근거를 검증하기 쉽게 하기 위한 변경입니다.

## 4. 실제 후보지 데이터 연결

실제 운영에는 주차장·운동장·광장 등의 **면 경계**가 필요합니다. 주소나 점 좌표만으로 경계를 지어내면 안 됩니다. 학교 부지 전체가 editable 운동장은 아닙니다. 실제 사용 여부·보존 구조물·소유·관리 상태는 별도 자료와 담당자 검토가 필요합니다.

GeoJSON FeatureCollection의 각 properties는 다음과 같습니다.

| 필드 | 필수 | 설명 |
|---|---|---|
| site_id | 예 | 자료 출처에서 안정적으로 유지되는 문자열 ID |
| name | 예 | 시설 이름 |
| site_type | 예 | parking_lot / schoolyard / public_plaza / public_rooftop 등 |
| source | 예 | 제공 기관·자료명·원본 식별자·갱신일 등을 적은 출처 |
| is_demo | 아니오 | 가상 자료는 반드시 true. 실제 확인 자료만 false |
| is_green | 아니오 | 기존 녹지 시설이면 true로 제외 |
| address | 아니오 | 주소 |
| impervious_ratio | 아니오 | 확인된 0~1 비율 또는 null |
| feasibility_score | 아니오 | 합의된 평가 근거가 있는 0~1 값 또는 null |

### DB 없이 실제 파일 사용

```bash
export IDLE_SITES_FILE='/absolute/path/real_sites.geojson'
python -m uvicorn main:app --reload --port 8001
```

추천 요청에서 `sites`를 생략합니다. 이 방식도 실제 경계가 있으면 실제 공간 교차를 수행합니다. **PostGIS가 없다고 공간 교차 자체가 불가능한 것은 아닙니다.**

저장한 녹지 부족 응답과 시설 파일을 하나의 요청으로 합치려면:

```bash
python prepare_request.py \
  --analysis examples/real_region_analysis.json \
  --sites /absolute/path/real_sites.geojson \
  --out recommend_request.json
```

제공된 격자 파일을 함께 쓰려면 `pip install geopandas` 후 `--grid-gpkg /absolute/path/green-deficit/output/grid_index.gpkg`를 추가합니다. 원본 `grid` 레이어의 `cell_id`와 `deficit_index`를 읽어 교차하는 격자만 요청에 넣습니다. 제공 폴더의 실제 파일로 이 변환을 검증했습니다.

### PostGIS 사용

```bash
pip install -r requirements-postgis.txt
export DATABASE_URL='postgresql://user:password@localhost:5432/regreen'
psql "$DATABASE_URL" -f sql/schema.sql
python import_sites.py /absolute/path/real_sites.geojson
```

기존 같은 이름의 테이블이 있다면 스키마를 먼저 비교하세요. `CREATE TABLE IF NOT EXISTS`는 기존 스키마를 변경하지 않습니다. import는 기존 site_id와 충돌하면 실패하며 덮어쓰지 않습니다. 하나의 트랜잭션이므로 실패 시 일괄 롤백됩니다. 실제 DB 연결은 이번 작업 환경에서 검증하지 않았습니다.

DB는 시설 조회만 담당하고 교차·면적·점수는 파일 방식과 동일한 Python 로직을 사용합니다. 따라서 `urban_grid`, `parks` 테이블을 별도로 만들지 않아도 됩니다. 큰 데이터에서는 계산을 PostGIS로 옮기는 추가 최적화가 필요합니다.

## 5. 파일별 역할

| 파일 | 역할 |
|---|---|
| main.py | FastAPI 경로, 오류 처리, CORS |
| schemas.py | 입력 필드·숫자·좌표 검증 |
| spatial.py | 좌표 변환, 폴리곤 검증, 면적 계산 |
| service.py | 교차 추출, 점수, ID, 선택, editable 전달 |
| repository.py | 파일 또는 PostGIS 입력 |
| prepare_request.py | 실제 분석 응답·시설·격자를 요청 JSON으로 준비 |
| import_sites.py | 실제 시설 GeoJSON을 PostGIS에 적재 |
| demo_flow.py | 실행 중인 API를 HTTP로 테스트하고 결과 저장 |
| examples/ | 요청·응답·후보지·가상 editable·실제 지역 분석 예시 |
| tests/ | 자동 검증 |
| sql/schema.sql | 선택적 PostGIS 테이블 |
