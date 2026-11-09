# 격자마다 지표 값(NDVI, 지표면 온도, 인구, 공원 거리)을 붙인다.
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize

from . import config


def raster_zonal(grid: gpd.GeoDataFrame, raster_path: str | Path,
                 stat: str = "mean") -> np.ndarray:
    """래스터를 격자 단위로 집계한다. stat = "mean" | "sum".

    픽셀 중심이 어느 격자에 속하는지로 나눈다. 격자를 래스터 위에 한 번 그린(rasterize)
    뒤 bincount로 묶기 때문에 격자 6만 개도 몇 초면 끝난다.
    sum은 모든 픽셀이 정확히 한 격자에만 들어가므로 총량(예: 인구 합계)이 보존된다.
    """
    with rasterio.open(raster_path) as src:
        band = src.read(1, masked=True).astype("float64")
        g = grid.to_crs(src.crs) if src.crs else grid
        idx = np.arange(len(g), dtype=np.int32)
        cell_index = rasterize(
            zip(g.geometry.values, idx), out_shape=src.shape,
            transform=src.transform, fill=-1, dtype="int32",
        )

    values = band.filled(np.nan)
    ok = (cell_index >= 0) & np.isfinite(values)
    ids, vals = cell_index[ok], values[ok]

    total = np.bincount(ids, weights=vals, minlength=len(grid))
    if stat == "sum":
        return total
    count = np.bincount(ids, minlength=len(grid))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def vector_population(grid: gpd.GeoDataFrame, pop: gpd.GeoDataFrame,
                      pop_col: str) -> np.ndarray:
    """폴리곤 인구 데이터(예: SGIS 100m 격자 인구, 집계구)를 면적 비율로 격자에 나눠 담는다."""
    pop = pop[[pop_col, "geometry"]].to_crs(config.CRS_CALC).copy()
    pop["_src_area"] = pop.geometry.area
    pieces = gpd.overlay(grid[["cell_id", "geometry"]], pop, how="intersection",
                         keep_geom_type=True)
    pieces["_pop"] = pieces[pop_col] * pieces.geometry.area / pieces["_src_area"]
    summed = pieces.groupby("cell_id")["_pop"].sum()
    return grid["cell_id"].map(summed).fillna(0).to_numpy()


def park_distance(grid: gpd.GeoDataFrame, parks: gpd.GeoDataFrame) -> np.ndarray:
    """격자 중심점에서 가장 가까운 공원(경계 또는 위치점)까지 직선거리(m). 공원 안이면 0."""
    parks = parks[["geometry"]].to_crs(config.CRS_CALC)
    centers = gpd.GeoDataFrame({"cell_id": grid["cell_id"].values},
                               geometry=grid.geometry.centroid, crs=config.CRS_CALC)
    near = gpd.sjoin_nearest(centers, parks, how="left", distance_col="dist")
    near = near[~near.index.duplicated()]
    return near["dist"].to_numpy()
