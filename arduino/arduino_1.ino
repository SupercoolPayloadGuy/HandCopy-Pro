/**
 * ╔══════════════════════════════════════════════════════════╗
 * ║   HANDWRITING ROBOT — FILE 1 of 2                        ║
 * ║   WiFi Bridge ESP32                                       ║
 * ║                                                           ║
 * ║   Flash this onto the ESP32 that connects to your WiFi.  ║
 * ║   It receives commands from the Python app and forwards  ║
 * ║   them to the Motor ESP32 over a serial cable.           ║
 * ╚══════════════════════════════════════════════════════════╝
 *
 * WIRING — three wires between this ESP32 and the Motor ESP32:
 *
 *   This ESP32 (WiFi)          Motor ESP32 (file 2)
 *   ─────────────────          ────────────────────
 *   GPIO 16  (RX)  ◄─────────  GPIO 1  (TX)
 *   GPIO 17  (TX)  ──────────► GPIO 3  (RX)
 *   GND            ───────────  GND
 *
 * SETUP:
 *   1. Fill in WIFI_SSID and WIFI_PASSWORD below
 *   2. Arduino IDE: Board → ESP32 Dev Module
 *   3. Upload this sketch
 *   4. Open Serial Monitor at 115200 baud
 *   5. It prints the IP address on boot
 *   6. Enter that IP in the Robot Control tab of the web app
 */

#include <WiFi.h>
#include <WebServer.h>

// ═══════════════════════════════════════════
//  CHANGE THESE
// ═══════════════════════════════════════════
const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
// ═══════════════════════════════════════════

#define MOTOR_RX_PIN  16
#define MOTOR_TX_PIN  17
#define MOTOR_BAUD    115200

WebServer server(80);


// ── Send one G-code line, wait for "ok" back ──────────────────
String sendLine(const String& line, unsigned long timeout_ms = 5000) {
  Serial1.println(line);
  String response = "";
  unsigned long start = millis();
  while (millis() - start < timeout_ms) {
    if (Serial1.available()) {
      char c = Serial1.read();
      response += c;
      if (response.endsWith("ok\n") || response.endsWith("ok\r\n") ||
          response.indexOf("error") >= 0 || response.indexOf("ALARM") >= 0) {
        break;
      }
    }
    delay(1);
  }
  response.trim();
  return response;
}

// ── Stream a full G-code program line by line ─────────────────
void streamGcode(const String& gcode) {
  Serial.printf("[BRIDGE] Streaming %d bytes\n", gcode.length());
  int lineCount = 0;
  int start = 0;
  while (start < (int)gcode.length()) {
    int end = gcode.indexOf('\n', start);
    if (end == -1) end = gcode.length();
    String line = gcode.substring(start, end);
    line.trim();
    if (line.length() > 0 && !line.startsWith(";") && !line.startsWith("(")) {
      sendLine(line, 10000);
      lineCount++;
      if (lineCount % 20 == 0) Serial.printf("[BRIDGE] %d lines sent\n", lineCount);
    }
    start = end + 1;
  }
  Serial.printf("[BRIDGE] Done — %d lines\n", lineCount);
}

// ── Query motor ESP32 status and return as JSON ───────────────
void handleStatus() {
  // Flush stale bytes
  while (Serial1.available()) Serial1.read();
  Serial1.print("?");

  String raw = "";
  unsigned long start = millis();
  while (millis() - start < 400) {
    if (Serial1.available()) {
      char c = Serial1.read();
      raw += c;
      if (c == '>') break;
    }
    delay(1);
  }

  // Parse <State|MPos:x,y,z|...>
  String state = "disconnected";
  float x = 0, y = 0;

  int ltb = raw.indexOf('<'), pipe = raw.indexOf('|');
  if (ltb >= 0 && pipe > ltb) {
    state = raw.substring(ltb + 1, pipe);
    state.toLowerCase();
  }
  int mp = raw.indexOf("MPos:");
  if (mp < 0) mp = raw.indexOf("WPos:");
  if (mp >= 0) {
    mp += 5;
    int ep = raw.indexOf('|', mp);
    if (ep < 0) ep = raw.indexOf('>', mp);
    if (ep > mp) {
      String c = raw.substring(mp, ep);
      int c1 = c.indexOf(',');
      if (c1 > 0) {
        x = c.substring(0, c1).toFloat();
        int c2 = c.indexOf(',', c1 + 1);
        if (c2 > 0) y = c.substring(c1 + 1, c2).toFloat();
      }
    }
  }

  String json = "{\"state\":\"" + state + "\","
                "\"pos\":{\"x\":" + String(x, 3) + ","
                         "\"y\":" + String(y, 3) + "}}";
  server.send(200, "application/json", json);
}

void handlePrint() {
  if (!server.hasArg("plain")) {
    server.send(400, "text/plain", "Send G-code as request body");
    return;
  }
  server.send(200, "text/plain", "OK");
  streamGcode(server.arg("plain"));
}

void handleHome() {
  Serial.println("[BRIDGE] Home");
  String r = sendLine("$H", 60000);
  server.send(200, "text/plain", "OK: " + r);
}

void handleStop() {
  Serial.println("[BRIDGE] STOP");
  Serial1.write(0x18);
  delay(200);
  server.send(200, "text/plain", "OK");
}

void handlePause() {
  Serial.println("[BRIDGE] Pause");
  Serial1.write('!');
  server.send(200, "text/plain", "OK");
}

void handleResume() {
  Serial.println("[BRIDGE] Resume");
  Serial1.write('~');
  server.send(200, "text/plain", "OK");
}


void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n=== Handwriting Robot — WiFi Bridge ===");

  Serial1.begin(MOTOR_BAUD, SERIAL_8N1, MOTOR_RX_PIN, MOTOR_TX_PIN);
  Serial.printf("Serial1 ready (RX=%d TX=%d)\n", MOTOR_RX_PIN, MOTOR_TX_PIN);

  Serial.printf("Connecting to WiFi: %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (++attempts > 40) {
      Serial.println("\nFailed. Rebooting...");
      delay(3000);
      ESP.restart();
    }
  }

  Serial.println("\n✓ WiFi connected");
  Serial.print("  ► IP Address: ");
  Serial.println(WiFi.localIP());
  Serial.println("  ← Enter this IP in the Robot Control tab\n");

  server.on("/status", HTTP_GET,  handleStatus);
  server.on("/print",  HTTP_POST, handlePrint);
  server.on("/home",   HTTP_POST, handleHome);
  server.on("/stop",   HTTP_POST, handleStop);
  server.on("/pause",  HTTP_POST, handlePause);
  server.on("/resume", HTTP_POST, handleResume);
  server.begin();
  Serial.println("✓ Web server on port 80");
}

void loop() {
  server.handleClient();

  // Mirror motor ESP32 output to Serial Monitor
  while (Serial1.available()) Serial.write(Serial1.read());

  // Auto-reconnect WiFi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost, reconnecting...");
    WiFi.reconnect();
    delay(5000);
  }
}
