"""Adapter for the supplied ai/main.py: multipart -> properties.class GeoJSON.
It does NOT infer editable, building footprints, or terrain suitability.
"""
import asyncio
import threading
import io
import json
import math
import os
import warnings
from urllib.parse import urlsplit
import httpx
from PIL import Image, UnidentifiedImageError
from pyproj import Transformer, CRS
from pyproj.exceptions import ProjError
from shapely.geometry import Polygon
from shapely.ops import unary_union
from spatial import metric, geojson, polygonal
from normalization import normalize_collection

class UpstreamError(RuntimeError):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def adapt_landcover(fc, region):
    normalized = normalize_collection(fc)
    region_m = metric(region)
    by_class = {'green':[], 'road':[], 'residential':[]}
    for i, f in enumerate(normalized['geojson']['features']):
        label = f['properties'].get('class')
        if label not in by_class:
            raise ValueError(f'AI feature {i}의 properties.class는 green/road/residential이어야 합니다.')
        g = polygonal(metric(f['geometry']).intersection(region_m))
        if not g.is_empty:
            by_class[label].append(g)
    merged = {k:unary_union(v) for k,v in by_class.items()}
    raw_sum = sum(g.area for g in merged.values())
    all_area = unary_union(list(merged.values())).area
    # Explicit precedence avoids >100% areas in downstream per-class statistics.
    assigned = unary_union([])
    items = []
    for label in ('green','road','residential'):
        geom = polygonal(merged[label].difference(assigned))
        assigned = unary_union([assigned, geom])
        if not geom.is_empty:
            items.append({'class':label,'geometry':geojson(geom)})
    return {'landcover':items, 'deficit_request':{'region':region,'landcover':items},
            'coverage_ratio':min(1.,all_area/region_m.area),
            'cross_class_overlap_m2':max(0.,raw_sum-all_area),
            'class_precedence':['green','road','residential'],
            'editable_status':'not_provided_by_ai',
            'warnings':[
                'coverage_ratio는 세 클래스 합집합 비율이며 정확도/영상 커버리지가 아닙니다. 미분류 영역을 editable로 간주하지 마세요.',
                'AI의 residential은 파일의 지정 주거지역이며 건물 경계 또는 유휴 공간이 아닙니다.',
                'AI의 road는 OSM 및 추정 폭 기반이고 green 라벨 매핑은 임시 설정입니다.',
                '클래스가 겹치면 green > road > residential 순서로 중복 면적을 제거합니다.'
            ]}


