# 백엔드 배포 (Docker Compose)

백엔드 3개를 한 서버에 띄우고, Nginx 가 하나의 주소에서 경로별로 나눠 준다. **AI 토지 피복 서버(`ai/`)는 제외** (torch 등 수 GB, 메모리 8GB 이상 필요).

```
http://서버주소:8080
 ├─ /deficit/    → 녹지 부족지수   (green-deficit)
 ├─ /candidate/  → 후보지 추천     (candidate-recommender-v2)
 └─ /design/     → 녹지 설계       (green-design-backend)
```

| 서비스 | API 문서 | 예: 원래 주소 → 배포 주소 |
|---|---|---|
| 녹지 부족지수 | `/deficit/docs` | `POST /api/region/analyze` → `POST /deficit/api/region/analyze` |
| 후보지 추천 | `/candidate/docs` | `POST /recommendations/select` → `POST /candidate/recommendations/select` |
| 녹지 설계 | `/design/docs` | `POST /api/design/calculate` → `POST /design/api/design/calculate` |

프론트는 **원래 경로 앞에 `/deficit`, `/candidate`, `/design` 만 붙이면** 된다.

## 파일

```
docker-compose.yml            서비스 4개(백엔드 3 + nginx) 정의
deploy/nginx.conf             경로별 분배
deploy/deficit.Dockerfile     녹지 부족지수 이미지
deploy/requirements-deficit.txt
deploy/candidate.Dockerfile   후보지 추천 이미지
deploy/design.Dockerfile      녹지 설계 이미지 (폴더에 requirements.txt 가 없어 패키지를 여기 적음)
.dockerignore
```

각 팀원 폴더의 코드는 건드리지 않는다. 코드가 바뀌면 다시 빌드만 하면 된다.

## 로컬에서 실행

Docker Desktop 을 켠 뒤 레포 루트에서:

```bash
docker compose up -d --build
```

→ http://localhost:8080 (첫 빌드는 몇 분 걸림)

```bash
docker compose ps          # 상태 (healthy 이면 정상)
docker compose logs -f     # 로그
docker compose down        # 끄기
```

## 클라우드 서버에 올리기

어느 리눅스 서버(AWS EC2·Lightsail, GCP, 네이버 클라우드 등)든 같다. 권장 사양: **메모리 2GB 이상**, 디스크 10GB 이상.

1. 서버에 Docker 설치 (Ubuntu 기준)
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
2. 레포 받기
   ```bash
   git clone https://github.com/yeonjaeae/2026SWAITHON.git && cd 2026SWAITHON
   ```
3. 80번 포트로 띄우기
   ```bash
   PORT=80 docker compose up -d --build
   ```
4. 서버 방화벽(보안 그룹)에서 **80 포트(HTTP) 열기**
5. `http://서버IP/` 접속 → API 문서 3개 링크가 보이면 성공

코드 업데이트 후 반영:

```bash
git pull && PORT=80 docker compose up -d --build
```

## 설정 (환경 변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `8080` | 외부에 여는 포트. 서버에서는 `80` |
| `CORS_ORIGINS` | `*` | 후보지 추천 API 가 허용할 프론트 주소 (쉼표로 구분). 배포 후에는 실제 프론트 주소로 좁히는 것을 권장 |

후보지 추천의 추천 결과(SQLite)는 `candidate-data` 볼륨에 저장되어 컨테이너를 다시 만들어도 유지된다.

## 알아둘 점

- 녹지 부족지수는 레포의 `green-deficit/output/` 분석 결과를 그대로 쓴다. 분석을 다시 돌렸다면 커밋 후 다시 빌드.
- AI 서버를 나중에 붙이려면 `docker-compose.yml` 에 서비스를 하나 더 추가하고 nginx 에 `/ai/` 경로를 추가하면 된다. 후보지 추천의 AI 연동은 `AI_BASE_URL` 환경 변수로 주소를 넘긴다.
