
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

BASE_DATA = {
    "candidate_id": "site_001",
    "total_area": 1000,
    "green_ratio": 40,
    "protected_area": 300,
    "vegetation": {
        "grass": 50,
        "shrub": 30,
        "tree": 20
    }
}


def test_normal_design():
    response = client.post(
        "/api/design/calculate",
        json=BASE_DATA
    )

    assert response.status_code == 200

    result = response.json()

    assert result["green_area"] == 400
    assert result["vegetation_area"]["grass"] == 200
    assert result["vegetation_area"]["shrub"] == 120
    assert result["vegetation_area"]["tree"] == 80
    assert result["plant_count"]["tree"] == 5

    effect = result["environmental_effect"]

    assert effect["carbon_absorption"]["total"] == 330
    assert effect["estimated_cost"]["total"] == 9300000


def test_excessive_green_ratio():
    data = BASE_DATA.copy()
    data["green_ratio"] = 90

    response = client.post(
        "/api/design/calculate",
        json=data
    )

    assert response.status_code == 200

    result = response.json()

    assert result["green_area"] == 700
    assert result["feasible"] is False
    assert len(result["warnings"]) > 0


def test_invalid_vegetation_ratio():
    data = {
        **BASE_DATA,
        "vegetation": {
            "grass": 50,
            "shrub": 30,
            "tree": 30
        }
    }

    response = client.post(
        "/api/design/calculate",
        json=data
    )

    assert response.status_code == 422


def test_invalid_protected_area():
    data = {
        **BASE_DATA,
        "protected_area": 1200
    }

    response = client.post(
        "/api/design/calculate",
        json=data
    )

    assert response.status_code == 400


def test_ai_design_data():
    response = client.post(
        "/api/design/calculate",
        json=BASE_DATA
    )

    assert response.status_code == 200

    result = response.json()
    ai_data = result["ai_design_data"]

    assert ai_data["green_area_m2"] == 400
    assert ai_data["plant_count"]["tree"] == 5
    assert ai_data["protected_area_m2"] == 300
