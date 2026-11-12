import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing in .env")

if not REPLICATE_API_TOKEN:
    raise ValueError("REPLICATE_API_TOKEN is missing in .env")

ADMIN_ID = int(ADMIN_ID) if ADMIN_ID else None
