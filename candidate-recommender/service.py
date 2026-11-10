"""Candidate extraction, transparent scoring, selection and team handoff."""
import hashlib
import json
from shapely import normalize
from shapely.geometry import Polygon
from shapely.ops import unary_union
from spatial import metric, polygonal, geojson
from repository import load_sites

WEIGHTS = {'deficit': .45, 'area': .25, 'impervious': .20, 'feasibility': .10}


def candidate_key(site_id, geometry):
    # Canonical geometry + original ID: same site clipped differently gets another ID.
    g = normalize(metric(geometry))
    # Quantize to mm so round-trip lon/lat serialization doesn't change the key.
    from shapely import set_precision
    content = site_id.encode() + normalize(set_precision(g, .001)).wkb
    return 'candidate_' + hashlib.sha256(content).hexdigest()[:20]


def recommend(req):
    if req.region_analysis.candidates is None:
        return {'source': 'no_candidate_zone', 'count': 0, 'recommendations': [], 'warnings': []}
    zone = metric(req.region_analysis.candidates)
    sites, source = (req.sites, 'request') if req.sites is not None else load_sites(req.region_analysis.candidates)
    ids = [s.site_id for s in sites]
    if len(ids) != len(set(ids)):
        raise ValueError('site_id가 중복됩니다. 원본 데이터에서 하나의 시설 경계를 합치거나 ID를 구분하세요.')
    grids = [(metric(g.geometry), g.deficit_index) for g in req.grids]
    # Require non-overlapping grid cells to avoid counting the same area twice.
    for i, (g, _) in enumerate(grids):
        if any(g.intersection(h).area > .01 for h, _ in grids[:i]):
            raise ValueError('격자 폴리곤이 서로 겹칩니다.')
    green = unary_union([metric(l.geometry) for l in req.landcover if l.cls == 'green'])
    results = []
    for site in sites:
        if site.is_green or site.site_type not in req.allowed_site_types:
            continue
        original = metric(site.geometry)
        clipped = polygonal(original.intersection(zone).difference(green))
        if clipped.is_empty or clipped.area < req.min_area_m2:
            continue
        geometry = geojson(clipped)
        # Use returned geometry for all areas so downstream receives the same shape.
        area = metric(geometry).area
        overlap = [(clipped.intersection(g).area, v) for g, v in grids]
        covered = sum(a for a, _ in overlap)
        grid_fraction = min(1., covered / area)
        fallback = req.region_analysis.deficit_index
        if covered > .0001:
            weighted = sum(a * v for a, v in overlap)
            if fallback is not None:
                deficit = (weighted + max(0., area-covered) * fallback) / area
                deficit_source = 'grid_weighted' if grid_fraction > .999 else 'grid_plus_region_fallback'
            else:
                deficit = weighted / covered
                deficit_source = 'covered_grid_only'
        else:
            deficit, deficit_source = fallback, 'region_average_fallback' if fallback is not None else 'missing'
        parts = {'deficit': deficit, 'area': min(area / 500., 1.),
                 'impervious': site.impervious_ratio, 'feasibility': site.feasibility_score}
        available = sum(WEIGHTS[k] for k, v in parts.items() if v is not None)
        score = sum(WEIGHTS[k]*v for k, v in parts.items() if v is not None) / available
        reasons = [f'후보지 교차 면적 {area:.2f}㎡', f'점수에 사용된 항목의 가중치 합 {available:.2f}']
        if deficit is not None:
            reasons.append(f'녹지 부족지수 {deficit:.3f} (출처: {deficit_source})')
        if site.impervious_ratio is not None:
            reasons.append(f'입력 데이터의 불투수율 {site.impervious_ratio:.1%}')
        if site.feasibility_score is not None:
            reasons.append(f'입력 데이터의 실현 가능성 점수 {site.feasibility_score:.3f}')
        results.append({
            'candidate_id': candidate_key(site.site_id, geometry), 'site_id': site.site_id,
            'name': site.name, 'site_type': site.site_type, 'address': site.address,
            'geometry': geometry, 'geometry_crs': 'EPSG:4326', 'area_m2': round(area, 6),
            'original_site_area_m2': round(original.area, 6), 'source': site.source, 'is_demo': site.is_demo,
            'green_deficit_score': deficit, 'green_deficit_source': deficit_source,
            'grid_coverage_ratio': grid_fraction, 'impervious_ratio': site.impervious_ratio,
            'feasibility_score': site.feasibility_score, 'total_score': score,
            'score_components': parts, 'score_data_coverage': available,
            'reasons': reasons, 'recommendation_text': '; '.join(reasons) + '. 실제 이용 현황과 녹지화 가능 여부는 별도 확인이 필요합니다.',
            'editable_status': 'pending_ai_review',
        })
    results.sort(key=lambda c: (-c['total_score'], c['candidate_id']))
    results = results[:req.limit]
    for rank, item in enumerate(results, 1):
        item['rank'] = rank
        item['total_score'] = round(item['total_score'], 6)
    return {'source': source, 'count': len(results), 'recommendations': results,
            'scoring_weights': WEIGHTS, 'warnings': [
                '누락 지표는 0으로 간주하지 않고 나머지 가중치 합으로 나눕니다. score_data_coverage를 함께 비교하세요.',
                '후보지 경계는 editable 확정 영역이 아닙니다. 실현 가능성·불투수율은 토지피복 3분류에서 자동 추정하지 않습니다.'
            ]}


