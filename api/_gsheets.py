"""
api/_gsheets.py — Shared Google Sheets client helper.
Underscore prefix = not treated as a Vercel serverless function.

Usage:
    from _gsheets import get_sheet
    sheet = get_sheet("listings")
    records = sheet.get_all_records()
"""
import json
import os
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv(Path(__file__).parent.parent / ".env")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_gspread_client: gspread.Client | None = None


def _get_client() -> gspread.Client:
    global _gspread_client
    if _gspread_client is None:
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_json:
            raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON is not set in environment")
        try:
            creds_dict = json.loads(sa_json)
        except json.JSONDecodeError as exc:
            raise EnvironmentError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON"
            ) from exc
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _gspread_client = gspread.authorize(creds)
    return _gspread_client


def get_sheet(sheet_name: str) -> gspread.Worksheet:
    """
    Return a gspread Worksheet object for the given sheet tab name.
    Credentials are read from GOOGLE_SERVICE_ACCOUNT_JSON (JSON string)
    and the spreadsheet is identified by GOOGLE_SHEETS_ID.

    Raises EnvironmentError if required env vars are missing.
    Raises gspread.exceptions.WorksheetNotFound if the tab doesn't exist.
    """
    sheets_id = os.getenv("GOOGLE_SHEETS_ID")
    if not sheets_id:
        raise EnvironmentError("GOOGLE_SHEETS_ID is not set in environment")

    spreadsheet = _get_client().open_by_key(sheets_id)
    return spreadsheet.worksheet(sheet_name)
