# LG Remote Broker – 4-evdev-relay

Állapot 2026-09-20: **4-evdev-relay telepítve és bekapcsolva a NAS kapcsolójával.**
A 4-es változat javítja a standby utáni téves heartbeat-lekapcsolást, publikálja
a gomb 1/2/0 fázisát a rövid/hosszú Home megkülönböztetéséhez, és az appindító
Luna-hívások a firmware-en működő `-t 1` formát használják. A korábbi 0.2.0 ZIP
klónalapú változata nem stabil kiadás.

## Változás

Az előző megoldás uinput klónokat hozott létre, amelyek mellett többször megszűnt
a TV bemenete. Az exact belső LG/Qt hiba oka még nincs bizonyítva. A 3-as változat
elhagyja ezt az útvonalat: az eredeti `LGE M-RCU - Builtin [0]` eseményeit
a már létező, külön `LGE M-RCU - Builtin [2]` evdev eszközre írja.
A két eszköz képességei ezen a TV-n egyeznek. Ezt az átviteli megközelítést használja
a [Magic Mapper](https://github.com/andrewfraley/magic_mapper/blob/main/magic_mapper.py) is.

Nem hoz létre/töröl bemeneti eszközt, nem injektál könyvtárat LG folyamatba,
és a felügyelet nem indít újra LG szolgáltatást.

## Védelmek és korlátok

- Egyetlen forrás és ettől különböző, pontos névvel azonosított kimenet;
  hiányzó/dupla eszköznél vagy eltérő képességnél nincs foglalás.
- Kernel `flock` védi a brokert és a supervisort a párhuzamos indulástól.
- Atomikusan cserélt heartbeat; a supervisor egymást követő változatlan mintákat
  számol, ezért standby után nem hasonlít össze eltérően futó órákat. Első valódi
  hibára továbbra is kikapcsol, nincs folyamatos újrafoglalási ciklus.
- Root-jogú, gombonkénti állapotfájl közli a lenyomás/ismétlés/felengedés fázist;
  a Home rövid nyomása gyorsmenü, hosszú nyomása teljes launcher lehet.
- A supervisor TERM/INT/HUP jelre valóban kilép, és megvárja a saját gyermekét.
- Gombnyomásonként rögzített továbbítás: újratöltéskor nem veszítjük el a
  felengedést; azonos célgombra két forrásgomb számlálással működik.
- Normál leálláskor a továbbított lenyomások felengedése, majd a grab feloldása.
  Rendellenes gyermekkilépésnél külön helyreállítás csak a dedikált [2] kimeneten.
- SYN_DROPPED / írási hiba esetén leállás; nem folytatjuk hibás gombállapottal.
- A kernel grab feloldása nem önmagában bizonyíték a TV kezelhetőségére.
  Fizikai távirányítóval tesztelendő: navigáció, görgő, pointer, rövid/hosszú nyomás,
  felülírás, be/ki kapcsolás, újratöltés, készenlét és újraindítás.
- A [2] eszközt nem használhatja közben egy másik injektor/remapper.

## Ellenőrzések

- 12 natív ARM tesztcsoport sikeres a TV-n, pipe-okon, valódi input megnyitása nélkül.
- 5 Linux shell felügyeleti teszt sikeres a NAS konténer ideiglenes mappájában:
  TERM, dupla indulás, crash, stale heartbeat, kikapcsolási marker.
- 57 backend/kapcsoló teszt sikeres Windows-on (az 5 Linux shell teszt ott kihagyva).
- `--check-devices`: a TV forrása és célja kompatibilis és alapállapotú;
  nem foglal eszközt, nem ír eseményt.
- `--run-seconds 60` legfeljebb egyperces, önmagától leálló kézi próbához.
  Két 60 másodperces próba lefutott: alap-továbbítás és mentett kiosztás.
  Mindkettő leállt, gyári szolgáltatás-újraindítás nélkül. A második próba
  naplójában nem volt akcióindítás. Később a NAS kapcsolóval bekapcsolt éles
  futásban két 1117-es akcióindítás megjelent, a felhasználó pozitív visszajelzésével.

## Fordítás és telepítés

```sh
zig cc -target arm-linux-musleabi -mcpu=arm1176jzf_s -Os -static \
  -std=gnu99 -Wall -Wextra -Werror -o remote-broker remote-broker.c
```

A konfiguráció immár `version=2`, kötelező külön `output=` sorral.
Az installer csak kikapcsolt brokernél telepít. Régi configot megőriz
`before-relay-v3-<timestamp>` mentésben és passzív alapkonfigurációt készít;
a gombkiosztás a NAS strukturált konfigurációjából újragenerálható.
Nem állít be automatikus indulást. Az új backend verzióellenőrzéssel tiltja a régi
bináris bekapcsolását.

## NAS kapcsoló

A http://192.168.0.223:8765/ oldal tetején Távirányító-felülírás kapcsoló,
állapotjelzés és külön Vészleállítás található. Az ON a mentett gombkiosztást tölti
be és TV-autostartot telepít. OFF leállítja a kezelőt, törli az engedélyezési
markert és init scriptet; a gombkiosztás megmarad.

GET/POST /api/remote-mapper/runtime; POST JSON: {"enabled":true/false}.
Csak engedélyezett LAN, böngészőből saját Origin; régi binárissal vagy aktív
PHP hookkal nincs bekapcsolás. OFF nem függ az app-/gombkatalógus működésétől.
NAS állapot: /var/lib/lgtv-control/remote-broker-switch.json.
A NAS újraindítása után a kikapcsolt állapot megmaradását élesben ellenőriztük.
A crash circuit breaker állapotát a NAS indulása nem engedélyezi újra.

Telepítési mentés a CT-ben: /root/lgtv-relay-v3-backup.Azlrmu.
TV bináris SHA-256: 49dea6fef84b4b7b18fa16d53ac7ef3faf16b11f7a2396e3a280d0e966a5d7f5.
A NAS kért állapota és a TV enabled/active állapota true. A kontrollált init-
újraindítás után új supervisor/broker PID indult, az engedélyezési marker megmaradt,
és a heartbeat a hibahatáron túl is változott. A következő külső ellenőrzés egy
valódi standby/ébredés vagy teljes TV-újraindítás utáni fizikai gombpróba.
