# webOS vezérlő Suite

Négy helyi webOS TV funkció (hat külön telepíthető hostcsomag) és a közös LAN-os vezérlőfelület
build- és átadási infrastruktúrája:

- `hu.szabi.mediaoverlay` 0.3.6: dinamikus és preset-alapú, megszakadás után újracsatlakozó kamera-/média-előnézet;
- `hu.szabi.cameraviewer` 0.3.10: lapozható, 16:9-es kameranézet WebRTC-hanggal, állítható előnézeti frissítéssel és fekete indulóképpel;
- `hu.szabi.remotemapper` 0.2.0: vizuális távirányító-szerkesztő a különálló fail-open Remote Brokerhez, Home Assistant webhook művelettel és fekete indulóképpel; a Home gomb
  külön figyelmeztetéssel, de visszaállíthatóan szerkeszthető, a védett gombok űrlapja rejtve marad;
- `hu.szabi.launcher` 0.3.29: normál, nem transzparens `card` host a teljes kezdőfelülethez;
- `hu.szabi.launcher.overlay` 0.3.29: `popup` host ugyanahhoz a teljes kezdőfelülethez;
- `hu.szabi.launcher.quick` 0.3.29: transzparens `popup` host a gyorsmenühöz. A három csomag ugyanazt az `apps/launcher` runtime-ot használja, csak a webOS ablakmanifest és a generált hostazonosító tér el.

Az overlay alaphelyzete a bal felső sarok. A saját beállításaiban választható mind a négy sarok,
a szélesség, magasság, vízszintes/függőleges margó és az automatikus bezárás ideje.

A négy funkció közös runtime-forrása az `apps/media-overlay`, `apps/camera-viewer`,
`apps/remote-mapper` és `apps/launcher` mappában van. Az `apps/launcher-quick` és
`apps/launcher-overlay` kizárólag a külön launcher-host manifestjét tartalmazza;
launcher HTML/CSS/JavaScript nem duplikálható oda. A közös build nem módosítja ezeket, és kihagyja az appok `tests/`,
`build/`, `*.ipk`, valamint app-root
`packageinfo.json` tartalmát. A csomag hiteles `packageinfo.json` fájlját a build hozza létre az
`/usr/palm/packages/<app-id>/` útvonalon.

## Bizalmi és indítási irány

Home Assistant indítja a `hu.szabi.mediaoverlay` appot a mozgásautomatika hatására. Az overlay nem
indít visszafelé Home Assistant automatizálást. A felhasználó overlayen végzett kattintása vagy OK-ja
helyben, fix app-ID-val indítja a `hu.szabi.cameraviewer` appot:

```json
{"id":"hu.szabi.cameraviewer","params":{"v":1,"action":"open","cameraId":"kapu","view":"full","requestId":"0123456789abcdef0123456789abcdef"}}
```

Az app-ID és a szemantikus célmezők fixek; az overlay minden kattintáshoz/OK-hoz új, 32 hexadecimális
karakteres `requestId` értéket készít helyben.

A teljes Home Assistant példa a `home-assistant/examples.yaml` fájlban van. Dinamikus launch:

```json
{
  "id": "hu.szabi.mediaoverlay",
  "params": {
    "v": 1,
    "action": "show",
    "kind": "image",
    "url": "http://192.168.0.150:1984/api/stream.mjpeg?src=camera_kapu_felso_preview",
    "fit": "cover",
    "corner": "bottom-right",
    "width": 720,
    "height": 405,
    "marginX": 24,
    "marginY": 24,
    "ttlMs": 0
  }
}
```

Minden layoutmező opcionális, és a TV-n mentett alapértéket örökli. `ttlMs:0` esetén nincs automatikus
bezárás. `action:dismiss` bezár, `action:configure` elmenti az alaplayoutot. A `preset-save` új presetet
hoz létre vagy azonos ID mellett módosít, a `preset-delete` töröl. A presethez opcionálisan
`clickAction:openCamera` és validált `cameraId` menthető; ettől még csak a fix Camera Viewer app indulhat.
Az opcionális `requestId` 32 kisbetűs hexadecimális karakter, kizárólag duplikációszűrésre szolgál.
Minden launch mező pontos allowlist alapján kerül ellenőrzésre.

Az appokban nincs beégetett TV-, NAS- vagy gateway-cím és nincs gyárilag rögzített kamera/preset.
A telepítési adatokat a tokenmentes, kizárólag helyi hálózatra szánt `Kapcsolatok` felület tárolja,
a kamerák és presetek pedig az ottani szerkesztőkből hozhatók létre és szinkronizálhatók.

