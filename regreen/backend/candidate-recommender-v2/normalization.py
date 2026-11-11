"""Explicit source-CRS ingestion; no coordinate guessing or silent feature loss."""
import math
from pyproj import CRS, Transformer
from shapely import make_valid, transform as project
from shapely.geometry import shape, mapping
from spatial import polygon, polygonal

MAX_VERTICES = 100_000
MAX_FEATURES = 5000

def crs_value(value):
    try:
        result = CRS.from_user_input(value)
        if not (result.is_projected or result.is_geographic):
            raise ValueError('평면/지리 좌표계만 지원합니다.')
        return result
    except Exception as exc:
        raise ValueError('알 수 없거나 지원하지 않는 원본 좌표계입니다.') from exc

def check_declared_crs(doc, source):
    metadata = doc.get('crs')
    if metadata is not None:
        try:
            declared = crs_value(metadata['properties']['name'])
        except (TypeError, KeyError) as exc:
            raise ValueError('GeoJSON crs 메타데이터를 확인하세요.') from exc
        if not declared.equals(source, ignore_axis_order=True):
            raise ValueError('source_crs와 파일의 crs 메타데이터가 다릅니다.')

def normalize_geometry(value, source_crs='EPSG:4326', repair=False):
    if not isinstance(value, dict):
        raise ValueError('geometry는 객체여야 합니다.')
    source = crs_value(source_crs)
    check_declared_crs(value, source)
    if value.get('type') == 'Feature':
        value = value.get('geometry')
    if not isinstance(value, dict) or value.get('type') not in ('Polygon', 'MultiPolygon'):
        raise ValueError('면 경계 Polygon/MultiPolygon이 필요합니다. 점으로 시설 경계를 추정하지 않습니다.')
    count = 0
    def visit(node):
        nonlocal count
        if not isinstance(node, (list, tuple)) or not node:
            raise ValueError('빈 좌표 또는 잘못된 좌표 구조입니다.')
        if isinstance(node[0], (int, float)):
            count += 1
            if count > MAX_VERTICES:
                raise ValueError('도형 하나의 좌표 수가 제한을 초과합니다.')
            if len(node) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in node):
                raise ValueError('유한한 2차원 좌표가 필요합니다. Z는 명시적으로 제거 후 입력하세요.')
        else:
            for child in node:
                visit(child)
    visit(value.get('coordinates'))
    try:
        g = shape(value)
    except Exception as exc:
        raise ValueError('도형 구조를 읽을 수 없습니다.') from exc
    repaired = False
    if not g.is_valid:
        if not repair:
            raise ValueError('유효하지 않은 경계입니다. 원본 확인 후 repair=true를 명시하세요.')
        g = polygonal(make_valid(g)); repaired = True
    if g.is_empty or g.area <= 0:
        raise ValueError('복구 후 유효한 면이 없거나 면적이 0입니다.')
    converter = Transformer.from_crs(source, 4326, always_xy=True)
    try:
        g = project(g, lambda x,y: converter.transform(x,y,errcheck=True), interleaved=False)
    except Exception as exc:
        raise ValueError('좌표 변환 실패: 좌표계와 원본 좌표를 확인하세요.') from exc
    output = mapping(g)
    polygon(output)  # final service area, finite coords, topology validation
    return output, repaired

def normalize_collection(doc, source_crs='EPSG:4326', repair=False):
    if not isinstance(doc, dict) or doc.get('type') != 'FeatureCollection' or not isinstance(doc.get('features'), list):
        raise ValueError('FeatureCollection이 필요합니다.')
    if len(doc['features']) > MAX_FEATURES:
        raise ValueError('한 요청의 feature 수는 5000개 이하여야 합니다.')
    check_declared_crs(doc, crs_value(source_crs))
    features, repairs = [], []
    for index, feature in enumerate(doc['features']):
        if not isinstance(feature,dict) or feature.get('type') != 'Feature' or not isinstance(feature.get('properties',{}),dict):
            raise ValueError(f'feature {index}: Feature/properties 구조를 확인하세요.')
        try:
            geometry, changed = normalize_geometry(feature, source_crs, repair)
        except ValueError as exc:
            raise ValueError(f'feature {index}: {exc}') from exc
        features.append({'type':'Feature', **({'id':feature['id']} if 'id' in feature else {}),
                         'geometry':geometry, 'properties':feature.get('properties',{})})
        if changed:
            repairs.append(index)
    return {'geojson':{'type':'FeatureCollection','features':features}, 'geometry_crs':'EPSG:4326',
            'repaired_feature_indices':repairs,
            'warnings':['복구 도형은 원본과 비교 검토해야 합니다.'] if repairs else []}
