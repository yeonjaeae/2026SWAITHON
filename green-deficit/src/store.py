"""분석 결과를 읽어 오는 곳.

지금은 output/ 의 GeoPackage 파일을 메모리에 올려서 쓴다.
PostGIS 담당자가 DB를 만들면 이 클래스만 DB를 읽도록 바꾸면 되고, API·영역 분석 코드는 그대로 둔다.
(예: gpd.read_postgis("SELECT * FROM grid_cell", engine, geom_col="geom"))
"""
import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyproj
import shapely

from . import config


class GridStore:
    def __init__(self, out_dir: Path = config.OUTPUT):
        self.grid = gpd.read_file(out_dir / "grid_index.gpkg", layer="grid")
        self.grid = self.grid.to_crs(config.CRS_CALC).set_index("cell_id", drop=False)
        self.parks = gpd.read_file(out_dir / "parks.gpkg", layer="parks").to_crs(config.CRS_CALC)
        meta = json.loads((out_dir / "norm_params.json").read_text(encoding="utf-8"))
        self.params = meta["norm"]

        # 격자 좌표 키: (x // 100, y // 100) → cell_id. 점이 어느 격자에 있는지 바로 찾기용
        b = self.grid.geometry.bounds
        gx = np.floor(b["minx"] / config.CELL_SIZE).astype(np.int64)
        gy = np.floor(b["miny"] / config.CELL_SIZE).astype(np.int64)
        self.key_to_cell = dict(zip(zip(gx, gy), self.grid["cell_id"]))

        # 위경도(4326) ↔ 미터 좌표(5179) 변환기
        self._to_calc = pyproj.Transformer.from_crs(config.CRS_WEB, config.CRS_CALC, always_xy=True)
        self._to_web = pyproj.Transformer.from_crs(config.CRS_CALC, config.CRS_WEB, always_xy=True)

    # 좌표 변환 (shapely 도형 단위)
    def to_calc(self, geom):
        return shapely.transform(geom, lambda xy: np.column_stack(
            self._to_calc.transform(xy[:, 0], xy[:, 1])))

    def to_web(self, geom):
        return shapely.transform(geom, lambda xy: np.column_stack(
            self._to_web.transform(xy[:, 0], xy[:, 1])))

    def cells_intersecting(self, geom_calc):
        idx = self.grid.sindex.query(geom_calc, predicate="intersects")
        return self.grid.iloc[idx]

    def parks_near(self, geom_calc, buffer_m: float):
        idx = self.parks.sindex.query(geom_calc.buffer(buffer_m), predicate="intersects")
        return self.parks.iloc[idx]


@lru_cache(maxsize=1)
def get_store() -> GridStore:
    return GridStore()
