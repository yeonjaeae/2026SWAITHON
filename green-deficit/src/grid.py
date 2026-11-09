# 100m 정사각 격자 생성
import math

import geopandas as gpd
import numpy as np
import shapely

from . import config


def make_grid(boundary: gpd.GeoDataFrame, name_col: str | None = None,
              size: int = config.CELL_SIZE) -> gpd.GeoDataFrame:
    """경계 안에 size(m) 격자를 만든다.

    - 좌표를 size의 배수에 맞춰 정렬하므로 통계청 SGIS 100m 격자와 칸이 일치한다.
    - 중심점이 경계 안에 있는 격자만 남긴다.
    - name_col이 있으면 각 격자에 행정구역 이름(예: 구 이름)을 붙인다.
    """
    boundary = boundary.to_crs(config.CRS_CALC)
    minx, miny, maxx, maxy = boundary.total_bounds
    minx = math.floor(minx / size) * size
    miny = math.floor(miny / size) * size

    xs = np.arange(minx, maxx, size)
    ys = np.arange(miny, maxy, size)
    xx, yy = np.meshgrid(xs, ys)
    xx, yy = xx.ravel(), yy.ravel()

    # 중심점이 경계 안에 있는 칸만
    centers = shapely.points(xx + size / 2, yy + size / 2)
    union = shapely.union_all(boundary.geometry.values)
    shapely.prepare(union)
    inside = shapely.contains(union, centers)
    xx, yy, centers = xx[inside], yy[inside], centers[inside]

    cells = shapely.box(xx, yy, xx + size, yy + size)
    grid = gpd.GeoDataFrame(
        {"cell_id": np.arange(len(cells), dtype=np.int64)},
        geometry=cells, crs=config.CRS_CALC,
    )

    if name_col:
        pts = gpd.GeoDataFrame(geometry=centers, crs=config.CRS_CALC)
        joined = gpd.sjoin(pts, boundary[[name_col, "geometry"]], how="left",
                           predicate="within")
        joined = joined[~joined.index.duplicated()]
        grid["sigungu"] = joined[name_col].values
    return grid
