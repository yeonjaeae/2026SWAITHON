
import io
import json
import re
from pathlib import Path
from functools import lru_cache

import cv2
import numpy as np
import osmnx as ox
import torch
from PIL import Image

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from transformers import (
    AutoImageProcessor,
    Mask2FormerForUniversalSegmentation,
)
from shapely.geometry import shape, mapping, Polygon
from shapely.ops import unary_union, transform as geo_transform
from shapely.validation import make_valid


def valid(geom):
    """꼬인 도형(자기 교차 등)을 고쳐서 면(Polygon) 부분만 남긴다. 합치기·자르기 전에 꼭 거친다."""
    if geom is None or geom.is_empty:
        return geom
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        geom = unary_union(polys) if polys else Polygon()
    return geom
from pyproj import Transformer

app = FastAPI(title="SWAITHON Landcover API")

MODEL_NAME = "mfaytin/mask2former-satellite"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
GREEN_IDS = [1, 4]  # 기존 시각화 기반 임시 매핑
TILE_SIZE = 512

ROAD_WIDTHS = {
    "motorway": 20,
    "trunk": 16,
    "primary": 14,
    "secondary": 12,
    "tertiary": 10,
    "residential": 7,
    "unclassified": 7,
    "service": 5,
    "living_street": 5,
    "motorway_link": 8,
    "trunk_link": 8,
    "primary_link": 7,
    "secondary_link": 6,
    "tertiary_link": 6,
}

TO_METRIC = Transformer.from_crs(
    "EPSG:4326", "EPSG:5179", always_xy=True
)
TO_WGS84 = Transformer.from_crs(
    "EPSG:5179", "EPSG:4326", always_xy=True
)
IMAGE_TO_WGS84 = Transformer.from_crs(
    "EPSG:3857", "EPSG:4326", always_xy=True
)


@lru_cache(maxsize=1)
def load_model():
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    model = Mask2FormerForUniversalSegmentation.from_pretrained(
        MODEL_NAME
    ).to(DEVICE)
    model.eval()
    return processor, model


@lru_cache(maxsize=1)
def load_residential():
    with open("residential.geojson", encoding="utf-8") as f:
        data = json.load(f)

    geoms = []
    for feature in data["features"]:
        if not feature.get("geometry"):
            continue
        geom = shape(feature["geometry"])
        geom = valid(geom)
        if not geom.is_empty:
            geoms.append(geom)
    return geoms


def predict_green(image):
    processor, model = load_model()
    width, height = image.size
    seg = np.zeros((height, width), dtype=np.uint8)

    for y in range(0, height, TILE_SIZE):
        for x in range(0, width, TILE_SIZE):
            x2 = min(x + TILE_SIZE, width)
            y2 = min(y + TILE_SIZE, height)

            tile = image.crop((x, y, x2, y2))
            inputs = processor(
                images=tile, return_tensors="pt"
            ).to(DEVICE)

            with torch.inference_mode():
                outputs = model(**inputs)

            predicted = processor.post_process_semantic_segmentation(
                outputs, target_sizes=[(y2 - y, x2 - x)]
            )[0]

            seg[y:y2, x:x2] = predicted.cpu().numpy()

    return np.isin(seg, GREEN_IDS)


def polygon_parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    if geometry.geom_type == "GeometryCollection":
        parts = []
        for g in geometry.geoms:
            parts.extend(polygon_parts(g))
        return parts
    return []


def make_feature(label, geometry):
    return {
        "type": "Feature",
        "properties": {"class": label},
        "geometry": mapping(geometry),
    }


def green_to_features(mask, pgw, region):
    # PGW: A, D, B, E, C, F
    A, D, B, E, C, F = pgw

    contours, hierarchy = cv2.findContours(
        (mask.astype(np.uint8) * 255),
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if hierarchy is None:
        return []

    hierarchy = hierarchy[0]
    features = []

    def coordinates(contour):
        points = contour.reshape(-1, 2)
        return [
            (
                A * float(x) + B * float(y) + C,
                D * float(x) + E * float(y) + F,
            )
            for x, y in points
        ]

    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1:
            continue
        if cv2.contourArea(contour) < 20:
            continue

        outer = coordinates(contour)
        if len(outer) < 3:
            continue

        holes = []
        child = hierarchy[i][2]

        while child != -1:
            hole = contours[child]
            if len(hole) >= 3 and cv2.contourArea(hole) >= 4:
                holes.append(coordinates(hole))
            child = hierarchy[child][0]

        polygon = Polygon(outer, holes)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        polygon = valid(geo_transform(
            IMAGE_TO_WGS84.transform, polygon
        ))

        clipped = polygon.intersection(region)

        for part in polygon_parts(clipped):
            if part.area > 0:
                features.append(make_feature("green", part))

    return features


def get_residential_features(region):
    features = []

    for geom in load_residential():
        if not geom.intersects(region):
            continue

        clipped = geom.intersection(region)

        for part in polygon_parts(clipped):
            if part.area > 0:
                features.append(
                    make_feature("residential", part)
                )

    return features


# 도로는 OpenStreetMap 공용 서버(Overpass)에서 받는다.
# 한 서버가 바쁘면(502/504/시간 초과) 다음 서버로 넘어간다.
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]
ox.settings.requests_timeout = 60      # 한 서버에서 최대 60초만 기다림 (기본 180초)
ox.settings.overpass_rate_limit = False  # 빈자리 날 때까지 기다리지 않고 바로 다음 서버로


