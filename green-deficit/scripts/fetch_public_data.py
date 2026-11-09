"""공개 데이터로 서울 25개 구 전체의 입력 데이터를 받는다. 계정 없이 동작.

  boundary.gpkg  구 경계          OpenStreetMap (Nominatim)
  parks.gpkg     공원 경계        OpenStreetMap (Overpass, leisure=park), 경계 밖 1km까지
  ndvi.tif       10m  여름 NDVI   Sentinel-2 L2A (Microsoft Planetary Computer)
  lst.tif        30m  여름 지표면 온도(°C)  Landsat 8/9 C2 L2 (Planetary Computer)
  pop.tif        100m 인구        WorldPop 2020 (constrained)

실행: python scripts/fetch_public_data.py, 
결과: data/raw/서울/
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import httpx
import numpy as np
import planetary_computer
import pystac_client
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config  # noqa: E402

UA = {"User-Agent": "swaithon-green-deficit/0.1 (hackathon research)"}
YEARS = [2023, 2024, 2025]
SUMMER = ("06-01", "09-30")
PARK_BUFFER = 1000           # 경계 밖 공원도 접근성 계산에 필요
RASTER_BUFFER = 300          # 경계 바깥쪽 여유
WORLDPOP_URLS = [   # 건물이 있는 곳에만 인구를 배분한 constrained 판 우선 (12.8MB)
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/KOR/kor_ppp_2020_constrained.tif",
    "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/KOR/kor_ppp_2020.tif",
]
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4",
                GDAL_HTTP_RETRY_DELAY="2", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF")

t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


# ───────── 경계 · 공원 (OSM) ─────────
SEOUL_GU = ["종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구",
            "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구",
            "구로구", "금천구", "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구"]


def _one_gu(gu: str):
    r = httpx.get("https://nominatim.openstreetmap.org/search", headers=UA, timeout=60,
                  params={"q": f"{gu}, 서울특별시", "polygon_geojson": 1,
                          "format": "jsonv2", "limit": 10})
    r.raise_for_status()
    # "중구"처럼 다른 도시에도 있는 이름이 있어 서울 결과만 고른다
    hits = [h for h in r.json()
            if h.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon")
            and "서울" in h.get("display_name", "")]
    if not hits:
        raise SystemExit(f"'{gu}' 경계를 찾지 못했습니다")
    return shape(hits[0]["geojson"])


def fetch_boundary(out: Path) -> gpd.GeoDataFrame:
    """서울 25개 구 경계."""
    names = SEOUL_GU
    geoms = []
    for i, name in enumerate(names):
        if i:
            time.sleep(1.1)          # Nominatim 이용 정책: 초당 1회
        geoms.append(_one_gu(name))
    gdf = gpd.GeoDataFrame({"sigungu": names}, geometry=geoms, crs=4326).to_crs(config.CRS_CALC)
    gdf.to_file(out / "boundary.gpkg", driver="GPKG")
    log(f"경계: {len(gdf)}개 구, 면적 {gdf.area.sum() / 1e6:.2f}㎢")
    return gdf


def fetch_parks(boundary: gpd.GeoDataFrame, out: Path) -> gpd.GeoDataFrame:
    w, s, e, n = transform_bounds(config.CRS_CALC, 4326,
                                  *boundary.buffer(PARK_BUFFER).total_bounds)
    q = f"""[out:json][timeout:180];
        (way["leisure"="park"]({s},{w},{n},{e}); relation["leisure"="park"]({s},{w},{n},{e}););
        out geom;"""
    r = httpx.post("https://overpass-api.de/api/interpreter", data={"data": q},
                   headers=UA, timeout=240)
    r.raise_for_status()
    rows = []
    for el in r.json()["elements"]:
        name = el.get("tags", {}).get("name")
        if el["type"] == "way" and len(el.get("geometry", [])) >= 4:
            ring = [(p["lon"], p["lat"]) for p in el["geometry"]]
            if ring[0] == ring[-1]:
                rows.append((name, shapely.Polygon(ring)))
        elif el["type"] == "relation":
            lines = [shapely.LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
                     for m in el.get("members", [])
                     if m.get("role") == "outer" and len(m.get("geometry", [])) >= 2]
            polys = list(shapely.polygonize(lines).geoms) if lines else []
            if polys:
                rows.append((name, shapely.union_all(polys)))
    gdf = gpd.GeoDataFrame({"name": [r[0] for r in rows]}, geometry=[r[1] for r in rows],
                           crs=4326).to_crs(config.CRS_CALC)
    gdf["geometry"] = gdf.geometry.make_valid()
    gdf = gdf[gdf.geometry.area > 0]
    gdf.to_file(out / "parks.gpkg", driver="GPKG")
    log(f"공원: {len(gdf)}개, 총 {gdf.area.sum() / 1e6:.2f}㎢")
    return gdf


# ───────── 위성영상 (Planetary Computer) ─────────
def target_grid(boundary, res):
    minx, miny, maxx, maxy = boundary.buffer(RASTER_BUFFER).total_bounds
    minx, miny = np.floor(minx / res) * res, np.floor(miny / res) * res
    maxx, maxy = np.ceil(maxx / res) * res, np.ceil(maxy / res) * res
    w, h = int((maxx - minx) / res), int((maxy - miny) / res)
    return from_origin(minx, maxy, res, res), (h, w)


def search(collection, bbox, extra):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=planetary_computer.sign_inplace)
    items = []
    for y in YEARS:
        items += cat.search(collections=[collection], bbox=bbox,
                            datetime=f"{y}-{SUMMER[0]}/{y}-{SUMMER[1]}",
                            query=extra).item_collection()
    return items


def read_into(href, transform, shape_, resampling=Resampling.nearest):
    """원격 COG에서 필요한 범위만 읽어 목표 격자(EPSG:5179)로 재투영."""
    dst = np.zeros(shape_, dtype="float32")
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as src:
        l, b, r, t = transform_bounds(config.CRS_CALC, src.crs,
                                      transform.c, transform.f + transform.e * shape_[0],
                                      transform.c + transform.a * shape_[1], transform.f)
        win = from_bounds(l, b, r, t, src.transform).round_offsets().round_lengths()
        data = src.read(1, window=win, boundless=True, fill_value=0)
        reproject(data, dst, src_transform=src.window_transform(win), src_crs=src.crs,
                  dst_transform=transform, dst_crs=config.CRS_CALC,
                  src_nodata=0, dst_nodata=0, resampling=resampling)
    return dst


def composite_tiled(items, fn, transform, shape_, label, max_px=2_000_000):
    """범위가 크면(서울 전체 등) 가로 띠로 나눠 처리해 메모리 사용을 제한한다.
    장면 40개 × 띠 200만 픽셀 × 4바이트 ≈ 320MB."""
    rows = max(1, max_px // shape_[1])
    if rows >= shape_[0]:
        return composite(items, fn, transform, shape_, label)
    out = np.full(shape_, np.nan, dtype="float32")
    n = -(-shape_[0] // rows)
    for k, r0 in enumerate(range(0, shape_[0], rows), 1):
        h = min(rows, shape_[0] - r0)
        tr = transform * rasterio.Affine.translation(0, r0)
        out[r0:r0 + h] = composite(items, fn, tr, (h, shape_[1]), f"{label} [{k}/{n}]")
    return out


def composite(items, fn, transform, shape_, label):
    """장면마다 fn(item) → 마스크된 배열, 그 중앙값."""
    stack = []

    def work(it):
        try:
            return fn(it, transform, shape_)
        except Exception as e:  # 장면 하나 실패해도 계속
            print(f"  건너뜀 {it.id}: {e}", flush=True)
            return None

    with ThreadPoolExecutor(8) as ex:
        for i, a in enumerate(ex.map(work, items), 1):
            if a is not None and np.isfinite(a).mean() > 0.05:
                stack.append(a)
            if i % 20 == 0:
                log(f"  {label}: {i}/{len(items)} 장면 처리")
    if not stack:
        log(f"{label}: 사용할 수 있는 장면이 없습니다 (빈 값으로 둠)")
        return np.full(shape_, np.nan, dtype="float32")
    arr = np.stack(stack)
    valid = np.isfinite(arr).sum(0)
    with np.errstate(all="ignore"):
        med = np.nanmedian(arr, axis=0)
    log(f"{label}: 장면 {len(stack)}개 사용, 픽셀당 유효 관측 중앙값 {int(np.median(valid))}회")
    return med.astype("float32")


def s2_ndvi(item, transform, shape_):
    b4 = read_into(item.assets["B04"].href, transform, shape_)
    b8 = read_into(item.assets["B08"].href, transform, shape_)
    scl = read_into(item.assets["SCL"].href, transform, shape_)
    # 2022-01-25 이후 처리 기준(baseline 04.00+)은 반사율에 +1000 오프셋이 있다
    off = 1000.0 if float(item.properties.get("s2:processing_baseline", "05.00")) >= 4 else 0.0
    red, nir = b4 - off, b8 - off
    bad = np.isin(scl, [0, 1, 3, 8, 9, 10, 11]) | (b4 == 0) | (b8 == 0)
    with np.errstate(all="ignore"):
        ndvi = (nir - red) / (nir + red)
    ndvi[bad | ~np.isfinite(ndvi)] = np.nan
    return np.clip(ndvi, -1, 1)


def landsat_lst(item, transform, shape_):
    st = read_into(item.assets["lwir11"].href, transform, shape_)
    qa = read_into(item.assets["qa_pixel"].href, transform, shape_).astype("uint16")
    bad = ((qa & (1 << 1)) | (qa & (1 << 3)) | (qa & (1 << 4)) | (qa & (1 << 5))) > 0
    lst = st * 0.00341802 + 149.0 - 273.15
    lst[bad | (st == 0)] = np.nan
    return lst


def write_tif(path, arr, transform, crs=config.CRS_CALC):
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1],
                       count=1, dtype="float32", crs=crs, transform=transform,
                       nodata=np.nan, compress="deflate") as dst:
        dst.write(arr.astype("float32"), 1)


# ───────── 인구 (WorldPop) ─────────
def fetch_pop(boundary, out: Path):
    bbox = transform_bounds(config.CRS_CALC, 4326, *boundary.buffer(RASTER_BUFFER).total_bounds)
    last = None
    cache = config.DATA_RAW / "_downloads"
    cache.mkdir(parents=True, exist_ok=True)
    for url in WORLDPOP_URLS:
        try:
            # WorldPop 서버는 부분 읽기(Range)를 지원하지 않아 파일 전체를 받아 둔다 (한 번만)
            local = cache / url.rsplit("/", 1)[-1]
            if not local.exists():
                tmp = local.with_suffix(".part")
                with httpx.stream("GET", url, headers=UA, timeout=300,
                                  follow_redirects=True) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
                tmp.rename(local)
                log(f"  다운로드 {local.name} ({local.stat().st_size / 1e6:.1f}MB)")
            with rasterio.open(local) as src:
                win = from_bounds(*bbox, src.transform).round_offsets().round_lengths()
                data = src.read(1, window=win, masked=True).filled(0).astype("float32")
                data[data < 0] = 0
                write_tif(out / "pop.tif", data, src.window_transform(win), src.crs)
            log(f"인구: {url.rsplit('/', 1)[-1]}  범위 내 합계 {data.sum():,.0f}명")
            return
        except Exception as e:
            last = e
            print(f"  실패 {url}: {e}", flush=True)
    raise SystemExit(f"WorldPop 인구를 받지 못했습니다: {last}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--skip", nargs="*", default=[],
                   choices=["boundary", "parks", "ndvi", "lst", "pop"])
    a = p.parse_args()
    out = config.DATA_RAW / "서울"
    out.mkdir(parents=True, exist_ok=True)

    bnd = (gpd.read_file(out / "boundary.gpkg") if "boundary" in a.skip
           else fetch_boundary(out))
    if "parks" not in a.skip:
        fetch_parks(bnd, out)
    bbox = list(transform_bounds(config.CRS_CALC, 4326, *bnd.total_bounds))

    if "ndvi" not in a.skip:
        items = search("sentinel-2-l2a", bbox, {"eo:cloud_cover": {"lt": 60}})
        log(f"Sentinel-2: 여름 장면 {len(items)}개 검색")
        tr, shp = target_grid(bnd, 10)
        write_tif(out / "ndvi.tif", composite_tiled(items, s2_ndvi, tr, shp, "NDVI"), tr)

    if "lst" not in a.skip:
        items = search("landsat-c2-l2", bbox, {"eo:cloud_cover": {"lt": 60},
                                               "platform": {"in": ["landsat-8", "landsat-9"]}})
        log(f"Landsat: 여름 장면 {len(items)}개 검색")
        tr, shp = target_grid(bnd, 30)
        write_tif(out / "lst.tif", composite_tiled(items, landsat_lst, tr, shp, "지표면 온도"), tr)

    if "pop" not in a.skip:
        fetch_pop(bnd, out)

    (out / "SOURCES.json").write_text(json.dumps({
        "boundary": "OpenStreetMap (Nominatim) © OpenStreetMap contributors, ODbL",
        "parks": "OpenStreetMap leisure=park © OpenStreetMap contributors, ODbL",
        "ndvi": f"Sentinel-2 L2A median, {YEARS} {SUMMER}, Microsoft Planetary Computer",
        "lst": f"Landsat 8/9 C2 L2 ST_B10 median, {YEARS} {SUMMER}, Microsoft Planetary Computer",
        "pop": "WorldPop 2020 (CC BY 4.0)",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"완료 → {out}")


if __name__ == "__main__":
    main()
