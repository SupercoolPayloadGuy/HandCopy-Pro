# 🖊 Handwriting Robot

Scan a document → robot writes it back in any stored handwriting style.

**Run one file. Open localhost. Done.**

---

## Setup (one time)

### 1. Install Python
Download from https://www.python.org/downloads/ — version 3.11 or newer.

### 2. Install Tesseract (needed for OCR)
**Windows:**
Download and run the installer from:
https://github.com/UB-Mannheim/tesseract/wiki
→ During install, tick "Add to PATH"

**Mac:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tesseract-ocr -y
```

### 3. Download this project
```bash
git clone https://github.com/YOUR_USERNAME/handwriting-robot.git
cd handwriting-robot
```

### 4. Install Python packages
```bash
pip install -r requirements.txt
```

### 5. Set your ESP32's IP address
```bash
cp .env.example .env
```
Open `.env` in any text editor and change:
```
ESP32_IP=192.168.1.100   ← put your ESP32's actual IP here
```

> To find your ESP32's IP: open Arduino IDE → Serial Monitor while the ESP32 is connected to WiFi. It prints its IP on startup.

---

## Running

```bash
python main.py
```

Open your browser at: **http://localhost:8000**

That's it. The database (SQLite) is created automatically in this folder on first run.
No Docker, no database server, no extra processes.

---

## How to use

### Step 1 — Create a handwriting profile
1. Click **Profiles** in the sidebar
2. Click **+ New Profile** → give it a name → Create

### Step 2 — Add letter images
For each letter you want the robot to write:
- Write the letter clearly on white paper
- Take a photo or scan it, crop tightly around the letter
- In the app: click the letter in the grid → click **Choose Image**
- The backend extracts the stroke paths automatically

> **Tip:** Start with lowercase a–z. You don't need every character before testing.

### Step 3 — Scan your document
Take a clear photo of the document you want to reproduce.
- Flat on a table, good lighting, no shadows
- 300 DPI scan is ideal, phone photo works too

### Step 4 — Create a print job
1. Click **Scan & Print**
2. Select your handwriting profile
3. Drop in your document photo
4. OCR runs automatically — you'll see the detected text
5. Click **→ Create Job**

### Step 5 — Print
1. Go to **Robot Control** → click **⌂ Home** (robot goes to X0 Y0)
2. Place paper with its top-left corner at the robot's home position
3. Back in Scan & Print → click **⚙ Generate G-code** → **🖨 Print Now**

---

## Project structure

```
handwriting-robot/
├── main.py            ← Run this
├── app.py             ← FastAPI app, serves frontend + API
├── config.py          ← Settings (reads from .env)
├── database.py        ← SQLite connection
├── requirements.txt
├── .env.example       ← Copy to .env
├── static/
│   └── index.html     ← The web interface
├── models/
│   ├── db_models.py   ← Database tables
│   └── schemas.py     ← Data validation
├── routers/
│   ├── profiles.py    ← Handwriting profiles & glyphs
│   ├── documents.py   ← Document scanning & print jobs
│   └── robot.py       ← Robot control
└── services/
    ├── ocr_service.py      ← Image → text + positions
    ├── stroke_service.py   ← Glyph image → stroke paths
    ├── gcode_service.py    ← Strokes → G-code
    └── robot_service.py    ← Talks to ESP32 over WiFi
```

---

## ESP32 firmware

Flash **GRBL-ESP32** for motion control:
https://github.com/bdring/Grbl_Esp32

You need a second ESP32 as a WiFi bridge. Minimal sketch:

```cpp
#include <WiFi.h>
#include <WebServer.h>

const char* ssid = "YOUR_WIFI_NAME";
const char* pass = "YOUR_WIFI_PASS";

WebServer server(80);
HardwareSerial grbl(1);  // UART to motion ESP32

void setup() {
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) delay(500);
  Serial.println(WiFi.localIP());  // ← note this IP, put it in .env

  grbl.begin(115200, SERIAL_8N1, 16, 17);

  server.on("/print", HTTP_POST, []() {
    String g = server.arg("plain");
    grbl.print(g);
    server.send(200, "text/plain", "OK");
  });
  server.on("/status", HTTP_GET, []() {
    server.send(200, "application/json",
      "{\"state\":\"idle\",\"pos\":{\"x\":0,\"y\":0}}");
  });
  server.on("/home",   HTTP_POST, []() { grbl.println("$H"); server.send(200,"text/plain","OK"); });
  server.on("/stop",   HTTP_POST, []() { grbl.write(0x18);   server.send(200,"text/plain","OK"); });
  server.on("/pause",  HTTP_POST, []() { grbl.write('!');    server.send(200,"text/plain","OK"); });
  server.on("/resume", HTTP_POST, []() { grbl.write('~');    server.send(200,"text/plain","OK"); });

  server.begin();
}

void loop() { server.handleClient(); }
```

---

## Troubleshooting

**"No text detected" after uploading**
→ Better lighting, no shadows, keep the document flat and straight

**"No strokes found" when uploading a glyph**
→ White background, dark pen, crop tightly around just the letter

**Robot shows "disconnected"**
→ Check the ESP32 is on, find its IP in Arduino Serial Monitor, update `.env`
→ Make sure your PC and ESP32 are on the same WiFi network
→ Try `ping 192.168.1.100` in a terminal to check

**Port 8000 already in use**
```bash
# Kill whatever is using it (Mac/Linux):
lsof -ti:8000 | xargs kill
# Then run again:
python main.py
```

**Packages fail to install**
```bash
# Try upgrading pip first:
python -m pip install --upgrade pip
pip install -r requirements.txt
```
