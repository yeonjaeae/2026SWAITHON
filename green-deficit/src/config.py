"""분석 전체에서 쓰는 설정값. 가중치·기준값을 바꾸려면 여기만 고치면 된다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
OUTPUT = ROOT / "output"

# 좌표계: 계산은 미터 단위인 UTM-K, 프론트와 주고받을 때는 위경도
CRS_CALC = "EPSG:5179"
CRS_WEB = "EPSG:4326"

CELL_SIZE = 100            # 격자 한 변 (m)
CELL_AREA = CELL_SIZE ** 2  # 10,000㎡ = 1ha

# 정규화: 극단값 영향을 줄이기 위해 5~95 퍼센타일 기준 min-max
NORM_PCT = (5, 95)

# 공원 접근성: 이 거리 이상이면 "접근성 부족" 최대(1.0). 근린공원 서비스 반경 기준
PARK_SERVICE_RADIUS = 500  # m

# 이보다 작은 공원 폴리곤은 제외 (OSM에 화단·놀이터 등 작은 조각이 공원으로 잡혀 있어서)
# 서울 OSM 기준 3,307개 중 982개가 제외되지만 면적은 전체의 0.8%뿐. 포인트 데이터는 그대로 둔다.
PARK_MIN_AREA = 1_000      # ㎡

# 우선순위 계산에서 제외할 격자 (사람이 거의 살지 않는 산지·하천 등)
MIN_POP = 1.0

# 녹지 부족지수 = 녹지 부족(1−NDVI) · 공원 접근성 부족의 가중합
DEFICIT_WEIGHTS = {"green_short": 0.6, "park_far": 0.4}

# 우선순위 = 녹지 부족지수 · 열 위험 · 인구 수요의 가중합 (API에서 바꿀 수 있음)
PRIORITY_WEIGHTS = {"deficit": 0.4, "heat": 0.3, "pop": 0.3}

# 1인당 녹지 면적 비교 기준 (WHO 권장)
GREEN_PER_CAPITA_TARGET = 9.0  # ㎡/인

# 영역 분석에서 녹지 확충 우선 구역으로 표시할 조건
CANDIDATE_MIN_DIST = 250   # 녹지에서 이 거리(m) 이상 떨어진 주택가
CANDIDATE_MIN_HEAT = 0.6   # 그리고 열 위험(정규화) 이 값 이상인 곳
