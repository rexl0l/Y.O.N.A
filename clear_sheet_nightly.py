"""
Clear the order spreadsheet every night. Run this script on a schedule:
  - Windows Task Scheduler: daily at midnight
  - Linux/Mac cron: 0 0 * * * cd /path/to/project && python clear_sheet_nightly.py
  - GitHub Actions: see .github/workflows/clear-sheet-nightly.yml
"""
import json
import os
import sys
from pathlib import Path

import tomllib  # Python 3.11+
import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).resolve().parent
SECRETS_PATH = PROJECT_ROOT / ".streamlit" / "secrets.toml"
SPREADSHEET_ID = "1aGrodq2WJ4--11XopsPH9HfB2oTH5yxdV1NKDWK29ow"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_service_account_info():
    env_json = os.environ.get("GSHEETS_SERVICE_ACCOUNT_JSON")
    if env_json:
        return json.loads(env_json)
    with open(SECRETS_PATH, "rb") as f:
        data = tomllib.load(f)
    secrets = data.get("connections", {}).get("gsheets", {})
    return {
        "type": "service_account",
        "project_id": secrets.get("project_id"),
        "private_key_id": secrets.get("private_key_id"),
        "private_key": secrets.get("private_key"),
        "client_email": secrets.get("client_email"),
        "client_id": secrets.get("client_id"),
        "auth_uri": secrets.get("auth_uri"),
        "token_uri": secrets.get("token_uri"),
        "auth_provider_x509_cert_url": secrets.get("auth_provider_x509_cert_url"),
        "client_x509_cert_url": secrets.get("client_x509_cert_url"),
    }


def clear_spreadsheet():
    info = get_service_account_info()
    if not info.get("private_key"):
        raise RuntimeError("No gsheets credentials (use .streamlit/secrets.toml or GSHEETS_SERVICE_ACCOUNT_JSON)")
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.get_worksheet(0)
    ws.clear()
    print(f"Cleared worksheet '{ws.title}' at {SPREADSHEET_ID}")


if __name__ == "__main__":
    try:
        clear_spreadsheet()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
