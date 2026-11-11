# Re:Green 후보지 추천 API v2.0

제공된 `ai/main.py`의 실제 계약에 맞춰 개선한 API입니다. **한국의 실제 시설 경계·지역 분석 결과·지리참조 항공사진을 입력받는 구조**이며, 토지피복을 실제 시공 허가 또는 editable로 간주하지 않습니다.

핵심 변경과 제약은 `CHANGELOG.md`, AI 구현 검토는 `AI_INTEGRATION.md`, 검증 기록은 `VALIDATION.md`에 있습니다.

## 1. 무엇이 연결되는가

```text
항공사진 + 월드파일 + 분석영역
 → 이 API /integrations/ai/landcover
 → 팀 AI /ai/landcover (이미 구현된 모델 서버)
 → properties.class FeatureCollection을 landcover 배열로 정리
 → 동희 API /api/region/analyze (프론트/통합 서버가 호출)
 → 이 API /recommendations/from-region-analysis + 실제 시설 경계
 → 추천 결과 서버 저장, recommendation_id 발급
 → /recommendations/select
 → 별도 AI/사람이 editable 검토
 → /recommendations/design-handoff
 → 환경 효과 API (프론트/통합 서버가 호출)
```

팀 AI는 green/road/residential을 반환하지만 **editable은 반환하지 않습니다.** 이 버전도 임의로 빈 공간 전체를 editable로 확정하지 않습니다. 실제 시설 경계 데이터 역시 별도로 필요합니다. AI에 들어 있는 `residential.geojson`은 서울 일대 지정 주거지역 자료로, 개별 주차장·운동장 경계가 아닙니다.

## 2. 설치 및 개발 실행

Python 3.11 이상. 이번 검증은 Python 3.15/macOS arm64에서 수행했습니다.

```bash
cd candidate-recommender
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export AI_BASE_URL=http://127.0.0.1:8003
python -m uvicorn main:app --reload --port 8001
```

문서: http://127.0.0.1:8001/docs

- 녹지 부족 API: 예시 포트 8000
- 후보지 API: 8001
- 환경 효과 API: 8002
- AI API: 예시 포트 8003. AI 폴더의 별도 환경에서 실행해야 합니다.

이 프로젝트가 torch나 AI 가중치를 설치하거나 실행하지는 않습니다. AI 서버가 따로 준비되어 있어야 실제 영상 분석을 호출할 수 있습니다. 현재 AI 코드가 `residential.geojson`을 현재 작업 폴더에서 읽으므로, AI 서버는 `ai/` 폴더에서 실행해야 합니다.

기본 `.env.example`은 설명용입니다. 자동으로 읽지 않으므로 필요한 값을 터미널이나 배포 환경에 설정하세요.

## 3. DB 없이 데모 확인

서버가 실행 중인 상태에서 새 터미널로 같은 폴더를 열어 실행합니다.

```bash
source .venv/bin/activate
python demo_flow.py
```

`demo_output/`에 추천·선택·가상 editable·환경 효과 요청 파일을 저장합니다. 서버가 발급한 recommendation_id를 사용합니다.

후보지·editable은 모두 가상 데이터입니다. 데모의 `review_status=reviewed`는 **예시 흐름을 위한 값**이며 실제 검토 결과가 아닙니다. 운영 모드에서는 데모 API와 `is_demo=true` 시설을 거부합니다. 운영 서버에 이 값을 허위로 바꾸어 넣으면 안 됩니다.

## 4. API 목록

