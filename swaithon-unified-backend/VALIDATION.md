# 통합 백엔드 검증 기록

## 실행 완료

- 통합 자동 테스트 **37개 통과**.
- 공개 경로 12개를 올바른 내부 경로로 전달하는지 확인.
- 서버용 후보지 키 주입, 브라우저 Authorization의 내부 서비스 전달 방지.
- multipart 파일/필드/boundary를 유지하는 전달 검증.
- CORS preflight, 과대 입력, 유한하지 않은 숫자 입력 처리.
- backend 409/422 유지, 연결 실패 502, 시간 초과 504 검증.
- 분석→추천·handoff→환경 효과 단계 연결 및 첫 단계 실패 시 후속 호출 중단.
- handoff가 임의 외부 URL로 연결되지 않도록 경로 허용 목록 검증.
- 합친 OpenAPI의 참조 해석 및 실제 multipart 업로드 스키마 확인.
- Compose YAML 구조 검사: gateway만 단일 포트 공개, 내부 서비스 연결·볼륨·빌드 대상 확인.
- setup_env가 키를 출력하지 않고 기존 설정을 덮어쓰지 않으며 파일 권한 0600을 사용하는지 확인.
- **실제 제공된 후보지·녹지 부족·환경 효과 앱**을 연결한 테스트 수행.
- localhost의 실제 개별 서버 프로세스를 통합 주소 하나로 호출: demo→선택→환경 효과 계산 완료.
- 같은 통합 주소에서 실제 녹지 부족 격자 분석→빈 시설 추천 완료. 격자 42개 결과 확인.
- AI 제외 테스트에서 /api/status가 올바르게 503 degraded를 반환함을 확인.
- 프론트 JS 모듈의 요청 구성·multipart 필드·409 전달을 fetch/FormData 대체 객체로 단위 검증.
- 로컬 HTTP 검증 후 테스트 서버 모두 종료.

테스트 환경은 Python 3.15/macOS arm64입니다. 4개 deprecation 경고가 있었고 테스트 실패는 없었습니다. Compose 이미지 설정의 Python은 3.12입니다.

## 미검증 사항

- 이 환경에 Docker 명령이 없어 **Docker 이미지 빌드 및 Compose 전체 기동은 실행하지 않았습니다.** YAML/구조 검사만 수행했습니다.
- AI torch/모델 다운로드, 실제 항공사진 추론, GPU, OSM 실조회는 실행하지 않았습니다. AI 전달 경로와 기존 v2 검증 어댑터 연동 계약을 확인한 것이며 추론 성공 검증이 아닙니다.
- 프론트 프로젝트가 제공되지 않아 실제 화면을 연결하거나 브라우저 E2E 테스트를 하지는 않았습니다. 복사해 사용할 API 모듈과 호출 예시를 제공합니다.
- 실제 PostGIS 서버, 신규 시설 경계 데이터, 실제 editable, 공개 배포·사용자 인증·부하 테스트는 범위에 포함하지 않았습니다.

## 설계 근거

내부 서비스는 Compose 서비스명으로 통신하고 gateway만 ports를 게시합니다. [Docker Compose 네트워크](https://docs.docker.com/compose/how-tos/networking/)

Gateway는 HTTPX AsyncClient를 재사용하며 stream 컨텍스트 안에서 제한된 응답을 읽고 연결을 닫습니다. [HTTPX 비동기 클라이언트](https://www.python-httpx.org/async/)
