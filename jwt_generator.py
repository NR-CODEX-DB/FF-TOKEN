
import json
import time
import asyncio
import httpx
import os
from typing import Dict, Optional

# Settings
RELEASEVERSION = "OB51"
USERAGENT = "Dalvik/2.1.0 (Linux; U; Android 13; CPH2095 Build/RKQ1.211119.001)"
API_URL = "https://api.freefireservice.dnc.su/oauth/account:login?data="

def get_repo_and_filename(region):
    """Determine repository and filename based on region"""
    if region == "IND":
        return "token_ind.json"
    elif region in {"BR", "US", "SAC", "NA"}:
        return "token_br.json"
    elif region == "OTHERS":
        return "token_others.json"  # New file for OTHERS
    else:
        # Default for BD or others
        return "token_bd.json"

# Token Generation
async def generate_jwt_token(client, uid: str, password: str) -> Optional[Dict]:
    """Generate JWT token using the new API endpoint"""
    try:
        url = f"{API_URL}{uid}:{password}"
        headers = {
            'User-Agent': USERAGENT,
            'Accept': 'application/json',
        }

        resp = await client.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if "8" in data:  # JWT token is in field "8"
                return {
                    "token": data["8"],
                    "notiRegion": data.get("2", ""),  # Region is in field "2"
                    "uid": data.get("1", "")  # UID is in field "1"
                }
        return None
    except Exception as e:
        print(f"Error generating token for {uid}: {str(e)}")
        return None

async def process_account_with_retry(client, index, uid, password, max_retries=2):
    for attempt in range(max_retries):
        try:
            token_data = await generate_jwt_token(client, uid, password)
            if token_data and "token" in token_data:
                return {
                    "serial": index + 1,
                    "uid": uid,
                    "password": password,
                    "token": token_data["token"],
                    "notiRegion": token_data.get("notiRegion", "")
                }
        except Exception as e:
            print(f"Attempt {attempt + 1} failed for UID #{index + 1}: {str(e)}")

        if attempt < max_retries - 1:
            print(f"⏳ UID #{index + 1} {uid} - Retry after 1 minute...")
            await asyncio.sleep(60)
    
    return {
        "serial": index + 1,
        "uid": uid,
        "password": password,
        "token": None,
        "notiRegion": ""
    }

def load_accounts_from_txt(region):
    """Load accounts from acc_region.txt file"""
    # region.lower() will convert 'OTHERS' to 'others', looking for 'acc_others.txt'
    input_file = f"acc_{region.lower()}.txt"
    accounts = []
    
    if not os.path.exists(input_file):
        print(f"⚠️ {input_file} not found. Skipping...")
        return accounts
    
    with open(input_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and ':' in line:
                parts = line.split(':')
                uid = parts[0].strip()
                password = parts[1].strip()
                accounts.append({"uid": uid, "password": password})
    
    return accounts

async def generate_tokens_for_region(region):
    start_time = time.time()

    accounts = load_accounts_from_txt(region)
    total_accounts = len(accounts)
    
    if total_accounts == 0:
        return 0

    print(f"🚀 Starting Token Generation for {region} Region using API...\n")
    region_tokens = []
    failed_serials = []
    failed_values = []
    
    async with httpx.AsyncClient() as client:
        tasks = []
        for index, account in enumerate(accounts):
            tasks.append(process_account_with_retry(client, index, account["uid"], account["password"]))
        
        results = await asyncio.gather(*tasks)
        
        for result in results:
            serial = result["serial"]
            uid = result["uid"]
            token = result["token"]
            token_region = result.get("notiRegion", "")
            
            # Logic Update: 
            # If processing "OTHERS", accept token regardless of region mismatch.
            # If processing specific region (IND, BD), strict check applies.
            is_valid_region = (token_region == region) or (region == "OTHERS")

            if token and is_valid_region:
                region_tokens.append({"uid": uid, "token": token})
                print(f"✅ UID #{serial} {uid} - Token saved for {region} (Region found: {token_region})")
            else:
                failed_serials.append(serial)
                failed_values.append(uid)
                print(f"❌ UID #{serial} {uid} - Failed. Got Region: {token_region}, Expected: {region}")

    output_file = get_repo_and_filename(region)
    
    # Save to file
    with open(output_file, "w") as f:
        json.dump(region_tokens, f, indent=2)
    
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    
    summary = (
        f"✅ {region} Token Generation Complete\n"
        f"🔹 Total Tokens: {len(region_tokens)}\n"
        f"❌ Failed UIDs: {len(failed_serials)}\n"
        f"⏱️ Time Taken: {minutes}m {seconds}s\n"
    )
    print(summary)
    return len(region_tokens)

# Run
if __name__ == "__main__":
    # Added OTHERS to the list
    regions = ["IND", "BD", "NA", "OTHERS"]
    total_tokens = 0

    for region in regions:
        print(f"----------------------------------------")
        print(f"🤖 Processing {region}...")
        try:
            tokens_generated = asyncio.run(generate_tokens_for_region(region))
            total_tokens += tokens_generated
        except Exception as e:
            print(f"⚠️ Error processing {region}: {e}")
    
    print(f"========================================")
    print(f"🤖 All Regions Completed!\nTotal Tokens Generated: {total_tokens}")
    print(f"========================================")
