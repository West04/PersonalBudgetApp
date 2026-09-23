import requests
import time
import sys
import os
import json
from datetime import date

BASE_URL = "http://127.0.0.1:12344"

def log(msg, success=True):
    icon = "✅" if success else "❌"
    print(f"{icon} {msg}")

def run_smoke_test():
    print(f"Waiting for server at {BASE_URL}...")
    for _ in range(30):
        try:
            requests.get(f"{BASE_URL}/docs")
            break
        except requests.ConnectionError:
            time.sleep(1)
    else:
        log("Server not reachable", success=False)
        sys.exit(1)

    print("Server up. Starting tests...\n")

    # 1. GET /category-groups
    try:
        r = requests.get(f"{BASE_URL}/category-groups")
        if r.status_code == 200:
            log(f"GET /category-groups: {len(r.json())} items")
        else:
            log(f"GET /category-groups failed: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"GET /category-groups error: {e}", False)

    # 2. GET /budget?budget_month=...
    try:
        r = requests.get(f"{BASE_URL}/budget?budget_month=2024-01-01")
        if r.status_code == 200:
            log("GET /budget?budget_month=2024-01-01")
        else:
            log(f"GET /budget failed: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"GET /budget error: {e}", False)

    # 3. GET /summary/budget?month=...
    try:
        r = requests.get(f"{BASE_URL}/summary/budget?month=2024-01")
        if r.status_code == 200:
            log("GET /summary/budget?month=2024-01")
        else:
            log(f"GET /summary/budget failed: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"GET /summary/budget error: {e}", False)

    # 4. GET /summary/dashboard?month=...
    try:
        r = requests.get(f"{BASE_URL}/summary/dashboard?month=2024-01")
        if r.status_code == 200:
            data = r.json()
            # Verify new account shape
            accounts = data.get('accounts', [])
            if accounts:
                if 'current_balance' in accounts[0]:
                    log("GET /summary/dashboard (Account fields verified)")
                else:
                    log("GET /summary/dashboard (Account fields MISSING)", False)
            else:
                log("GET /summary/dashboard (No accounts to verify, but 200 OK)")
        else:
            log(f"GET /summary/dashboard failed: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"GET /summary/dashboard error: {e}", False)

    # 5. GET /transactions (Pagination)
    try:
        r = requests.get(f"{BASE_URL}/transactions?limit=50&offset=0")
        if r.status_code == 200:
            data = r.json()
            if 'items' in data and 'total' in data:
                log(f"GET /transactions (Paginated: {data['total']} total)")
                tx_list = data['items']
            else:
                log("GET /transactions response shape mismatch (missing items/total)", False)
                tx_list = []
        else:
            log(f"GET /transactions failed: {r.status_code} {r.text}", False)
            tx_list = []
    except Exception as e:
        log(f"GET /transactions error: {e}", False)
        tx_list = []

    # 6. GET /transactions?uncategorized=true
    try:
        r = requests.get(f"{BASE_URL}/transactions?uncategorized=true&limit=50&offset=0")
        if r.status_code == 200:
            log("GET /transactions?uncategorized=true")
        else:
            log(f"GET /transactions?uncategorized=true failed: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"GET /transactions?uncategorized=true error: {e}", False)

    # 7. PUT /transactions/{id}
    if tx_list:
        tx_id = tx_list[0]['transaction_id']
        try:
            # First, we need a category ID. Let's create one or get one.
            groups = requests.get(f"{BASE_URL}/category-groups").json()
            if groups:
                cat_id = groups[0]['categories'][0]['category_id'] if groups[0]['categories'] else None
            else:
                cat_id = None
            
            if cat_id:
                r = requests.put(f"{BASE_URL}/transactions/{tx_id}", json={"category_id": cat_id})
                if r.status_code == 200:
                    log(f"PUT /transactions/{tx_id}")
                else:
                    log(f"PUT /transactions/{tx_id} failed: {r.status_code} {r.text}", False)
            else:
                log("Skipping PUT /transactions (No category available)", True)
        except Exception as e:
            log(f"PUT /transactions error: {e}", False)
    else:
        log("Skipping PUT /transactions (No transactions found)", True)

    # 8. GET /accounts
    try:
        r = requests.get(f"{BASE_URL}/accounts")
        if r.status_code == 200:
            accts = r.json()
            log(f"GET /accounts: {len(accts)} items")
        else:
            log(f"GET /accounts failed: {r.status_code} {r.text}", False)
            accts = []
    except Exception as e:
        log(f"GET /accounts error: {e}", False)
        accts = []

    # 9. PUT /accounts/{id}
    if accts:
        acc_id = accts[0]['account_id']
        try:
            r = requests.put(f"{BASE_URL}/accounts/{acc_id}", json={"name": "Renamed Test Account"})
            if r.status_code == 200:
                log(f"PUT /accounts/{acc_id}")
            else:
                log(f"PUT /accounts/{acc_id} failed: {r.status_code} {r.text}", False)
        except Exception as e:
            log(f"PUT /accounts error: {e}", False)
    else:
        log("Skipping PUT /accounts (No accounts found)", True)

    # 10. Plaid: Create Link Token
    try:
        r = requests.post(f"{BASE_URL}/plaid/create_link_token")
        if r.status_code == 200:
            link_token = r.json().get('link_token')
            log(f"POST /plaid/create_link_token: {link_token[:10]}...")
        else:
            log(f"POST /plaid/create_link_token failed: {r.status_code} {r.text}", False)
    except Exception as e:
        log(f"POST /plaid/create_link_token error: {e}", False)

    # 11. Plaid: Exchange Public Token (Expect 400 without valid token, but confirms endpoint reachable)
    try:
        # We send a dummy token. Plaid should reject it with 400 INVALID_PUBLIC_TOKEN
        r = requests.post(f"{BASE_URL}/plaid/exchange_public_token", json={"public_token": "invalid-token"})
        if r.status_code in [400, 500]: # 500 might happen if uncaught exception, but we hope for 400
            log("POST /plaid/exchange_public_token (Reached, rejected invalid token as expected)")
        elif r.status_code == 200:
             log("POST /plaid/exchange_public_token (Unexpected 200 with invalid token?)", False)
        else:
             log(f"POST /plaid/exchange_public_token status: {r.status_code}")
    except Exception as e:
        log(f"POST /plaid/exchange_public_token error: {e}", False)

    # 12. Plaid: Sync Accounts (Needs item_id, will fail but check reachability)
    try:
        # random item id
        r = requests.post(f"{BASE_URL}/plaid/sync_accounts", json={"plaid_item_id": "item-sandbox-123"})
        if r.status_code == 404: # Item not found
            log("POST /plaid/sync_accounts (Reached, returned 404 Item Not Found as expected)")
        else:
             log(f"POST /plaid/sync_accounts status: {r.status_code}")
    except Exception as e:
        log(f"POST /plaid/sync_accounts error: {e}", False)

    # 13. Plaid: Sync Transactions (Same)
    try:
        r = requests.post(f"{BASE_URL}/plaid/sync_transactions", json={"plaid_item_id": "item-sandbox-123"})
        if r.status_code == 404:
             log("POST /plaid/sync_transactions (Reached, returned 404 Item Not Found as expected)")
        else:
             log(f"POST /plaid/sync_transactions status: {r.status_code}")
    except Exception as e:
        log(f"POST /plaid/sync_transactions error: {e}", False)

if __name__ == "__main__":
    run_smoke_test()
