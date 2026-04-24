#include <Arduino.h>
#include <ArduinoJson.h>
#include <M5Unified.h>

struct BuddyState {
  uint8_t total = 0;
  uint8_t running = 0;
  uint8_t waiting = 0;
  uint32_t tokensToday = 0;
  bool completed = false;
  bool connected = false;
  uint32_t lastLiveMs = 0;
  char msg[64] = "No Claude connected";
  char entries[6][72] = {};
  uint8_t nEntries = 0;
  char promptId[40] = "";
  char promptTool[24] = "";
  char noticeFrom[24] = "";
  char noticeBody[96] = "";
  char weather[32] = "";
  char themeTitle[24] = "";
  char themeSubtitle[24] = "";
  char themeDetail[24] = "";
};

static BuddyState state;
static char lineBuf[1024];
static size_t lineLen = 0;
static char deviceName[24] = "BuddyParallel";
static char ownerName[24] = "";
static uint8_t brightnessLevel = 3;
static bool soundEnabled = true;
static bool ledEnabled = true;
static uint32_t lastDrawMs = 0;
static uint32_t lastAnimMs = 0;
static uint8_t animFrame = 0;

static void safeCopy(char* dst, size_t len, const char* src) {
  if (!dst || len == 0) return;
  strncpy(dst, src ? src : "", len - 1);
  dst[len - 1] = 0;
}

static void setBrightness(uint8_t level) {
  brightnessLevel = level > 4 ? 4 : level;
  M5.Display.setBrightness(32 + brightnessLevel * 48);
}

static void beep(uint16_t freq, uint16_t dur) {
  if (!soundEnabled) return;
  M5.Speaker.tone(freq, dur);
}

static void sendLine(const char* text) {
  Serial.println(text);
}

static void sendPermission(const char* decision) {
  if (!state.promptId[0]) return;
  char out[128];
  snprintf(out, sizeof(out), "{\"cmd\":\"permission\",\"id\":\"%s\",\"decision\":\"%s\"}", state.promptId, decision);
  sendLine(out);
  state.promptId[0] = 0;
  beep(strcmp(decision, "approve") == 0 ? 1600 : 600, 90);
}

static void sendStatus() {
  char out[768];
  snprintf(
    out,
    sizeof(out),
    "{\"ack\":\"status\",\"ok\":true,\"n\":0,\"data\":{"
    "\"name\":\"%s\",\"owner\":\"%s\",\"sec\":false,"
    "\"settings\":{\"brightness\":%u,\"sound\":%s,\"led\":%s},"
    "\"pet\":{\"mode\":\"cores3\",\"index\":0,\"name\":\"cores3\",\"gif_available\":false},"
    "\"bat\":{\"usb\":true},"
    "\"sys\":{\"up\":%lu,\"heap\":%u,\"fsFree\":0,\"fsTotal\":0},"
    "\"stats\":{\"appr\":0,\"deny\":0,\"vel\":0,\"nap\":0,\"lvl\":1}"
    "}}\n",
    deviceName,
    ownerName,
    brightnessLevel,
    soundEnabled ? "true" : "false",
    ledEnabled ? "true" : "false",
    millis() / 1000,
    ESP.getFreeHeap()
  );
  Serial.print(out);
}

static void clearTransientFields(BuddyState& s) {
  s.promptId[0] = 0;
  s.promptTool[0] = 0;
  s.noticeFrom[0] = 0;
  s.noticeBody[0] = 0;
  s.weather[0] = 0;
  s.themeTitle[0] = 0;
  s.themeSubtitle[0] = 0;
  s.themeDetail[0] = 0;
}

