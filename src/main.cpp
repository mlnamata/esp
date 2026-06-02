#include <Arduino.h>
#include "config.h"
#include "wifi_ap.h"
#include "web_server.h"

// ── Piny ──────────────────────────────────────────────────────────────────
static const int LED_WIFI = 5;   // Modrá LED – WiFi stav (aktivní HIGH)
// GPIO1 (TX) a GPIO3 (RX) jsou rezervovány pro UART ke STM32 – nepoužívat

// ── Globální stav ─────────────────────────────────────────────────────────
Config cfg;           // Aktuální konfigurace (teplota, název)
bool   g_ledState  = false;   // Aktuální logický stav LED (exportován do web_server.cpp)
bool   g_savedFlag = false;   // Příznak: právě proběhlo uložení → 3× rychlé blikání

// ── Stavy LED automatu ────────────────────────────────────────────────────
enum LedMode {
    LED_FAST,        // 100 ms / 100 ms  – AP bez klientů
    LED_SLOW,        // 500 ms / 500 ms  – AP s klientem
    LED_SAVE_BLINK   // 3× 80 ms / 80 ms – potvrzení uložení
};

static LedMode   ledMode          = LED_FAST;
static uint32_t  ledLastToggle    = 0;
static int       saveBlinkCount   = 0;   // Čítač bliknutí při LED_SAVE_BLINK
static LedMode   ledModeAfterSave = LED_SLOW; // Stav LED po dokončení blikání

// ── Aktualizace LED (voláno každou iteraci loop) ──────────────────────────
static void updateLed() {
    uint32_t now = millis();

    // Přepnutí do animace uložení při nastavení příznaku
    if (g_savedFlag) {
        g_savedFlag    = false;
        ledMode        = LED_SAVE_BLINK;
        saveBlinkCount = 0;
        ledLastToggle  = now;
        Serial.println("[LED] Spuštěno 3× rychlé bliknutí (uložení)");
    }

    // Výběr intervalu podle aktuálního módu
    uint32_t interval;
    switch (ledMode) {
        case LED_FAST:       interval = 100; break;
        case LED_SLOW:       interval = 500; break;
        case LED_SAVE_BLINK: interval = 80;  break;
        default:             interval = 500; break;
    }

    if ((now - ledLastToggle) >= interval) {
        ledLastToggle = now;
        g_ledState    = !g_ledState;
        digitalWrite(LED_WIFI, g_ledState ? HIGH : LOW);

        // Po 6 přepnutích (= 3 bliknutí) se vrátíme do pomalého módu
        if (ledMode == LED_SAVE_BLINK) {
            saveBlinkCount++;
            if (saveBlinkCount >= 6) {
                ledMode = ledModeAfterSave;
                Serial.println("[LED] Animace uložení dokončena, přechod na pomalé blikání");
            }
        }
    }

    // Průběžná aktualizace módu podle počtu připojených klientů
    // (mimo animaci uložení)
    if (ledMode != LED_SAVE_BLINK) {
        int clients = getClientCount();
        LedMode desired = (clients > 0) ? LED_SLOW : LED_FAST;
        if (desired != ledMode) {
            ledMode = desired;
            Serial.printf("[LED] Klientů: %d → přepnutí na %s blikání\n",
                          clients, (ledMode == LED_SLOW) ? "pomalé" : "rychlé");
        }
        // Aktualizuj záložní mód pro návrat po animaci
        ledModeAfterSave = desired;
    }
}

// ── setup ─────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Serial.println("\n[Boot] DroneDocker – start firmwaru");

    // Inicializace LED pinu
    pinMode(LED_WIFI, OUTPUT);
    digitalWrite(LED_WIFI, LOW);

    // Načtení konfigurace z NVS
    loadConfig(cfg);

    // Spuštění WiFi AP
    startAP();

    // Spuštění HTTP serveru
    startWebServer(cfg, g_savedFlag);

    Serial.println("[Boot] Inicializace dokončena, vstupuji do smyčky");
}

// ── loop ──────────────────────────────────────────────────────────────────
void loop() {
    // Aktualizace LED (neblokující, pouze millis())
    updateLed();

    // Prostor pro budoucí rozšíření (čtení UART ze STM32, atd.)
}
