# Handwriting Robot

A pen plotter that reproduces handwriting. You teach it someone's handwriting by uploading photos of their letters, then it writes any text in that style — or copies a scanned document exactly, preserving where each word appears on the page.

---

## Table of Contents

1. [What you need](#1-what-you-need)
2. [How it works — overview](#2-how-it-works--overview)
3. [Physical build](#3-physical-build)
4. [Wiring](#4-wiring)
5. [Software setup](#5-software-setup)
6. [ESP32 firmware](#6-esp32-firmware)
7. [First run](#7-first-run)
8. [Using the app](#8-using-the-app)
9. [How each part works — technical](#9-how-each-part-works--technical)
10. [Troubleshooting](#10-troubleshooting)
11. [File reference](#11-file-reference)

---

## 1. What you need

### Hardware

| Part | Notes |
|------|-------|
| 2× ESP32 Dev Module | Any standard 38-pin ESP32 board |
| 2× A4988 stepper driver | TMC2209 also works and is quieter |
| 2× NEMA 17 stepper motor | Standard 200 steps/rev, 1.8° |
| 1× SG90 servo | For raising and lowering the pen |
| 1× 12V power supply | At least 2A for the motors |
| GT2 belt + pulleys | 20-tooth pulleys, 2mm pitch belt |
| Linear rails or rods | For X and Y axes |
| 2× endstop switches | Mechanical or optical |
| Jumper wires | For connections between boards |
| A pen holder | 3D printed or improvised |

### Software (on your computer)

- Python 3.11 or newer — https://python.org/downloads
- Arduino IDE — https://arduino.cc/en/software
- Tesseract OCR:
  - **Windows:** https://github.com/UB-Mannheim/tesseract/wiki — tick "Add to PATH" during install
  - **Mac:** `brew install tesseract`
  - **Linux:** `sudo apt install tesseract-ocr -y`

---

## 2. How it works — overview

```
Your computer                  ESP32 #1              ESP32 #2
─────────────────              ────────────           ──────────────
Python app          WiFi HTTP  WiFi Bridge  Serial    Motor Controller
  │                ─────────►  │           ──────────►  │
  │  Web browser               │                        │
  └──────────────              │                        ├── X stepper
     localhost:8000            │                        ├── Y stepper
                               │                        └── Pen servo
```

1. You run `python main.py` on your computer. It starts a web server at `localhost:8000`.
2. You open that address in your browser. The web app is served directly from Python — no separate frontend server.
3. You teach the robot a handwriting style by uploading photos of handwritten letters. The backend traces the pen strokes from each photo.
4. You either type text or upload a document scan.
5. The backend generates G-code — a list of motor movement instructions.
6. When you click Print, the Python app sends that G-code over WiFi to ESP32 #1 (the bridge).
7. ESP32 #1 forwards it over a serial cable to ESP32 #2 (the motor controller).
8. ESP32 #2 steps the motors and moves the servo, drawing each character stroke by stroke.

---

## 3. Physical build

The robot is a 2-axis pen plotter — essentially a miniature CNC machine. The pen moves in X and Y, and a servo lifts it between strokes.

**Axis layout:**

```
(0,0) ──────────────────► X (mm)
  │
  │        ← paper goes here →
  │
  ▼
  Y (mm)
```

- X=0, Y=0 is the **top-left corner** of the paper.
- X increases to the right.
- Y increases downward.
- When you home the robot (`$H`), it moves to X0 Y0. Place the paper so its top-left corner is exactly at that position.

**Steps per mm:**

This is the most important number to get right. It depends on your specific belt and pulley combination.

```
STEPS_PER_MM = (motor_steps_per_rev × microstepping) / (belt_pitch_mm × pulley_teeth)
```

For the most common setup (200-step motor, 1/16 microstepping, GT2 belt, 20-tooth pulley):

```
(200 × 16) / (2 × 20) = 80 steps/mm
```

Set this value in `2_motor_controller.ino` before flashing.

---

## 4. Wiring

### Stepper drivers (A4988) — do this for both X and Y

```
A4988 pin    Connect to
─────────────────────────────────────────────
VMOT         12V power supply +
GND (VMOT)   12V power supply −  (the GND near VMOT)
VDD          3.3V on ESP32
GND (VDD)    GND on ESP32  (the GND near VDD)
ENABLE       GPIO 13 on Motor ESP32  (shared between both drivers)
STEP         GPIO 26 (X driver) or GPIO 14 (Y driver)
DIR          GPIO 27 (X driver) or GPIO 12 (Y driver)
1A, 1B       One coil pair of the stepper motor
2A, 2B       Other coil pair of the stepper motor
MS1          HIGH  ─┐
MS2          HIGH   ├── for 1/16 microstepping
MS3          HIGH  ─┘
```

> **Important:** The 12V ground and the logic ground must be connected together at one point. Run a wire from the 12V PSU negative terminal to a GND pin on the ESP32.

### Endstops

```
Endstop      Connect to
──────────────────────────────────────────────
X endstop    GPIO 34 on Motor ESP32, and GND
Y endstop    GPIO 35 on Motor ESP32, and GND
```

The firmware uses `INPUT_PULLUP`. The switch should connect the GPIO pin to GND when triggered. No resistor needed.

### Pen servo (SG90)

```
Servo wire   Connect to
──────────────────────────────────────────────
Orange       GPIO 25 on Motor ESP32
Red          5V  (use 5V, not 3.3V — the servo is stronger)
Brown/Black  GND
```

### ESP32 to ESP32 (three wires)

```
WiFi Bridge ESP32    Motor Controller ESP32
─────────────────    ──────────────────────
GPIO 16 (RX)    ←── GPIO 1 (TX)
GPIO 17 (TX)    ──► GPIO 3 (RX)
GND             ─── GND
```

### Full wiring diagram (text)

```
12V PSU +  ──────────────────────────── A4988-X VMOT
                                    └── A4988-Y VMOT
12V PSU −  ──────────────────────────── A4988-X GND(VMOT)
         │                          └── A4988-Y GND(VMOT)
         └────────────────────────────── Motor ESP32 GND

Motor ESP32 3.3V ───────────────────── A4988-X VDD
                                    └── A4988-Y VDD
Motor ESP32 GND  ───────────────────── A4988-X GND(VDD)
                                    └── A4988-Y GND(VDD)

Motor ESP32 GPIO 13 ────────────────── A4988-X ENABLE
                                    └── A4988-Y ENABLE

Motor ESP32 GPIO 26 ────────────────── A4988-X STEP
Motor ESP32 GPIO 27 ────────────────── A4988-X DIR
Motor ESP32 GPIO 14 ────────────────── A4988-Y STEP
Motor ESP32 GPIO 12 ────────────────── A4988-Y DIR

Motor ESP32 GPIO 34 ────────────────── X endstop (other leg to GND)
Motor ESP32 GPIO 35 ────────────────── Y endstop (other leg to GND)

Motor ESP32 GPIO 25 ────────────────── Servo signal (orange)
5V                  ────────────────── Servo power  (red)
GND                 ────────────────── Servo GND    (brown)

Motor ESP32 GPIO  1 (TX) ───────────── WiFi Bridge GPIO 16 (RX)
Motor ESP32 GPIO  3 (RX) ◄──────────── WiFi Bridge GPIO 17 (TX)
Motor ESP32 GND          ───────────── WiFi Bridge GND

WiFi Bridge          ~~~~WiFi~~~~      Your computer (Python app)
```

---

## 5. Software setup

### Install Python packages

```bash
cd handwriting-robot
pip install -r requirements.txt
```

If you are on a system where pip complains about permissions:

```bash
pip install -r requirements.txt --break-system-packages
```

If you get errors about Pillow, numpy, or scikit-image (common on Python 3.13):

```bash
pip install -r requirements.txt --upgrade
```

### Configure the ESP32 IP

Copy the example config file:

```bash
cp .env.example .env
```

Open `.env` and set the IP address of your WiFi Bridge ESP32. You will find out what this is after flashing and booting it (it prints the IP to Serial Monitor). Leave it as the default for now and update it from the web UI later.

```
ESP32_IP=192.168.1.100
ESP32_PORT=80
```

You can also change these from the web UI after starting the app — no need to touch the file directly.

---

## 6. ESP32 firmware

You need to flash two separate sketches — one per ESP32.

### Install ESP32 board support in Arduino IDE

1. Open Arduino IDE
2. Go to **File → Preferences**
3. In "Additional boards manager URLs" paste:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Go to **Tools → Board → Boards Manager**
5. Search `esp32`, install **ESP32 by Espressif Systems**

### Flash ESP32 #1 — WiFi Bridge (`1_wifi_bridge.ino`)

1. Open `esp32/1_wifi_bridge.ino` in Arduino IDE
2. Edit the two lines at the top:
   ```cpp
   const char* WIFI_SSID     = "your network name";
   const char* WIFI_PASSWORD = "your password";
   ```
3. Set board: **Tools → Board → ESP32 Dev Module**
4. Select the correct COM port under **Tools → Port**
5. Click Upload
6. Open **Tools → Serial Monitor**, set baud to **115200**
7. You will see something like:
   ```
   ✓ WiFi connected
     ► IP Address: 192.168.1.105
     ← Enter this IP in the Robot Control tab
   ```
8. Note that IP — enter it in the Robot Control tab of the web app

### Flash ESP32 #2 — Motor Controller (`2_motor_controller.ino`)

1. Install the required library first:
   - **Tools → Manage Libraries**
   - Search `ESP32Servo`
   - Install **ESP32Servo by Kevin Harrington**

2. Open `esp32/2_motor_controller.ino`

3. Tune these values near the top for your specific machine:

   ```cpp
   float STEPS_PER_MM   = 80.0;  // see formula in section 3
   int   PEN_DOWN_ANGLE = 30;    // servo angle where pen touches paper
   int   PEN_UP_ANGLE   = 90;    // servo angle where pen clears paper
   float MAX_FEED       = 5000.0; // mm/min speed limit
   float HOMING_SPEED   = 10.0;  // mm/s during homing (slower = more reliable)
   ```

   To find the right servo angles: connect the servo, open Serial Monitor, and manually send `M3` (pen down) and `M5` (pen up). Adjust the angles until the pen just touches the paper for `M3` and fully clears it for `M5`.

4. Upload to the motor ESP32

5. Open Serial Monitor — you should see:
   ```
   === Handwriting Robot — Motor Controller ===
   Waiting for G-code. Send $H to home first.
   ```

### Connect the two ESP32s

Wire them as shown in the wiring section (three wires: RX, TX, GND). After wiring, the WiFi Bridge will be able to relay commands to the Motor Controller.

---

## 7. First run

```bash
python main.py
```

Open **http://localhost:8000** in your browser.

### Check connection

1. Go to **Robot Control**
2. The sidebar shows "disconnected" in red — that is expected until the robot is configured
3. Enter your ESP32's IP address in the Connection settings panel
4. Click **⚡ Test Connection** — if it says "Connected — robot state: Alarm", that is correct. Alarm means it has not been homed yet.
5. Click **💾 Save Config**

### Home the robot

Before the robot can print anything it needs to home — it moves each axis slowly toward its endstop to find X0 Y0.

1. Make sure the robot has clear travel space in the negative X and Y directions
2. Click **⌂ Home** in the Robot Control tab
3. The robot moves both axes to their endstops, then backs off slightly to a known position
4. Status changes to "Idle" — the robot is ready

---

## 8. Using the app

### Creating a handwriting profile

A profile stores the stroke data for every character in one person's handwriting, plus style measurements like slant angle and baseline wobble.

Go to **Profiles → + New Profile**. Give it a name (e.g. "Emma — cursive") and create it.

### Adding handwriting — Option A: Calligraphr sheet (recommended)

This is the fastest way to add all characters at once.

1. Go to https://www.calligraphr.com — create a free account
2. Click **Download Template → Basic Latin → PNG**
3. Print the template
4. Write every character in its box using a dark pen on the white paper. Write naturally — don't try to be perfect, the wobble and imperfection is what makes it look real.
5. Scan at 300 DPI, or take a flat photo with good even lighting and no shadows
6. In the app: **Profiles → select your profile → Add handwriting → Calligraphr sheet**
7. Upload the scan

The app detects all the boxes on the sheet, extracts the stroke path from each one, and saves them all at once. You will see the character grid fill up with amber dots.

### Adding handwriting — Option B: Individual letter photos

For each letter you want to add:

1. Write that letter clearly on white paper with a dark pen
2. Photograph or scan it, then crop tightly around just that letter
3. In the app: click the letter in the character grid (it turns blue), then click **Choose photo** and upload the crop

The backend traces the skeleton of the ink strokes from the image and saves the normalized path.

### Measuring style

After uploading glyphs, go to **Add handwriting → Measure style** and upload any photo of this person's handwriting — a sentence or a few lines. The app measures:

- **Slant:** how many degrees the letters lean forward or backward
- **Baseline wobble:** how much the letters bounce up and down on the line

These values are applied when generating G-code to make the output look more natural.

### Printing typed text

Go to **Type & Print**.

1. Select a profile
2. Type whatever you want the robot to write
3. Set position on paper:
   - **Start X** — how many mm from the left edge to begin writing
   - **Start Y** — how many mm from the top edge
   - **Max line width** — text wraps when it reaches this width
   - **Letter height** — how tall the letters are in mm (5mm is natural handwriting size)
4. The paper preview on the right shows roughly where the text will appear
5. Click **⚙ Generate G-code**
6. Go to Robot Control → click **⌂ Home**
7. Place paper with top-left corner at the robot's home position
8. Click **🖨 Print Now**

### Printing a scanned document

Go to **Scan & Print** to reproduce a document in handwriting at the same positions as the original.

1. Take a clear photo of the document — flat on a table, even lighting, no rotation
2. Select a profile and DPI (300 is good for a scan, 150 works for phone photos)
3. Drop the image into the upload area
4. OCR runs automatically — you see yellow boxes over the detected words in the preview
5. Check the detected text looks correct
6. Click **→ Create Job**, then **⚙ Generate G-code**, then **🖨 Print Now**

### Robot Control tab

| Button | What it does |
|--------|-------------|
| ⌂ Home | Moves both axes to endstops to find X0 Y0. Do this before every print. |
| ⛔ Stop | Immediately halts all motion and resets the motor controller. |
| ⏸ Pause | Holds at current position. Resume to continue. |
| ▶ Resume | Continues after a pause. |
| Manual G-code | Type any G-code command and press Enter to send it directly. |

**Connection & Motion Settings** — configure the ESP32 IP, port, pen up/down commands, and motor speeds. Changes take effect immediately and are saved to `.env` so they persist after a restart.

---

## 9. How each part works — technical

### Stroke extraction (`services/stroke_service.py`)

When you upload a photo of a handwritten letter, the backend:

1. Converts to grayscale and applies a Gaussian blur
2. Thresholds to binary (black ink, white paper) using Otsu's method — this handles varying lighting automatically
3. Applies morphological closing to fill small gaps in the ink
4. Skeletonizes the binary image — reduces the ink from a filled shape to a 1-pixel-wide centerline
5. Walks the skeleton graph to extract ordered sequences of points (strokes)
6. Fits B-spline curves through the points to smooth out pixel-grid jaggedness
7. Normalizes all coordinates to the range 0.0–1.0 (width and height independently)
8. Stores the result as a list of strokes, where each stroke is a list of `[x, y]` points

The width-to-height ratio of the original bounding box is stored separately as `width_ratio`. This lets characters like "i" (narrow) and "m" (wide) scale correctly when rendered at any letter height.

### Calligraphr sheet parsing (`services/calligraphr_service.py`)

The sheet parser:

1. Finds all rectangular regions on the page using contour detection
2. Filters by size — boxes that are too small (noise) or too large (the page itself) are discarded
3. Finds the median box size and keeps only boxes within 40% of that size
4. Sorts boxes left-to-right, top-to-bottom using row clustering
5. Maps each box to the expected character using Calligraphr's fixed template order (A–Z, a–z, 0–9, punctuation)
6. Crops each box with a small inset to remove the border lines
7. Runs stroke extraction on each crop

### G-code generation (`services/gcode_service.py`)

To write a character at position (X, Y) with height H:

1. Look up the character's stored strokes (normalized 0–1 coordinates)
2. Apply slant transformation — shear the X coordinates based on the profile's slant angle:
   ```
   x_slanted = x + tan(slant_degrees) × (1 - y) × H
   ```
   This leans the character without changing its baseline.
3. Scale from normalized to real mm:
   ```
   x_real = origin_x + x_normalized × H × width_ratio
   y_real = origin_y + y_normalized × H
   ```
4. Add baseline wobble — a small random vertical offset per character, seeded by position so it is consistent between generates
5. For each stroke: emit `G0` (rapid, pen up) to the first point, then `M3` (pen down), then `G1` (linear, pen down) for each subsequent point, then `M5` (pen up)
6. Advance the cursor by `H × width_ratio × letter_spacing` after each character
7. Wrap to a new line when the cursor exceeds `max_width_mm`

The full G-code file begins with:
```
G21    ; millimeter units
G90    ; absolute positioning
M5     ; pen up
G28 X Y ; home both axes
```
And ends with:
```
M5     ; pen up
G0 X0 Y0 F3000  ; return to origin
M2     ; end of program
```

### OCR pipeline (`services/ocr_service.py`)

When you upload a document scan:

1. Decodes the image (supports JPEG, PNG, TIFF)
2. Deskews — detects any rotation and corrects it using the minimum area rectangle of detected ink
3. Preprocesses — denoises, then applies adaptive thresholding (handles uneven lighting across the page)
4. Runs Tesseract with `--psm 3` (automatic page segmentation) and `--oem 3` (LSTM neural network)
5. Filters out words with confidence below 60%
6. Converts pixel coordinates to millimeters using the scan DPI
7. Groups words into lines by clustering words with similar Y coordinates

The resulting text blocks carry both the text content and the exact X/Y position in mm. This means the G-code reproduces not just the words but their layout — paragraph breaks, indentation, and spacing are all preserved.

### WiFi Bridge (`esp32/1_wifi_bridge.ino`)

The bridge runs a simple HTTP server on port 80. The Python app talks to it using standard HTTP requests. The bridge translates each HTTP request into serial bytes sent to the motor controller:

| HTTP endpoint | Action |
|--------------|--------|
| `GET /status` | Sends `?` to motor ESP32, parses the GRBL-format status response, returns JSON |
| `POST /print` | Streams G-code line by line over serial, waits for `ok` after each line |
| `POST /home` | Sends `$H` |
| `POST /stop` | Sends `0x18` (GRBL soft-reset byte) |
| `POST /pause` | Sends `!` (GRBL feed-hold character) |
| `POST /resume` | Sends `~` (GRBL cycle-start character) |

The `/print` handler responds with HTTP 200 immediately, then streams the G-code. This prevents the Python app's HTTP client from timing out on long prints.

### Motor Controller (`esp32/2_motor_controller.ino`)

The motor controller is a minimal G-code interpreter. It reads lines from Serial, parses them, and drives the motors.

**Movement** uses Bresenham's line algorithm to step both axes simultaneously, producing straight diagonal lines. The step rate is calculated from the requested feed rate:

```
step_frequency = (feed_mm_per_min / 60) × STEPS_PER_MM
half_period_us = 500000 / step_frequency
```

**Homing** works in two passes per axis: a fast approach at `HOMING_SPEED`, then when the endstop triggers it backs off 3mm and approaches again slowly. This gives a repeatable home position even if the initial approach overshoots slightly.

**Feed hold** (`!`) is handled character-by-character in the main loop, outside the line buffer. When `!` is received, `machineState` is set to `HOLD`. The movement loop checks this flag on every step and pauses when it sees it. This means the robot stops within one step — effectively instantaneous.

**Supported G-code:**

| Command | Action |
|---------|--------|
| `G0 X_ Y_ F_` | Rapid move (pen travel) |
| `G1 X_ Y_ F_` | Linear move (pen writing) |
| `G4 P_` | Dwell (pause) in seconds |
| `G21` | Set mm units (acknowledged, always mm) |
| `G28` | Go to home position |
| `G90` | Absolute positioning (acknowledged, always absolute) |
| `M3` | Pen down (servo to PEN_DOWN_ANGLE) |
| `M5` | Pen up (servo to PEN_UP_ANGLE) |
| `M2` / `M30` | End of program |
| `$H` | Run homing cycle |
| `?` | Report status in GRBL format |
| `!` | Feed hold (real-time, not line-buffered) |
| `~` | Resume from hold |
| `0x18` | Soft reset |

### Database

The app uses SQLite stored in `handwriting_robot.db` in the project folder. No database server needed — SQLite is a file. Three tables:

**handwriting_profiles** — one row per style. Stores name, slant angle, letter spacing multiplier, word spacing multiplier, baseline wobble amount, and stroke width.

**glyphs** — one row per character per profile. Stores the character itself, the stroke data as JSON, and the width ratio. The stroke JSON looks like:
```json
[
  {"pen": "down", "points": [[0.1, 0.0], [0.15, 0.3], [0.2, 0.8]]},
  {"pen": "down", "points": [[0.4, 0.1], [0.5, 0.9]]}
]
```

**writing_jobs** — one row per print job. Stores the source image path (for scan jobs), the detected text blocks as JSON, the generated G-code as text, and the job status (pending → generating → ready → printing → done, or error).

---

## 10. Troubleshooting

**Robot shows "disconnected" in the app**
The Python app polls `/api/robot/status` every 4 seconds. If it cannot reach the ESP32, it shows disconnected. Check:
- ESP32 is powered and booted (LED on)
- Both devices are on the same WiFi network
- IP address in the app matches what the ESP32 printed to Serial Monitor
- Try `ping 192.168.1.xxx` in a terminal to verify basic reachability

**"No text detected" after uploading a document**
- Better lighting — shadows cause OCR to fail
- Make the document flat — creases create shadows
- Try a higher DPI setting if using a phone photo
- Ensure the document has clear, dark text on a light background

**"No strokes found" when uploading a glyph photo**
- Use a white or very light background
- Write with a dark pen — pencil is often too light
- Crop tightly around just the letter — extra whitespace is fine, other letters are not
- Ensure the image is in focus

**Letters print at wrong size or position**
- `STEPS_PER_MM` is wrong — measure a known move (e.g. `G0 X100 Y0`) with a ruler and compare
- Paper is not placed at the correct home position — the top-left corner must be exactly at X0 Y0

**Pen does not lift between strokes**
- `PEN_UP_ANGLE` needs adjusting — increase it until the pen clearly clears the paper
- The servo may not have enough power — make sure it is connected to 5V, not 3.3V

**Motors make noise but do not move**
- Check coil wiring — swap one coil pair (1A↔1B or 2A↔2B) if the motor just vibrates
- Check ENABLE pin is pulled LOW (motor controller does this automatically on first move)
- Increase the current limit on the A4988 (potentiometer on the driver)

**Homing does not stop at the endstop**
- Endstop wiring: one terminal to the GPIO pin, other terminal to GND
- Test with a multimeter — the pin should read ~3.3V at rest and 0V when triggered
- Confirm `INPUT_PULLUP` is working — no external resistor needed

**Port 8000 already in use**
```bash
# Mac / Linux
lsof -ti:8000 | xargs kill
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Python packages fail to install**
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 11. File reference

```
handwriting-robot/
│
├── main.py                     Entry point — run this. Auto-installs packages,
│                               starts uvicorn web server on port 8000.
│
├── app.py                      FastAPI application factory. Registers all routes,
│                               serves the frontend at /, API at /api/.
│
├── config.py                   All settings with defaults. Reads from .env if
│                               present. Variables can be changed at runtime via
│                               the Robot Control config panel.
│
├── database.py                 SQLite connection using SQLAlchemy async ORM.
│                               Creates handwriting_robot.db on first run.
│                               Call init_db() to create tables.
│
├── requirements.txt            Python dependencies.
│
├── .env.example                Copy to .env, fill in ESP32_IP.
│
├── handwriting_robot.db        Created automatically on first run. Contains all
│                               profiles, glyphs, and job history.
│
├── uploads/                    Uploaded document scans are stored here.
│
├── static/
│   └── index.html              The entire frontend — one HTML file with React
│                               via CDN. No build step. Served by FastAPI.
│
├── models/
│   ├── db_models.py            SQLAlchemy table definitions (HandwritingProfile,
│   │                           Glyph, WritingJob).
│   └── schemas.py              Pydantic request/response models for the API.
│
├── routers/
│   ├── profiles.py             /api/profiles/ — CRUD for profiles, glyph upload
│   │                           (single image and Calligraphr sheet), style measurement.
│   ├── documents.py            /api/documents/ — scan preview (OCR), job creation
│   │                           from scan or typed text, G-code generation, print.
│   └── robot.py                /api/robot/ — status, home, stop, pause, resume,
│                               raw G-code send, config get/set/test.
│
├── services/
│   ├── ocr_service.py          Image → words with mm coordinates.
│   │                           Uses OpenCV for preprocessing, Tesseract for OCR.
│   ├── stroke_service.py       Glyph image → normalized stroke paths.
│   │                           Uses skeletonization + B-spline smoothing.
│   ├── calligraphr_service.py  Filled Calligraphr sheet → all glyphs at once.
│   │                           Detects boxes, crops each, runs stroke extraction.
│   ├── gcode_service.py        Text blocks + strokes → G-code.
│   │                           Applies slant, wobble, spacing, wrapping.
│   └── robot_service.py        HTTP client for the ESP32 bridge.
│                               All calls use the live config values from config.py.
│
└── esp32/
    ├── 1_wifi_bridge.ino       Flash onto the WiFi ESP32. Runs an HTTP server,
    │                           forwards commands to the motor ESP32 over Serial1.
    └── 2_motor_controller.ino  Flash onto the motor ESP32. Parses G-code from
                                Serial0, drives steppers and servo.
```

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Server health and robot connection state |
| POST | `/api/shutdown` | Gracefully shut down the server |
| GET | `/api/profiles/` | List all profiles |
| POST | `/api/profiles/` | Create a profile |
| PATCH | `/api/profiles/{id}` | Update profile settings |
| DELETE | `/api/profiles/{id}` | Delete profile and all its glyphs |
| GET | `/api/profiles/{id}/glyphs` | List glyphs in a profile |
| POST | `/api/profiles/{id}/glyphs/upload-image` | Upload one letter photo |
| POST | `/api/profiles/{id}/glyphs/upload-calligraphr` | Upload a filled Calligraphr sheet |
| DELETE | `/api/profiles/{id}/glyphs/{char}` | Delete one glyph |
| POST | `/api/profiles/{id}/measure-slant` | Measure slant from a handwriting photo |
| POST | `/api/documents/scan-preview` | OCR a document, return word positions |
| POST | `/api/documents/jobs/from-scan` | Create a job from a scanned document |
| POST | `/api/documents/jobs/from-text` | Create a job from typed text |
| GET | `/api/documents/jobs` | List all jobs |
| POST | `/api/documents/jobs/{id}/generate` | Generate G-code for a job |
| POST | `/api/documents/jobs/{id}/print` | Send G-code to robot |
| GET | `/api/documents/jobs/{id}/gcode` | Download G-code file |
| DELETE | `/api/documents/jobs/{id}` | Delete a job |
| GET | `/api/robot/status` | Robot state and position |
| GET | `/api/robot/config` | Current ESP32 connection settings |
| POST | `/api/robot/config` | Update and save settings |
| POST | `/api/robot/config/test` | Test connection without saving |
| POST | `/api/robot/home` | Run homing cycle |
| POST | `/api/robot/stop` | Emergency stop |
| POST | `/api/robot/pause` | Feed hold |
| POST | `/api/robot/resume` | Resume from hold |
| POST | `/api/robot/send-raw` | Send arbitrary G-code |

Interactive API docs are available at **http://localhost:8000/docs** while the server is running.