static void applyJson(const char* line) {
  JsonDocument doc;
  if (deserializeJson(doc, line)) return;

  const char* cmd = doc["cmd"];
  if (cmd) {
    if (strcmp(cmd, "status") == 0) {
      sendStatus();
    } else if (strcmp(cmd, "name") == 0) {
      safeCopy(deviceName, sizeof(deviceName), doc["name"] | deviceName);
      Serial.println("{\"ack\":\"name\",\"ok\":true,\"n\":0}");
    } else if (strcmp(cmd, "owner") == 0) {
      safeCopy(ownerName, sizeof(ownerName), doc["name"] | ownerName);
      Serial.println("{\"ack\":\"owner\",\"ok\":true,\"n\":0}");
    } else if (strcmp(cmd, "brightness") == 0) {
      int level = brightnessLevel;
      if (doc["level"].is<int>()) level = doc["level"].as<int>();
      else if (doc["value"].is<int>()) level = doc["value"].as<int>();
      if (level < 0) level = 0;
      setBrightness((uint8_t)level);
      Serial.printf("{\"ack\":\"brightness\",\"ok\":true,\"n\":%u}\n", brightnessLevel);
    } else if (strcmp(cmd, "sound") == 0) {
      if (doc["on"].is<bool>()) soundEnabled = doc["on"].as<bool>();
      else if (doc["value"].is<bool>()) soundEnabled = doc["value"].as<bool>();
      Serial.printf("{\"ack\":\"sound\",\"ok\":true,\"n\":%u}\n", soundEnabled ? 1 : 0);
    } else if (strcmp(cmd, "led") == 0) {
      if (doc["on"].is<bool>()) ledEnabled = doc["on"].as<bool>();
      else if (doc["value"].is<bool>()) ledEnabled = doc["value"].as<bool>();
      Serial.printf("{\"ack\":\"led\",\"ok\":true,\"n\":%u}\n", ledEnabled ? 1 : 0);
    }
    state.lastLiveMs = millis();
    state.connected = true;
    return;
  }

  if (!doc["time"].isNull()) {
    state.lastLiveMs = millis();
    state.connected = true;
    return;
  }

  state.total = doc["total"] | state.total;
  state.running = doc["running"] | state.running;
  state.waiting = doc["waiting"] | state.waiting;
  state.completed = doc["completed"] | false;
  state.tokensToday = doc["tokens_today"] | state.tokensToday;
  safeCopy(state.msg, sizeof(state.msg), doc["msg"] | state.msg);
  state.nEntries = 0;
  JsonArray entries = doc["entries"];
  if (!entries.isNull()) {
    for (JsonVariant v : entries) {
      if (state.nEntries >= 6) break;
      safeCopy(state.entries[state.nEntries], sizeof(state.entries[state.nEntries]), v.as<const char*>());
      state.nEntries++;
    }
  }

  JsonObject root = doc.as<JsonObject>();
  if (root.containsKey("prompt")) {
    JsonObject prompt = root["prompt"].as<JsonObject>();
    if (prompt.isNull()) {
      state.promptId[0] = 0;
      state.promptTool[0] = 0;
    } else {
      safeCopy(state.promptId, sizeof(state.promptId), prompt["id"] | "");
      safeCopy(state.promptTool, sizeof(state.promptTool), prompt["tool"] | "Approve");
    }
  }
  if (root.containsKey("notice")) {
    JsonObject notice = root["notice"].as<JsonObject>();
    if (notice.isNull()) {
      state.noticeFrom[0] = 0;
      state.noticeBody[0] = 0;
    } else {
      safeCopy(state.noticeFrom, sizeof(state.noticeFrom), notice["from"] | "");
      safeCopy(state.noticeBody, sizeof(state.noticeBody), notice["body"] | "");
    }
  }
  if (root.containsKey("weather")) {
    JsonObject weather = root["weather"].as<JsonObject>();
    const char* summary = weather.isNull() ? "" : (weather["board_summary"] | "");
    safeCopy(state.weather, sizeof(state.weather), summary);
  }
  if (root.containsKey("theme")) {
    JsonObject theme = root["theme"].as<JsonObject>();
    if (theme.isNull()) {
      state.themeTitle[0] = 0;
      state.themeSubtitle[0] = 0;
      state.themeDetail[0] = 0;
    } else {
      safeCopy(state.themeTitle, sizeof(state.themeTitle), theme["title"] | "");
      safeCopy(state.themeSubtitle, sizeof(state.themeSubtitle), theme["subtitle"] | "");
      safeCopy(state.themeDetail, sizeof(state.themeDetail), theme["detail"] | "");
    }
  }
  state.lastLiveMs = millis();
  state.connected = true;
}

static void pollSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        lineBuf[lineLen] = 0;
        if (lineBuf[0] == '{') applyJson(lineBuf);
        lineLen = 0;
      }
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    }
  }
  if (state.connected && millis() - state.lastLiveMs > 30000) {
    state.connected = false;
    state.total = 0;
    state.running = 0;
    state.waiting = 0;
    state.completed = false;
    safeCopy(state.msg, sizeof(state.msg), "No Claude connected");
    state.nEntries = 0;
    clearTransientFields(state);
  }
}

