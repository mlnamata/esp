#pragma once
#include <Arduino.h>

// Struktura uchovávající konfiguraci zařízení
struct Config {
    int    temp_target;   // Cílová teplota ve °C (0–60)
    String device_name;  // Název stanice (max 32 znaků)
};

// Načte konfiguraci z NVS (Preferences), při absenci použije výchozí hodnoty
void loadConfig(Config &cfg);

// Uloží konfiguraci do NVS (Preferences)
void saveConfig(const Config &cfg);