A Media Overlay a `show` művelet előtt lekéri az `lgtv-control` CT rövid életű Camera Viewer-jelenléti
állapotát. Aktív Camera Viewer esetén a PiP tartalom megjelenítése nélkül bezár; ha a CT nem érhető
el, tartalékként megpróbálja a TV előtér-app lekérdezését. Ha már fut vagy betölt egy PiP, az újabb
`show` relaunch kérést figyelmen kívül hagyja, ezért a meglevő tartalom nem írható felül. A 0.3.5 a
közvetlen launch paraméter mellett a webOS által esetenként átadott teljes launcher/payload/params
borítékot és a `webOSLaunch` eseményt is kezeli.

A 0.3.5 minden sikeresen elfogadott `show` kérés feloldott, validált tartalmát és végleges layoutját
megjegyzi. A TV menüjéből történő üres vagy egzakt `storeCaller:home` indítás ezt az utolsó PiP-et
játssza vissza; korábbi bejegyzés nélkül a beállítások nyílnak meg. Az explicit `action:settings`
változatlanul közvetlenül a beállítófelületet nyitja, a `requestId` nem kerül a mentett kérésbe.

A külön `lgtv-control` CT token nélkül, csak a megbízható helyi hálózatról ad böngészős felületet.
A presetek és kamerák listából választhatók, betöltődnek szerkesztéshez és törléshez, és a felület a
TV-n ténylegesen tárolt konfigurációt szinkronizálja. Ugyanitt állítható a 2×2/3×3/4×4 layout,
a kiemelt kamera és a képernyőkímélő-védelem. A kamerák tárolási és megjelenítési sorrendje külön
listában drag-and-droppal vagy a fel/le gombokkal módosítható, majd egy lépésben a TV-re menthető.

A Távirányító gombok modul bal oldalán egy kattintható LG távirányító, jobb oldalán a kiválasztott
gomb kötése látható. Ugyanez a felület a TV-n a `hu.szabi.remotemapper` appban is elérhető. A CT a
visszafelé kompatibilis kötéstárat biztonsági mentésekkel, atomikusan módosítja, majd a strukturált
kötéseket a különálló `remote-broker` szigorú konfigurációjára fordítja. A broker nem tölt kódot LG
rendszerfolyamatba, és nincs tetszőleges shell-parancs a kliens felől. A fejléc a broker állapotát,
illetve a régi natív hook esetleges jelenlétét is mutatja.

## Launcher indítás, Home-kezelés és webhook csempék

A jelenlegi launcher kiadás **0.3.29**. A Web sor csempéi Weboldal vagy Webhook módban használhatók; a webhookot közvetlenül a TV küldi GET vagy POST kéréssel, opcionális POST body-val. Részletes használat: [docs/launcher-webhook-hu.md](docs/launcher-webhook-hu.md).

A korábbi 0.3.8 kiadás indítási és Home-kezelési alapjai továbbra is érvényesek.


A három launcher IPK jelenlegi verziója 0.3.29, felbontásuk 1920×1080.
A teljes/gyors menü és a rövid/hosszú Home hozzárendelése külön beállítás a teljes launcher
`card` vagy `popup` megjelenítésétől.

Az új watchdog kizárólag az `lginput2` folyamatra korlátozott `repair-home-hook.sh` segédet hívja.
Az eredeti Input Hook szolgáltatás indítása és a `/var/lib/webosbrew/init.d/inputhook`
automatikus indítója maradjon letiltva: az eredeti indítás más LG rendszerfolyamatokba,
köztük a `micomservice` folyamatba is betölt natív kódot. A 2026-09-14-i hibajelentés
ebben a betöltött könyvtárban rögzített `micomservice` összeomlást.

A CT `input_hook_watchdog_enabled` beállítása alapból `false`; csak explicit JSON `true`
engedélyezi az új figyelő automatikus telepítését/indítását. Ez nem kapcsolja ki egy régi
telepítés már engedélyezett TV-s indítóit. A szűkített segéd is natív kódot tölt be:
csak lezárt ébredés és kész boot után, stabil Active állapotban, ellenőrzött PID/indulási
azonosság mellett próbálkozik, folyamatpéldányonként legfeljebb egyszer.
Ha a hook már be van töltve, bekapcsolási ciklusonként egyszer újraolvastatja a
gombkiosztást; ehhez nem csatlakozik újra a folyamathoz.

A háttérben vagy parkolt állapotban lévő launcher figyelmen kívül hagyja a távirányító
Back/OK eseményeit. A láthatóságváltás törli a függő OK-nyomást. A szerver csak akkor
indíthatja vissza az előző appot a launcher Back-kérésére, ha a teljes saját launcher
natív felülete ténylegesen előtérben van. Ez a kézi Vissza-művelet különbözik a
bekapcsoláskori automatikus folytatás kapcsolójától.

