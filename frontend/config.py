import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

CEO_SECRET_PHRASE = os.getenv("CEO_SECRET_PHRASE")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dropz.db")
BASE_DIR = Path(__file__).resolve().parent