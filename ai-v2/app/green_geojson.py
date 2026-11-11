
import cv2
import numpy as np

from shapely.geometry import Polygon, MultiPolygon, mapping
from shapely.ops import unary_union

from app.geo_utils import pixel_to_geojson


def green_mask_to_geojson(
    green_mask,
    world_file,
    image_crs="EPSG:3857",
    min_area=100,
):
    binary = (green_mask.astype(np.uint8) * 255)

    # 외곽선과 내부 구멍 추출
    contours, hierarchy = cv2.findContours(
        binary,
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if hierarchy is None:
        return {
            "type": "MultiPolygon",
            "coordinates": [],
        }

    hierarchy = hierarchy[0]
    polygons = []

    for i, contour in enumerate(contours):
        # 부모가 있는 외곽선은 구멍이므로 건너뛰기
        if hierarchy[i][3] != -1:
            continue

        if cv2.contourArea(contour) < min_area:
            continue

        exterior = contour[:, 0, :].tolist()
        holes = []

        child = hierarchy[i][2]

        while child != -1:
            hole = contours[child][:, 0, :].tolist()

            if len(hole) >= 3:
                holes.append(hole)

            child = hierarchy[child][0]

        if len(exterior) < 3:
            continue

        polygon = Polygon(exterior, holes)

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return {
            "type": "MultiPolygon",
            "coordinates": [],
        }

    merged = unary_union(polygons)

    return pixel_to_geojson(
        merged,
        world_file,
        image_crs=image_crs,
    )
