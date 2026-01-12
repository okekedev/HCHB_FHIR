"""
Use Case: Get Patient's Payor ID

Description:
    Retrieves the payor organization for a given patient by querying the Account resource.

    Flow: Patient -> Account (by subject) -> guarantor -> Organization (Payor)

Parameters:
    patient_id      Patient FHIR ID (optional - fetches first patient if not provided)

Usage:
    python get_patient_payor.py
    python get_patient_payor.py --patient_id xxbgjz5i1
"""
import os
import sys
import time
import json
import logging
import argparse
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configuration
CLIENT_ID = os.getenv("HCHB_CLIENT_ID")
RESOURCE_SECURITY_ID = os.getenv("HCHB_RESOURCE_SECURITY_ID")
AGENCY_SECRET = os.getenv("HCHB_AGENCY_SECRET")
TOKEN_URL = os.getenv("HCHB_TOKEN_URL")
API_BASE_URL = os.getenv("HCHB_API_BASE_URL")

REQUEST_TIMEOUT = 120
OUTPUT_DIR = Path(__file__).parent / "output"


class TokenManager:
    def __init__(self):
        self.token = None
        self.last_refresh = 0

    def get_token(self, force_refresh=False) -> str:
        current_time = time.time()
        if force_refresh or self.token is None or current_time - self.last_refresh > 3000:
            self.token = self._fetch_new_token()
            self.last_refresh = current_time
        return self.token

    def _fetch_new_token(self) -> str:
        data = {
            "grant_type": "agency_auth",
            "client_id": CLIENT_ID,
            "scope": "openid HCHB.api.scope agency.identity hchb.identity",
            "resource_security_id": RESOURCE_SECURITY_ID,
            "agency_secret": AGENCY_SECRET,
        }
        resp = requests.post(TOKEN_URL, data=data, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("access_token")


token_manager = TokenManager()


def get_sample_patient():
    """Fetch a single patient to use as sample."""
    headers = {
        "Authorization": f"Bearer {token_manager.get_token()}",
        "Accept": "application/fhir+json",
    }

    url = f"{API_BASE_URL}/Patient"
    params = {"_count": "1", "active": "true"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        bundle = response.json()

        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if resource and resource.get("resourceType") == "Patient":
                return resource.get("id")
    except Exception as e:
        logger.error(f"Error fetching sample patient: {e}")

    return None


def get_patient_payor(patient_id):
    """
    Get the payor organization for a patient.

    Returns:
        dict with patient_id, payor_id, and payor_details (if found)
    """
    headers = {
        "Authorization": f"Bearer {token_manager.get_token()}",
        "Accept": "application/fhir+json",
    }

    result = {
        "patient_id": patient_id,
        "payor_ids": [],
        "payor_details": []
    }

    # Step 1: Query Account by patient
    account_url = f"{API_BASE_URL}/Account"
    params = {"subject": f"Patient/{patient_id}", "_count": "100"}

    try:
        response = requests.get(account_url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        bundle = response.json()

        # Extract unique payor IDs from guarantor field
        payor_ids = set()
        for entry in bundle.get("entry", []):
            account = entry.get("resource", {})
            for guarantor in account.get("guarantor", []):
                party = guarantor.get("party", {})
                ref = party.get("reference", "")
                if ref.startswith("Organization/"):
                    payor_ids.add(ref.replace("Organization/", ""))

        result["payor_ids"] = list(payor_ids)

        # Step 2: Fetch payor organization details
        for payor_id in payor_ids:
            org_url = f"{API_BASE_URL}/Organization/{payor_id}"
            org_response = requests.get(org_url, headers=headers, timeout=REQUEST_TIMEOUT)
            if org_response.status_code == 200:
                org = org_response.json()
                result["payor_details"].append({
                    "id": org.get("id"),
                    "name": org.get("name"),
                    "type": org.get("type", [{}])[0].get("coding", [{}])[0].get("code"),
                    "phone": next((t.get("value") for t in org.get("telecom", []) if t.get("system") == "phone"), None),
                    "address": org.get("address", [{}])[0] if org.get("address") else None
                })

    except Exception as e:
        logger.error(f"Error fetching payor for patient {patient_id}: {e}")
        result["error"] = str(e)

    return result


def export_to_json(data, filename):
    OUTPUT_DIR.mkdir(exist_ok=True)
    filepath = OUTPUT_DIR / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    return filepath


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Get patient's payor organization")
    parser.add_argument("--patient_id", default="enter_patient_id", help="Patient FHIR ID")
    args = parser.parse_args()

    if args.patient_id == "enter_patient_id":
        print("No patient_id provided, fetching sample patient...")
        args.patient_id = get_sample_patient()
        if not args.patient_id:
            print("Error: Could not fetch sample patient")
            sys.exit(1)

    print(f"Fetching payor for patient: {args.patient_id}")
    result = get_patient_payor(args.patient_id)

    if result["payor_ids"]:
        print(f"\nFound {len(result['payor_ids'])} payor(s):")
        for payor in result["payor_details"]:
            print(f"\n  ID: {payor['id']}")
            print(f"  Name: {payor['name']}")
            print(f"  Type: {payor['type']}")
            print(f"  Phone: {payor['phone']}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = export_to_json(result, f"patient_payor_{args.patient_id}_{timestamp}.json")
        print(f"\nExported to: {filepath}")
    else:
        print("No payors found for this patient")
