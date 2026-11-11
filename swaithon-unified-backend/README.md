# SWAITHON 통합 백엔드 — 프론트 포트 8080

프론트는 **http://localhost:8080** 하나만 사용합니다. AI·녹지 부족 분석·후보지 추천·환경 효과 계산은 내부에서 분리 실행하고 공통 FastAPI 서버가 연결합니다. 모델 라이브러리와 모듈 이름 충돌 없이 기존 코드를 유지하는 구조입니다.

```text
프론트(3000 또는 5173)
       │ http://localhost:8080/api/...
       ▼
통합 Gateway (공개 포트 하나)
       ├─ 녹지 부족 분석
       ├─ 후보지 추천 ── AI 토지피복 분석
       └─ 환경 효과 계산
```

Docker 실행에서는 **gateway만 호스트에 포트를 공개**합니다. 다른 네 서비스는 내부 네트워크의 서비스 이름으로 통신합니다. [Docker Compose 공식 네트워크 설명](https://docs.docker.com/compose/how-tos/networking/)

## 1. 권장 실행 — Docker Compose

Docker Desktop/Compose가 설치되어 실행 중이어야 합니다. 프로젝트 최상위에서:

```bash
python3 setup_env.py
docker compose up --build -d
```

- API 문서: http://localhost:8080/docs
- 서버 생존 확인: http://localhost:8080/api/health
- 네 백엔드 상태: http://localhost:8080/api/status

처음에는 Python·GIS·AI 라이브러리 설치에 시간이 걸립니다. AI 가중치는 첫 분석 요청에서 내려받으므로 별도 시간이 걸릴 수 있습니다. 기본 AI 컨테이너는 CPU 실행이며 GPU 설정은 포함하지 않았습니다.

```bash
docker compose logs -f gateway candidate deficit design ai
docker compose down
```

`docker compose down`은 영구 볼륨의 추천 결과·모델 캐시를 보존합니다. `down -v`는 해당 볼륨을 지우므로 초기화할 때만 사용하세요.

`.env`는 setup_env.py가 생성합니다. 내부 후보지 API 키를 자동 생성하되 출력하지 않고, 기존 .env는 덮어쓰지 않습니다. 기본은 로컬 개발 모드입니다.

## 2. 프론트가 호출할 주소

| 기능 | 메서드 | 통합 경로 |
|---|---|---|
| AI 사진 분석 | POST | `/api/ai/landcover` |
| AI 결과 형식 변환 | POST | `/api/ai/normalize-landcover` |
| 좌표계·도형 정규화 | POST | `/api/data/normalize` |
| 지역 녹지 부족 분석 | POST | `/api/region/analyze` |
| 후보지 추천 | POST | `/api/recommendations/from-region-analysis` |
| 가상 후보지 데모 | GET | `/api/recommendations/demo` |
| 후보지 선택 | POST | `/api/recommendations/select` |
| editable → 설계 요청 생성 | POST | `/api/recommendations/design-handoff` |
| 후보지 수신 | POST | `/api/design/candidate` |
| 수치 기반 효과 계산 | POST | `/api/design/calculate` |
| 후보지 기반 효과 계산 | POST | `/api/design/from-candidate` |
| editable 기반 효과 계산 | POST | `/api/design/spatial` |
| **지역 분석 + 후보지 추천** | POST | **`/api/workflows/recommend`** |
| **editable 확인 + 환경 효과 계산** | POST | **`/api/workflows/design`** |

프론트에는 내부 서비스 키나 내부 포트가 필요하지 않습니다. CORS는 통합 서버에서 처리하며, 기본 허용 주소는 localhost/127.0.0.1의 3000·5173 포트입니다. 다른 프론트 주소는 `.env`의 `CORS_ORIGINS`를 변경하고 gateway를 다시 시작하세요.

원본의 `/health`, `/api/health`, `main.py`가 서로 충돌하지 않습니다. 각 서비스가 독립 프로세스/컨테이너에서 실행됩니다. `/docs`에는 실제 백엔드에서 추출한 요청 스키마를 이름 충돌 없이 합쳤습니다.

## 3. 프론트 연결 모듈

`frontend/api.mjs`를 프론트 프로젝트에 복사해 사용하세요. 기존 프론트 구현은 이번에 제공되지 않았으므로 실제 화면 코드를 수정하지는 않았습니다.

```javascript
import { createSwaithonApi } from './api.mjs';

// Vite 사용 시 .env.local에 VITE_API_BASE_URL=http://localhost:8080
const api = createSwaithonApi(import.meta.env.VITE_API_BASE_URL);
```

Vite가 아니면 `createSwaithonApi('http://localhost:8080')`처럼 직접 설정하면 됩니다. 배포 시 localhost는 사용자의 컴퓨터를 의미하므로 실제 통합 서버 주소 또는 동일 출처 주소로 변경하세요.

### A. 항공사진 분석

```javascript
const ai = await api.analyzeImage({
  image: imageFile,
  worldFile: pgwFile,
  region: regionGeoJSON,
  imageCrs: 'EPSG:3857',
});
```

이 경로는 후보지 v2의 영상 검증 어댑터를 거쳐 실제 AI `/ai/landcover`를 호출합니다. 입력 파일을 중간에 임의 변환하지 않습니다. multipart `Content-Type`은 브라우저가 boundary와 함께 설정하도록 둡니다.

현재 AI는 EPSG:3857 영상과 대응하는 월드파일이 필요합니다. `ai.deficit_request`가 다음 단계의 `{region, landcover}` 입력입니다. AI는 editable을 반환하지 않습니다.

### B. 지역 분석과 추천을 한 번에

```javascript
const result = await api.recommend({
  analysis: ai.deficit_request,
  options: {
    sites: realSites,
    min_area_m2: 80,
    limit: 10,
  },
});
const { recommendation_id, recommendations } = result.recommendation;
```

항공사진 없이도 다음처럼 지역 분석을 시작할 수 있습니다.

```javascript
const result = await api.recommend({
  analysis: {
    sw: { lat: 37.5440, lng: 126.9615 },
    ne: { lat: 37.5485, lng: 126.9680 },
  },
  options: { sites: realSites },
});
```

- `analysis`: 기존 녹지 부족 API 요청
- `options`: 후보지 API 옵션. region_analysis는 게이트웨이가 생성하므로 넣지 않습니다.
- `analysis.landcover`는 별도 지정하지 않으면 추천 단계에도 전달합니다.
- 시설 파일/DB를 설정했다면 options의 sites를 생략할 수 있습니다.
- `sites: []`는 명시적 빈 목록이므로 추천 결과도 0개입니다.
- 첫 단계가 실패하면 후보지 API는 호출하지 않습니다. 중간 오류를 성공으로 바꾸지 않습니다.

### C. 후보지 선택

```javascript
if (recommendations.length === 0) {
  // 화면에 '이 자료와 조건에서 추천 후보지가 없습니다' 표시
} else {
  const candidate = await api.select(
    recommendation_id,
    recommendations[0].candidate_id,
  );
  // candidate.feature.geometry를 지도/AI 검토 단계로 전달
}
```

추천 스냅샷이 만료되면 404입니다. 재추천 후 새 ID를 사용하세요.

### D. editable 검토 후 효과 계산까지

```javascript
const result = await api.calculateDesign({
  recommendation_id,
  candidate_id: selectedCandidateId,
  editable: {
    candidate_id: selectedCandidateId,
    geometry_crs: 'EPSG:4326',
    editable_geometry: reviewedEditableGeometry,
    source: editableReviewSource,
    review_status: 'reviewed',
  },
  protected_geometries: [],
  green_ratio: 40,
  vegetation: { grass: 50, shrub: 30, tree: 20 },
});
// result.handoff: 적용한 editable 및 면적
// result.design: 실제 환경 효과 API 계산 결과
```

게이트웨이가 후보지 API의 handoff를 먼저 호출하고, 검증된 payload를 환경 효과 API에 전달합니다. editable이 0㎡이면 후보지 API가 지정한 from-candidate 경로로 연결합니다. 임의의 URL을 받아 전달하지 않습니다.

검토 전에는 `review_status: 'pending'`이며 409로 차단됩니다. 이 예시의 reviewed를 실제 검토 없이 복사해 적용하면 안 됩니다. 토지피복 결과를 editable로 확정하지 않습니다.

### 오류 처리

```javascript
try {
  const result = await api.select(recommendationId, candidateId);
} catch (error) {
  console.error(error.status, error.detail);
  // 404: 만료/없는 후보지, 409: editable 검토 미완료
  // 422: 입력 오류, 502: 백엔드 연결/응답 오류, 504: 시간 초과
}
```

기존 백엔드의 오류 상태와 JSON 본문을 보존합니다. 게이트웨이에서 연결에 실패하면 서비스 이름과 502/504를 반환합니다.

## 4. 실제 시설 데이터

기존 후보지 API의 데이터 준비·정규화·PostGIS 기능을 그대로 사용합니다. `candidate-recommender-v2/README.md`를 참고하세요.

Docker의 로컬 파일 사용 예:

1. 실제 시설 GeoJSON을 프로젝트의 `datasets/real_sites.geojson`에 둡니다.
2. `.env`에 `IDLE_SITES_FILE=/datasets/real_sites.geojson`을 설정합니다.
3. `docker compose up -d candidate`로 설정을 반영합니다.

`/datasets/...`는 **컨테이너 안의 경로**입니다. 사용자 Mac의 절대 경로를 그대로 넣지 않습니다. datasets는 커밋 제외되어 있으며 자료의 출처·갱신일·공유 조건을 별도로 관리하세요.

제공된 demo/예제 시설과 editable은 가상 데이터입니다. 실제 녹지 부족 격자와 AI 주거지역 자료가 있다고 해서 실제 개별 시설 목록과 editable까지 준비된 것은 아닙니다.

## 5. Docker 없이 실행

통합/후보지/녹지 부족/설계용 Python 환경을 준비합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r gateway/requirements-deficit.txt \
            -r gateway/requirements-design.txt \
            -r candidate-recommender-v2/requirements-postgis.txt
```

AI는 Python 3.12 등 torch와 해당 transformers 버전이 지원하는 **별도 환경**을 권장합니다.

```bash
python run_local.py --ai-python /absolute/path/ai-env/bin/python
```

AI 환경에는 `ai/requirements.txt`를 설치해야 합니다. 도구가 ai/를 작업 폴더로 지정하므로 residential.geojson 경로도 맞습니다. Ctrl+C로 모든 자식 서버를 종료합니다. 어느 프로세스가 종료되면 전체를 정리하고 원인을 logs/에 남깁니다.

AI가 아직 준비되지 않았을 때 다른 연결만 테스트:

```bash
python run_local.py --without-ai
```

이 모드는 AI를 가짜 응답으로 대체하지 않습니다. 영상 분석은 사용할 수 없으며 `/api/status`는 AI unavailable을 포함한 503 degraded를 반환합니다.

로컬 모드는 내부 서비스를 127.0.0.1:8101~8104에 실행하고 프론트는 8080만 사용합니다. Docker 모드는 내부 서비스 포트를 호스트에 공개하지 않습니다. `run_local.py`는 Compose용 .env를 자동으로 읽지 않으므로 커스텀 설정은 환경변수로 전달하세요.

## 6. 운영 시 구분할 부분

이번 기본 설정은 팀 개발용이며 호스트 노출 주소는 127.0.0.1입니다. 네트워크 배포 시 HTTPS·사용자 인증·접근 제어를 별도로 연결해야 합니다.

- `APP_ENV=production`이면 GATEWAY_API_KEY와 SERVICE_API_KEY가 각각 32자 이상 필요합니다.
- SERVICE_API_KEY는 gateway→candidate 내부 인증이며 브라우저에 주지 않습니다.
- GATEWAY_API_KEY 역시 신뢰하는 인증/BFF 서버용입니다. 프론트에 고정 비밀키를 넣는 사용자 인증 방식은 아닙니다.
- 공개 사용자 서비스는 로그인/권한을 처리하는 서버를 gateway 앞에 연결하세요. 현재 사용자별 스냅샷 권한 분리는 포함되어 있지 않습니다.
- 저수준 `/api/design/*`는 기존 기능 호환용입니다. 후보지·editable 검증이 필요한 사용자 흐름에서는 `/api/workflows/design`을 사용하세요.
- AI 프로세스의 모델 다운로드·CPU/GPU 메모리·OSM 네트워크 상태는 별도로 관리해야 합니다.
- SQLite 추천 볼륨은 단일 호스트용입니다. 여러 호스트로 늘릴 때는 공유 저장소로 변경하세요.

## 7. 검증 및 스키마 갱신

```bash
pip install -r gateway/requirements-dev.txt
python -m pytest tests -q
```

실제 서비스 연동 테스트에는 위의 비-AI 실행 의존성도 설치되어 있어야 합니다. 결과는 `VALIDATION.md`를 참고하세요.

백엔드 입력 모델을 변경하면 다음으로 Swagger 계약을 갱신합니다.

```bash
python generate_contracts.py
```

세 비-AI 백엔드의 실제 OpenAPI를 각각 별도 프로세스로 읽습니다. AI 업로드 계약은 후보지 검증 어댑터의 실제 스키마를 사용하므로, 게이트웨이를 켤 때 torch를 import하지 않습니다.

## 8. 기존 저장소에 반영된 구조

기존 네 서비스 코드는 유지했고 아래를 추가했습니다.

- gateway/: 통합 서버와 합친 Swagger 스키마
- frontend/api.mjs: 프론트 요청 모듈
- compose.yaml / Dockerfile: 하나의 공개 포트로 실행
- run_local.py: 로컬 다중 프로세스 실행·종료
- setup_env.py: 개발 설정 생성
- generate_contracts.py: 문서 스키마 갱신
- tests/: 라우팅·오류·실제 서비스 연동 테스트

원본 저장소에서는 이 문서를 `README_UNIFIED.md`로도 제공합니다. GitHub 업로드/PR/외부 배포는 수행하지 않았습니다.
