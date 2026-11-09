"""녹지 부족지수 API.

실행: uvicorn src.api:app --reload --port 8000
문서: http://localhost:8000/docs
"""
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from shapely.geometry import box, shape

from . import config
from .region import analyze_region
from .store import get_store

app = FastAPI(title="녹지 부족지수 API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.get("/api/health", summary="서버 확인")
def health():
    s = get_store()
    return {"status": "ok", "cells": len(s.grid), "parks": len(s.parks)}


class LandcoverItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    cls: str = Field(alias="class", description="green | residential | road | 기타")
    geometry: dict = Field(description="GeoJSON Polygon/MultiPolygon (EPSG:4326)")


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90, description="위도")
    lng: float = Field(ge=-180, le=180, description="경도")


class RegionRequest(BaseModel):
    """영역은 둘 중 하나로 보낸다.
    1) 사각형 (권장): sw(남서쪽 꼭짓점) + ne(북동쪽 꼭짓점)
    2) 임의 도형: region (GeoJSON Polygon, [경도, 위도] 순서)
    """
    # Swagger 예시는 아래 REGION_EXAMPLES (드롭다운) 에 있다
    sw: LatLng | None = Field(None, description="South-West(남서쪽) = 사각형 왼쪽 아래 꼭짓점")
    ne: LatLng | None = Field(None, description="North-East(북동쪽) = 사각형 오른쪽 위 꼭짓점")
    region: dict | None = Field(None, description="임의 도형 영역. GeoJSON geometry 또는 Feature "
                                                  "(EPSG:4326). sw/ne 를 보내면 생략")
    landcover: list[LandcoverItem] = Field(default_factory=list,
                                           description="모델이 나눈 토지 피복 폴리곤")
    weights: dict[str, float] | None = Field(None, description='예: {"deficit":0.4,"heat":0.3,"pop":0.3}')


def _geom(obj: dict):
    if obj.get("type") == "Feature":
        obj = obj["geometry"]
    try:
        return shape(obj)
    except Exception:
        raise HTTPException(422, "GeoJSON geometry 형식이 아닙니다")


def _region_geom(req: RegionRequest):
    if req.sw and req.ne:
        # 꼭짓점을 반대로 보내도 되도록 min/max 로 정리
        minx, maxx = sorted((req.sw.lng, req.ne.lng))
        miny, maxy = sorted((req.sw.lat, req.ne.lat))
        if minx == maxx or miny == maxy:
            raise HTTPException(422, "sw 와 ne 가 같은 선 위에 있어 사각형이 되지 않습니다")
        return box(minx, miny, maxx, maxy)
    if req.sw or req.ne:
        raise HTTPException(422, "사각형은 sw 와 ne 를 둘 다 보내야 합니다")
    if req.region:
        return _geom(req.region)
    raise HTTPException(422, "영역이 없습니다. sw + ne (사각형) 또는 region (GeoJSON) 을 보내세요")


REGION_DOC = """
지도에서 선택한 사각형 영역의 녹지 부족지수를 계산합니다.

#### 요청

| 필드 | 필수 | 설명 |
|---|:---:|---|
| `sw` | ✓ | **S**outh-**W**est · 사각형 왼쪽 아래 꼭짓점 `{lat, lng}` |
| `ne` | ✓ | **N**orth-**E**ast · 사각형 오른쪽 위 꼭짓점 `{lat, lng}` |
| `landcover` | | 모델 결과 (green / residential / road 폴리곤) |
| `weights` | | 우선순위 가중치 · 기본 deficit 0.4, heat 0.3, pop 0.3 |

`lat` 위도, `lng` 경도 · 카카오맵 `getSouthWest()` · `getNorthEast()` 값을 그대로 사용

#### 응답

| 필드 | 설명 |
|---|---|
| `deficit_index` | 녹지 부족지수 (0~1, 높을수록 부족) |
| `priority_score` | 우선순위 점수 (0~1) |
| `avg_ndvi` · `avg_lst` · `population` | 평균 녹지 정도 · 평균 지표면 온도(°C) · 인구 |
| `avg_dist_to_green_m` | 녹지까지 평균 거리 (m) |
| `candidates` · `candidate_area_m2` | 녹지 확충 필요 구역 (MultiPolygon) · 면적 (㎡) |
"""


def _rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


# Swagger 의 Examples 드롭다운에 보이는 예시 (숙명여대 일대)
REGION_EXAMPLES = {
    "basic": {
        "summary": "기본: 사각형만",
        "value": {
            "sw": {"lat": 37.5440, "lng": 126.9615},
            "ne": {"lat": 37.5485, "lng": 126.9680},
        },
    },
    "full": {
        "summary": "전체: 모델 결과 + 가중치 포함",
        "description": "landcover 좌표는 GeoJSON 이라 [경도, 위도] 순서입니다.",
        "value": {
            "sw": {"lat": 37.5440, "lng": 126.9615},
            "ne": {"lat": 37.5485, "lng": 126.9680},
            "landcover": [
                {"class": "green", "geometry": _rect(126.9640, 37.5458, 126.9655, 37.5470)},
                {"class": "residential", "geometry": _rect(126.9615, 37.5440, 126.9680, 37.5450)},
                {"class": "road", "geometry": _rect(126.9615, 37.5450, 126.9680, 37.5452)},
            ],
            "weights": {"deficit": 0.4, "heat": 0.3, "pop": 0.3},
        },
    },
}


@app.post("/api/region/analyze", summary="선택 영역 분석 (사각형 sw/ne)",
          description=REGION_DOC)
def region_analyze(req: Annotated[RegionRequest, Body(openapi_examples=REGION_EXAMPLES)]):
    weights = None
    if req.weights:
        weights = {**config.PRIORITY_WEIGHTS, **req.weights}
    try:
        return analyze_region(get_store(), _region_geom(req),
                              [(lc.cls, _geom(lc.geometry)) for lc in req.landcover],
                              weights)
    except ValueError as e:
        raise HTTPException(422, str(e))
