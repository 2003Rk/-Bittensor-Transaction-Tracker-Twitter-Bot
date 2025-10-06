# get_txs.py
import requests
import time
from config import BASE_URL, LIMIT

def get_all_transfers(api_key: str, address: str, network: str = "finney") -> list:
    """
    Fetch transfer data for a given Bittensor address from Taostats API.

    Args:
        api_key (str): Taostats API key
        address (str): Bittensor wallet address
        network (str): Network name (default: "finney")

    Returns:
        list: JSON responses from Taostats API for TAO transfers
    """
    headers = {
        "accept": "application/json",
        "Authorization": api_key
    }

    all_data = []
    page_number = 1

    # Fetch TAO transfers
    print("🔍 Fetching TAO transfers...")
    while True:
        if page_number > 5: break
        url = f"{BASE_URL}/transfer/v1?network={network}&address={address}&limit={LIMIT}&page={page_number}"

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            break
        
        all_data.append(data)
        page_number += 1

        print(f"✔ Fetched TAO page {page_number} ✔")
        
        # Add a small delay to avoid hitting rate limits
        time.sleep(0.5)
    
    return all_data

def classify_transactions(transactions:list, treasury:str, tracked_address:str):
    """
    Remove treasury transactions and classify as Transfers In/Out.
    """
    filtered = []
    transfers_in = []
    transfers_out = []

    for page in transactions:
        if not page or not page.get("data"):
            continue
            
        for tx in page.get("data", []):
            # print(tx)
            # Each tx usually has 'from' and 'to' fields
            from_info = tx.get("from")
            to_info = tx.get("to")
            
            if not from_info or not to_info:
                continue
                
            from_addr = from_info.get("ss58")
            to_addr = to_info.get("ss58")

            # Skip treasury-related tx
            if from_addr == treasury or to_addr == treasury:
                continue

            filtered.append(tx)

            # Classify
            if to_addr == tracked_address:  # going into Bittensor (so from Solana → Bittensor)
                transfers_out.append(tx)
            elif from_addr == tracked_address:  # leaving Bittensor (so Bittensor → Solana)
                transfers_in.append(tx)

    return filtered, transfers_in, transfers_out
