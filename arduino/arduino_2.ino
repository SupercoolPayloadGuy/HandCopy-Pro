/**
 * ╔══════════════════════════════════════════════════════════╗
 * ║   HANDWRITING ROBOT — FILE 2 of 2                        ║
 * ║   Motor Controller ESP32                                  ║
 * ║                                                           ║
 * ║   Flash this onto the ESP32 wired to the stepper         ║
 * ║   drivers and pen servo.                                  ║
 * ║   It reads G-code from the WiFi Bridge over serial       ║
 * ║   and moves the motors.                                   ║
 * ╚══════════════════════════════════════════════════════════╝
 *
 * ── STEPPER DRIVER WIRING (A4988 or TMC2209) ────────────────
 *
 *   ESP32 pin  →  Driver pin
 *   ──────────────────────────────
 *   GPIO 26    →  X STEP
 *   GPIO 27    →  X DIR
 *   GPIO 14    →  Y STEP
 *   GPIO 12    →  Y DIR
 *   GPIO 13    →  ENABLE  (active LOW, shared by both drivers)
 *
 * ── ENDSTOPS ─────────────────────────────────────────────────
 *
 *   GPIO 34    →  X endstop signal  (GND when triggered)
 *   GPIO 35    →  Y endstop signal  (GND when triggered)
 *   Uses INPUT_PULLUP — no external resistor needed.
 *
 * ── PEN SERVO (SG90 or similar) ─────────────────────────────
 *
 *   GPIO 25    →  Servo signal (orange/yellow wire)
 *   5V         →  Servo power  (red wire)   ← use 5V not 3.3V
 *   GND        →  Servo GND    (brown/black wire)
 *
 * ── TO WIFI BRIDGE ESP32 ─────────────────────────────────────
 *
 *   GPIO 1 (TX)  →  Bridge GPIO 16 (RX)
 *   GPIO 3 (RX)  ←  Bridge GPIO 17 (TX)
 *   GND          ─   GND
 *
 * ── STEPPER DRIVER WIRING (A4988) ───────────────────────────
 *
 *   A4988        →  Connect to
 *   ───────────────────────────────────────────────────────────
 *   VMOT             12V PSU +
 *   GND (motor)      12V PSU -
 *   VDD              3.3V (ESP32)
 *   GND (logic)      GND (ESP32)
 *   ENABLE           GPIO 13
 *   STEP             GPIO 26 (X) or GPIO 14 (Y)
 *   DIR              GPIO 27 (X) or GPIO 12 (Y)
 *   1A 1B 2A 2B      Stepper motor coils
 *   MS1 MS2 MS3      Microstepping pins — tie all HIGH for 1/16 step
 *
 * ── STEPS PER MM ─────────────────────────────────────────────
 *
 *   Formula: (motor_steps_per_rev × microstepping) / (belt_pitch_mm × pulley_teeth)
 *
 *   Typical setup: 200 steps, 1/16 micro, GT2 belt (2mm), 20-tooth pulley
 *   → (200 × 16) / (2 × 20) = 80 steps/mm
 *
 * ── REQUIRED LIBRARY ─────────────────────────────────────────
 *
 *   Install "ESP32Servo" by Kevin Harrington via Library Manager
 */

#include <ESP32Servo.h>

// ═══════════════════════════════════════════════════
//  TUNE THESE FOR YOUR MACHINE
// ═══════════════════════════════════════════════════
float STEPS_PER_MM   = 80.0;   // see formula above
int   PEN_DOWN_ANGLE = 30;     // servo degrees — pen on paper
int   PEN_UP_ANGLE   = 90;     // servo degrees — pen lifted
float MAX_FEED       = 5000.0; // mm/min hard limit
float HOMING_SPEED   = 10.0;   // mm/s during homing
// ═══════════════════════════════════════════════════

// Pin definitions
#define X_STEP_PIN    26
#define X_DIR_PIN     27
#define Y_STEP_PIN    14
#define Y_DIR_PIN     12
#define ENABLE_PIN    13
#define X_ENDSTOP_PIN 34
#define Y_ENDSTOP_PIN 35
#define SERVO_PIN     25

Servo penServo;

float posX = 0.0, posY = 0.0;
bool  penIsDown  = false;
bool  isHomed    = false;

enum State { IDLE, RUN, HOLD, ALARM };
State machineState = ALARM;   // stays ALARM until homed


// ══════════════════════════════════════════════════
//  MOTORS
// ══════════════════════════════════════════════════

void enableMotors()  { digitalWrite(ENABLE_PIN, LOW);  }
void disableMotors() { digitalWrite(ENABLE_PIN, HIGH); }