def validate_image_world(image_bytes, world_bytes, region, image_crs):
    # Existing AI assumes 3857. Reprojecting six coefficients alone is NOT valid.
    try:
        if not CRS.from_user_input(image_crs).equals(CRS.from_epsg(3857)):
            raise ValueError('현재 팀 AI는 EPSG:3857 영상만 지원합니다. 영상과 월드파일을 함께 재투영하세요.')
    except Exception as exc:
        raise ValueError('image_crs는 EPSG:3857이어야 합니다. 다른 영상은 재투영 후 사용하세요.') from exc
    if len(image_bytes) > 20*1024*1024 or len(world_bytes) > 1024:
        raise ValueError('영상은 20MB, 월드파일은 1KB 이하여야 합니다.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            im=Image.open(io.BytesIO(image_bytes))
            if im.format not in ('PNG','JPEG'):
                raise ValueError('PNG/JPEG 영상만 지원합니다.')
            width,height=im.size
            if width*height > 16_000_000:
                raise ValueError('영상은 1600만 픽셀 이하여야 합니다.')
            if im.getexif().get(274,1) != 1:
                raise ValueError('EXIF 회전 영상을 먼저 정규화하고 월드파일을 함께 맞추세요.')
            im.load()
            im.close()
        pgw=[float(v) for v in world_bytes.decode('utf-8-sig').split()]
    except (OSError, UnicodeError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('영상 또는 월드파일을 읽을 수 없습니다.') from exc
    if len(pgw)!=6 or not all(math.isfinite(v) for v in pgw):
        raise ValueError('월드파일에는 유한한 수 6개(A,D,B,E,C,F)가 필요합니다.')
    A,D,B,E,C,F=pgw
    determinant=A*E-B*D
    if not math.isfinite(determinant) or abs(determinant) < 1e-12:
        raise ValueError('월드파일 변환 행렬이 퇴화했습니다.')
    t=Transformer.from_crs(3857,4326,always_xy=True)
    # world files use pixel centers; boundary corners start at -0.5.
    corners=[(-.5,-.5),(width-.5,-.5),(width-.5,height-.5),(-.5,height-.5)]
    ring=[]
    # Densify edges so metric conversion of a rotated footprint stays accurate.
    for i,(x,y) in enumerate(corners):
        nx,ny=corners[(i+1)%4]
        for j in range(33):
            u=x+(nx-x)*j/33; v=y+(ny-y)*j/33
            try:
                ring.append(t.transform(A*u+B*v+C,D*u+E*v+F,errcheck=True))
            except ProjError as exc:
                raise ValueError("월드파일 좌표 변환에 실패했습니다. 원본 계수를 확인하세요.") from exc
    from shapely.geometry import mapping
    footprint=metric(mapping(Polygon(ring)))
    region_m=metric(region)
    missing=region_m.difference(footprint).area
    if missing > max(.01,region_m.area*1e-6):
        raise ValueError('분석 영역이 영상 범위 밖으로 나갑니다. 맞는 영상·월드파일·영역을 사용하세요.')
    if region_m.area > 25_000_000:
        raise ValueError('한 번의 AI 분석 영역은 25㎢ 이하여야 합니다.')
    return {'width':width,'height':height,'image_crs':'EPSG:3857','world_file':pgw,
            'footprint':geojson(footprint)}


def ai_url():
    base=os.getenv('AI_BASE_URL','').rstrip('/')
    parts=urlsplit(base)
    if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise UpstreamError('관리자가 AI_BASE_URL을 올바르게 설정해야 합니다.',503)
    return base+'/ai/landcover'

async def _request_ai(image_bytes, world_bytes, region, image_crs):
    from starlette.concurrency import run_in_threadpool
    metadata=await run_in_threadpool(validate_image_world,image_bytes,world_bytes,region,image_crs)
    try:
        async with asyncio.timeout(120):
            async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5),follow_redirects=False) as client:
                async with client.stream('POST',ai_url(),data={'region':json.dumps(region)},
                    files={'image':('aerial.png',image_bytes),'world_file':('aerial.pgw',world_bytes)}) as r:
                    if r.status_code != 200:
                        raise UpstreamError(f'AI 서버가 분석을 완료하지 못했습니다 (HTTP {r.status_code}).')
                    chunks=[]; size=0
                    async for chunk in r.aiter_bytes():
                        size+=len(chunk)
                        if size>10*1024*1024:
                            raise UpstreamError('AI 응답이 10MB 제한을 초과했습니다.')
                        chunks.append(chunk)
                    raw=json.loads(b''.join(chunks))
        result=await run_in_threadpool(adapt_landcover,raw,region)
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise UpstreamError('AI 분석 시간이 제한을 초과했습니다. 결과를 생성하지 않았습니다.',504) from exc
    except httpx.HTTPError as exc:
        raise UpstreamError('AI 서버 연결에 실패했습니다.',502) from exc
    except (ValueError, TypeError) as exc:
        raise UpstreamError('AI 응답의 GeoJSON 형식·좌표를 확인해야 합니다.') from exc
    result['image_metadata']=metadata
    return result

_AI_SLOTS=threading.BoundedSemaphore(2)

async def request_ai(image_bytes,world_bytes,region,image_crs):
    if not _AI_SLOTS.acquire(blocking=False):
        raise UpstreamError('AI 분석 요청이 처리 중입니다. 잠시 후 다시 시도하세요.',429)
    try:
        return await _request_ai(image_bytes,world_bytes,region,image_crs)
    finally:
        _AI_SLOTS.release()
