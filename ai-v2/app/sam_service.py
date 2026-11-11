
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from shapely.geometry import shape, Polygon, mapping
from shapely.ops import unary_union
from sam2.sam2_image_predictor import SAM2ImagePredictor

from app.geo_utils import (
    geojson_to_pixel_geometry,
    pixel_to_geojson,
    clip_to_image,
)


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"

MODEL_NAME = "facebook/sam2.1-hiera-tiny"


def get_device():
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def mask_to_geometry(mask, min_area=100):
    """SAM2 마스크를 이미지 픽셀 좌표의 Polygon으로 변환."""
    binary = (mask.astype(np.uint8) * 255)

    contours, hierarchy = cv2.findContours(
        binary,
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if hierarchy is None:
        return Polygon()

    hierarchy = hierarchy[0]
    polygons = []

    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1:
            continue

        if cv2.contourArea(contour) < min_area:
            continue

        outer = contour.reshape(-1, 2)

        if len(outer) < 3:
            continue

        holes = []
        child = hierarchy[i][2]

        while child != -1:
            hole = contours[child]

            if len(hole) >= 3 and cv2.contourArea(hole) >= 4:
                holes.append(hole.reshape(-1, 2).tolist())

            child = hierarchy[child][0]

        polygon = Polygon(outer, holes)

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if not polygon.is_empty:
            polygons.append(polygon)

    if not polygons:
        return Polygon()

    return unary_union(polygons)


def analyze_region(
    image_path,
    world_file_path,
    region_geojson,
    image_crs="EPSG:3857",
):
    """입력 지역을 SAM2로 분할하고 EPSG:4326으로 반환."""

    image = Image.open(image_path).convert("RGB")
    image_np = np.array(image)

    width, height = image.size

    # 1. GeoJSON → 이미지 픽셀
    pixel_region = geojson_to_pixel_geometry(
        region_geojson,
        world_file_path,
        image_crs,
    )

    pixel_region = clip_to_image(
        pixel_region,
        width,
        height,
    )

    if pixel_region.is_empty:
        raise ValueError("선택한 영역이 항공사진 범위 밖입니다.")

    # 2. 선택 영역에서 자동으로 박스 생성
    minx, miny, maxx, maxy = pixel_region.bounds

    input_box = np.array([
        max(0, minx),
        max(0, miny),
        min(width - 1, maxx),
        min(height - 1, maxy),
    ], dtype=np.float32)

    # 3. SAM2 모델 로드
    predictor = SAM2ImagePredictor.from_pretrained(
        MODEL_NAME,
        device=get_device(),
    )

    predictor.set_image(image_np)

    with torch.inference_mode():
        masks, scores, _ = predictor.predict(
            box=input_box,
            multimask_output=True,
        )

    best_mask = np.asarray(
        masks[np.argmax(scores)]
    ) > 0

    # 4. 선택 영역 밖은 마스크에서 제거
    region_mask = np.zeros((height, width), dtype=np.uint8)

    def draw_geometry(geometry):
        if geometry.geom_type == "Polygon":
            outer = np.round(
                np.array(geometry.exterior.coords)
            ).astype(np.int32)

            cv2.fillPoly(region_mask, [outer], 1)

            for ring in geometry.interiors:
                hole = np.round(
                    np.array(ring.coords)
                ).astype(np.int32)
                cv2.fillPoly(region_mask, [hole], 0)

        elif geometry.geom_type == "MultiPolygon":
            for geom in geometry.geoms:
                draw_geometry(geom)

    draw_geometry(pixel_region)

    final_mask = best_mask & (region_mask > 0)

    # 5. 마스크 → GeoJSON
    pixel_geometry = mask_to_geometry(final_mask)

    if pixel_geometry.is_empty:
        raise ValueError("SAM2가 유효한 영역을 추출하지 못했습니다.")

    geojson = pixel_to_geojson(
        pixel_geometry,
        world_file_path,
        image_crs,
    )

    # 6. 시각화 저장
    OUTPUTS.mkdir(exist_ok=True)

    overlay = image_np.copy()
    overlay[final_mask] = (
        image_np[final_mask] * 0.55
        + np.array([50, 190, 90]) * 0.45
    ).astype(np.uint8)

    Image.fromarray(overlay).save(
        OUTPUTS / "sam2_overlay.png"
    )

    return {
        "type": "Feature",
        "properties": {
            "class": "editable",
            "sam_score": float(np.max(scores)),
        },
        "geometry": geojson,
    }