// Move both axes simultaneously using Bresenham interpolation
void moveTo(float tx, float ty, float feed_mm_per_min) {
  if (machineState == ALARM) return;

  float dx = tx - posX;
  float dy = ty - posY;
  if (abs(dx) < 0.001 && abs(dy) < 0.001) return;

  feed_mm_per_min = constrain(feed_mm_per_min, 1.0, MAX_FEED);
  float speed_hz  = (feed_mm_per_min / 60.0) * STEPS_PER_MM;

  long stepsX    = (long)(dx * STEPS_PER_MM);
  long stepsY    = (long)(dy * STEPS_PER_MM);
  long totalSteps = max(abs(stepsX), abs(stepsY));
  if (totalSteps == 0) return;

  digitalWrite(X_DIR_PIN, stepsX >= 0 ? HIGH : LOW);
  digitalWrite(Y_DIR_PIN, stepsY >= 0 ? HIGH : LOW);

  long halfPeriod_us = (long)(500000.0 / speed_hz);
  if (halfPeriod_us < 2) halfPeriod_us = 2;

  long errX = 0, errY = 0;
  long absX = abs(stepsX), absY = abs(stepsY);

  for (long i = 0; i < totalSteps; i++) {
    // Feed hold
    while (machineState == HOLD) delay(50);
    if (machineState == ALARM) break;

    errX += absX;
    errY += absY;
    bool doX = (errX * 2 >= totalSteps);
    bool doY = (errY * 2 >= totalSteps);

    if (doX) { digitalWrite(X_STEP_PIN, HIGH); errX -= totalSteps; }
    if (doY) { digitalWrite(Y_STEP_PIN, HIGH); errY -= totalSteps; }
    delayMicroseconds(halfPeriod_us);
    if (doX) digitalWrite(X_STEP_PIN, LOW);
    if (doY) digitalWrite(Y_STEP_PIN, LOW);
    delayMicroseconds(halfPeriod_us);
  }

  posX = tx;
  posY = ty;
}


// ══════════════════════════════════════════════════
//  PEN SERVO
// ══════════════════════════════════════════════════

void setPen(bool down) {
  penServo.write(down ? PEN_DOWN_ANGLE : PEN_UP_ANGLE);
  penIsDown = down;
  delay(120);
}


// ══════════════════════════════════════════════════
//  HOMING
// ══════════════════════════════════════════════════

void homeAxis(int stepPin, int dirPin, int endstopPin, float& pos) {
  long halfPeriod_us = (long)(500000.0 / (HOMING_SPEED * STEPS_PER_MM));

  // Fast approach toward endstop (negative direction)
  digitalWrite(dirPin, LOW);
  while (digitalRead(endstopPin) == HIGH) {
    digitalWrite(stepPin, HIGH); delayMicroseconds(halfPeriod_us);
    digitalWrite(stepPin, LOW);  delayMicroseconds(halfPeriod_us);
  }

  // Back off 3mm
  digitalWrite(dirPin, HIGH);
  long backoff = (long)(STEPS_PER_MM * 3);
  for (long i = 0; i < backoff; i++) {
    digitalWrite(stepPin, HIGH); delayMicroseconds(halfPeriod_us * 2);
    digitalWrite(stepPin, LOW);  delayMicroseconds(halfPeriod_us * 2);
  }

  // Slow approach
  digitalWrite(dirPin, LOW);
  halfPeriod_us *= 5;
  while (digitalRead(endstopPin) == HIGH) {
    digitalWrite(stepPin, HIGH); delayMicroseconds(halfPeriod_us);
    digitalWrite(stepPin, LOW);  delayMicroseconds(halfPeriod_us);
  }

  pos = 0.0;
}

void doHoming() {
  Serial.println("[MOTOR] Homing...");
  setPen(false);
  enableMotors();
  homeAxis(X_STEP_PIN, X_DIR_PIN, X_ENDSTOP_PIN, posX);
  Serial.println("[MOTOR] X homed");
  homeAxis(Y_STEP_PIN, Y_DIR_PIN, Y_ENDSTOP_PIN, posY);
  Serial.println("[MOTOR] Y homed");
  posX = 0; posY = 0;
  isHomed = true;
  machineState = IDLE;
  Serial.println("[MOTOR] Homing complete");
}


// ══════════════════════════════════════════════════
//  G-CODE PARSER
// ══════════════════════════════════════════════════

float getParam(const String& line, char letter, float def) {
  int i = line.indexOf(letter);
  if (i < 0) return def;
  int e = i + 1;
  while (e < (int)line.length() &&
         (isDigit(line[e]) || line[e] == '.' || line[e] == '-')) e++;
  return line.substring(i + 1, e).toFloat();
}

bool hasParam(const String& line, char letter) {
  return line.indexOf(letter) >= 0;
}