| 메서드/경로 | 내용 |
|---|---|
| GET `/health`, `/api/health` | 서버 생존 상태 |
| GET `/ready` | 인증 설정·추천 저장소 확인. AI·시설 DB 실제 가용성까지 보증하지 않음 |
| POST `/data/normalize` | 명시한 원본 CRS → EPSG:4326. 선택적 경계 복구 |
| POST `/integrations/ai/normalize-landcover` | 이미 받은 AI FeatureCollection을 팀 공통 형식으로 변환 |
| POST `/integrations/ai/landcover` | 파일을 검증한 뒤 실제 AI 서버로 multipart 요청 |
| POST `/recommendations/from-region-analysis` | 실제 시설과 필요 구역 교차·추천·서버 저장 |
| GET `/recommendations/demo` | 개발 모드의 가상 추천 |
| POST `/recommendations/select` | 저장된 추천에서 후보지 선택 |
| POST `/recommendations/design-handoff` | 검토 완료 editable을 환경 효과 요청으로 변환 |

## 5. AI 연동

### 실제 항공사진 호출

```bash
curl -X POST http://127.0.0.1:8001/integrations/ai/landcover \
  -F image=@aerial.png \
  -F world_file=@aerial.pgw \
  -F image_crs=EPSG:3857 \
  -F 'region=<region.geojson'
```

`region.geojson`은 EPSG:4326 Polygon/MultiPolygon 또는 Feature입니다. 경도·위도 순서입니다. 파일은 실제 사진과 정확히 대응해야 합니다.

현재 팀 AI는 영상 좌표계를 **EPSG:3857로 고정**합니다. EPSG:5179·5186 등의 다른 영상은 월드파일 숫자나 좌표계 이름만 바꾸면 안 됩니다. GIS 도구로 **영상 자체를 재투영하고 대응하는 월드파일을 새로 생성**한 뒤 사용하세요. 현재 프록시는 다른 영상 CRS를 422로 거부합니다.

월드파일은 A,D,B,E,C,F 6개 수이고 C,F는 왼쪽 위 픽셀 중심입니다. 프록시는 -0.5 픽셀부터 영상 외곽을 계산해 회전·기울어진 영상도 검사하며, 분석 영역 전체가 영상 안에 있어야 합니다. 파일이 올바르다는 사실만으로 촬영 위치·시점·정확성까지 증명되지는 않습니다.

### AI 반환값 처리

실제 AI 응답 형식:

```json
{"type":"FeatureCollection","features":[]}
```

각 feature는 `properties.class`가 green/road/residential이고 Polygon/MultiPolygon geometry를 가집니다. 빈 features도 가능하며, 빈 결과를 실패한 지역의 실제 무녹지 상태라고 해석하지 않습니다.

어댑터의 응답:

- `landcover`: `[{"class":"green","geometry":...}, ...]`
- `deficit_request`: 동희 API에 보낼 `{region, landcover}`
- `coverage_ratio`: 세 분류 도형의 합집합 / 분석 영역. 모델 정확도나 데이터 완전성이 아님
- `cross_class_overlap_m2`: 분류 간 중복 면적의 합계 초과분
- `class_precedence`: green → road → residential
- `editable_status`: 항상 `not_provided_by_ai`
- 영상 업로드 경로에서는 `image_metadata`도 반환

실제 AI는 모델 녹지, OSM 도로, 주거지역 자료를 각각 합치므로 서로 겹칠 수 있습니다. 후속 API의 면적 비율이 중복 계산되지 않도록 green > road > residential 우선순위로 겹치는 부분을 제거합니다. 이는 프로젝트 연동 정책이며 정답 분류를 보증하지 않습니다.

이미 AI 응답을 받았다면 `/integrations/ai/normalize-landcover`에 `region`과 `feature_collection`을 보내세요. `examples/ai_normalize_request.json`은 **가상** 도형으로 만든 실행 예시입니다.

## 6. 실제 시설 데이터 준비

필요 자료는 점 좌표나 주소가 아닌 **개별 시설의 면 경계**입니다. 주차장·학교 부지 전체와 실제 사용 가능한 외부공간은 다를 수 있으므로 정확한 경계를 제공해야 합니다.

각 시설의 입력 항목:

