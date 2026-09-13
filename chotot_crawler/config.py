import os
from pathlib import Path
from dotenv import load_dotenv

# Tự động nạp các biến từ file .env nếu có
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# API Endpoints
CHOTOT_API_URL = os.getenv(
    "CHOTOT_API_URL", 
    "https://gateway.chotot.com/v1/public/ad-listing"
)

REGION_ID = int(os.getenv("REGION_ID", 12000))
TARGET_DATA = int(os.getenv("TARGET_DATA", 7000))
LIMIT_PER_REQUEST = int(os.getenv("LIMIT_PER_REQUEST", 20))

raw_categories = os.getenv("CATEGORIES", "1050,1010,1020")
CG_LIST = [int(cg.strip()) for cg in raw_categories.split(",") if cg.strip()]

DELAY_MIN = float(os.getenv("DELAY_MIN", 1.5))
DELAY_MAX = float(os.getenv("DELAY_MAX", 3.0))

OUTPUT_RAW_JSON = BASE_DIR / "chotot_hanoi_raw.json"
OUTPUT_RAW_CSV = BASE_DIR / "chotot_hanoi_raw.csv"
OUTPUT_CLEANED_CSV = BASE_DIR / "chotot_hanoi_cleaned.csv"
