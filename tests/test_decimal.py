import requests
import uuid
from datetime import date

BASE_URL = "http://127.0.0.1:12344"

def test_decimal_precision():
    # 1. Get a category ID
    r = requests.get(f"{BASE_URL}/category-groups")
    groups = r.json()
    cat_id = groups[0]['categories'][0]['category_id']
    
    # 2. Try to POST budget with more than 2 decimal places
    payload = {
        "budget_month": "2026-02-01",
        "planned_amount": 100.555,
        "category_id": cat_id
    }
    print(f"Testing POST /budget with 3 decimals: {payload}")
    r = requests.post(f"{BASE_URL}/budget", json=payload)
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text}")

    # 3. Try to POST budget with 2 decimal places
    payload["planned_amount"] = 100.55
    payload["budget_month"] = "2026-03-01"
    print(f"Testing POST /budget with 2 decimals: {payload}")
    r = requests.post(f"{BASE_URL}/budget", json=payload)
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text}")

if __name__ == "__main__":
    test_decimal_precision()
