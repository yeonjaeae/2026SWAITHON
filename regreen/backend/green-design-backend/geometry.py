from shapely.geometry import shape, mapping
from shapely.ops import transform
from pyproj import Transformer

to_meter = Transformer.from_crs(
    "EPSG:4326", "EPSG:5179", always_xy=True
)

to_wgs84 = Transformer.from_crs(
    "EPSG:5179", "EPSG:4326", always_xy=True
)


def calculate_editable_area(candidate_geometry, editable_geometry):
    candidate = shape(candidate_geometry)
    editable = shape(editable_geometry)

    if candidate.is_empty or editable.is_empty:
        raise ValueError("후보지 또는 녹지화 대상 영역이 비어 있습니다.")

    if not candidate.is_valid or not editable.is_valid:
        raise ValueError("유효하지 않은 GeoJSON 폴리곤입니다.")

    if candidate.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("후보지는 Polygon 또는 MultiPolygon이어야 합니다.")

    if editable.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("녹지화 대상 영역은 Polygon 또는 MultiPolygon이어야 합니다.")

    candidate_m = transform(to_meter.transform, candidate)
    editable_m = transform(to_meter.transform, editable)

    intersection = candidate_m.intersection(editable_m)

    if intersection.is_empty:
        return {
            "editable_area_m2": 0,
            "editable_geometry": None
        }

    intersection_wgs84 = transform(to_wgs84.transform, intersection)

    return {
        "editable_area_m2": round(intersection.area, 2),
        "editable_geometry": mapping(intersection_wgs84)
    }