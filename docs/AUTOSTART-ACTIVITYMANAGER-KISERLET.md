# webOS Activity Manager indítási kísérlet

## Mi ez

A webOS saját `com.webos.service.activitymanager` szolgáltatása tartós vagy feltételes munkákat tud nyilvántartani, és egy LS2 callbackkel dinamikus service-t tud felébreszteni. Ez áll a legközelebb a Windows „Start at boot” mechanizmusához, de webOS-on nem egy appinfo kapcsoló: egy activity, egy callback service és megfelelő Luna-jogosultság kell hozzá.

Ez a cél TV-n nem elméleti API:

- `getManagerInfo` szerint a firmware követelményei: `bootup`, `internet`, `wifi`.
- A gyári `demo.smartdemokit.launch` activity létezik; az activity ID rebootonként változhat, ezért név alapján kell azonosítani.
- Típusa `continuous:true, foreground:true`, triggerében a bootManager `firstAppLaunched:true` állapota látszik, a `getDetails` szerint viszont `callback:null`, tehát önmagában nem bizonyít közvetlen app-launch callbacket.
- A gyári Activity Manager role outbound `*`, tehát a manager elvben képes más LS2 callbacket meghívni.

A mai read-only bizonyíték a `private-live/diagnostics/activity-manager.txt` fájlban lesz. A publikus webOS OSE API leírás is támogat callbacket, `persist` típust és `bootup:true` requirementet. A kereskedelmi LG firmware ACG-jogai eltérhetnek, ezért ezt előbb mérő-próbával kell igazolni.

## 2026-09-25 mért eredmények

A teljes kísérletsorozat a cél TV-n lefutott; a production launcher nem módosult, a rollback baseline végig megmaradt.

- Az azonnali Activity Manager -> saját JS service callback működik a `com.palm.activitymanager` aliason.
- Persistent `requirements: {bootup:true}` service callback: **67.85 s** boot uptime.
- Persistent bootManager `firstAppLaunched:true` service callback: **66.25 s** boot uptime.
- Activity Manager -> közvetlen `com.webos.service.applicationmanager/launch` callback reboot nélkül működik.
- Ugyanez persistent `firstAppLaunched:true` triggerrel reboot után:
  - renderer navigation: kb. **65.14 s** boot uptime;
  - app JavaScript start: kb. **65.46 s**;
  - első paint marker: kb. **65.69 s**.
  Az utólagos visszaszámítás a TV másodperc-felbontású `date +%s` értéke miatt kb. ±1 s pontosságú.
- Korábbi production cold-boot mérésben a launcher natív felülete kb. **53.594 s** boot uptime-nál már megjelent.

Következtetés: ezen a firmware-en sem a service callback, sem a JS service-t megkerülő közvetlen Activity Manager app-launch út nem ad korábbi indulási pontot a jelenlegi production megoldásnál. Emiatt az Activity Manager irányt nem kell productionbe integrálni startup-gyorsításként.

A teszt végén a persistent direkt activity már nem található, a `hu.szabi.launcher.startupprobe` app/service nincs telepítve. A production launcher változatlan maradt.

## Miért lehet gyorsabb

A jelenlegi guard a Homebrew `/var/lib/webosbrew/init.d` láncból indul. Teljes OS bootnál ez csak a root setup, bind mountok, sync és egyéb Homebrew lépések után fut. A beépített Activity Manager és bootManager már a webOS saját bootfolyamatának része, ezért a callback service a root SSH/`startup.sh` előtt elindulhat.

Az Activity Manager nem gyorsítja fel a WAM renderert. A nyereség az lehet, hogy a launcher launch kérése sok másodperccel korábban érkezik SAM/WAM-hoz, így az LG Home kevesebb ideig látszik.

## Biztonsági elv

Az első változat **nem indíthat launchert**. Csak egy időbélyeget írjon a service saját írható könyvtárába. A következő lépcső egy külön, minimális `hu.szabi.launcher.startupprobe` app. A valódi launcher csak akkor következhet, ha a mérés bizonyítja az előnyt és nincs launch-loop.

Soha ne:

- módosítsd a bootloadert, `startup.sh` vagy `jumpstart.sh` fájlokat;
- írj gyári `/usr` fájlba;
- adj `continuous:true` activityt olyan feltétellel, amely az újraindítás után is folyamatosan igaz, mert callback-loopot okozhat;
- hagyd egyszerre a guardot, a NAS SSAP gyorsítót és a próbát ugyanarra a bootra korlátozás nélkül indítani.

## Javasolt kísérleti felépítés

### 1. Külön service-csomag

Hozz létre külön, eltávolítható developer service-t:

```text
hu.szabi.launcher.autostart.service/
  package.json
  services.json
  service.js
```

Javasolt service ID: `hu.szabi.launcher.autostart.service`. Javasolt metódusok:

- `/probe`: callback adatait validálja és atomikusan időbélyeget ír;
- `/arm`: létrehozza vagy cseréli a név szerinti teszt activityt;
- `/cancel`: név vagy tárolt activity ID alapján töröl;
- `/status`: csak a saját állapotot adja vissza.

A service minden metódusa legyen idempotens. A `/probe` eleinte sem shellt, sem `applicationManager/launch` hívást ne végezzen.

### 2. Jogosultság-próba reboot nélkül

Root shellből vagy az új service-ből hívd a `create` API-t egy azonnali, nem persistent mérő activityvel. A callback csak `/probe` legyen. Ha `ACG`/permission hiba jön, ne lazíts globális role fájlt; előbb készíts package-szintű LS2 role/permission manifestet, csak a következő outbound célokra:

