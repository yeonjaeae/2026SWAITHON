
# Re:Green AI API

AI 기반 도시 녹지 분석 및 공간 분할 서버

## 주요 기능

- `POST /ai/landcover`
  - Mask2Former 기반 녹지 후보 분석
  - 도로·건물 GIS 데이터를 활용한 녹지 후보 보정
  - green / road / residential GeoJSON 반환

- `POST /ai/segment`
  - SAM2 기반 사용자 선택 영역 분할
  - GeoJSON 반환 (검토 필요)

- `GET /health`
  - 서버 상태 확인

## 실행 방법

Python 3.11 권장

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Swagger API 문서:
http://127.0.0.1:8000/docs

## API 입력

### /ai/landcover

multipart/form-data

필수:
- image: 항공사진
- world_file: 좌표 정보 파일
- region: 분석 영역 GeoJSON 문자열 (EPSG:4326)

선택:
- roads: 도로 Polygon GeoJSON 문자열
- buildings: 건물 Polygon GeoJSON 문자열
- residential: 주거용 토지이용 Polygon GeoJSON 문자열

현재 World File 좌표계는 EPSG:3857 기준.

### /ai/segment

multipart/form-data

필수:
- image
- world_file
- region

## 주의사항

- 모델은 최초 실행 시 Hugging Face에서 다운로드합니다.
- 녹지 클래스 [1, 4]는 잠정 매핑입니다.
- 녹지와 SAM2 분할 결과는 검토용 후보입니다.
- 도로·건물 데이터를 전달하지 않으면 녹지 보정이 적용되지 않습니다.
- 주거지역 GIS를 전달하지 않으면 빈 MultiPolygon을 반환합니다.
- 로컬 테스트는 숙명여대 주변 항공사진을 사용했습니다.
- 다른 지역의 정확도 및 실제 배포 환경은 추가 검증이 필요합니다.
```
