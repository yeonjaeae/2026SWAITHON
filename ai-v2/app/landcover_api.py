
import json
import tempfile
from pathlib import Path

import numpy as np

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape, mapping, MultiPolygon
from shapely.ops import transform, unary_union

from app.landcover_service import predict_landcover
from app.green_geojson import green_mask_to_geojson

router = APIRouter()


def project(geom, src, dst):
    transformer = Transformer.from_crs(
        src, dst, always_xy=True
    )
    return transform(transformer.transform, geom)


def polygons_only(geom):
    if geom.is_empty:
        return MultiPolygon()

    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])

    if geom.geom_type == "MultiPolygon":
        return geom

    polygons = []

    for part in getattr(geom, "geoms", []):
        if part.geom_type == "Polygon":
            polygons.append(part)
        elif part.geom_type == "MultiPolygon":
            polygons.extend(part.geoms)

    return MultiPolygon(polygons)


def parse_geometry(data):
    if data["type"] == "Feature":
        return shape(data["geometry"])

    if data["type"] == "FeatureCollection":
        return unary_union([
            shape(f["geometry"])
            for f in data["features"]
            if f.get("geometry")
        ])

    return shape(data)


def feature(name, geom):
    geom = polygons_only(geom)

    return {
        "type": "Feature",
        "properties": {
            "class": name,
            "status": "candidate",
        },
        "geometry": mapping(geom),
    }


@router.post("/ai/landcover")
async def landcover(
    image: UploadFile = File(...),
    world_file: UploadFile = File(...),
    region: str = Form(...),
    residential: str | None = Form(None),
    roads: str | None = Form(None),
    buildings: str | None = Form(None),
):
    # 1. 입력 GeoJSON 검증
    try:
        region_geom = parse_geometry(json.loads(region))

        if (
            region_geom.is_empty
            or not region_geom.is_valid
            or region_geom.geom_type not in ("Polygon", "MultiPolygon")
        ):
            raise ValueError("유효한 Polygon이 필요합니다.")

        residential_geom = (
            parse_geometry(json.loads(residential))
            if residential else MultiPolygon()
        )

        roads_geom = (
            parse_geometry(json.loads(roads))
            if roads else MultiPolygon()
        )

        buildings_geom = (
            parse_geometry(json.loads(buildings))
            if buildings else MultiPolygon()
        )

        for name, geom in [
            ("도로", roads_geom),
            ("건물", buildings_geom),
        ]:
            if (
                not geom.is_empty
                and (
                    not geom.is_valid
                    or geom.geom_type not in ("Polygon", "MultiPolygon")
                )
            ):
                raise ValueError(
                    f"{name} GeoJSON은 유효한 Polygon이어야 합니다."
                )

        if (
            not residential_geom.is_empty
            and (
                not residential_geom.is_valid
                or residential_geom.geom_type not in
                ("Polygon", "MultiPolygon")
            )
        ):
            raise ValueError("주거지역 Polygon이 유효하지 않습니다.")

    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 모든 입력 GeoJSON은 EPSG:4326
    # 항공사진 World File은 EPSG:3857 기준
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)

        image_path = temp_dir / "aerial.png"
        world_path = temp_dir / "aerial.pgw"

        image_path.write_bytes(await image.read())
        world_path.write_bytes(await world_file.read())

        try:
            aerial = Image.open(image_path).convert("RGB")

            # 2. Mask2Former 녹지 후보
            segmentation = predict_landcover(aerial)
            green_mask = np.isin(segmentation, [1, 4])

            green_geojson = green_mask_to_geojson(
                green_mask,
                world_path,
                image_crs="EPSG:3857",
            )

            green_geom = shape(green_geojson)

            # 선택한 지역 내부로 제한
            green_geom = green_geom.intersection(region_geom)

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Mask2Former 분석 실패: {e}"
            )


    # 3. GIS 백엔드에서 받은 도로·건물 데이터 사용
    road_geom = roads_geom.intersection(region_geom)
    building_geom = buildings_geom.intersection(region_geom)

    # 4. 녹지 후보에서 도로·건물 제외
    green_filtered = green_geom.difference(
        unary_union([road_geom, building_geom])
    )

    # 5. 주거지역 GIS 데이터 결합
    residential_filtered = residential_geom.intersection(
        region_geom
    )

    # 6. GeoJSON FeatureCollection 반환
    return {
        "type": "FeatureCollection",
        "features": [
            feature("green", green_filtered),
            feature("road", road_geom),
            feature("residential", residential_filtered),
        ],
        "metadata": {
            "green_status": (
                "candidate_filtered"
                if roads or buildings
                else "candidate_unfiltered"
            ),
            "road_source": (
                "provided_GIS" if roads
                else "not_provided"
            ),
            "building_source": (
                "provided_GIS" if buildings
                else "not_provided"
            ),
            "residential_source": (
                "provided_GIS" if residential
                else "not_provided"
            ),
            "crs": "EPSG:4326",
        },
    }
