import requests
import json
import random
from datetime import date, timedelta

BASE_URL = "http://127.0.0.1:12344"

def log(msg, success=True):
    icon = "🌱" if success else "❌"
    print(f"{icon} {msg}")

def seed_data():
    print(f"Seeding data to {BASE_URL}...\n")

    # 1. Create Category Groups
    groups = [
        {"name": "Housing", "sort_order": 1},
        {"name": "Food", "sort_order": 2},
        {"name": "Transportation", "sort_order": 3},
        {"name": "Lifestyle", "sort_order": 4}
    ]
    
    created_groups = []
    
    for g in groups:
        try:
            r = requests.post(f"{BASE_URL}/category-groups", json=g)
            if r.status_code == 201:
                created_groups.append(r.json())
                log(f"Created Group: {g['name']}")
            else:
                log(f"Failed Group {g['name']}: {r.status_code} {r.text}", False)
        except Exception as e:
            log(f"Error Group {g['name']}: {e}", False)

    if not created_groups:
        print("No groups created. Exiting.")
        return

    # 2. Create Categories
    # Map group name to ID
    group_map = {g['name']: g['category_group_id'] for g in created_groups}
    
    categories = [
        {"name": "Rent/Mortgage", "group_id": group_map.get("Housing"), "type": "expense"},
        {"name": "Electricity", "group_id": group_map.get("Housing"), "type": "expense"},
        {"name": "Groceries", "group_id": group_map.get("Food"), "type": "expense"},
        {"name": "Restaurants", "group_id": group_map.get("Food"), "type": "expense"},
        {"name": "Gas", "group_id": group_map.get("Transportation"), "type": "expense"},
        {"name": "Car Maintenance", "group_id": group_map.get("Transportation"), "type": "expense"},
        {"name": "Hobbies", "group_id": group_map.get("Lifestyle"), "type": "expense"},
    ]
    
    created_cats = []
    
    for c in categories:
        if not c['group_id']: continue
        try:
            r = requests.post(f"{BASE_URL}/categories", json=c)
            if r.status_code == 201:
                created_cats.append(r.json())
                log(f"Created Category: {c['name']}")
            else:
                log(f"Failed Category {c['name']}: {r.status_code} {r.text}", False)
        except Exception as e:
            log(f"Error Category {c['name']}: {e}", False)

    # 3. Create Account (Manual)
    account_payload = {
        "name": "Manual Checking",
        "type": "depository",
        "subtype": "checking",
        "current_balance": 1500.50,
        "currency": "USD",
        "is_active": True
    }
    
    account_id = None
    try:
        r = requests.post(f"{BASE_URL}/accounts/", json=account_payload)
        if r.status_code == 201:
            acc = r.json()
            account_id = acc['account_id']
            log(f"Created Account: {acc['name']}")
        else:
            log(f"Failed Account: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"Error Account: {e}", False)

    if not account_id:
        print("No account created. Exiting.")
        return

    # 4. Create Transactions
    # Create some transactions, some categorized, some uncategorized
    
    cat_map = {c['name']: c['category_id'] for c in created_cats}
    
    txns = [
        {
            "account_id": account_id,
            "amount": 1200.00,
            "date": str(date.today()),
            "description": "Luxury Apartments Rent",
            "category_id": cat_map.get("Rent/Mortgage")
        },
        {
            "account_id": account_id,
            "amount": 150.25,
            "date": str(date.today() - timedelta(days=1)),
            "description": "Whole Foods",
            "category_id": cat_map.get("Groceries")
        },
        {
            "account_id": account_id,
            "amount": 45.00,
            "date": str(date.today() - timedelta(days=2)),
            "description": "Shell Gas Station",
            "category_id": cat_map.get("Gas")
        },
        {
            "account_id": account_id,
            "amount": 85.00,
            "date": str(date.today() - timedelta(days=3)),
            "description": "Unknown Charge",
            "category_id": None # Uncategorized
        }
    ]
    
    for t in txns:
        try:
            r = requests.post(f"{BASE_URL}/transactions/", json=t)
            if r.status_code == 201:
                log(f"Created Transaction: {t['description']}")
            else:
                log(f"Failed Transaction {t['description']}: {r.status_code} {r.text}", False)
        except Exception as e:
            log(f"Error Transaction {t['description']}: {e}", False)

    print("\nSeed Complete.")

if __name__ == "__main__":
    seed_data()
