import os
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_CLOUD_CREDENTIALS"),
    scopes=SCOPES
)

client = gspread.authorize(creds)

# Valid sheet pages
income_sheet = client.open_by_key(os.getenv("SHEET_ID")).worksheet("Entrada")
outcome_sheet = client.open_by_key(os.getenv("SHEET_ID")).worksheet("Saída")
