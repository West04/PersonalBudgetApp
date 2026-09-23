import requests
import uuid
from datetime import date

BASE_URL = "http://127.0.0.1:12344"

def test_create_budget():
    # 1. Get a category ID
    r = requests.get(f"{BASE_URL}/category-groups")
    groups = r.json()
    cat_id = groups[0]['categories'][0]['category_id']
    
    # 2. Try to POST budget without trailing slash
    payload = {
        "budget_month": "2026-01-01",
        "planned_amount": 100.00,
        "category_id": cat_id
    }
    print(f"Testing POST /budget with payload: {payload}")
    r = requests.post(f"{BASE_URL}/budget", json=payload)
    print(f"POST /budget status: {r.status_code}")
    print(f"POST /budget body: {r.text}")

    # 3. Try to POST budget with trailing slash
    r = requests.post(f"{BASE_URL}/budget/", json=payload)
    print(f"POST /budget/ status: {r.status_code}")
    # print(f"POST /budget/ body: {r.text}")

if __name__ == "__main__":
    test_create_budget()
