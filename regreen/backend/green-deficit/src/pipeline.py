"""격자 생성 → 지표 계산 → 정규화 → 지수 계산 → output/ 에 저장.

실행 예:
  python -m src.pipeline --dir data/raw/서울          # fetch_public_data.py 로 받은 공개 데이터
  python -m src.pipeline --boundary data/raw/seoul_gu.shp --name-col SIG_KOR_NM \
      --ndvi data/raw/seoul_ndvi.tif --lst data/raw/seoul_lst.tif \
      --pop data/raw/seoul_pop.tif --parks data/raw/parks.gpkg

인구는 래스터(.tif, 픽셀값=인구수)나 폴리곤(--pop-col 로 인구 컬럼 지정) 둘 다 된다.
공원은 폴리곤(공원 경계)이나 포인트(공원 위치) 둘 다 된다.
"""
import argparse
import json
import time
from pathlib import Path

import geopandas as gpd

from . import config, features, grid as grid_mod, index

OUT_GRID = config.OUTPUT / "grid_index.gpkg"
OUT_PARKS = config.OUTPUT / "parks.gpkg"
OUT_PARAMS = config.OUTPUT / "norm_params.json"


def run(boundary, ndvi, lst, pop, parks, name_col=None, pop_col=None,
        out_dir: Path = config.OUTPUT):
    t0 = time.time()

    def log(msg):
        print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)

    log("격자 생성")
    bnd = gpd.read_file(boundary)
    g = grid_mod.make_grid(bnd, name_col=name_col)
    log(f"  격자 {len(g):,}개")

    log("NDVI 평균")
    g["ndvi"] = features.raster_zonal(g, ndvi, "mean")
    log("지표면 온도 평균")
    g["lst"] = features.raster_zonal(g, lst, "mean")

    log("인구")
    if str(pop).lower().endswith((".tif", ".tiff")):
        g["pop"] = features.raster_zonal(g, pop, "sum")
    else:
        if not pop_col:
            raise SystemExit("폴리곤 인구 데이터는 --pop-col 로 인구 컬럼을 지정해야 합니다")
        g["pop"] = features.vector_population(g, gpd.read_file(pop), pop_col)

    log("공원까지 거리")
    parks_gdf = gpd.read_file(parks).to_crs(config.CRS_CALC)
    is_poly = parks_gdf.geom_type.isin(["Polygon", "MultiPolygon"])
    small = is_poly & (parks_gdf.area < config.PARK_MIN_AREA)
    parks_gdf = parks_gdf[~small]
    log(f"  공원 {len(parks_gdf):,}개 사용 ({config.PARK_MIN_AREA:,}㎡ 미만 {small.sum():,}개 제외)")
    g["park_dist"] = features.park_distance(g, parks_gdf)

    log("정규화 · 지수 계산")
    params = index.fit_norm(g)
    g = index.score_grid(g, params)

    log("저장")
    g.to_file(out_dir / OUT_GRID.name, layer="grid", driver="GPKG")
    parks_gdf[["geometry"]].to_file(out_dir / OUT_PARKS.name, layer="parks", driver="GPKG")
    (out_dir / OUT_PARAMS.name).write_text(
        json.dumps({"norm": params,
                    "deficit_weights": config.DEFICIT_WEIGHTS,
                    "priority_weights": config.PRIORITY_WEIGHTS},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    valid = g["priority_score"].notna()
    log(f"완료: 격자 {len(g):,}개 (우선순위 대상 {valid.sum():,}개) → {out_dir}")
    print(g.loc[valid, ["ndvi", "lst", "pop", "park_dist",
                        "deficit_index", "priority_score"]].describe().round(3))
    return g


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", help="fetch_public_data.py 결과 폴더 (예: data/raw/서울)")
    p.add_argument("--boundary")
    p.add_argument("--name-col", help="경계 파일의 행정구역 이름 컬럼 (예: SIG_KOR_NM)")
    p.add_argument("--ndvi")
    p.add_argument("--lst")
    p.add_argument("--pop")
    p.add_argument("--pop-col")
    p.add_argument("--parks")
    a = p.parse_args()

    if a.dir:
        s = Path(a.dir)
        run(s / "boundary.gpkg", s / "ndvi.tif", s / "lst.tif", s / "pop.tif",
            s / "parks.gpkg", name_col="sigungu")
    else:
        missing = [k for k in ("boundary", "ndvi", "lst", "pop", "parks") if not getattr(a, k)]
        if missing:
            p.error("필요한 입력: " + ", ".join("--" + m for m in missing))
        run(a.boundary, a.ndvi, a.lst, a.pop, a.parks, a.name_col, a.pop_col)


if __name__ == "__main__":
    main()
