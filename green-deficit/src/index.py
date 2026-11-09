#정규화와 녹지 부족지수 · 우선순위 계산.
"""
격자 단위 계산(pipeline)과 드래그 영역 계산(region)이 같은 함수를 쓰므로
두 결과의 점수 기준이 항상 같다.

정규화된 지표는 모두 0~1이고 "클수록 녹지가 더 필요하다"는 방향으로 통일한다.
  green_short_n : 녹지 부족      = 1 − NDVI(정규화)
  park_far_n    : 공원 접근성 부족 = 공원까지 거리 / 500m (최대 1)
  heat_n        : 열 위험        = 지표면 온도(정규화)
  pop_n         : 인구 수요      = log(1+인구밀도)(정규화)  ← 인구는 편차가 커서 로그
"""
import numpy as np
import pandas as pd

from . import config

RAW_FOR_NORM = {
    "ndvi": lambda df: df["ndvi"].clip(lower=0),   # 물(음수)은 "식생 없음" = 0 으로
    "lst": lambda df: df["lst"],
    "pop_log": lambda df: np.log1p(df["pop"]),
}


def fit_norm(df: pd.DataFrame) -> dict:
    """정규화 기준값(퍼센타일 하한·상한)을 구한다. 영역 분석에서도 재사용하려고 저장해 둔다.

    기준은 사람이 사는 격자(우선순위 대상)로만 잡는다. 한강·산지까지 넣으면 범위가 넓어져
    주거지끼리의 차이가 묻히기 때문.
    """
    lo_p, hi_p = config.NORM_PCT
    lived = df["pop"].to_numpy() >= config.MIN_POP
    params = {}
    for name, getter in RAW_FOR_NORM.items():
        v = getter(df).to_numpy(dtype=float)[lived]
        v = v[np.isfinite(v)]
        params[name] = [float(np.percentile(v, lo_p)), float(np.percentile(v, hi_p))]
    return params


def _scale(v, lo, hi):
    v = np.asarray(v, dtype=float)
    if hi <= lo:
        return np.zeros_like(v)
    return np.clip((v - lo) / (hi - lo), 0.0, 1.0)


def components(ndvi, lst, pop, park_dist, params: dict) -> dict:
    #원시 값 → 0~1 정규화 지표. 스칼라(영역 하나)와 배열(격자 전체) 모두 받는다.
    return {
        "green_short_n": 1.0 - _scale(np.clip(np.asarray(ndvi, dtype=float), 0, None),
                                      *params["ndvi"]),
        "park_far_n": np.clip(np.asarray(park_dist, dtype=float)
                              / config.PARK_SERVICE_RADIUS, 0.0, 1.0),
        "heat_n": _scale(lst, *params["lst"]),
        "pop_n": _scale(np.log1p(np.asarray(pop, dtype=float)), *params["pop_log"]),
    }


def _normalized(weights: dict) -> dict:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("가중치 합은 0보다 커야 합니다")
    return {k: v / total for k, v in weights.items()}


def deficit_index(c: dict, weights: dict | None = None):
    w = _normalized(weights or config.DEFICIT_WEIGHTS)
    return w["green_short"] * c["green_short_n"] + w["park_far"] * c["park_far_n"]


def priority_score(deficit, heat_n, pop_n, weights: dict | None = None):
    w = _normalized(weights or config.PRIORITY_WEIGHTS)
    return w["deficit"] * deficit + w["heat"] * heat_n + w["pop"] * pop_n


def score_grid(df: pd.DataFrame, params: dict,
               priority_weights: dict | None = None) -> pd.DataFrame:
    # 격자 DataFrame에 정규화 지표 · 부족지수 · 우선순위 · 순위 컬럼을 채운다
    out = df.copy()
    c = components(out["ndvi"], out["lst"], out["pop"], out["park_dist"], params)
    for k, v in c.items():
        out[k] = v
    out["deficit_index"] = deficit_index(c)
    out["priority_score"] = priority_score(out["deficit_index"], out["heat_n"],
                                           out["pop_n"], priority_weights)
    # 사람이 거의 없는 격자(산지·하천)나 값이 없는 격자는 우선순위에서 제외
    invalid = (out["pop"] < config.MIN_POP) | out[["ndvi", "lst"]].isna().any(axis=1)
    out.loc[invalid, "priority_score"] = np.nan
    out["priority_rank"] = out["priority_score"].rank(ascending=False, method="min")
    out["priority_rank"] = out["priority_rank"].astype("Int64")
    return out
