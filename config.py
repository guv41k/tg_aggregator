import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
COLLECTOR_TOKEN = os.getenv("COLLECTOR_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(uid.strip()) for uid in ADMIN_IDS_RAW.split(",") if uid.strip().isdigit()
]
