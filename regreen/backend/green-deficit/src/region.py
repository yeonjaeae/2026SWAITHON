"""드래그한 영역 분석.

입력: 영역 폴리곤 + 모델이 나눈 토지 피복 폴리곤(green / residential / road …), 모두 위경도(EPSG:4326)
출력: 분류별 면적, 영역 평균 지표, 1인당 녹지 면적, 주택가→녹지 거리, 부족지수 · 우선순위,
      녹지 확충 우선 구역 폴리곤

면적과 거리는 모두 EPSG:5179(미터)로 바꿔서 계산한다.
"""
import math

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import mapping

from . import config, index
from .store import GridStore

KNOWN_CLASSES = ("green", "residential", "road")
MAX_SAMPLE_POINTS = 40_000   # 주택가 거리 계산용 샘플 점 개수 상한 (응답 속도 보장)
PARK_SEARCH_BUFFER = 1_000   # 영역 밖이라도 이 거리 안의 공공 공원은 녹지로 친다


def _clean(geom):
    geom = shapely.make_valid(geom)
    # make_valid 결과에서 면(폴리곤)만 남김
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        geom = shapely.union_all(polys) if polys else shapely.Polygon()
    return geom


def _sample_points(area_geom, spacing: float):
    """폴리곤 안에 일정 간격으로 점을 뿌린다 (점마다 녹지까지 거리를 재기 위해)."""
    if area_geom.is_empty:
        return np.array([]), spacing
    spacing = max(spacing, math.sqrt(area_geom.area / MAX_SAMPLE_POINTS))
    minx, miny, maxx, maxy = area_geom.bounds
    xs = np.arange(minx + spacing / 2, maxx, spacing)
    ys = np.arange(miny + spacing / 2, maxy, spacing)
    xx, yy = np.meshgrid(xs, ys)
    pts = shapely.points(xx.ravel(), yy.ravel())
    shapely.prepare(area_geom)
    return pts[shapely.contains(area_geom, pts)], spacing


def _f(v, nd=3):
    """JSON용 숫자 정리 (NaN → None)."""
    if v is None:
        return None
    v = float(v)
    return None if not math.isfinite(v) else round(v, nd)