| 항목 | 설명 |
|---|---|
| site_id | 원본 자료의 안정적 문자열 ID |
| name | 시설명 |
| site_type | parking_lot / schoolyard / public_plaza / public_rooftop 등 |
| source | 제공 기관·자료명·갱신일·원본 ID·공유 조건 등 출처 |
| geometry | EPSG:4326 Polygon/MultiPolygon |
| is_demo | 실제 자료는 false, 예시는 true |
| is_green | 기존 녹지로 확인된 시설이면 true |
| impervious_ratio | 확인된 불투수율 0~1. 모르면 null |
| feasibility_score | 근거가 있는 평가 값 0~1. 모르면 null |

### GeoPackage·Shapefile·GeoJSON 준비 도구

```bash
pip install -r requirements-data.txt
python prepare_sites.py facilities.gpkg \
  --layer parking \
  --id-field FACILITY_ID \
  --name-field FACILITY_NAME \
  --site-type parking_lot \
  --source '제공기관 / 자료명 / 갱신일 / 공유조건' \
  --out data/real_sites.geojson
```

필드명과 레이어는 실제 자료에 맞게 바꾸세요. 한 파일에 여러 시설 유형이 있으면 `--site-type` 대신 표준 유형 값이 들어 있는 `--type-field`를 사용합니다.

- 파일의 CRS를 읽고 EPSG:4326으로 변환합니다.
- CRS가 없는 자료에는 확인된 `--source-crs EPSG:5186` 등을 넣습니다.
- 파일의 CRS와 지정한 CRS가 다르면 오류입니다. 추측해 지정하면 안 됩니다.
- 중복 ID, 점 자료, 빈 geometry, 없는 필수 속성은 오류입니다.
- `--repair`를 명시해야 잘못된 도형을 복구하며, 옆에 `.report.json`을 저장합니다.
- 복구한 도형은 원본과 비교해야 합니다. 자동 복구는 실제 경계의 진실성을 증명하지 않습니다.
- 변환 도구의 `is_green=false`와 null 평가 항목은 초기 입력값입니다. 시설 현황에 맞게 검토·보완하세요.

API로 같은 변환을 하려면 `/data/normalize`에 `geojson`, `source_crs`, 선택적 `repair`를 입력합니다. **지원 지역은 한국 범위(경도 124~132, 위도 33~39.5)**이며, 한국 안에서도 팀의 실제 데이터 커버리지가 있는 곳에서만 전체 분석이 가능합니다. 현재 녹지 부족 격자와 AI 주거지역은 서울 기반입니다.

### 파일 또는 PostGIS 연결

```bash
export IDLE_SITES_FILE=/absolute/path/data/real_sites.geojson
export IDLE_SITES_CRS=EPSG:4326
```

요청의 `sites`를 생략하면 파일을 읽습니다. 파일 설정이 없으면 DATABASE_URL의 PostGIS를 조회합니다. 실제 DB 경로는 `requirements-postgis.txt`, `sql/schema.sql`, `import_sites.py`를 사용합니다. v1과 같은 테이블 구조이며 이번 환경에서 실서버 연결은 수행하지 않았습니다.

`sites: []`는 명시적 빈 목록입니다. 누락된 데이터베이스를 가상 데이터로 대체하지 않습니다. 시설 자료의 출처·정확성·완전성을 API가 자동 검증할 수 없으므로 `facility_inventory_completeness: not_verified`를 반환합니다.

## 7. 추천 요청

`/recommendations/from-region-analysis`:

- `region_analysis`: 동희 API 응답 전체. candidates=null이면 정상 0개
- `sites`: 선택 입력. 생략하면 설정한 실제 파일/DB 사용
- `grids`: 선택 입력. `{grid_id, geometry, deficit_index}` 배열
- `landcover`: 정리된 토지피복 배열
- `ai_landcover`: AI 원본 FeatureCollection. landcover와 둘 중 하나만 사용
- `protected_geometries`: 보존할 건물·출입구·보행로·수역 등의 **확인된** 도형 배열
- `min_area_m2`: 기본 80㎡
- `limit`: 기본 10, 최대 100

