# DroneDocker – přesné přistání s Nicla Vision

Arduino **Nicla Vision** (OpenMV / MicroPython) kouká kamerou dolů na přistávací
značku a navádí dron: říká mu, kam se má posunout, jak se natočit a kdy klesat.
Povely do stran a otáčení jsou v **procentech**, nahoru / dolů jako **rychlost** (mm/s).
Povely vypisuje čitelně do terminálu a zároveň je posílá po UARTu, aby je
v další fázi mohla přímo použít řídicí jednotka dronu.

## Jak to funguje

Na papíře jsou dva prvky:

| Prvek | K čemu slouží |
|---|---|
| **Černý kříž X** | střed = místo přistání, 4 ramena = 4 rohy (odpovídají ramenům dronu) |
| **Červený pruh** vpravo od středu | určuje natočení – kříž sám je souměrný, pruh říká, který roh je který |

Pro každý snímek program:

1. najde kříž (tmavý souměrný útvar s černým středem) a červený pruh ve správné vzdálenosti,
2. spočítá, kde je střed kříže vůči středu dronu – měřítko bere
   z laserového dálkoměru VL53L1X na Nicle, případně z velikosti kříže,
3. spočítá natočení ze směru středu → pruh, zpřesní ho podle osy pruhu a hran kříže (± 1°),
4. přiřadí rohy kříže ramenům dronu (`PP` přední pravé, `PL`, `ZL`, `ZP`),
5. stavový automat rozhodne, co dělat (natočit / dorovnat / klesat / dosednout),
6. z odchylek udělá povely v % (čím dál od středu, tím víc %, max. 50 %),
7. vypíše povel do terminálu a pošle řádek `$NLAND,...` po UARTu.

## Přistávací značka

Předloha (červený pruh je vpravo od středu, vodorovně):

```
  \        /
   \      /
    \    /
     \  /   ▬▬▬▬   ← červený pruh
     /  \
    /    \
   /      \
  /        \
```

- Změř šířku kříže od špičky ke špičce (vodorovně) a zapiš ji do `ZNACKA_ROZPETI_MM`.
- Čím větší značka, tím z větší výšky ji kamera najde (značka 18 cm ≈ do 1,5 m).
- Papír by měl být matný, bez lesku.

Při výchozím nastavení (`CILOVY_UHEL_DEG = 0`) má dron po přistání červený pruh
**po své pravé straně** a rohy kříže připadnou ramenům takto:

| Rameno kříže (při pohledu na předlohu) | Rameno dronu |
|---|---|
| vpravo nahoře (nad pruhem) | `PP` – přední pravé |
| vlevo nahoře | `PL` – přední levé |
| vlevo dole | `ZL` – zadní levé |
| vpravo dole (pod pruhem) | `ZP` – zadní pravé |

Jiné natočení nastavíš v `CILOVY_UHEL_DEG` (90 = pruh před dronem, 180 = vlevo, -90 = za dronem).

## Zapojení

| Nicla Vision | Řídicí jednotka dronu |
|---|---|
| TX (PA9) | RX |
| RX (PA10) | TX (zatím nevyužito) |
| GND | GND |

UART `LP1`, 115200 Bd, 8N1, logika **3,3 V**. Kamera míří dolů, horní okraj
obrazu ideálně k přídi dronu (jinak nastav `KAMERA_OTOCENI_DEG`).

## Nahrání

