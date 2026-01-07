"""
Patient API Functions

Functions for retrieving Patient resources from the HCHB FHIR API.
"""
import os
import time
import json
import logging
import requests
import tenacity
from requests.exceptions import HTTPError, ReadTimeout
import concurrent.futures
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Default values
DEFAULT_PAGE_SIZE = 100
DEFAULT_ACTIVE = "true"

logger = logging.getLogger(__name__)

# Configuration from environment
CLIENT_ID = os.getenv("HCHB_CLIENT_ID")
RESOURCE_SECURITY_ID = os.getenv("HCHB_RESOURCE_SECURITY_ID")
AGENCY_SECRET = os.getenv("HCHB_AGENCY_SECRET")
TOKEN_URL = os.getenv("HCHB_TOKEN_URL")
API_BASE_URL = os.getenv("HCHB_API_BASE_URL")
EXPORT_JSON = os.getenv("EXPORT_JSON")

# Samples folder path
SAMPLES_DIR = Path(__file__).parent / "samples"

REQUEST_TIMEOUT = 120
TOKEN_REFRESH_INTERVAL = 100
MAX_WORKERS = 5


class TokenManager:
    def __init__(self):
        self.token = None
        self.request_count = 0
        self.last_refresh = 0

    def get_token(self, force_refresh=False) -> str:
        current_time = time.time()
        if (
            force_refresh
            or self.token is None
            or self.request_count >= TOKEN_REFRESH_INTERVAL
            or current_time - self.last_refresh > 3000  # 50 minutes
        ):
            self.token = self._fetch_new_token()
            self.request_count = 0
            self.last_refresh = current_time
        self.request_count += 1
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
        token = resp.json().get("access_token")
        if not token:
            raise Exception("Failed to fetch access token")
        return token


token_manager = TokenManager()


def _is_retriable_error(e):
    """Return True if the exception is a retriable HTTPError or a ReadTimeout."""
    if isinstance(e, ReadTimeout):
        return True
    if isinstance(e, HTTPError):
        return e.response.status_code in [429, 500, 502, 503, 504]
    return False


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=60),
    stop=tenacity.stop_after_attempt(5),
    retry=tenacity.retry_if_exception(_is_retriable_error),
    before_sleep=tenacity.before_sleep_log(logger, logging.INFO),
)
def _make_request(url, headers, params=None):
    """Make an HTTP GET request with retry logic."""
    response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response


def _fetch_page(url, headers, params=None):
    """Fetches a single page of Patient results and returns the entries and the next URL."""
    try:
        response = _make_request(url, headers=headers, params=params)

        if response.status_code == 401:
            logger.info("Token expired, refreshing...")
            headers["Authorization"] = f"Bearer {token_manager.get_token(force_refresh=True)}"
            response = _make_request(url, headers=headers, params=params)

        bundle = response.json()

        page_resources = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if resource and resource.get("resourceType") == "Patient":
                page_resources.append(resource)

        next_url = None
        for link in bundle.get("link", []):
            if link.get("relation") == "next":
                next_url = link.get("url")
                break

        total = bundle.get("total") if params else None

        return page_resources, next_url, total

    except HTTPError as e:
        logger.error(f"HTTP Error fetching page {url}: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching page {url}: {e}")

    return [], None, None


def get_patients(filter_params=None, page_size=DEFAULT_PAGE_SIZE, max_pages=1, include_inactive=False):
    """
    Retrieve Patient resources from the HCHB FHIR API.

    Args:
        filter_params: Dictionary of search parameters
        page_size: Number of results per page (default: 100)
        max_pages: Maximum pages to fetch (default: 1)
        include_inactive: If True, include inactive patients (default: False)

    Returns:
        List of Patient resources
    """
    if filter_params is None:
        filter_params = {}

    headers = {
        "Authorization": f"Bearer {token_manager.get_token()}",
        "Accept": "application/fhir+json",
    }

    params = filter_params.copy()
    params["_count"] = str(page_size)
    if not include_inactive:
        params.setdefault("active", DEFAULT_ACTIVE)

    all_patients = []

    first_url = f"{API_BASE_URL}/Patient"
    logger.info(f"Fetching first page from {first_url} with params {params}")
    page_resources, next_url, total = _fetch_page(first_url, headers, params=params)
    all_patients.extend(page_resources)

    pages_fetched = 1

    if total is not None:
        logger.info(f"API reported a total of {total} Patient records.")
        if total >= 5000:
            logger.warning(
                f"MANUAL FLAG: API reported {total} records. Max 5000 records can be returned per request."
            )
    else:
        logger.warning("API did not report a total number of Patient records.")

    if (max_pages and pages_fetched >= max_pages) or not next_url:
        logger.info(f"Total Patients retrieved: {len(all_patients)}")
        return all_patients

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_page, next_url, headers)}

        while futures:
            for future in concurrent.futures.as_completed(futures):
                page_resources, next_url, _ = future.result()

                if page_resources:
                    all_patients.extend(page_resources)
                    pages_fetched += 1
                    logger.info(f"Retrieved {len(all_patients)} Patients so far (page {pages_fetched})...")

                futures.remove(future)

                if max_pages and pages_fetched >= max_pages:
                    logger.info(f"Reached max_pages limit ({max_pages})")
                    break

                if next_url:
                    futures.add(executor.submit(_fetch_page, next_url, headers))
                    break

    logger.info(f"Finished fetching. Total Patients retrieved: {len(all_patients)}")

    return all_patients


def get_patient_by_id(patient_id):
    """
    Retrieve a single Patient by ID.

    Args:
        patient_id: The FHIR resource ID of the patient

    Returns:
        Patient resource dict or None if not found
    """
    headers = {
        "Authorization": f"Bearer {token_manager.get_token()}",
        "Accept": "application/fhir+json",
    }

    url = f"{API_BASE_URL}/Patient/{patient_id}"

    try:
        response = _make_request(url, headers)
        return response.json()
    except HTTPError as e:
        if e.response.status_code == 404:
            logger.warning(f"Patient with ID {patient_id} not found")
            return None
        logger.error(f"HTTP Error fetching patient {patient_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error fetching patient {patient_id}: {e}")
        raise


def export_to_json(data, filename="patients.json"):
    """Export data to JSON file in samples folder."""
    SAMPLES_DIR.mkdir(exist_ok=True)
    filepath = SAMPLES_DIR / filename
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Exported {len(data)} records to {filepath}")
    return filepath


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Fetching patients...")
    patients = get_patients()

    if patients:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if EXPORT_JSON:
            export_to_json(patients, f"patients_{timestamp}.json")

        print(f"Retrieved {len(patients)} patients")
    else:
        print("No patients retrieved")