후보지 = 시설 ∩ 필요 구역 − 기존 녹지 − 명시된 보존 도형입니다. 도로 전체를 자동 제외하지 않으며, 실제 도로 보호가 필요하면 확인된 protected_geometries를 입력하세요. residential을 시설/건물/불투수율로 자동 변환하지 않습니다.

같은 시설 ID가 중복되면 오류이고, 서로 다른 ID의 후보지가 겹치면 `overlap_with_candidate_ids`로 알려줍니다. 시설이 다른지 동일 시설의 중복인지 자동 판단하지 않으므로 면적을 단순 합산하면 안 됩니다.

면적은 EPSG:5179의 **수평 투영면적**입니다. 경사면의 표면적·토질·배수·지반 안정성을 계산하지 않습니다. 이런 실제 지형 적합성은 DEM/DSM·경사·지반·시설물 자료와 별도 평가가 필요합니다.

점수는 v1과 같은 녹지 부족도 45%, 면적 25%, 불투수율 20%, 실현 가능성 10%입니다. 없는 항목을 임의 생성하지 않으며 나머지 가중치로 재정규화합니다. `score_data_coverage`는 사용한 가중치 합이지 확률이나 신뢰도가 아닙니다. 격자 교차는 공간 인덱스로 검색하고 면적 가중평균합니다. 추천 사유는 규칙 기반입니다.

## 8. 서버 저장 결과 선택

추천 응답에는 `recommendation_id`와 `expires_at_unix`가 추가됩니다.

```json
{
  "recommendation_id": "추천 응답에서 받은 ID",
  "candidate_id": "선택한 recommendations 항목의 candidate_id"
}
```

위 내용을 `/recommendations/select`에 보냅니다. 서버 SQLite에 저장한 경계에서 선택하므로 사용자가 geometry·면적을 바꾸어 다시 보내지 않습니다. 기본 만료 기간은 24시간이고 만료되면 404와 함께 재추천을 요구합니다. 후보지의 `site_id`는 원본 시설 ID, `candidate_id`는 시설 ID와 교차 경계를 반영한 ID입니다.

v1의 `{candidate_id, recommendations}` 방식은 개발 모드에서만 지원합니다. `examples/select_request.json`도 개발 전용 이전 방식 예시입니다. 운영에서는 recommendation_id를 사용해야 합니다.

## 9. editable과 환경 효과 연결

권장 요청 형식:

```json
{
  "recommendation_id": "추천 응답 ID",
  "candidate_id": "선택 후보지 ID",
  "editable": {
    "candidate_id": "같은 후보지 ID",
    "geometry_crs": "EPSG:4326",
    "editable_geometry": null,
    "source": "검토자 또는 별도 분석 실행 ID",
    "review_status": "reviewed"
  },
  "protected_geometries": [],
  "green_ratio": 40,
  "vegetation": {"grass":50,"shrub":30,"tree":20}
}
```

null은 **검토 결과 편집 가능 공간이 없음**을 의미합니다. 분석 미완료라면 review_status를 pending으로 유지하고 요청을 보내지 마세요. pending 또는 누락 상태는 409로 차단합니다. 검토 여부는 신뢰하는 통합 서버가 확인해야 하며 이 문자열만으로 실제 검토가 인증되는 것은 아닙니다.

- 후보지·editable ID가 일치해야 함
- 후보지 밖 editable은 잘림
- 추가 보존 도형을 제외함
- 면적이 있으면 `/api/design/spatial`의 payload 생성
- 0㎡이면 `/api/design/from-candidate`에 전부 보존 면적으로 전달
- 환경 효과 서버는 자동 호출하지 않음