def analyze_region(store: GridStore, region_wgs84, landcover: list[tuple[str, object]],
                   priority_weights: dict | None = None,
                   candidate_min_dist: float | None = None,
                   candidate_min_heat: float | None = None) -> dict:
    default_dist = config.CANDIDATE_MIN_DIST_LANDCOVER if landcover else config.CANDIDATE_MIN_DIST
    min_dist = default_dist if candidate_min_dist is None else candidate_min_dist
    min_heat = config.CANDIDATE_MIN_HEAT if candidate_min_heat is None else candidate_min_heat
    region = _clean(store.to_calc(region_wgs84))
    if region.is_empty or region.area == 0:
        raise ValueError("영역 폴리곤이 비어 있습니다")
    total_area = region.area

    # ── 1. 분류별 면적 (겹치는 부분은 한 번만 세도록 분류별로 합침) ──
    by_class: dict[str, list] = {}
    for cls, geom in landcover:
        cls = (cls or "").strip().lower()
        cls = cls if cls in KNOWN_CLASSES else "other"
        g = _clean(store.to_calc(geom)).intersection(region)
        if not g.is_empty:
            by_class.setdefault(cls, []).append(g)
    merged = {cls: _clean(shapely.union_all(gs)) for cls, gs in by_class.items()}
    # 분류끼리 겹치면 한 곳은 한 분류로만 센다: 녹지 > 도로 > 주택가 > 기타
    # (주택가가 용도지역 기준이면 그 안에 녹지·도로가 통째로 들어 있어서)
    taken = shapely.Polygon()
    for cls in ("green", "road", "residential", *(c for c in merged if c not in KNOWN_CLASSES)):
        if cls in merged:
            merged[cls] = _clean(merged[cls].difference(taken)) if not taken.is_empty else merged[cls]
            taken = _clean(shapely.union_all([taken, merged[cls]]))
    landcover_out = {
        cls: {"area_m2": _f(merged[cls].area, 1) if cls in merged else 0.0,
              "ratio": _f(merged[cls].area / total_area) if cls in merged else 0.0}
        for cls in (*KNOWN_CLASSES, *(c for c in merged if c not in KNOWN_CLASSES))
    }
    green = merged.get("green", shapely.Polygon())
    residential = merged.get("residential", shapely.Polygon())

    # ── 2. 영역에 걸친 격자 값 (겹친 면적 비율로 가중) ──
    cells = store.cells_intersecting(region)
    if len(cells) == 0:
        raise ValueError("영역이 분석 대상 지역(격자) 밖에 있습니다")
    overlap = shapely.area(shapely.intersection(cells.geometry.values, region))
    w = overlap / config.CELL_AREA                      # 격자 중 영역에 들어온 비율
    population = float(np.nansum(cells["pop"].to_numpy() * w))

    def wmean(col):
        v = cells[col].to_numpy(dtype=float)
        ok = np.isfinite(v)
        return float(np.average(v[ok], weights=overlap[ok])) if ok.any() else float("nan")

    avg_ndvi, avg_lst = wmean("ndvi"), wmean("lst")
    pop_density = population / (total_area / config.CELL_AREA)   # 명/ha (= 격자 1칸당 인구)

    # ── 3. 주택가 → 녹지 거리 (모델 녹지 + 주변 공공 공원) ──
    # 거리 기준이 되는 녹지는 공원과 같은 기준(PARK_MIN_AREA 이상)의 덩어리만 쓴다.
    # 모델 녹지에는 가로수·화단 같은 수십㎡ 조각이 많아서, 그대로 쓰면 어디서나 "녹지가 가깝다"가 된다.
    # (녹지 면적·비율·1인당 녹지 면적은 조각까지 모두 센다)
    green_patches = [p for p in getattr(green, "geoms", [green])
                     if not p.is_empty and p.area >= config.PARK_MIN_AREA]
    parks = store.parks_near(region, PARK_SEARCH_BUFFER)
    green_all = shapely.union_all([*green_patches, *parks.geometry.values])
    pts, spacing = _sample_points(residential, 20.0)
    dist = None
    if len(pts):
        dist = (shapely.distance(pts, green_all) if not green_all.is_empty
                else np.full(len(pts), np.inf))
        finite = np.isfinite(dist)
        avg_dist = float(dist[finite].mean()) if finite.any() else float("inf")
        dist_source = "model_residential"
    else:
        # 주택가가 없으면 격자 중심→공원 거리로 대신
        avg_dist = wmean("park_dist")
        dist_source = "grid_park_dist"

    # ── 4. 부족지수 · 우선순위 (격자와 같은 기준) ──
    c = index.components(avg_ndvi, avg_lst, pop_density, avg_dist, store.params)
    c = {k: float(v) for k, v in c.items()}
    deficit = float(index.deficit_index(c))
    priority = float(index.priority_score(deficit, c["heat_n"], c["pop_n"], priority_weights))

    green_area = green.area
    # 모델 결과가 없으면 녹지 면적을 알 수 없으므로 null
    per_capita = green_area / population if (landcover and population > 0) else None

    # ── 5. 녹지 확충 필요 구역: 기존 녹지를 뺀 영역 중 녹지에서 멀고 뜨거운 곳 ──
    # 주택가로 자르지 않는다. 주차장·학교·공공시설은 모델이 road/other 로 분류할 수 있어서,
    # 주택가로 자르면 이후 유휴 공간 교차 분석(PostGIS)에서 빠져 버리기 때문.
    # 모델 결과가 없어도(landcover 비어 있음) 공공 공원 기준으로 계산된다.
    candidates = None
    candidate_area = 0.0
    existing_green = _clean(shapely.union_all([green, green_all]))   # 이미 녹지인 곳은 모두 제외
    need_area = _clean(region.difference(existing_green)) if not existing_green.is_empty else region
    npts, nspacing = _sample_points(need_area, 20.0)
    if len(npts):
        ndist = (shapely.distance(npts, green_all) if not green_all.is_empty
                 else np.full(len(npts), np.inf))
        xs, ys = shapely.get_x(npts), shapely.get_y(npts)
        keys = zip(np.floor(xs / config.CELL_SIZE).astype(int),
                   np.floor(ys / config.CELL_SIZE).astype(int))
        heat_lookup = store.grid["heat_n"]
        heat = np.array([heat_lookup.get(store.key_to_cell.get(k), np.nan) for k in keys])
        pick = (ndist >= min_dist) & (heat >= min_heat)
        if pick.any():
            h = nspacing / 2
            boxes = shapely.box(xs[pick] - h, ys[pick] - h, xs[pick] + h, ys[pick] + h)
            cand = _clean(shapely.union_all(boxes).intersection(need_area))
            if not cand.is_empty:
                candidate_area = cand.area
                if cand.geom_type == "Polygon":          # 형식을 항상 MultiPolygon 으로 통일
                    cand = shapely.MultiPolygon([cand])
                candidates = mapping(store.to_web(cand))

    # 영역에 걸친 100m 격자 (지도 색칠용, 후보지 추천 API 의 grids 형식과 같음)
    grids = []
    web_geoms = gpd.GeoSeries(cells.geometry.values, crs=config.CRS_CALC).to_crs(config.CRS_WEB)
    for cid, geom, d in zip(cells["cell_id"], web_geoms, cells["deficit_index"]):
        if d is None or not math.isfinite(float(d)):
            continue                                  # 값이 없는 칸(하천 등)은 제외
        grids.append({"grid_id": str(int(cid)), "deficit_index": _f(min(max(float(d), 0.0), 1.0)),
                      "geometry": mapping(geom)})

    return {
        "total_area_m2": _f(total_area, 1),
        "landcover": landcover_out,
        "grid_cells": int(len(cells)),
        "grids": grids,
        "avg_ndvi": _f(avg_ndvi),
        "avg_lst": _f(avg_lst, 2),
        "population": _f(population, 0),
        "pop_density_per_ha": _f(pop_density, 1),
        "green_area_m2": _f(green_area, 1),
        "green_per_capita_m2": _f(per_capita, 2),
        "green_per_capita_target_m2": config.GREEN_PER_CAPITA_TARGET,
        "avg_dist_to_green_m": _f(avg_dist, 1),
        "dist_source": dist_source,
        "components": {k: _f(v) for k, v in c.items()},
        "deficit_index": _f(deficit),
        "priority_score": _f(priority),
        "candidate_area_m2": _f(candidate_area, 1),
        "candidate_criteria": {"min_dist_m": min_dist, "min_heat": min_heat},
        "candidates": candidates,   # GeoJSON (EPSG:4326) 또는 null
    }
