import os
from dotenv import load_dotenv

load_dotenv()  # loads .env if it exists, silently skips if it doesn't

# Database — SQLite, stored right here in the project folder
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./handwriting_robot.db")

# Your ESP32's IP address on your local network
ESP32_IP   = os.getenv("ESP32_IP",   "192.168.1.100")
ESP32_PORT = int(os.getenv("ESP32_PORT", "80"))

# Where to save uploaded scans
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

# Paper size (A4)
PAPER_WIDTH_MM  = 210.0
PAPER_HEIGHT_MM = 297.0
SCAN_DPI        = int(os.getenv("SCAN_DPI", "300"))

# Robot pen commands (GRBL)
PEN_DOWN_CMD   = "M3"
PEN_UP_CMD     = "M5"
DEFAULT_FEED   = 800   # mm/min writing speed
RAPID_FEED     = 3000  # mm/min pen-up travel speed
CHAR_HEIGHT_MM = float(os.getenv("CHAR_HEIGHT_MM", "5.0"))


def px_to_mm(px: float, dpi: int = None) -> float:
    return px * 25.4 / (dpi or SCAN_DPI)
