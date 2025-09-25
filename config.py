# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# --- GPIO Pins ---
PIR_PIN = 4
LED_PINS = {"red": 17, "yellow": 27, "green": 22}

# --- Camera Settings ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
PHOTOS_DIR = os.path.join(STATIC_DIR, "images")
FRAME_SIZE = (640, 480)
WINDOW_NAME = "Camera"
LOGS_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "photo_logs.txt")

# --- Email Settings ---
SENDER_EMAIL = os.getenv("MY_EMAIL")
PASSWORD = os.getenv("MY_EMAIL_APP_PASSWORD")
if not SENDER_EMAIL or not PASSWORD:
    raise ValueError("Please set MY_EMAIL and MY_EMAIL_APP_PASSWORD in .env")
RECEIVER_EMAIL = SENDER_EMAIL
SUBJECT = "Photo from Raspberry Pi"
BODY = "Sent from Raspberry Pi"

# --- Timing Constants ---
MOTION_THRESHOLD_SECONDS = 5
COOLDOWN_DURATION_SECONDS = 30
YELLOW_FLASH_INTERVAL_SECONDS = 0.2
GREEN_FLASH_COUNT = 3
GREEN_FLASH_INTERVAL_SECONDS = 0.1