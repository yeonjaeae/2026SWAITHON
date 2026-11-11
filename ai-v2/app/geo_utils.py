
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import shape, mapping, box
from shapely.ops import transform


def read_world_file(path):
    """World File의 6개 좌표 변환 계수를 읽는다."""
    values = [
        float(v)
        for v in Path(path).read_text().split()
    ]

    if len(values) != 6:
        raise ValueError("World File에는 숫자 6개가 필요합니다.")

    return values


def geojson_to_pixel_geometry(
    region_geojson,
    world_file,
    image_crs="EPSG:3857",
):
    """
    EPSG:4326 GeoJSON을 이미지 픽셀 좌표로 변환한다.
    World File은 픽셀 중심 기준으로 계산한다.
    """
    if region_geojson.get("type") == "Feature":
        region_geojson = region_geojson["geometry"]

    region = shape(region_geojson)

    if (
        region.is_empty
        or not region.is_valid
        or region.geom_type not in ("Polygon", "MultiPolygon")
    ):
        raise ValueError("유효한 Polygon 또는 MultiPolygon이 필요합니다.")

    A, D, B, E, C, F = read_world_file(world_file)

    matrix = np.array([[A, B], [D, E]], dtype=float)
    offset = np.array([C, F], dtype=float)

    if abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("World File의 좌표 변환 행렬이 유효하지 않습니다.")

    inverse = np.linalg.inv(matrix)

    to_image_crs = Transformer.from_crs(
        "EPSG:4326",
        image_crs,
        always_xy=True,
    )

    def to_pixel(x, y, z=None):
        mx, my = to_image_crs.transform(x, y)
        px = inverse[0, 0] * (mx - C) + inverse[0, 1] * (my - F)
        py = inverse[1, 0] * (mx - C) + inverse[1, 1] * (my - F)
        return px, py

    return transform(to_pixel, region)


def pixel_to_geojson(
    pixel_geometry,
    world_file,
    image_crs="EPSG:3857",
):
    """이미지 픽셀 좌표를 EPSG:4326 GeoJSON으로 변환한다."""
    A, D, B, E, C, F = read_world_file(world_file)

    to_wgs84 = Transformer.from_crs(
        image_crs,
        "EPSG:4326",
        always_xy=True,
    )

    def to_geo(x, y, z=None):
        mx = A * x + B * y + C
        my = D * x + E * y + F
        return to_wgs84.transform(mx, my)

    geometry = transform(to_geo, pixel_geometry)

    return mapping(geometry)


def clip_to_image(pixel_geometry, image_width, image_height):
    """선택 영역을 이미지 범위 안으로 제한한다."""
    image_bounds = box(
        -0.5,
        -0.5,
        image_width - 0.5,
        image_height - 0.5,
    )

    return pixel_geometry.intersection(image_bounds)
