#include "wifi_ap.h"
#include <WiFi.h>

static const char* AP_SSID     = "DroneDocker-Setup";
static const char* AP_PASSWORD = "drone1234";

// Statická IP konfigurace AP
static const IPAddress AP_IP      (192, 168, 4, 1);
static const IPAddress AP_GATEWAY (192, 168, 4, 1);
static const IPAddress AP_SUBNET  (255, 255, 255, 0);

// Obsluha WiFi událostí – volána automaticky driverem
static void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
    switch (event) {
        case ARDUINO_EVENT_WIFI_AP_STACONNECTED:
            Serial.printf("[WiFi AP] Zařízení připojeno  (MAC: %02X:%02X:%02X:%02X:%02X:%02X)\n",
                info.wifi_ap_staconnected.mac[0], info.wifi_ap_staconnected.mac[1],
                info.wifi_ap_staconnected.mac[2], info.wifi_ap_staconnected.mac[3],
                info.wifi_ap_staconnected.mac[4], info.wifi_ap_staconnected.mac[5]);
            Serial.printf("[WiFi AP] Celkem klientů: %d\n", WiFi.softAPgetStationNum());
            break;

        case ARDUINO_EVENT_WIFI_AP_STADISCONNECTED:
            Serial.printf("[WiFi AP] Zařízení odpojeno  (MAC: %02X:%02X:%02X:%02X:%02X:%02X)\n",
                info.wifi_ap_stadisconnected.mac[0], info.wifi_ap_stadisconnected.mac[1],
                info.wifi_ap_stadisconnected.mac[2], info.wifi_ap_stadisconnected.mac[3],
                info.wifi_ap_stadisconnected.mac[4], info.wifi_ap_stadisconnected.mac[5]);
            Serial.printf("[WiFi AP] Čekám na další připojení...\n");
            break;

        default:
            break;
    }
}

void startAP() {
    // Registrace event handleru před spuštěním AP
    WiFi.onEvent(onWifiEvent);

    WiFi.mode(WIFI_AP);
    WiFi.softAPConfig(AP_IP, AP_GATEWAY, AP_SUBNET);
    WiFi.softAP(AP_SSID, AP_PASSWORD);

    Serial.println("[WiFi AP] ─────────────────────────────────");
    Serial.printf( "[WiFi AP] SSID:  %s\n", AP_SSID);
    Serial.printf( "[WiFi AP] Heslo: %s\n", AP_PASSWORD);
    Serial.printf( "[WiFi AP] IP:    %s\n", WiFi.softAPIP().toString().c_str());
    Serial.println("[WiFi AP] Čekám na připojení zařízení...");
    Serial.println("[WiFi AP] ─────────────────────────────────");
}

int getClientCount() {
    return WiFi.softAPgetStationNum();
}
