#include "config.h"
#include <Preferences.h>

// Jmenný prostor v NVS
static const char* NVS_NS = "config";

void loadConfig(Config &cfg) {
    Preferences prefs;
    prefs.begin(NVS_NS, /*readOnly=*/true);

    cfg.temp_target  = prefs.getInt("temp_target", 30);
    cfg.device_name  = prefs.getString("device_name", "DroneDocker-01");

    prefs.end();

    Serial.println("[Konfigurace] Načtena z NVS:");
    Serial.printf("  Cílová teplota: %d °C\n", cfg.temp_target);
    Serial.printf("  Název stanice:  %s\n", cfg.device_name.c_str());
}

void saveConfig(const Config &cfg) {
    Preferences prefs;
    prefs.begin(NVS_NS, /*readOnly=*/false);

    prefs.putInt("temp_target", cfg.temp_target);
    prefs.putString("device_name", cfg.device_name);

    prefs.end();

    Serial.println("[Konfigurace] Uložena do NVS:");
    Serial.printf("  Cílová teplota: %d °C\n", cfg.temp_target);
    Serial.printf("  Název stanice:  %s\n", cfg.device_name.c_str());
}