1. Nainstaluj [OpenMV IDE](https://openmv.io/pages/download) a připoj Niclu přes USB
   (IDE případně nabídne aktualizaci firmwaru).
2. Otevři `main.py` a spusť zelenou šipkou – v terminálu uvidíš povely,
   ve framebufferu obraz s vyznačeným křížem, pruhem a pojmenovanými rohy.
3. Až to funguje: **Tools → Save open script to OpenMV Cam (as main.py)** –
   pak se program spustí sám po každém zapnutí.

Program funguje s novým (modul `csi`) i starším firmwarem (modul `sensor`).

## Nastavení

Vše je na začátku `main.py`:

| Parametr | Výchozí | Popis |
|---|---|---|
| `ZNACKA_ROZPETI_MM` | 180 | šířka kříže špička–špička |
| `CILOVY_UHEL_DEG` | 0 | kde má být červený pruh vůči dronu po přistání |
| `KAMERA_OTOCENI_DEG` | 0 | kam míří horní okraj obrazu vůči přídi (0/90/180/270, po směru hodin) |
| `KAMERA_POSUN_VPRED_MM`, `..._VPRAVO_MM` | 0 | poloha kamery vůči středu dronu |
| `PRAH_CERNA`, `PRAH_CERVENA` | – | barevné prahy LAB (Tools → Machine Vision → Threshold Editor) |
| `TOL_POZICE_MM`, `TOL_UHEL_DEG` | 25 mm, 4° | tolerance pro klesání |
| `KP_BOK`, `MAX_BOK` | 0,25 %/mm, 50 % | povel do stran: 100 mm odchylky → 25 %, nejvýš 50 % |
| `KP_TOC`, `MAX_TOC` | 2 %/°, 50 % | povel otáčení: 10° odchylky → 20 %, nejvýš 50 % |
| `KLESANI_MM_S`, `KLESANI_POMALU_MM_S` | 250, 100 | rychlost klesání (pomalu pod `VYSKA_POMALU_MM`) |
| `VYSKA_DOSEDNUTI_MM` | 150 | pod touto výškou stav `DOSEDNUTI` |
| `VYPIS_POVELU` | True | čitelné povely do terminálu |
| `VYPIS_PROTOKOLU` | False | navíc surové řádky `$NLAND` do terminálu |
| `VYPIS_INTERVAL_MS` | 200 | jak často vypisovat (UART posílá každý snímek) |

## Kalibrace (5 minut, bez letu)

1. Drž dron (s Niclou) nad papírem natočený přesně tak, jak má přistát.
   V terminálu nesmí být žádný povel `TOC` a ve framebufferu musí u ramen kříže
   svítit správné zkratky (`PP` u předního pravého ramene dronu atd.).
2. Posuň papír před příď dronu → terminál musí hlásit `VPRED … %`.
   Posuň ho doprava → `VPRAVO … %`. Pokud ne, uprav `KAMERA_OTOCENI_DEG`,
   případně `KAMERA_ZRCADLIT` (obraz musí vypadat jako pohled shora).
3. Pootoč papír po směru hodin → terminál musí hlásit `TOC VPRAVO … %`
   (dron se má točit za papírem).
4. Když kříž nebo pruh občas zmizí, dolaď prahy v Threshold Editoru.

## Výpis v terminálu

Ukázka ze simulace přistání (dron začíná 20 cm vedle a 70° natočený):

```
NATACENI  | POVEL: VZAD 25 %, VLEVO 42 %, TOC VLEVO 50 %
NAVADENI  | POVEL: VPRED 1 %, VLEVO 2 %, TOC VLEVO 28 %
KLESANI   | POVEL: TOC VLEVO 4 %, DOLU 250 mm/s
KLESANI   | POVEL: DOLU 100 mm/s
DOSEDNUTI | POVEL: DOSEDNI A VYPNI MOTORY, DOLU 100 mm/s
HLEDANI   | POVEL: DRZ POZICI (znacka nenalezena)
```

- `VPRED` / `VZAD`, `VLEVO` / `VPRAVO`, `TOC VLEVO` / `TOC VPRAVO` – v **%**
  (100 % = plná výchylka; jak ji dron přepočte na náklon/rychlost, je na něm),
- `NAHORU` / `DOLU` – **rychlost** v mm/s,
- co je 0, se nevypisuje; když je všechno 0 → `DRZ POZICI`.

## Protokol UART (pro samostatné řízení dronu)

Každý snímek (~20–30× za sekundu) jeden řádek ASCII:

```
$NLAND,seq,stav,vpred,vpravo,toc,vz*CS\r\n
```

| Pole | Jednotka | Význam |
|---|---|---|
| `seq` | – | pořadové číslo 0–65535 (dokola) |
| `stav` | – | viz tabulka stavů |
| `vpred` | % | dopředu (záporné = dozadu), -100 až 100 |
| `vpravo` | % | doprava (záporné = doleva), -100 až 100 |
| `toc` | % | otáčení doprava / po směru hodin shora (záporné = doleva), -100 až 100 |
| `vz` | mm/s | rychlost nahoru (záporné = dolů), 0 = držet výšku |
| `CS` | hex | XOR všech znaků mezi `$` a `*` (jako NMEA) |

Všechny hodnoty jsou celá čísla. Příklad: `$NLAND,7,4,10,-3,-4,-250*56`
= klesá, 10 % dopředu, 3 % doleva, točit 4 % doleva, dolů 250 mm/s.

### Stavy

| Číslo | Stav | Co má dron dělat |
|---|---|---|
| 0 | `HLEDANI` | značka nenalezena → držet pozici (všechny rychlosti 0) |
| 1 | `JEN_KRIZ` | vidí kříž, ne pruh → jen centrovat, neklesat |
| 2 | `NATACENI` | natočení mimo o víc než 15° → točit a centrovat, neklesat |
| 3 | `NAVADENI` | dorovnání polohy a natočení, neklesat |
| 4 | `KLESANI` | vše v toleranci → klesat a průběžně korigovat |
| 5 | `DOSEDNUTI` | těsně nad zemí → dosednout a vypnout motory |

### Příjem v C/C++ (STM32, ESP32, Arduino)

```c
#include <stdio.h>
#include <string.h>

typedef struct {
    int seq, stav;
    int vpred, vpravo, toc;   // %
    int vz;                   // mm/s, + nahoru, - dolů
} NlandZprava;

// Vrátí 1, pokud je řádek platný (včetně kontrolního součtu)
int nland_parse(const char *radek, NlandZprava *z) {
    if (radek[0] != '$') return 0;
    const char *hvezda = strchr(radek, '*');
    if (!hvezda) return 0;
    unsigned char cs = 0;
    for (const char *p = radek + 1; p < hvezda; p++) cs ^= (unsigned char)*p;
    unsigned int cs_prijaty;
    if (sscanf(hvezda + 1, "%2x", &cs_prijaty) != 1 || cs_prijaty != cs) return 0;
    return sscanf(radek, "$NLAND,%d,%d,%d,%d,%d,%d",
                  &z->seq, &z->stav, &z->vpred, &z->vpravo, &z->toc, &z->vz) == 6;
}
```

## Bezpečnost a omezení

- Povely jsou **doporučení** – řídicí jednotka musí mít vlastní ochrany:
  když 0,3 s nepřijde platný řádek nebo je stav `HLEDANI`, držet pozici;
  pilot musí mít vždy možnost převzít řízení.
- Náklon dronu se zatím nekompenzuje (při prudkém manévru se odchylka krátce zkreslí).
- Na přímém slunci může laserový dálkoměr selhávat – výška se pak bere z velikosti kříže.
- Nejdřív testuj bez vrtulí (držením dronu v ruce nad papírem).
