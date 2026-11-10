
from constants import CARBON_FACTORS, COST_FACTORS


def calculate_environmental_effect(
    grass_area: float,
    shrub_area: float,
    tree_count: int
):
    # 연간 탄소 흡수량 추정 (kg CO2/year)
    grass_carbon = grass_area * CARBON_FACTORS["grass"]
    shrub_carbon = shrub_area * CARBON_FACTORS["shrub"]
    tree_carbon = tree_count * CARBON_FACTORS["tree"]

    total_carbon = (
        grass_carbon + shrub_carbon + tree_carbon
    )

    # 녹지 조성 예상 비용 (KRW)
    grass_cost = grass_area * COST_FACTORS["grass"]
    shrub_cost = shrub_area * COST_FACTORS["shrub"]
    tree_cost = tree_count * COST_FACTORS["tree"]

    total_cost = grass_cost + shrub_cost + tree_cost

    return {
        "carbon_absorption": {
            "grass": round(grass_carbon, 2),
            "shrub": round(shrub_carbon, 2),
            "tree": round(tree_carbon, 2),
            "total": round(total_carbon, 2),
            "unit": "kg CO2/year"
        },
        "estimated_cost": {
            "grass": round(grass_cost),
            "shrub": round(shrub_cost),
            "tree": round(tree_cost),
            "total": round(total_cost),
            "currency": "KRW"
        },
        "estimate_note": (
            "시연용 가정 계수 기반 추정값이며 "
            "실제 환경 효과 및 시공 견적이 아닙니다."
        )
    }
