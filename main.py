# DroneDocker – Nicla Vision: navádění dronu na přistávací značku
#
# Kamera se dívá dolů na papír se značkou:
#   • černý kříž X   → střed = místo přistání, 4 ramena = 4 rohy (ramena dronu)
#   • červený pruh   → leží vpravo od středu kříže a určuje natočení,
#                      takže je jasné, který roh je který
#
# Z polohy kříže a pruhu program spočítá, o kolik se má dron posunout
# a natočit. Povely vypisuje čitelně do terminálu OpenMV IDE a každý snímek
# je posílá po UARTu řádkem $NLAND pro řídicí jednotku dronu (viz README.md).
#
# Nahrání: OpenMV IDE → otevřít tento soubor → Tools → Save open script
# to OpenMV Cam (as main.py). Pak běží po každém zapnutí Nicly.

import math
import time

try:
    from pyb import UART, LED
    NA_KAMERE = True
except ImportError:          # spuštění na PC (testy výpočtů)
    NA_KAMERE = False

# ══════════════════════════════════════════════════════════════════════════
# KONFIGURACE
# ══════════════════════════════════════════════════════════════════════════

# ── Komunikace s řídicí jednotkou dronu ───────────────────────────────────
UART_PORT      = "LP1"    # Nicla Vision: TX = PA9, RX = PA10 (3,3 V logika)
UART_RYCHLOST  = 115200

# ── Výpis do terminálu (OpenMV IDE / USB) ─────────────────────────────────
VYPIS_POVELU      = True   # čitelné povely pro dron (VPRED, TOC VLEVO, KLESEJ…)
VYPIS_PROTOKOLU   = False  # navíc surové řádky $NLAND (to, co jde po UARTu)
VYPIS_INTERVAL_MS = 200    # jak často vypisovat; změna stavu se vypíše hned

# ── Kamera ────────────────────────────────────────────────────────────────
KAMERA_HFOV_DEG        = 64.9   # vodorovné zorné pole GC2145 (datasheet)
KAMERA_OTOCENI_DEG     = 0      # kam míří horní okraj obrazu vůči přídi dronu,
                                # ve směru hodinových ručiček: 0 / 90 / 180 / 270
KAMERA_ZRCADLIT        = False  # obraz v IDE musí vypadat jako pohled shora
KAMERA_PREKLOPIT       = False
KAMERA_POSUN_VPRED_MM  = 0      # poloha kamery vůči středu dronu
KAMERA_POSUN_VPRAVO_MM = 0

# ── Přistávací značka ─────────────────────────────────────────────────────
ZNACKA_ROZPETI_MM = 180   # šířka kříže od špičky ke špičce (změř na papíře!)

# LAB prahy (L 0..100, A/B -128..127) – doladit v OpenMV IDE → Threshold Editor
PRAH_CERNA   = (0, 40, -25, 25, -25, 25)
PRAH_CERVENA = (15, 85, 25, 127, -10, 100)
ADAPTIVNI_PRAH = True     # při slabém světle zpřísní práh černé podle snímku

MIN_PIXELU_KRIZ    = 80
MIN_PIXELU_CERVENA = 15

# ── Požadované natočení po přistání ───────────────────────────────────────
# Kde má ležet červený pruh vůči dronu, když je dron správně natočený:
#    0 = vpravo (jako na předloze), 90 = vpředu, 180 = vlevo, -90 = vzadu
# Rohy kříže pak připadnou ramenům dronu (pro 0):
#    horní pravé rameno kříže (u pruhu) → přední pravé rameno dronu atd.
CILOVY_UHEL_DEG = 0

# ── Tolerance a průběh přistání ───────────────────────────────────────────
TOL_POZICE_MM           = 25    # max. odchylka středu pro klesání
TOL_UHEL_DEG            = 4     # max. odchylka natočení pro klesání
UHEL_NEJDRIV_NATOCIT    = 15    # větší chyba → nejdřív natočit, neklesat
STABILNI_SNIMKY         = 5     # kolik snímků po sobě musí být v toleranci
HYSTEREZE               = 2.0   # při klesání se tolerance násobí (neškube to)
VYSKA_POMALU_MM         = 600   # pod touto výškou klesat pomalu
VYSKA_DOSEDNUTI_MM      = 150   # pod touto výškou → DOSEDNUTI

