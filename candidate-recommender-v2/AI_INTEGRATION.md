# 첨부 AI 구현 검토 및 연결 계약

검토 대상: 제공된 `2026SWAITHON-main/ai/main.py`, `requirements.txt`, `residential.geojson`. 원본 해시는 `REAL_DATA_AUDIT.json`에 있습니다.

## 코드에서 확인한 실제 동작

- `POST /ai/landcover`
- multipart 필수 필드: image, world_file, region(JSON 문자열)
- `Mask2Former`의 `mfaytin/mask2former-satellite` 모델을 사용합니다. 메시지에 나온 SegFormer/SAM 구현으로 가정하지 않았습니다.
- green: 영상 모델에서 GREEN_IDS=[1,4]로 임시 매핑
- road: OSM highway와 유형별 폭/width 속성으로 선을 버퍼 처리
- residential: 로컬 residential.geojson의 지정 주거지역을 분석 영역으로 잘라 사용
- 결과: properties.class가 green/road/residential인 FeatureCollection
- editable 반환, candidate_id 반환, 건물·출입구 식별 기능은 없음
- 영상 world-file 좌표는 EPSG:3857로 고정, 면적/도로 버퍼는 5179

따라서 세 분류는 모두 영상에서 직접 예측한 결과가 아닙니다. 지정 주거지역을 실제 건물 밀집도, 불투수율, 편집 가능 공간으로 바꾸어 해석하지 않습니다.

## 실제 자료 검사

- 주거지역 Feature 6,874개
- 파일 범위: 경도 약 126.7986~127.1831, 위도 약 37.4337~37.6915 (서울 일대)
- 도형 유효성 오류 18개, 기본 정규화 통과 6,856개
- 명시적 make_valid 복구 후 오류 18개의 출력 도형 유효성 확인
- 좌표 범위는 bounding box이며, 그 사각형 전체를 자료가 빈틈없이 덮는다는 의미가 아님
- 이는 도형 형식 검사이며 원본 자료의 최신성·정확도·실제 시설/현황 여부 검증이 아님

원본 AI도 `buffer(0)`로 일부 잘못된 경계를 복구하지만, 그 복구가 실제 경계를 정확히 보존하는지는 별도 확인이 필요합니다. 후보지 API의 데이터 정규화는 복구 여부와 위치를 보고합니다.

## AI 담당자와 추가로 맞출 사항

1. GREEN_IDS의 모델 실제 라벨 의미를 확인하고 예시 영상에 대해 정확도를 검증해야 합니다.
2. 주거지역 데이터 커버리지·원본 출처·갱신 시점을 응답 메타데이터로 제공하면 데이터 없는 지역을 구분하기 쉽습니다.
3. OSM의 정상적인 빈 조회와 네트워크 장애를 구분해야 합니다. 후보지 프록시는 AI 오류를 502/504로 반환하며 가짜 성공 결과를 생성하지 않습니다.
4. residential 파일 경로를 `Path(__file__).parent` 기준으로 변경하면 실행 폴더에 덜 의존합니다. 현재 원본에서는 ai/ 폴더에서 서버를 실행해야 합니다.
5. editable은 별도 검토 단계가 필요합니다. 추가할 경우 candidate_id, geometry_crs, editable_geometry, source, review_status를 공유하면 됩니다. review_status는 실제 검토를 마친 뒤 통합 서버에서 설정하세요.
6. 현재 원본 green contour는 OpenCV 윤곽의 픽셀 중심 좌표와 면적 필터를 사용합니다. 매우 작은 객체·가장자리의 면적 오차는 실제 사진·정답 마스크로 별도 측정해야 합니다. 이번 작업은 모델 폴리곤의 정밀도를 검증하거나 변경하지 않았습니다.

## 좌표와 월드파일

월드파일은 공간참조 좌표계 자체를 담지 않습니다. 원본 영상 CRS를 별도로 알아야 합니다. 기존 AI가 3857로 가정하므로 프록시는 image_crs=EPSG:3857을 요구합니다. 실제 영상이 다른 CRS인데 이름만 바꾸는 것은 허용되는 변환이 아닙니다.

프록시의 영상 외곽 검사는 왼쪽 위 픽셀 중심에서 -0.5 픽셀 오프셋을 적용합니다. 회전·기울기 행렬과 외곽 변환을 이용해 분석영역이 영상 안에 있는지 검사합니다. 공간 좌표와 면적은 x/y 순서를 고정해 변환합니다.

기술 근거:

- [GDAL world file: 픽셀 중심과 6개 계수](https://gdal.org/en/stable/drivers/raster/wld.html)
- [GDAL geotransform: 픽셀 코너/중심 구분](https://gdal.org/en/stable/tutorials/geotransforms_tut.html)
- [pyproj Transformer: always_xy 좌표 순서](https://pyproj4.github.io/pyproj/latest/api/transformer.html)
- [Shapely make_valid: 복구 결과가 GeometryCollection일 수 있음](https://shapely.readthedocs.io/en/2.1.2/reference/shapely.make_valid.html)

## 검증 범위

원본 analyze_landcover 함수의 파일 입력·JSON 파싱·FeatureCollection 반환 계약은 원본 함수 코드로 테스트했습니다. 다만 green 예측/OSM/주거지역 조회는 대체 함수로 실행했습니다. GPU 모델 다운로드, 실제 영상 추론, OSM 실네트워크 접근, 실제 editable 생성은 수행하지 않았습니다.