```text
com.webos.service.activitymanager
com.webos.bootManager
com.webos.service.applicationmanager
```

Az API figyelmeztetése szerint a callback akkor működik, ha az Activity Manager és az activity létrehozója is jogosult a callbackre/triggerre.

### 3. A bootfeltétel viselkedésének mérése

Két külön, launch nélküli próbát készíts; mindkettőt azonnal töröld, ha ismételten callbackel:

**A. `bootup` requirement próba**

```json
{
  "activity": {
    "name": "hu.szabi.launcher.autostart.probe",
    "description": "One-shot cold boot timing probe",
    "type": {"foreground": true, "persist": true, "explicit": true},
    "requirements": {"bootup": true},
    "callback": {
      "method": "luna://hu.szabi.launcher.autostart.service/probe",
      "params": {"kind": "bootup"}
    }
  },
  "replace": true,
  "start": true
}
```

**B. bootManager trigger próba**

```json
{
  "activity": {
    "name": "hu.szabi.launcher.autostart.probe",
    "description": "One-shot firstAppLaunched timing probe",
    "type": {"foreground": true, "persist": true, "explicit": true},
    "trigger": {
      "method": "luna://com.webos.bootManager/getBootStatus",
      "params": {"subscribe": true},
      "where": {"prop": "firstAppLaunched", "op": "=", "val": true}
    },
    "callback": {
      "method": "luna://hu.szabi.launcher.autostart.service/probe",
      "params": {"kind": "firstAppLaunched"}
    }
  },
  "replace": true,
  "start": true
}
```

Ezeket először futó rendszerben teszteld. Ha az activity azonnal elsül, akkor önmagában nem következő-boot trigger. Töröld, és ne rebootolj vele. Ha várakozó állapotban marad, `getDetails` kimenettel rögzítsd a specifikációt.

### 4. Kontrollált reboot mérőpróba

Csak felhasználói engedéllyel:

1. Mentsd az activity/service állapotot.
2. A TV-local guard `enabled` markerét nevezd át, ne töröld.
3. Telepíts időkorlátos recovery init hookot, amely legfeljebb 150 másodperc után visszateszi a markert és elindítja a guardot. Referencia: `source/current-development/native-probe-tv-recover.sh` és `native-probe-tv-recovery-init.sh`.
4. Állítsd le ideiglenesen a CT125 `lgtv-launcher-early.service`-t, és ütemezz NAS-oldali automatikus visszaindítást.
5. A callback csak fájlba írjon: TV epoch, `/proc/uptime`, boot status, power state. Ne indítson appot.
6. Reboot után hasonlítsd össze:
   - Activity callback uptime;
   - LG Home első foreground ideje `/var/log/bootd.log` alapján;
   - Homebrew guard process indulása;
   - root SSH első elérhetősége.
7. Mindig állítsd vissza a guardot és a NAS service-t, majd töröld a próba activityt/service-t.

### 5. Minimal startup app próba

Ha a callback legalább több másodperccel megelőzi a Homebrew guardot, következő rebootnál csak a `hu.szabi.launcher.startupprobe` appot indítsd. Forrás és IPK a checkpointban van. A callback előtt kétszer ellenőrizd:

- power `Active`;
- foreground csak LG Home, HDMI, Live TV vagy boot/splash;
- nincs saját launcher/popup surface;
- ugyanabban a bootban még nem történt dispatch.

Egy bootban egyetlen launch kísérlet legyen; bizonytalan timeout után nincs retry.

### 6. Éles változat csak sikeres mérés után

Ha a minimal app stabilan és korábban megjelenik:

- callback célja lehet közvetlenül `com.webos.service.applicationmanager/launch`, vagy a service `/launch` metódusa;
- paraméter: `id=hu.szabi.launcher`, `noSplash=true`, `source=activity-manager-boot`;
- a service írjon bootonkénti dispatch markert;
- valódi app foregroundja megszakítja a kísérletet;
- a TV-local guard marad fallback, de a friss Activity launch markerét 15 másodpercig tiszteletben tartja;
- a CT125 SSAP gyorsító Quick Start ébresztésre maradhat, cold rebootnál nem találhat ki OFF állapotot puszta disconnectből.

## Lekérdezés és rollback

Állapot:

```sh
luna-send -t 1 -f -w 1500 \
  luna://com.webos.service.activitymanager/getManagerInfo '{}'

luna-send -t 1 -f -w 1500 \
  luna://com.webos.service.activitymanager/getDetails \
  '{"activityName":"hu.szabi.launcher.autostart.probe","current":true,"internal":true}'
```

Törlés a creator service-ből vagy a rögzített ID-val:

```sh
luna-send -t 1 -f -w 1500 \
  luna://com.webos.service.activitymanager/cancel \
  '{"activityId":ACTIVITY_ID}'
```

Ezután távolítsd el a developer service package-et a normál `dev/remove` API-val, töröld csak a saját `/var/lib/webosbrew/launcher-autostart-probe` állapotát, és ellenőrizd, hogy a guard/NAS accelerator újra fut. Ne törölj más Activity Manager adatbázis-bejegyzést és ne szerkessz db8 fájlokat közvetlenül.

## Sikerfeltétel

Csak akkor érdemes megtartani, ha legalább három cold bootban:

- nincs reboot-loop, service-loop vagy launcher-duplaindítás;
- a callback minden bootban korábban fut, mint a Homebrew guard;
- a startup probe/launcher natív surface mérhetően korábban látszik;
- HDMI/Live TV és valódi user app megőrzése működik;
- a guard recovery minden megszakított teszt után automatikusan helyreáll.