def select_candidate(req):
    matches = [c for c in req.recommendations if c.get('candidate_id') == req.candidate_id]
    if not matches:
        raise LookupError('후보지 ID를 추천 목록에서 찾지 못했습니다.')
    if len(matches) != 1:
        raise ValueError('후보지 ID가 중복됩니다.')
    c = matches[0]
    if c.get('geometry_crs') != 'EPSG:4326':
        raise ValueError('EPSG:4326만 지원합니다.')
    if not isinstance(c.get('site_id'), str) or candidate_key(c['site_id'], c.get('geometry')) != req.candidate_id:
        raise ValueError('후보지 ID와 geometry가 일치하지 않습니다. 추천을 다시 요청하세요.')
    geometry = c['geometry']
    area = round(metric(geometry).area, 6)
    props = {k: c.get(k) for k in ('site_id', 'name', 'site_type', 'source', 'is_demo')}
    props.update(candidate_id=req.candidate_id, area_m2=area, editable_status='pending_ai_review')
    return {'candidate_id': req.candidate_id, 'area_m2': area, 'geometry_crs': 'EPSG:4326',
            'feature': {'type': 'Feature', 'id': req.candidate_id, 'geometry': geometry, 'properties': props}}


def design_handoff(req):
    c = req.candidate
    if c.get('geometry_crs') != 'EPSG:4326':
        raise ValueError('후보지 좌표계는 EPSG:4326이어야 합니다.')
    feature = c.get('feature', {})
    if not isinstance(feature, dict) or not isinstance(feature.get('properties', {}), dict):
        raise ValueError('Feature와 properties는 JSON 객체여야 합니다.')
    cid = c.get('candidate_id')
    if not cid or feature.get('id') != cid or req.editable.candidate_id != cid:
        raise ValueError('candidate_id가 후보지·Feature·editable에서 일치해야 합니다.')
    if feature.get('type') != 'Feature':
        raise ValueError('candidate.feature는 Feature여야 합니다.')
    candidate_m = metric(feature.get('geometry'))
    candidate = {**c, 'area_m2': round(candidate_m.area, 6)}
    candidate['feature'] = {**feature, 'properties': {**feature.get('properties', {}), 'area_m2': candidate['area_m2']}}
    editable_m = metric(req.editable.editable_geometry) if req.editable.editable_geometry is not None else Polygon()
    clipped = polygonal(candidate_m.intersection(editable_m))
    area = clipped.area
    payload = {'candidate': candidate, 'green_ratio': req.green_ratio, 'vegetation': req.vegetation.model_dump()}
    warnings = []
    if editable_m.area-area > .01:
        warnings.append('후보지 밖 editable 부분을 잘랐습니다.')
    if area <= .000001:
        # Existing spatial endpoint rejects empty/null geometry. Use its numeric endpoint.
        endpoint = '/api/design/from-candidate'
        payload['protected_area'] = candidate['area_m2']
        editable_geometry = None
        warnings.append('editable 면적이 0이므로 전체를 보존 면적으로 전달합니다.')
    else:
        endpoint = '/api/design/spatial'
        editable_geometry = geojson(clipped)
        payload['editable_geometry'] = editable_geometry
    return {'target_endpoint': endpoint, 'payload': payload,
            'editable_geometry': editable_geometry, 'editable_area_m2': round(area, 6),
            'protected_area_m2': round(max(0., candidate_m.area-area), 6),
            'editable_source': req.editable.source, 'warnings': warnings}
