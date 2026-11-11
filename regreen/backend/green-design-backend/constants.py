
# 시연용 가정 계수 (실측 또는 검증된 계수 아님)

# 연간 탄소 흡수량
# 잔디/관목: kg CO2 / m² / year
# 교목: kg CO2 / tree / year
CARBON_FACTORS = {
    "grass": 0.5,
    "shrub": 1.5,
    "tree": 10.0
}

# 조성 비용 (KRW)
# 잔디/관목: 원 / m²
# 교목: 원 / 주
COST_FACTORS = {
    "grass": 15000,
    "shrub": 40000,
    "tree": 300000
}
