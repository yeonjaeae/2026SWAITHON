"""GeoJSON: lon/lat, calculations: Korea EPSG:5179, polygon-only outputs."""
import math
from shapely.geometry import shape, mapping, Polygon
from shapely import transform as project
from shapely.ops import unary_union
from pyproj import Transformer

_TO_M = Transformer.from_crs(4326, 5179, always_xy=True)
_TO_WGS = Transformer.from_crs(5179, 4326, always_xy=True)


def polygon(value):
    if not isinstance(value, dict):
        raise ValueError('GeoJSON 객체가 필요합니다.')
    if 'crs' in value:
        from normalization import check_declared_crs, crs_value
        check_declared_crs(value,crs_value('EPSG:4326'))
    if value.get('type') == 'Feature':
        value = value.get('geometry')
    if not isinstance(value, dict) or value.get('type') not in ('Polygon', 'MultiPolygon'):
        raise ValueError('Polygon 또는 MultiPolygon이 필요합니다.')
    count = 0
    def coordinates(node):
        nonlocal count
        if not isinstance(node, (list, tuple)) or not node:
            raise ValueError('좌표가 비어 있거나 올바르지 않습니다.')
        if isinstance(node[0], (int, float)):
            count += 1
            if count > 100_000:
                raise ValueError('도형 하나의 좌표 수가 100000개를 초과합니다.')
            if len(node) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in node):
                raise ValueError('유한한 [경도, 위도] 두 값이 필요합니다.')
            # This API intentionally supports Korea only, matching EPSG:5179.
            if not (124 <= node[0] <= 132 and 33 <= node[1] <= 39.5):
                raise ValueError('대한민국 범위의 EPSG:4326 [경도, 위도] 좌표가 필요합니다.')
        else:
            for child in node:
                coordinates(child)
    coordinates(value.get('coordinates'))
    try:
        rings = value['coordinates'] if value['type'] == 'Polygon' else [r for p in value['coordinates'] for r in p]
        if any(len(r) < 4 or r[0] != r[-1] for r in rings):
            raise ValueError('각 링은 4개 이상 좌표로 닫혀 있어야 합니다.')
    except TypeError as exc:
        raise ValueError('폴리곤 좌표의 중첩 구조가 올바르지 않습니다.') from exc
    try:
        g = shape(value)
    except Exception as exc:
        raise ValueError('GeoJSON 좌표 구조가 올바르지 않습니다.') from exc
    if g.is_empty or not g.is_valid or g.area <= 0:
        raise ValueError('비어 있거나 자기 교차하는 폴리곤입니다.')
    return g


def metric(value):
    return project(polygon(value), lambda x,y: _TO_M.transform(x,y,errcheck=True), interleaved=False)


def polygonal(g):
    if g.is_empty:
        return Polygon()
    if g.geom_type in ('Polygon', 'MultiPolygon'):
        return g
    if hasattr(g, 'geoms'):
        return unary_union([polygonal(p) for p in g.geoms])
    return Polygon()


def geojson(g):
    g = polygonal(g)
    return None if g.is_empty else mapping(project(g, lambda x,y: _TO_WGS.transform(x,y,errcheck=True), interleaved=False))