void processLine(String line) {
  line.trim();
  line.toUpperCase();
  if (line.length() == 0 || line.startsWith(";") || line.startsWith("(")) {
    Serial.println("ok");
    return;
  }
  // Strip inline comment
  int sc = line.indexOf(';');
  if (sc >= 0) line = line.substring(0, sc);
  line.trim();

  // Status query
  if (line == "?") {
    String st;
    switch (machineState) {
      case IDLE:  st = "Idle";  break;
      case RUN:   st = "Run";   break;
      case HOLD:  st = "Hold";  break;
      default:    st = "Alarm"; break;
    }
    Serial.printf("<<%s|MPos:%.3f,%.3f,0.000>>\n", st.c_str(), posX, posY);
    return;
  }

  // Homing
  if (line == "$H") {
    doHoming();
    Serial.println("ok");
    return;
  }

  // Ignore other $ commands
  if (line.startsWith("$")) { Serial.println("ok"); return; }

  float feed = 1000.0;
  if (hasParam(line, 'F')) feed = getParam(line, 'F', feed);

  // G0 — rapid move
  if (line.startsWith("G0")) {
    float tx = hasParam(line, 'X') ? getParam(line, 'X', posX) : posX;
    float ty = hasParam(line, 'Y') ? getParam(line, 'Y', posY) : posY;
    machineState = RUN;
    moveTo(tx, ty, 3000.0);
    machineState = IDLE;
    Serial.println("ok");
    return;
  }

  // G1 — linear move
  if (line.startsWith("G1")) {
    float tx = hasParam(line, 'X') ? getParam(line, 'X', posX) : posX;
    float ty = hasParam(line, 'Y') ? getParam(line, 'Y', posY) : posY;
    machineState = RUN;
    moveTo(tx, ty, feed);
    machineState = IDLE;
    Serial.println("ok");
    return;
  }

  // G4 — dwell
  if (line.startsWith("G4")) {
    float p = getParam(line, 'P', 0);
    delay((unsigned long)(p * 1000));
    Serial.println("ok");
    return;
  }

  // G21 — mm mode (always mm, just ack)
  if (line.startsWith("G21")) { Serial.println("ok"); return; }

  // G90 — absolute mode (always absolute, just ack)
  if (line.startsWith("G90")) { Serial.println("ok"); return; }

  // G28 — go home
  if (line.startsWith("G28")) {
    setPen(false);
    if (!isHomed) doHoming();
    else moveTo(0, 0, 3000);
    Serial.println("ok");
    return;
  }

  // M3 — pen down
  if (line.startsWith("M3")) {
    setPen(true);
    Serial.println("ok");
    return;
  }

  // M5 — pen up
  if (line.startsWith("M5")) {
    setPen(false);
    Serial.println("ok");
    return;
  }

  // M2 / M30 — end of program
  if (line.startsWith("M2") || line.startsWith("M30")) {
    setPen(false);
    machineState = IDLE;
    Serial.println("ok");
    return;
  }

  // Unknown command — ack anyway so sender doesn't hang
  Serial.print("ok ; unknown: ");
  Serial.println(line);
}


// ══════════════════════════════════════════════════
//  SETUP & LOOP
// ══════════════════════════════════════════════════

void setup() {
  // Serial0 = USB + UART0 pins (GPIO1 TX, GPIO3 RX)
  // This is how the WiFi Bridge talks to us
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Handwriting Robot — Motor Controller ===");
  Serial.println("Waiting for G-code. Send $H to home first.\n");

  pinMode(X_STEP_PIN,    OUTPUT);
  pinMode(X_DIR_PIN,     OUTPUT);
  pinMode(Y_STEP_PIN,    OUTPUT);
  pinMode(Y_DIR_PIN,     OUTPUT);
  pinMode(ENABLE_PIN,    OUTPUT);
  disableMotors();

  pinMode(X_ENDSTOP_PIN, INPUT_PULLUP);
  pinMode(Y_ENDSTOP_PIN, INPUT_PULLUP);

  penServo.attach(SERVO_PIN);
  setPen(false);
}

String inputBuffer = "";

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    // Real-time single-byte commands
    if (c == '!') { machineState = HOLD;  continue; }
    if (c == '~') { machineState = RUN;   continue; }
    if (c == 0x18) {
      setPen(false);
      machineState = ALARM;
      inputBuffer  = "";
      Serial.println("Grbl reset");
      continue;
    }
    if (c == '?') { processLine("?"); continue; }

    // Accumulate line
    if (c == '\n' || c == '\r') {
      if (inputBuffer.length() > 0) {
        processLine(inputBuffer);
        inputBuffer = "";
      }
    } else {
      inputBuffer += c;
      if (inputBuffer.length() > 256) inputBuffer = "";  // overflow guard
    }
  }
}
