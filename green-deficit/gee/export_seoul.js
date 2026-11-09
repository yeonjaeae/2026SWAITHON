/**
 * 서울 여름철 NDVI · 지표면 온도(LST) · 인구(WorldPop) 내보내기
 *
 * 사용법: https://code.earthengine.google.com 에 붙여넣고 [Run] → 오른쪽 Tasks 탭에서 각 작업 [RUN]
 * 결과: Google Drive의 swaithon 폴더에 GeoTIFF 3개 → analysis/data/raw/ 로 옮기기
 *   - seoul_ndvi.tif  (10m,  EPSG:5179)
 *   - seoul_lst.tif   (30m,  EPSG:5179, 단위 °C)
 *   - seoul_pop.tif   (100m, EPSG:5179, 픽셀당 인구수)  ← SGIS 100m 격자 인구를 못 구할 때 대체용
 */

// ───── 설정 ─────
var YEARS = [2023, 2025];     // 여러 해를 합쳐 장마 구름 영향을 줄임
var MONTHS = [6, 9];          // 6~9월 (식생이 가장 무성한 시기)
var CRS = 'EPSG:5179';        // UTM-K (미터 단위, 격자와 동일)
var FOLDER = 'swaithon';

// 서울 경계 (FAO GAUL). 정확한 경계가 필요하면 행정구역 SHP를 Assets로 올려서 바꿔 쓰기
var seoul = ee.FeatureCollection('FAO/GAUL/2015/level1')
  .filter(ee.Filter.eq('ADM1_NAME', 'Seoul'));
var region = seoul.geometry();
Map.centerObject(seoul, 11);

var dateFilter = ee.Filter.and(
  ee.Filter.calendarRange(YEARS[0], YEARS[1], 'year'),
  ee.Filter.calendarRange(MONTHS[0], MONTHS[1], 'month')
);

// ───── 1. NDVI (Sentinel-2) ─────
// SCL(장면 분류) 밴드로 구름·그림자·눈 픽셀 제거
function maskS2(img) {
  var scl = img.select('SCL');
  var bad = scl.eq(3)      // 구름 그림자
    .or(scl.eq(8))         // 구름(중간 확률)
    .or(scl.eq(9))         // 구름(높은 확률)
    .or(scl.eq(10))        // 얇은 권운
    .or(scl.eq(11));       // 눈
  return img.updateMask(bad.not());
}

var ndvi = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(region)
  .filter(dateFilter)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60))
  .map(maskS2)
  .map(function (img) {
    return img.normalizedDifference(['B8', 'B4']).rename('ndvi');
  })
  .median()                // 남은 픽셀의 중앙값 → 구름 없는 합성 영상
  .clip(region);

Map.addLayer(ndvi, {min: 0, max: 0.8, palette: ['#a50026', '#fee08b', '#1a9850']}, 'NDVI');

// ───── 2. 지표면 온도 (Landsat 8/9 Collection 2 Level-2) ─────
function maskLandsat(img) {
  var qa = img.select('QA_PIXEL');
  var bad = qa.bitwiseAnd(1 << 1).neq(0)   // dilated cloud
    .or(qa.bitwiseAnd(1 << 3).neq(0))      // cloud
    .or(qa.bitwiseAnd(1 << 4).neq(0))      // cloud shadow
    .or(qa.bitwiseAnd(1 << 5).neq(0));     // snow
  return img.updateMask(bad.not());
}

function toCelsius(img) {
  // ST_B10 → 켈빈: DN * 0.00341802 + 149.0  → 섭씨: −273.15
  return img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('lst');
}

var landsat = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
  .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
  .filterBounds(region)
  .filter(dateFilter)
  .filter(ee.Filter.lt('CLOUD_COVER', 60));

var lst = landsat.map(maskLandsat).map(toCelsius).median().clip(region);

Map.addLayer(lst, {min: 25, max: 50, palette: ['#313695', '#ffffbf', '#a50026']}, 'LST (°C)');

// ───── 3. 인구 (WorldPop 100m, 대체용) ─────
var pop = ee.ImageCollection('WorldPop/GP/100m/pop')
  .filter(ee.Filter.eq('country', 'KOR'))
  .filter(ee.Filter.eq('year', 2020))
  .first()
  .rename('pop')
  .clip(region);

// ───── 내보내기 ─────
Export.image.toDrive({
  image: ndvi.toFloat(), description: 'seoul_ndvi', folder: FOLDER,
  region: region, scale: 10, crs: CRS, maxPixels: 1e10
});
Export.image.toDrive({
  image: lst.toFloat(), description: 'seoul_lst', folder: FOLDER,
  region: region, scale: 30, crs: CRS, maxPixels: 1e10
});
Export.image.toDrive({
  image: pop.toFloat(), description: 'seoul_pop', folder: FOLDER,
  region: region, scale: 100, crs: CRS, maxPixels: 1e10
});