ROADS_FILE = Path(__file__).resolve().parent / "seoul_roads.gpkg"   # build_roads.py 로 만든 파일


@lru_cache(maxsize=1)
def load_local_roads():
    import geopandas as gpd
    gdf = gpd.read_file(ROADS_FILE, layer="roads")
    gdf.sindex                                     # 공간 색인 미리 만들기
    return gdf


def fetch_roads(region):
    # 1) 서울 도로 파일이 있으면 그걸 쓴다 (인터넷 안 씀, 거의 바로 끝남)
    if ROADS_FILE.exists():
        gdf = load_local_roads()
        return gdf.iloc[gdf.sindex.query(region, predicate="intersects")]
    # 2) 없으면 공용 서버에 묻는다
    errors = []
    for url in OVERPASS_URLS:
        ox.settings.overpass_url = url
        try:
            return ox.features_from_polygon(region, tags={"highway": True})
        except Exception as ex:
            errors.append(f"{url.split('/')[2]}: {str(ex)[:80]}")
    raise RuntimeError("도로 데이터 서버(Overpass)가 모두 응답하지 않습니다 — " + " | ".join(errors))


def get_road_features(region):
    roads = fetch_roads(region).to_crs(epsg=5179)

    polygons = []

    for _, row in roads.iterrows():
        highway = row.get("highway")

        if isinstance(highway, (list, tuple)):
            kind = next(
                (h for h in highway if h in ROAD_WIDTHS),
                None
            )
        else:
            kind = (
                highway
                if isinstance(highway, str)
                and highway in ROAD_WIDTHS
                else None
            )

        if kind is None:
            continue

        geom = row.geometry
        if geom is None or geom.is_empty:
            continue

        width = ROAD_WIDTHS[kind]
        raw = row.get("width")

        if isinstance(raw, str):
            match = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)\s*(?:m)?\s*",
                raw
            )
            if match:
                candidate = float(match.group(1))
                if 2 <= candidate <= 40:
                    width = candidate

        if geom.geom_type in ("LineString", "MultiLineString"):
            polygons.append(valid(geom.buffer(width / 2)))
        elif geom.geom_type in ("Polygon", "MultiPolygon"):
            polygons.append(valid(geom))

    if not polygons:
        return []

    combined = valid(unary_union([p for p in polygons if not p.is_empty]))

    region_m = valid(geo_transform(
        TO_METRIC.transform, region
    ))
    clipped = combined.intersection(region_m)

    if clipped.is_empty:
        return []

    result = geo_transform(
        TO_WGS84.transform, clipped
    )

    return [
        make_feature("road", p)
        for p in polygon_parts(result)
        if p.area > 0
    ]


@app.get("/health")
def health():
    return {"status": "ok", "device": DEVICE}


@app.post("/ai/landcover")
async def analyze_landcover(
    image: UploadFile = File(...),
    world_file: UploadFile = File(...),
    region: str = Form(...),
):
    try:
        data = json.loads(region)
        if data.get("type") == "Feature":
            data = data["geometry"]

        region_geom = shape(data)

        if (
            region_geom.geom_type not in ("Polygon", "MultiPolygon")
            or region_geom.is_empty
            or not region_geom.is_valid
        ):
            raise ValueError("Invalid region geometry")

        image_bytes = await image.read()
        aerial = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        pgw = [
            float(v)
            for v in (await world_file.read()).decode().split()
        ]

        if len(pgw) != 6:
            raise ValueError("Invalid world file")

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        green_mask = predict_green(aerial)
        green = green_to_features(
            green_mask, pgw, region_geom
        )
        road = get_road_features(region_geom)
        residential = get_residential_features(region_geom)

        features = green + residential + road

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