static void drawHeader() {
  M5.Display.fillRect(0, 0, 320, 34, 0x2104);
  M5.Display.setTextColor(0xFFFF, 0x2104);
  M5.Display.setTextSize(2);
  M5.Display.drawString(deviceName, 10, 8);
  M5.Display.setTextSize(1);
  M5.Display.setTextColor(state.connected ? 0x07E0 : 0xC618, 0x2104);
  M5.Display.drawString(state.connected ? "USB live" : "waiting", 238, 12);
}

static void drawCard(int x, int y, int w, int h, const char* title, uint16_t accent) {
  M5.Display.fillRoundRect(x, y, w, h, 8, 0x1082);
  M5.Display.drawRoundRect(x, y, w, h, 8, accent);
  M5.Display.setTextColor(accent, 0x1082);
  M5.Display.setTextSize(1);
  M5.Display.drawString(title, x + 10, y + 8);
}

static void drawMain() {
  M5.Display.fillScreen(0x0000);
  drawHeader();

  uint16_t accent = state.waiting ? 0xFA20 : (state.running ? 0x07FF : 0x7BEF);
  drawCard(10, 44, 300, 78, "Status", accent);
  M5.Display.setTextColor(0xFFFF, 0x1082);
  M5.Display.setTextSize(2);
  M5.Display.drawString(state.msg, 20, 70);
  M5.Display.setTextSize(1);
  char stats[80];
  snprintf(stats, sizeof(stats), "sessions %u | running %u | waiting %u | tokens %lu", state.total, state.running, state.waiting, state.tokensToday);
  M5.Display.setTextColor(0xC618, 0x1082);
  M5.Display.drawString(stats, 20, 102);

  drawCard(10, 132, 145, 86, "Queue", 0xFBC0);
  M5.Display.setTextColor(0xFFFF, 0x1082);
  for (uint8_t i = 0; i < state.nEntries && i < 4; i++) {
    M5.Display.drawString(state.entries[i], 20, 158 + i * 14);
  }

  drawCard(165, 132, 145, 86, "Side", 0x07FF);
  M5.Display.setTextColor(0xFFFF, 0x1082);
  if (state.promptId[0]) {
    M5.Display.drawString("Approve?", 175, 158);
    M5.Display.drawString(state.promptTool, 175, 174);
    M5.Display.drawString("A yes  C no", 175, 198);
  } else if (state.noticeBody[0]) {
    M5.Display.drawString(state.noticeFrom[0] ? state.noticeFrom : "Notice", 175, 158);
    M5.Display.drawString(state.noticeBody, 175, 176);
  } else if (state.themeTitle[0]) {
    M5.Display.drawString(state.themeTitle, 175, 158);
    M5.Display.drawString(state.themeSubtitle, 175, 176);
    M5.Display.drawString(state.themeDetail, 175, 194);
  } else if (state.weather[0]) {
    M5.Display.drawString("Weather", 175, 158);
    M5.Display.drawString(state.weather, 175, 178);
  } else {
    const char* face[] = {"(^_^)", "(o_o)", "(-_-)"};
    M5.Display.setTextSize(2);
    M5.Display.drawString(face[animFrame % 3], 192, 168);
    M5.Display.setTextSize(1);
  }
}

void setup() {
  auto cfg = M5.config();
  M5.begin(cfg);
  Serial.begin(115200);
  M5.Display.setRotation(1);
  setBrightness(brightnessLevel);
  M5.Display.fillScreen(0x0000);
  safeCopy(state.msg, sizeof(state.msg), "No Claude connected");
  drawMain();
}

void loop() {
  M5.update();
  pollSerial();

  if (M5.BtnA.wasPressed()) {
    if (state.promptId[0]) sendPermission("approve");
  }
  if (M5.BtnC.wasPressed() || M5.BtnB.wasPressed()) {
    if (state.promptId[0]) sendPermission("deny");
  }

  if (millis() - lastAnimMs > 800) {
    lastAnimMs = millis();
    animFrame++;
  }
  if (millis() - lastDrawMs > 250) {
    lastDrawMs = millis();
    drawMain();
  }
  delay(10);
}