Bekapcsoláskor a guard legfeljebb 180 másodpercig vár a rendszer és az előtér natív felületének
készenlétére. Amint mindkettő kész, elindítja a launchert; ekkor kezdődik a legfeljebb
40 másodperces, ritkított újrapróbálási időablak. Ezek felső korlátok, nem hozzáadott várakozások.
A közben megfigyelt felhasználói app vagy saját popup lezárja az ébredési próbát; a lezárt
próba után a guard nem veszi át a később kiválasztott HDMI/Live TV bemenetet. Az LG Home
leváltása ezután is működik, ha a guard engedélyezett és a rendszer kész.

Az előtöltés és az elrejtett app megőrzése segítheti a meleg nyitást, de a webOS memóriafelszabadítása
és a Quick Start visszaállítása miatt a folyamat életben maradása nem garantált.
További üzemeltetési részletek: [remote-control/README-HU.md](remote-control/README-HU.md).

## URL-szabályzat

A `common/url-core.js` Chrome 79-kompatibilis, DNS-feloldást nem végző referencia-validátor és
offline policy-teszt. A két app ugyanezt a kötelező policyt saját, a felületéhez szűkített runtime
validátorral is ellenőrzi közvetlenül a médiaforrás használata előtt. A referencia csak teljes
`http://` vagy `https://` URL-t fogad el kanonikus, numerikus RFC1918 IPv4-címmel. Kötelező tiltások:

- `192.168.0.100` minden porton;
- hostname, IPv6, publikus/loopback/link-local cím;
- URL userinfo (`user:password@...`) és fragment (`#...`);
- query-paraméter, amelynek dekódolt neve `token`, `access_token`, `password`, `auth`, `key` vagy
  `signature`, illetve ezeket külön névrészként tartalmazza.

Query egyébként használható, de megengedett nevű paraméter értékébe se kerüljön jelszó, token vagy
aláírás. Az API: `WebOsPipUrlCore.parse(url)`, `normalize(url)` és `isAllowed(url)`.

A Camera Viewer 0.3.10 nem kér kézzel összerakott stream-URL-t: a validált gateway hostból és rövid
go2rtc aliasból állítja elő a snapshot/MJPEG URL-eket. A teljes nézet sorrendje
WebRTC → MJPEG → JPEG snapshot. Tetszőleges számú validált kamera menthető;
a képernyő kapacitásán felüli profilok lapozhatók. 3×3 vagy 4×4 nézetben egy kiválasztott kamera
2×2 cellát foglalhat el a bal felső sarokban. A kiemelés minden előnézet jobb felső szemgombjával
kapcsolható; az aktív állapotot áthúzott szem jelzi. A Camera Viewerben nincs PiP gomb, mert a webOS
overlay nem ad valódi bemenet-átengedést a rendszer menüje vagy más alkalmazás felé. IP-alakú alias
és a `.100` hivatkozása tiltott.

A rács keskeny felső címsávja tartalmazza az app ikonját, a lapozót és jobb felül a beállításgombot;
a lapozó és a fogaskerék között fix 26 pixeles rés marad. A lebegő
alkalmazás- és lejátszási üzenetek öt másodperc után eltűnnek. A rács snapshot-előnézete alapból
öt másodpercenként frissül, a TV-appban és az `lgtv-control` felületén 1–60 másodperc között állítható;
a TV-s mentés azonnal újrarajzolja a rácsot az új időzítéssel.
A kapcsolható
képernyőkímélő-védelem a TV két fix, nyilvánosan elérhető `tvpower` Luna-metódusát használja:
feliratkozik az indulási kérésre, majd `ack:false` válasszal vétózza azt. App-felfüggesztéskor
leiratkozik; tetszőleges Luna URI nem adható át paraméterként.

## Offline ellenőrzés és build

```sh
node --check common/url-core.js
node tests/url-core.test.js
node tests/lifecycle-contract.test.js
node tests/launcher-quick-core.test.js
node apps/media-overlay/tests/media-overlay.test.js
node apps/camera-viewer/tests/camera-viewer.test.js
node apps/camera-viewer/tests/webos-player.test.js
python3 gateway/go2rtc-tv-player/test_server.py
python3 -m py_compile gateway/go2rtc-tv-player/server.py
python3 tests/test_launcher_packaging.py
python3 remote-control/tests/test_server.py
# POSIX környezetben, hamis Luna-válaszokkal; a TV-t nem használja:
python3 tests/test_home_shell.py
sh -n gateway/go2rtc-tv-player/install-on-proxmox.sh
chmod +x scripts/*.sh
./scripts/build-all.sh
# vagy Windowson a mellékelt Python 3 build:
python scripts/build-all.py
```