# ── Regulace (P regulátor) ────────────────────────────────────────────────
KP_POZICE          = 0.8   # [1/s]   rychlost = KP × odchylka
MAX_RYCHLOST_MM_S  = 300
KP_UHEL            = 1.2   # [1/s]
MAX_OTACENI_DEG_S  = 45
KLESANI_MM_S       = 250
KLESANI_POMALU_MM_S = 100

# ══════════════════════════════════════════════════════════════════════════

# Stavy navádění (posílají se jako číslo)
HLEDANI   = 0   # značka nenalezena → držet pozici
JEN_KRIZ  = 1   # kříž vidět, červený pruh ne → jen centrovat, neklesat
NATACENI  = 2   # velká chyba natočení → točit (a centrovat), neklesat
NAVADENI  = 3   # dorovnání polohy a natočení, neklesat
KLESANI   = 4   # vše v toleranci → klesat a průběžně korigovat
DOSEDNUTI = 5   # těsně nad zemí → dosednout / vypnout motory
NAZVY_STAVU = ("HLEDANI", "JEN_KRIZ", "NATACENI", "NAVADENI", "KLESANI", "DOSEDNUTI")

# Úhly rohů kříže vůči červenému pruhu (pruh = 0°, proti směru hodin)
ROHY_ZNACKY = (45.0, 135.0, -135.0, -45.0)
NAZVY_SMERU = ("VPRAVO", "PP", "VPRED", "PL", "VLEVO", "ZL", "VZAD", "ZP")


# ── Pomocné funkce ────────────────────────────────────────────────────────
def _v(obj, jmeno, nahradni=None):
    # Nový firmware OpenMV vrací hodnoty blobů jako atributy, starší jako
    # metody – tahle funkce funguje s oběma.
    try:
        a = getattr(obj, jmeno)
    except AttributeError:
        a = getattr(obj, nahradni)
    return a() if callable(a) else a


def normuj_uhel(u):
    # Úhel do rozsahu (-180, 180]
    while u > 180.0:
        u -= 360.0
    while u <= -180.0:
        u += 360.0
    return u


def omez(x, m):
    return max(-m, min(m, x))


def obraz_na_dron(x, y):
    # Vektor v obraze (x vpravo, y nahoru) → souřadnice dronu (vpravo, vpřed)
    t = math.radians(KAMERA_OTOCENI_DEG)
    c = math.cos(t)
    s = math.sin(t)
    return x * c + y * s, -x * s + y * c


