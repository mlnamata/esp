#pragma once
#include "config.h"

// Inicializuje a spustí HTTP server na portu 80
// cfg      – reference na globální konfiguraci (čtení/zápis)
// savedFlag – ukazatel na příznak "právě uloženo" pro blikání LED
void startWebServer(Config &cfg, bool &savedFlag);