v1의 candidate 객체 직접 전달 방식은 개발 모드만 허용합니다. 개발 예시 `handoff_request.json`은 가상 검토 상태입니다.

## 10. 운영 설정과 한계

```bash
export APP_ENV=production
export SERVICE_API_KEY='실제 배포용으로 생성한 32자 이상의 무작위 비밀값'
export RECOMMENDATION_DB=/persistent-volume/recommendations.sqlite3
export RECOMMENDATION_TTL_SECONDS=86400
export AI_BASE_URL=http://ai-service:8003
export IDLE_SITES_FILE=/data/real_sites.geojson
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --limit-concurrency 16
```

`--reload`는 운영에서 사용하지 않습니다. 키는 비밀 저장소로 관리하고 **브라우저 코드에 넣지 마세요.** 프론트 → 로그인/권한을 관리하는 팀 통합 서버 → 이 API 구조를 사용하세요. 이 패키지의 Bearer 키는 신뢰하는 서버 사이 인증이며 사용자별 로그인·권한 분리 기능은 아닙니다.

운영 호출에는 `Authorization: Bearer <SERVICE_API_KEY>`가 필요합니다. 공개 생존 확인 경로만 예외입니다. 키가 없거나 너무 짧으면 운영 앱 기동을 거부합니다. CORS만으로 인증을 대체하지 않습니다.

SQLite 저장소는 영구 디스크가 있는 **단일 호스트**용입니다. 같은 호스트의 프로세스 재시작·WAL 동시 접근은 지원하지만 여러 호스트/서버리스의 로컬 파일은 서로 공유되지 않습니다. 여러 서버로 배포하려면 PostgreSQL/Redis 같은 공유 저장소로 교체하세요.

제한:

- 요청 본문 24MB, 도형 하나 100,000개 좌표
- 한 요청 시설/격자 5,000개, 분석 면적 25㎢
- 시설 파일 50MB. 대규모 자료는 지역 분할 또는 PostGIS 사용
- 영상 PNG/JPEG, 20MB, 1,600만 픽셀
- 월드파일 1KB, 현재 영상 CRS는 EPSG:3857만
- AI 연결 5초, 분석/응답 수신 전체 120초, 응답 10MB
- AI 동시 요청은 후보지 API 프로세스당 2개. 추가 요청은 429
- 활성 추천 저장 최대 10,000건. 만료 데이터는 새 추천 저장 시 정리

대규모 트래픽의 부하 테스트, HTTPS·프록시 요청 속도 제한, 사용자 인증, 실제 AI GPU 준비는 배포 환경에서 별도로 완료해야 합니다.

## 11. 검증

```bash
pip install -r requirements-dev.txt
TEAM_REPO=/absolute/path/2026SWAITHON-main python -m pytest -q
```

TEAM_REPO가 없으면 팀원 원본에 의존하는 테스트만 skip됩니다. 원본 AI endpoint를 사용하는 테스트도 **모델·OSM 조회는 대체하여 계약만 검사**합니다. 실제 항공사진 모델 추론·정확도 테스트가 아닙니다.

`VALIDATION.md`, `REAL_DATA_AUDIT.json`에 실행한 검증과 미검증 항목을 기록했습니다. 포함된 실제 자료 검사 결과를 시설 후보지나 검증된 editable로 해석하면 안 됩니다.

## 12. GitHub 적용

기존 `candidate-recommender/`의 소스와 문서를 이 폴더로 교체하세요. 사용자 `.env`, 실제 시설 자료, 운영 SQLite 파일은 덮어쓰거나 커밋하지 마세요. 의존성을 다시 설치하고 프론트/통합 서버의 선택 요청을 recommendation_id 방식으로 변경합니다.

팀원 원본 `ai/`, `green-deficit/`, `green-design-backend/`는 이번 작업에서 수정하지 않았습니다. 원격 GitHub 업로드·PR·배포 역시 수행하지 않았습니다.