def nazev_smeru(uhel):
    # Úhel v souřadnicích dronu (0 = vpravo, 90 = vpřed) → zkratka ramene
    return NAZVY_SMERU[int(((uhel + 22.5) % 360.0) // 45.0)]


# ── Detekce značky v obraze ───────────────────────────────────────────────
def prah_cerne(img):
    if not ADAPTIVNI_PRAH:
        return PRAH_CERNA
    l_otsu = _v(img.get_histogram().get_threshold(), "l_value")
    l_max = max(15, min(PRAH_CERNA[1], l_otsu))
    return (PRAH_CERNA[0], l_max) + tuple(PRAH_CERNA[2:])


def _stred_je_tmavy(img, x, y, l_max):
    # Průsečík ramen musí být černý – odliší kříž od tmavého okolí papíru
    w = img.width()
    h = img.height()
    x0 = max(0, min(w - 3, int(x) - 1))
    y0 = max(0, min(h - 3, int(y) - 1))
    st = img.get_statistics(roi=(x0, y0, 3, 3))
    return _v(st, "l_mean") <= l_max


def najdi_znacku(img):
    # Vrátí slovník s polohou kříže (px) a červeného pruhu, nebo None.
    w = img.width()
    h = img.height()
    prah = prah_cerne(img)

    kandidati = []
    for b in img.find_blobs([prah], pixels_threshold=MIN_PIXELU_KRIZ,
                            area_threshold=MIN_PIXELU_KRIZ, merge=False):
        bw = _v(b, "w")
        bh = _v(b, "h")
        if bw < 12 or bh < 12 or not (0.5 < bw / bh < 2.0):
            continue
        if not (0.06 < _v(b, "density") < 0.6):
            continue
        cx = _v(b, "cxf", "cx")
        cy = _v(b, "cyf", "cy")
        if not _stred_je_tmavy(img, cx, cy, prah[1]):
            continue

        rohy = [tuple(r) for r in _v(b, "min_corners")]
        strany = [math.sqrt((rohy[i][0] - rohy[i - 1][0]) ** 2 +
                            (rohy[i][1] - rohy[i - 1][1]) ** 2) for i in range(4)]
        rozpeti = sum(strany) / 4.0
        bx = _v(b, "x")
        by = _v(b, "y")
        oriznuty = bx <= 1 or by <= 1 or bx + bw >= w - 1 or by + bh >= h - 1

        # Kříž je souměrný: těžiště musí ležet uprostřed opsaného čtverce
        if not oriznuty:
            sx = sum(r[0] for r in rohy) / 4.0
            sy = sum(r[1] for r in rohy) / 4.0
            if math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2) > 0.15 * rozpeti:
                continue
        kandidati.append({"cx": cx, "cy": cy, "rohy": rohy, "rozpeti_px": rozpeti,
                          "oriznuty": oriznuty, "pixely": _v(b, "pixels"),
                          "cervena": None})
    if not kandidati:
        return None

    cervene = img.find_blobs([PRAH_CERVENA], pixels_threshold=MIN_PIXELU_CERVENA,
                             area_threshold=MIN_PIXELU_CERVENA, merge=False)

    # Ke každému kříži hledáme červený pruh ve správné vzdálenosti od středu
    for k in kandidati:
        nejlepsi = 0
        for c in cervene:
            px = _v(c, "pixels")
            if not (0.02 < px / k["pixely"] < 0.8):
                continue
            rx = _v(c, "cxf", "cx")
            ry = _v(c, "cyf", "cy")
            d = math.sqrt((rx - k["cx"]) ** 2 + (ry - k["cy"]) ** 2)
            if not k["oriznuty"] and not (0.12 < d / k["rozpeti_px"] < 0.65):
                continue
            if px > nejlepsi:
                nejlepsi = px
                # Osa pruhu je spolehlivá, jen když je celý v obraze a protáhlý
                x, y, pw, ph = _v(c, "x"), _v(c, "y"), _v(c, "w"), _v(c, "h")
                cely = x > 1 and y > 1 and x + pw < w - 1 and y + ph < h - 1
                osa = _v(c, "rotation") if cely and _v(c, "roundness") < 0.5 else None
                k["cervena"] = {"x": rx, "y": ry, "osa": osa}

    # Přednost má kříž s nalezeným pruhem, pak ten největší
    kandidati.sort(key=lambda k: (k["cervena"] is not None, k["pixely"]), reverse=True)
    return kandidati[0]


# ── Výpočet odchylek (čistá geometrie, testovatelné i na PC) ──────────────
def vyhodnot(znacka, w, h, f_px, vyska_tof, posledni_mm_na_px):
    # Vrátí slovník:
    #   dx, dy  – kde je střed značky vůči středu dronu [mm] (vpřed, vpravo)
    #   yaw     – o kolik stupňů se má dron otočit doprava (None = neznámo)
    #   vyska   – výška nad značkou [mm] (-1 = neznámo)
    #   mm_na_px, rohy (seznam (x, y, název ramene))
    if znacka is None:
        return None

    cx = znacka["cx"]
    cy = znacka["cy"]
    rozpeti = znacka["rozpeti_px"]
    platne_rozpeti = not znacka["oriznuty"] and rozpeti >= 12

    # Měřítko a výška: přednostně ToF, jinak z velikosti kříže
    vyska = -1
    if vyska_tof > 0:
        vyska = vyska_tof
    elif platne_rozpeti:
        vyska = f_px * ZNACKA_ROZPETI_MM / rozpeti
    if platne_rozpeti:
        mm_na_px = ZNACKA_ROZPETI_MM / rozpeti
    elif vyska > 0:
        mm_na_px = vyska / f_px
    else:
        mm_na_px = posledni_mm_na_px

    # Poloha středu kříže vůči středu obrazu → vůči středu dronu
    vpravo, vpred = obraz_na_dron(cx - w / 2.0, h / 2.0 - cy)
    dx = vpred * mm_na_px + KAMERA_POSUN_VPRED_MM
    dy = vpravo * mm_na_px + KAMERA_POSUN_VPRAVO_MM

    # Natočení: směr středu → červený pruh (hrubě, určuje který roh je který)
    yaw = None
    rohy = []
    cervena = znacka["cervena"]
    if cervena is not None:
        x, y = obraz_na_dron(cervena["x"] - cx, cy - cervena["y"])
        uhel = math.degrees(math.atan2(y, x))

        # Zpřesnění – průměr z nezávislých odhadů, které jsou k dispozici
        opravy = []

        # a) osa červeného pruhu (leží ve směru 0°/180° značky)
        if cervena["osa"] is not None:
            x, y = obraz_na_dron(math.cos(cervena["osa"]), -math.sin(cervena["osa"]))
            o = normuj_uhel(math.degrees(math.atan2(y, x)) - uhel)
            if o > 90:
                o -= 180
            elif o < -90:
                o += 180
            if abs(o) < 30:
                opravy.append(o)

        # b) rohy kříže – každý má ležet 45° / 135° od pruhu
        if platne_rozpeti:
            odchylky = []
            prirazeni = []
            for (qx, qy) in znacka["rohy"]:
                x, y = obraz_na_dron(qx - cx, cy - qy)
                rel = normuj_uhel(math.degrees(math.atan2(y, x)) - uhel)
                jmen = min(ROHY_ZNACKY, key=lambda r: abs(normuj_uhel(rel - r)))
                odchylky.append(normuj_uhel(rel - jmen))
                prirazeni.append(jmen)
            if len(set(prirazeni)) == 4 and max(abs(o) for o in odchylky) < 25:
                opravy.append(sum(odchylky) / 4.0)

        if opravy:
            uhel = normuj_uhel(uhel + sum(opravy) / len(opravy))

        yaw = normuj_uhel(CILOVY_UHEL_DEG - uhel)

        # Pojmenování rohů: ke kterému rameni dronu roh patří
        for (qx, qy) in znacka["rohy"]:
            x, y = obraz_na_dron(qx - cx, cy - qy)
            rel = normuj_uhel(math.degrees(math.atan2(y, x)) - uhel)
            jmen = min(ROHY_ZNACKY, key=lambda r: abs(normuj_uhel(rel - r)))
            rohy.append((qx, qy, nazev_smeru(CILOVY_UHEL_DEG + jmen)))

    return {"dx": dx, "dy": dy, "yaw": yaw, "vyska": vyska,
            "mm_na_px": mm_na_px, "rohy": rohy}


# ── Stavový automat navádění ──────────────────────────────────────────────
class Navadeni:
    def __init__(self):
        self.stav = HLEDANI
        self.stabilni = 0
        self.dosednuto = False
        self.posledni_vyska = -1
        self.posledni_ms = 0

    def krok(self, m, vyska_tof, ted_ms):
        # Vrátí (stav, vx, vy, vyaw, vz):
        #   vx vpřed, vy vpravo, vz dolů [mm/s], vyaw doprava [°/s]
        vyska = m["vyska"] if m is not None else vyska_tof

        # Dosednutí je „zamčené“, dokud dron znovu nevzlétne
        if self.dosednuto:
            if vyska > 2 * VYSKA_DOSEDNUTI_MM:
                self.dosednuto = False
            else:
                return self._stav(DOSEDNUTI), 0, 0, 0, KLESANI_POMALU_MM_S

        if m is None:
            # Těsně nad zemí kamera značku ztratí – to je v pořádku
            if (self.stav == KLESANI and 0 < self.posledni_vyska < 2 * VYSKA_DOSEDNUTI_MM
                    and time.ticks_diff(ted_ms, self.posledni_ms) < 1000):
                self.dosednuto = True
                return self._stav(DOSEDNUTI), 0, 0, 0, KLESANI_POMALU_MM_S
            self.stabilni = 0
            return self._stav(HLEDANI), 0, 0, 0, 0

        if vyska > 0:
            self.posledni_vyska = vyska
        self.posledni_ms = ted_ms

        vx = omez(KP_POZICE * m["dx"], MAX_RYCHLOST_MM_S)
        vy = omez(KP_POZICE * m["dy"], MAX_RYCHLOST_MM_S)
        if m["yaw"] is None:
            self.stabilni = 0
            return self._stav(JEN_KRIZ), vx, vy, 0, 0

        yaw = m["yaw"]
        vyaw = omez(KP_UHEL * yaw, MAX_OTACENI_DEG_S)
        chyba = math.sqrt(m["dx"] ** 2 + m["dy"] ** 2)
        k = HYSTEREZE if self.stav == KLESANI else 1.0

        if abs(yaw) > UHEL_NEJDRIV_NATOCIT:
            self.stabilni = 0
            return self._stav(NATACENI), vx, vy, vyaw, 0
        if chyba > TOL_POZICE_MM * k or abs(yaw) > TOL_UHEL_DEG * k:
            self.stabilni = 0
            return self._stav(NAVADENI), vx, vy, vyaw, 0

        self.stabilni += 1
        if self.stav != KLESANI and self.stabilni < STABILNI_SNIMKY:
            return self._stav(NAVADENI), vx, vy, vyaw, 0

        if 0 < vyska < VYSKA_DOSEDNUTI_MM:
            self.dosednuto = True
            return self._stav(DOSEDNUTI), 0, 0, 0, KLESANI_POMALU_MM_S
        vz = KLESANI_POMALU_MM_S if 0 < vyska < VYSKA_POMALU_MM else KLESANI_MM_S
        return self._stav(KLESANI), vx, vy, vyaw, vz

    def _stav(self, s):
        self.stav = s
        return s


# ── Protokol ──────────────────────────────────────────────────────────────
def zprava(seq, stav, m, vx, vy, vyaw, vz):
    # $NLAND,seq,stav,dx,dy,yaw,vyska,vx,vy,vyaw,vz*CS
    if m is None:
        dx = dy = yaw = 0
        vyska = -1
    else:
        dx = m["dx"]
        dy = m["dy"]
        yaw = m["yaw"] if m["yaw"] is not None else 0
        vyska = m["vyska"]
    hodnoty = (seq, stav, dx, dy, yaw, vyska, vx, vy, vyaw, vz)
    telo = "NLAND," + ",".join(str(int(round(v))) for v in hodnoty)
    cs = 0
    for ch in telo:
        cs ^= ord(ch)
    return "$%s*%02X\r\n" % (telo, cs)


def povel_text(stav, m, vx, vy, vyaw, vz):
    # Čitelný řádek do terminálu, např.:
    # NAVADENI  | vpred 45 mm, vlevo 12 mm, otocit vlevo 3°, vyska 520 mm
    #           | POVEL: VPRED 36 mm/s, VLEVO 10 mm/s, TOC VLEVO 4°/s
    if m is None:
        odchylka = "znacka nenalezena"
    else:
        dx = int(round(m["dx"]))
        dy = int(round(m["dy"]))
        odchylka = "%s %d mm, %s %d mm" % ("vpred" if dx >= 0 else "vzad", abs(dx),
                                           "vpravo" if dy >= 0 else "vlevo", abs(dy))
        if m["yaw"] is None:
            odchylka += ", natoceni nezname (nevidim cerveny pruh)"
        else:
            yaw = int(round(m["yaw"]))
            odchylka += ", otocit %s %d°" % ("vpravo" if yaw >= 0 else "vlevo", abs(yaw))
        if m["vyska"] > 0:
            odchylka += ", vyska %d mm" % int(m["vyska"])

    povely = []
    if stav == DOSEDNUTI:
        povely.append("DOSEDNI A VYPNI MOTORY")
    vx = int(round(vx))
    vy = int(round(vy))
    vyaw = int(round(vyaw))
    vz = int(round(vz))
    if vx:
        povely.append("%s %d mm/s" % ("VPRED" if vx > 0 else "VZAD", abs(vx)))
    if vy:
        povely.append("%s %d mm/s" % ("VPRAVO" if vy > 0 else "VLEVO", abs(vy)))
    if vyaw:
        povely.append("TOC %s %d°/s" % ("VPRAVO" if vyaw > 0 else "VLEVO", abs(vyaw)))
    if vz:
        povely.append("KLESEJ %d mm/s" % vz)
    if not povely:
        povely.append("DRZ POZICI")
    return "%-9s | %s | POVEL: %s" % (NAZVY_STAVU[stav], odchylka, ", ".join(povely))


# ── Hardware Nicla Vision ─────────────────────────────────────────────────
def kamera_init():
    try:
        import csi                      # firmware OpenMV 4.7+
        cam = csi.CSI()
        cam.reset()
        cam.pixformat(csi.RGB565)
        cam.framesize(csi.QVGA)
        cam.hmirror(KAMERA_ZRCADLIT)
        cam.vflip(KAMERA_PREKLOPIT)
        cam.snapshot(time=2000)         # ustálení expozice a vyvážení bílé
        cam.auto_whitebal(False)        # stálé barvy pro práh červené
        return cam.snapshot
    except ImportError:
        import sensor                   # starší firmware
        sensor.reset()
        sensor.set_pixformat(sensor.RGB565)
        sensor.set_framesize(sensor.QVGA)
        sensor.set_hmirror(KAMERA_ZRCADLIT)
        sensor.set_vflip(KAMERA_PREKLOPIT)
        sensor.skip_frames(time=2000)
        sensor.set_auto_whitebal(False)
        return sensor.snapshot


def tof_init():
    # Laserový dálkoměr VL53L1X na Nicla Vision (míří stejně jako kamera)
    try:
        from machine import I2C
        from vl53l1x import VL53L1X
        return VL53L1X(I2C(2))
    except Exception as e:
        print("[ToF] nedostupný:", e)
        return None


def tof_cti(tof):
    if tof is None:
        return -1
    try:
        d = tof.read()
    except OSError:
        return -1
    return d if 30 < d < 4000 else -1


def kresli(img, znacka, m, stav):
    # Ladicí obraz pro OpenMV IDE (na výstup nemá vliv)
    w = img.width()
    h = img.height()
    img.draw_cross(w // 2, h // 2, color=(255, 255, 255), size=8)
    if znacka is not None:
        cx = int(znacka["cx"])
        cy = int(znacka["cy"])
        img.draw_edges(znacka["rohy"], color=(255, 255, 0))
        img.draw_cross(cx, cy, color=(0, 255, 0), size=10, thickness=2)
        img.draw_line(w // 2, h // 2, cx, cy, color=(0, 255, 255))
        if znacka["cervena"] is not None:
            rx = int(znacka["cervena"]["x"])
            ry = int(znacka["cervena"]["y"])
            img.draw_arrow(cx, cy, rx, ry, color=(255, 0, 0), thickness=2)
        if m is not None:
            for (qx, qy, nazev) in m["rohy"]:
                img.draw_string(int(qx) - 6, int(qy) - 6, nazev, color=(255, 0, 255), scale=1)
    img.draw_string(2, 2, NAZVY_STAVU[stav], color=(255, 255, 0), scale=2)
    if m is not None:
        text = "dx%d dy%d" % (int(m["dx"]), int(m["dy"]))
        if m["yaw"] is not None:
            text += " yaw%d" % int(m["yaw"])
        img.draw_string(2, h - 12, text, color=(255, 255, 0), scale=1)


def main():
    snimek = kamera_init()
    uart = UART(UART_PORT, UART_RYCHLOST, timeout_char=10)
    tof = tof_init()
    led_r, led_g, led_b = LED(1), LED(2), LED(3)

    img = snimek()
    w = img.width()
    h = img.height()
    f_px = (w / 2.0) / math.tan(math.radians(KAMERA_HFOV_DEG) / 2.0)

    nav = Navadeni()
    mm_na_px = 1.0
    seq = 0
    posledni_stav = -1
    posledni_vypis = time.ticks_ms()
    print("[Nicla] navádění spuštěno, %dx%d, f=%.0f px" % (w, h, f_px))

    while True:
        img = snimek()
        vyska_tof = tof_cti(tof)

        znacka = najdi_znacku(img)
        m = vyhodnot(znacka, w, h, f_px, vyska_tof, mm_na_px)
        if m is not None:
            mm_na_px = m["mm_na_px"]
        ted = time.ticks_ms()
        stav, vx, vy, vyaw, vz = nav.krok(m, vyska_tof, ted)

        # Dron dostává povely po UARTu každý snímek
        radek = zprava(seq, stav, m, vx, vy, vyaw, vz)
        uart.write(radek)
        seq = (seq + 1) & 0xFFFF

        # Terminál: stejné povely čitelně (omezeně, aby se dal číst)
        if stav != posledni_stav or time.ticks_diff(ted, posledni_vypis) >= VYPIS_INTERVAL_MS:
            if VYPIS_POVELU:
                print(povel_text(stav, m, vx, vy, vyaw, vz))
            if VYPIS_PROTOKOLU:
                print(radek, end="")
            posledni_stav = stav
            posledni_vypis = ted

        # LED: červená = hledá, modrá = navádí, zelená = klesá / dosedá
        led_r.on() if stav == HLEDANI else led_r.off()
        led_b.on() if stav in (JEN_KRIZ, NATACENI, NAVADENI) else led_b.off()
        led_g.on() if stav in (KLESANI, DOSEDNUTI) else led_g.off()

        kresli(img, znacka, m, stav)


if NA_KAMERE:
    main()
