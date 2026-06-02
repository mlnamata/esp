#pragma once
#include <Arduino.h>

// Spustí WiFi Access Point se zadaným SSID, heslem a statickou IP
void startAP();

// Vrátí počet aktuálně připojených klientů k AP
int getClientCount();