A POSIX belépési pont és a közvetlen parancs ugyanazt a standard Python 3-ra épülő
`scripts/build-all.py` implementációt futtatja. Ez egyetlen szűk fájl-allowlistből, 0755/0644,
root:root tar-metaadattal, nulla időbélyegekkel determinisztikus IPK-t állít elő Windowson és Linuxon is.

A build minden csomagnál ellenőrzi az elvárt app-ID-t és a háromtagú verziót. A kimenet a `build/`
mappába kerül `hu.szabi.<app>_<version>_all.ipk` néven; a parancs kiírja a SHA-256 értéket.
A launcher build három csomagot ad: `hu.szabi.launcher_<version>_all.ipk`,
`hu.szabi.launcher.overlay_<version>_all.ipk` és `hu.szabi.launcher.quick_<version>_all.ipk`.
Mindháromban byte-azonos a közös runtime és benne van a
`launcher-cache.js`; csak az `appinfo.json` és a build által generált `launcher-host.js` különbözik.
A csomag csak explicit allowlistelt runtime fájlokat tartalmaz; teszt és README nem kerül az IPK-ba.

## Telepítés és eltávolítás

A Camera Viewer WebRTC módjához előbb a go2rtc LXC-n futó, szűk same-origin bridge-et kell
telepíteni a Proxmox hostról:

```sh
sh gateway/go2rtc-tv-player/install-on-proxmox.sh 120
```

Ez csak a TV IP-jét, a player statikus fájljait és biztonságos karakterkészletű streamaliasokat
engedélyez; IP-alakú forrás és a go2rtc admin API tiltott. A telepítő egy apró fekete H.264 videót
is készít a kapcsolható képernyőkímélő-védelemhez, továbbá hash-, syntax-, systemd- és `/healthz` ellenőrzést
végez, hiba esetén visszaállítja a korábbi állapotot.

Másold a kiválasztott IPK-t és a scriptet a TV egy ideiglenes könyvtárába, majd a TV shelljében:

```sh
sh install-local-on-tv.sh /tmp/hu.szabi.mediaoverlay_0.3.6_all.ipk EXPECTED_SHA256
sh install-local-on-tv.sh /tmp/hu.szabi.cameraviewer_0.3.10_all.ipk EXPECTED_SHA256
sh install-local-on-tv.sh /tmp/hu.szabi.remotemapper_0.1.4_all.ipk EXPECTED_SHA256
sh install-local-on-tv.sh /tmp/hu.szabi.launcher_0.3.8_all.ipk EXPECTED_SHA256
sh install-local-on-tv.sh /tmp/hu.szabi.launcher.overlay_0.3.8_all.ipk EXPECTED_SHA256
sh install-local-on-tv.sh /tmp/hu.szabi.launcher.quick_0.3.8_all.ipk EXPECTED_SHA256
```

A telepítő előbb ellenőrzi a hash-t, majd a developer install API terminális állapotát. Csak az utolsó
`statusValue: 30` számít sikernek. **A telepítő nem indítja el az appot**, ezért minden post-install
launch és fizikai megjelenítési próba külön, explicit tesztlépés.

Ezen a webOS 6.5 TV-n a Luna subscription válasza SSH-n csak kiosztott TTY mellett jelent meg. PuTTY
`plink` használatakor ezért a telepítőt `-t` kapcsolóval kell futtatni; TTY nélkül a script
fail-closed módon leáll, ha nem látja a 30-as végállapotot.

Eltávolítás:

```sh
sh remove-local-on-tv.sh hu.szabi.mediaoverlay
sh remove-local-on-tv.sh hu.szabi.cameraviewer
```

A remove script kizárólag ezt a két app-ID-t fogadja el, és terminális `statusValue: 31` állapotot vár.

## Átadási kapuk

Kiadás előtt rögzítendő: forrásverzió; IPK méret és SHA-256; outer/data/control fájllista; control,
packageinfo és appinfo verzióegyezés; telepítés terminális állapota; külön cold és warm launch; hibás
launch paraméterek elutasítása; tiltott URL-ek elutasítása; Home/Back visszaút; eltávolítás és
újratelepítés. A commercial webOS TV-n az `overlay` ablakot a Surface Manager 1–2 perc után
láthatatlanná tette, ezért a 0.3.2 a szintén átlátszó `popup` ablakréteget használja. Ez sem nyilvános
kompatibilitási garancia, ezért firmware-frissítés után ismét fizikai próba szükséges.

Az aktuális artifact-hasheket a `SHA256SUMS.txt`, a végrehajtott és még függő teszteket a
`TEST-REPORT.md`, az átadási célokat pedig a `TRANSFER-NOTES.md` tartalmazza.
