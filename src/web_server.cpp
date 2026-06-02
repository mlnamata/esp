#include "web_server.h"
#include "wifi_ap.h"
#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>

static AsyncWebServer server(80);

// ── HTML šablona hlavní stránky ────────────────────────────────────────────
static const char HTML_PAGE[] PROGMEM = R"rawhtml(
<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DroneDocker – Konfigurace</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', sans-serif;
      background: #1e3a5f;
      color: #f0f4f8;
      min-height: 100vh;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 2rem 1rem;
    }
    .card {
      background: #162d4a;
      border-radius: 12px;
      padding: 2rem;
      width: 100%;
      max-width: 480px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }
    h1 { color: #f59e0b; font-size: 1.5rem; margin-bottom: 1.5rem; }
    .banner {
      background: #166534;
      color: #bbf7d0;
      border-radius: 8px;
      padding: 0.75rem 1rem;
      margin-bottom: 1.25rem;
      font-weight: 600;
    }
    .form-row {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    label { flex: 0 0 160px; font-size: 0.95rem; color: #cbd5e1; }
    input[type=number], input[type=text] {
      flex: 1;
      padding: 0.45rem 0.75rem;
      background: #1e3a5f;
      border: 1px solid #334d6e;
      border-radius: 6px;
      color: #f0f4f8;
      font-size: 0.95rem;
      min-width: 0;
    }
    input:focus { outline: 2px solid #f59e0b; border-color: transparent; }
    .unit { color: #94a3b8; font-size: 0.9rem; flex: 0 0 auto; }
    button[type=submit] {
      padding: 0.45rem 1.1rem;
      background: #f59e0b;
      color: #1e3a5f;
      border: none;
      border-radius: 6px;
      font-weight: 700;
      cursor: pointer;
      flex: 0 0 auto;
      transition: background 0.15s;
    }
    button[type=submit]:hover { background: #fbbf24; }
    .divider {
      border: none;
      border-top: 1px solid #334d6e;
      margin: 1.5rem 0 1rem;
    }
    .info-section h2 {
      color: #94a3b8;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.75rem;
    }
    .info-grid { display: grid; grid-template-columns: auto 1fr; gap: 0.3rem 1rem; }
    .info-key  { color: #94a3b8; font-size: 0.9rem; }
    .info-val  { color: #f0f4f8; font-size: 0.9rem; font-weight: 600; }
  </style>
</head>
<body>
<div class="card">
  <h1>DroneDocker – Konfigurace</h1>

  %BANNER%

  <!-- Formulář: cílová teplota -->
  <form method="POST" action="/save">
    <input type="hidden" name="field" value="temp">
    <div class="form-row">
      <label for="temp_target">Cílová teplota:</label>
      <input type="number" id="temp_target" name="temp_target"
             value="%TEMP%" min="0" max="60" required>
      <span class="unit">°C</span>
      <button type="submit">Uložit</button>
    </div>
  </form>

  <!-- Formulář: název stanice -->
  <form method="POST" action="/save">
    <input type="hidden" name="field" value="name">
    <div class="form-row">
      <label for="device_name">Název stanice:</label>
      <input type="text" id="device_name" name="device_name"
             value="%NAME%" maxlength="32" required>
      <button type="submit">Uložit</button>
    </div>
  </form>

  <hr class="divider">

  <!-- Aktuální hodnoty -->
  <div class="info-section">
    <h2>Aktuální hodnoty</h2>
    <div class="info-grid">
      <span class="info-key">Cílová teplota:</span>
      <span class="info-val">%TEMP% °C</span>
      <span class="info-key">Název stanice:</span>
      <span class="info-val">%NAME%</span>
      <span class="info-key">Uptime:</span>
      <span class="info-val">%UPTIME% s</span>
    </div>
  </div>
</div>
</body>
</html>
)rawhtml";

// ── Pomocná funkce: nahradí placeholdery skutečnými hodnotami ──────────────
static String buildPage(const Config &cfg, bool showBanner) {
    String html = FPSTR(HTML_PAGE);

    // Zelený banner po úspěšném uložení
    if (showBanner) {
        html.replace("%BANNER%",
            "<div class=\"banner\">&#10003; Nastavení uloženo!</div>");
    } else {
        html.replace("%BANNER%", "");
    }

    html.replace("%TEMP%",   String(cfg.temp_target));
    html.replace("%NAME%",   cfg.device_name);
    html.replace("%UPTIME%", String(millis() / 1000));

    return html;
}

// ── Obsluha GET / ──────────────────────────────────────────────────────────
static void handleRoot(AsyncWebServerRequest *req, const Config &cfg) {
    bool showBanner = req->hasParam("saved") &&
                      req->getParam("saved")->value() == "1";
    req->send(200, "text/html", buildPage(cfg, showBanner));
}

// ── Obsluha POST /save ─────────────────────────────────────────────────────
static void handleSave(AsyncWebServerRequest *req, Config &cfg, bool &savedFlag) {
    // Validace a uložení cílové teploty
    if (req->hasParam("temp_target", /*isPost=*/true)) {
        String val = req->getParam("temp_target", true)->value();
        int t = val.toInt();
        if (t < 0 || t > 60) {
            req->send(400, "text/plain", "Chyba: teplota musí být 0–60 °C");
            Serial.printf("[Web] Neplatná teplota: %s\n", val.c_str());
            return;
        }
        cfg.temp_target = t;
        Serial.printf("[Web] Uložena teplota: %d °C\n", t);
    }

    // Validace a uložení názvu stanice
    if (req->hasParam("device_name", /*isPost=*/true)) {
        String name = req->getParam("device_name", true)->value();
        name.trim();
        if (name.isEmpty()) {
            req->send(400, "text/plain", "Chyba: název stanice nesmí být prázdný");
            Serial.println("[Web] Prázdný název stanice – zamítnuto");
            return;
        }
        if (name.length() > 32) name = name.substring(0, 32);
        cfg.device_name = name;
        Serial.printf("[Web] Uložen název: %s\n", name.c_str());
    }

    // Zápis do NVS
    extern void saveConfig(const Config &);
    saveConfig(cfg);

    // Nastav příznak pro 3× rychlé blikání LED
    savedFlag = true;

    // Přesměrování zpět na hlavní stránku s příznakem úspěchu
    req->redirect("/?saved=1");
}

// ── Obsluha GET /data (JSON API) ──────────────────────────────────────────
static void handleData(AsyncWebServerRequest *req, const Config &cfg, bool ledState) {
    StaticJsonDocument<256> doc;
    doc["temp_target"]  = cfg.temp_target;
    doc["device_name"]  = cfg.device_name;
    doc["uptime_s"]     = millis() / 1000;
    doc["ap_clients"]   = getClientCount();
    doc["led_state"]    = ledState;

    String json;
    serializeJson(doc, json);
    req->send(200, "application/json", json);
}

// ── Veřejná inicializační funkce ──────────────────────────────────────────
void startWebServer(Config &cfg, bool &savedFlag) {
    // Globální proměnná pro stav LED (čtena z main.cpp přes extern)
    extern bool g_ledState;

    // GET /
    server.on("/", HTTP_GET, [&cfg](AsyncWebServerRequest *req) {
        handleRoot(req, cfg);
    });

    // POST /save
    server.on("/save", HTTP_POST, [&cfg, &savedFlag](AsyncWebServerRequest *req) {
        handleSave(req, cfg, savedFlag);
    });

    // GET /data
    server.on("/data", HTTP_GET, [&cfg](AsyncWebServerRequest *req) {
        extern bool g_ledState;
        handleData(req, cfg, g_ledState);
    });

    // 404 pro ostatní cesty
    server.onNotFound([](AsyncWebServerRequest *req) {
        req->send(404, "text/plain", "Stránka nenalezena");
    });

    server.begin();
    Serial.println("[Web] HTTP server spuštěn na portu 80");
}
