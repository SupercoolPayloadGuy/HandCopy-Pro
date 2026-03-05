"""
╔══════════════════════════════════════════════════════╗
║          HANDWRITING ROBOT — LAUNCHER                ║
║  Run this file. Open http://localhost:8000           ║
╚══════════════════════════════════════════════════════╝

Usage:
    python main.py

That's it. No Docker, no database server, no extra setup.
SQLite database is created automatically in this folder.
"""

import subprocess
import sys
import os

# ── Auto-install missing packages ────────────────────────────────────────────
REQUIRED = [
    "fastapi", "uvicorn", "sqlalchemy", "aiosqlite",
    "python-multipart", "httpx", "Pillow",
    "opencv-python-headless", "numpy", "pytesseract",
    "scipy", "scikit-image", "aiofiles", "pydantic",
]

def ensure_packages():
    import importlib
    missing = []
    check_map = {
        "opencv-python-headless": "cv2",
        "python-multipart": "multipart",
        "scikit-image": "skimage",
        "Pillow": "PIL",
        "sqlalchemy": "sqlalchemy",
        "aiosqlite": "aiosqlite",
        "pydantic": "pydantic",
    }
    for pkg in REQUIRED:
        module = check_map.get(pkg, pkg.replace("-", "_"))
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n📦 Installing missing packages: {', '.join(missing)}\n")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("\n✅ Packages installed.\n")

ensure_packages()

# ── Now import everything ─────────────────────────────────────────────────────
import uvicorn
from app import create_app

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════╗
║          HANDWRITING ROBOT                           ║
╠══════════════════════════════════════════════════════╣
║  → Open your browser at:  http://localhost:8000      ║
║  → API docs at:           http://localhost:8000/docs ║
║  → Press Ctrl+C to stop                              ║
╚══════════════════════════════════════════════════════╝
""")
    uvicorn.run(
        "app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=["*.db", "uploads/*"],
    )
