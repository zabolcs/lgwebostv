# LG webOS vezérlőrendszer – technikai átadás, 2026-09-25

## 1. Cél és jelenlegi eredmény

A rendszer egy LG UP78003LB / webOS 6.5 TV gyári Home felületét saját launcherrel váltja ki, kezeli a rövid és hosszú Home/Back műveleteket, kameraképet és PiP ablakot jelenít meg, valamint egy LAN-on elérhető webes adminfelületet ad. Minden beavatkozás visszaállítható; az immutable rootfs, a bootloader és a rootolási exploitlánc nem lett módosítva.

Az éles állapot a mentéskor:

| Komponens | Éles verzió/állapot |
|---|---|
| Full launcher `hu.szabi.launcher` | 0.3.11 |
| Overlay launcher `hu.szabi.launcher.overlay` | 0.3.11 |
| Quick launcher `hu.szabi.launcher.quick` | 0.3.11 |
| Camera Viewer `hu.szabi.cameraviewer` | 0.3.11 |
| Media Overlay / PiP `hu.szabi.mediaoverlay` | 0.3.7 |
| Remote Mapper `hu.szabi.remotemapper` | 0.2.0 |
| Magic Remote overlay `hu.szabi.magicremoteoverlay` | 0.3.2 |
| Guacamole/Home Assistant/Lyrion webwrapper | 1.0.3 mindhárom |
| TV-local launcher guard | engedélyezve, fut |
| Stabil remote broker | engedélyezve, `factory-evdev-relay`, fut |
| Régi natív InputHook | letiltva; nincs autostart marker és nincs betöltött `libphp.so` |
| CT125 `lgtv-control.service` | enabled + active |
| CT125 `lgtv-launcher-early.service` | enabled + active |
| Full launcher megjelenítés | `app` |
| Home mód | `split` |
| Utolsó app visszaindítása bekapcsoláskor | kikapcsolva |
| Animációk / drága effektek | kikapcsolva / kikapcsolva |
| Háttérképek | bekapcsolva |

Az éles, pontos konfiguráció a privát tarokban van. A fenti állapotot a `LIVE-STATE-SUMMARY.json` rögzíti. A NAS-kötet NTFS/FUSE csatolása miatt a PVE-n a fájlok `0777` móddal látszanak; a `private-live` védelmét a NAS megosztási ACL-jével kell megoldani, és ezt a könyvtárat tilos nyilvános repositoryba másolni.

## 2. Topológia és elérés

```text
PC / Codex
  |
  | SSH, host key ellenőrzéssel
  v
Proxmox VE 192.168.0.120 (root)
  |-- CT125 192.168.0.223  lgtv-control web/NAS app, port 8765
  |      |-- kulcsos SSH --> TV 192.168.0.240 (root)
  |      `-- párosított WSS/SSAP --> TV 192.168.0.240:3001
  |
  `-- CT120 192.168.0.150  go2rtc:1984 + korlátozott player bridge:1985
                              |
                              `-- kameraképek / WebRTC a TV appjai felé
```

### Webes felület

- URL: `http://192.168.0.223:8765/`
- A szolgáltatás LAN-hálózatra korlátozott (`127.0.0.0/8`, `192.168.0.0/24`).
- A CT125 címe DHCP-s, de jelenleg 192.168.0.223. Ha változik, a `public_base_url`, a `connections.json` és a TV-n a `control-origin` is frissítendő.

### Proxmox és konténerek

- PVE: `root@192.168.0.120`.
- A PVE jelszava nincs megismételve ebben a dokumentumban. A meglévő, működő PC-s helper a korábbi privát checkpointból olvassa, és pinned `known_hosts` fájlt használ: `source/previous-work-20260905/remote.py`.
- CT125-be közvetlen root+jelszó belépés szándékosan nincs: a root account zárolt, az SSH `PermitRootLogin without-password`. Használd a PVE-t:

```sh
ssh root@192.168.0.120
pct enter 125
# vagy egy parancsra:
pct exec 125 -- systemctl status lgtv-control.service
```

- CT120 kezelése ugyanígy: `pct enter 120`.

### TV root shell

A TV kulcsa és rögzített host key-je a CT125-ben van:

```sh
pct exec 125 -- ssh -T \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/lgtv-control/known_hosts \
  -i /etc/lgtv-control/id_rsa \
  root@192.168.0.240
```

Ne állítsd `StrictHostKeyChecking=no` értékre. Host key változás esetén előbb fizikailag ellenőrizd, hogy valóban a TV változott-e.

## 3. A forrás felépítése

A kanonikus, legfrissebb forrás: `source/current-suite/`.

- `apps/launcher/`: közös launcher core és UI. A full, quick és overlay csomag ezt használja; nincs három külön implementáció.
- `apps/launcher-quick/`, `apps/launcher-overlay/`: csak a host-specifikus manifest és leírás.
- `apps/camera-viewer/`: kameranézet, snapshot/WebRTC lejátszó.
- `apps/media-overlay/`: PiP/popup overlay.
- `apps/remote-mapper/`: TV-s gombkiosztás felület.
- `remote-control/`: a teljes CT125 web app (`server.py`, statikus admin UI), SSAP kliens/párosítás és korai indító.
- `remote-broker/`: C forrású, natív hook nélküli evdev relay és supervisor.
- `gateway/go2rtc-tv-player/`: CT120 same-origin kamera bridge.
- `scripts/`: determinisztikus IPK builder és telepítők.
- `tests/`: JS és Python regressziós tesztek.
- `build/`: meglévő kiadási IPK-k, TV guard szkriptek és broker artifactok.

A `source/current-development/` az összes újabb deploy/mérő/probe szkriptet megőrzi. Ezek közül több szándékosan megszakít appot vagy újraindítja a TV-t; a fájl fejlécét mindig olvasd el futtatás előtt.

## 4. Build és teszt

### webOS appok

Windows vagy Linux alatt, a suite gyökeréből:

```sh
python scripts/build-all.py
```

A determinisztikus builder a `build/` könyvtárba készíti az IPK-kat. A verziót az adott `appinfo.json` adja. Kiadás előtt:

```sh
python tests/test_launcher_packaging.py
python tests/test_home_shell.py
python remote-control/tests/test_server.py
python remote-control/tests/test_launcher_early.py
python remote-control/tests/test_lg_ssap.py
python remote-control/tests/test_ssap_pairing.py
node tests/launcher-cache.test.js
node tests/launcher-input-lifecycle.test.js
node tests/launcher-popup-lifecycle.test.js
node apps/camera-viewer/tests/camera-viewer.test.js
node apps/media-overlay/tests/media-overlay.test.js
```

A teljes korábbi tesztlista a `TEST-REPORT.md` és `source/previous-work-20260905/run-checks.py` fájlokban van.

### remote broker

A Makefile alapértelmezésben statikus ARM Linux GCC-t vár:

```sh
cd remote-broker
make CC=arm-linux-gnueabi-gcc
sha256sum remote-broker
```

A jelenlegi éles bináris és a hozzá tartozó C forrás a checkpointban megvan. A `toolchains/` a korábban használt Zig csomagokat is tartalmazza, de ezek harmadik féltől származnak. Fordítás után mindig futtasd a PC-s teszteket, majd először passzív módban próbáld.

## 5. Telepítés

### IPK telepítés a TV-re

1. Másold az IPK-t és `scripts/install-local-on-tv.sh` fájlt a TV `/tmp` könyvtárába.
2. Számíts SHA-256-ot.
3. A TV root shellben:

```sh
sh /tmp/install-local-on-tv.sh /tmp/hu.szabi.launcher_0.3.11_all.ipk EXPECTED_SHA256
```

A telepítő ellenőrzi a hash-t, az app ID-t/verziót és az install API válaszát, majd az installált manifestet. Nem indítja el automatikusan az appot. Mindig csak a módosított csomagot telepítsd; a Camera/PiP/Remote Mapper külön csomagok.

### CT125 web app friss telepítése

A tiszta alaptelepítő:

```sh
cd source/current-suite/remote-control
sh install-in-ct.sh /ABSZOLUT/UT/id_rsa 192.168.0.240
```

Ez létrehozza az `lgtv-control` system usert, bemásolja a backend/UI fájlokat, létrehozza a konfigurációt, host key-t gyűjt, engedélyezi és elindítja az alap service-t. A telepítő jelenlegi változata nem rakja fel önmagában a később hozzáadott SSAP gyorsítót. Ahhoz a `source/current-development/deploy-native-launcher.py` a referencia: bemásolja a `lg_ssap.py`, `launcher_early.py`, `ssap_pairing.py`, `static/ssap-control.js` és `lgtv-launcher-early.service` fájlokat. A mentett SSAP credentialt csak privát restore során másold vissza; új TV vagy tanúsítványváltozás esetén a web UI-n indíts felügyelt újrapárosítást.

Az éles állapot pontos visszaállításához egyszerűbb a `private-live/ct125-current.tar.gz`: állítsd le a két service-t, készíts új mentést az érintett útvonalakról, bontsd ki az archívumot `/` alá, ellenőrizd a tulajdonosokat és módokat, majd `systemctl daemon-reload` és service restart.

Fontos jogosultságok:

```text
/etc/lgtv-control/config.json               0640 root:lgtv-control
/etc/lgtv-control/id_rsa                    0600 lgtv-control:lgtv-control
/var/lib/lgtv-control/lg-ssap.json          0600 lgtv-control:lgtv-control
```

### CT120 kamera bridge

A PVE hoston, a suite gyökeréből:

```sh
sh gateway/go2rtc-tv-player/install-on-proxmox.sh 120
```

A telepítő tranzakciós, hash-t és health endpointot ellenőriz, és hibánál visszaáll. Éles útvonal: `/opt/go2rtc-tv-player`; unit: `/etc/systemd/system/go2rtc-tv-player.service`; health: `http://192.168.0.150:1985/healthz`.

### Guard és broker

- Guard: `/var/lib/webosbrew/launcher-home/guard.sh`, init: `/var/lib/webosbrew/init.d/launcher-home`.
- Broker: `/var/lib/webosbrew/remote-broker/remote-broker`, `supervisor.sh`, `bindings.conf`, init: `/var/lib/webosbrew/init.d/remote-broker`.
- A broker telepítője: `remote-broker/install-on-tv.sh`; engedélyezett broker mellett szándékosan nem írja felül a binárist.
- Módosítás előtt kapcsold ki a markerét, állítsd le szabályosan, telepíts, konfigurációellenőrzés, passzív próba, csak utána `grab`/relay mód.

## 6. Mit próbáltunk és mi lett az eredmény

### Launcher és cache

- Offline-first indulás: a launcher localStorage/IndexedDB állapotból rajzol, a hálózati szinkron később fut.
- Régi kamera snapshot és háttérkép azonnali cache-ből megjelenhet, majd cserélődik frissre.
- Közös, bundle-olt runtime csökkenti a fájl- és parse-költséget.
- Fekete splash/boot cover elfedi a részleges UI-t; a cover felső korlátja beállítható.
- A full/quick/overlay ugyanazt a core-t használja.
- Animáció és drága vizuális effekt külön kapcsoló. A háttérkép és a kijelölt csempe olvashatósági háttere ettől független.
- 720p próbát vissza kellett vonni, mert négyzetes/hibás csempéket okozott; a manifest 1920×1080.
- Minimal startup probe A/B-ben körülbelül 0,8 s előnyt adott, tehát a 10–15 s wake késés fő oka nem a nagy UI.
- `networkStableTimeout: 0.25` nem hozott mérhető javulást, ezért eltávolításra került.
- `handlesRelaunch:false` nem javította a standby indulást, visszaállt `true` értékre.
- Meleg retained oldal 2–3 s körüli natív surface-t tudott; hideg renderer már felállt TV-n ~4 s. A teljes OS bootnál a WAM/SAM és rendszerkészültség dominál.

### Warm start és overlay

- A quick launcher rejtve tartása és előmelegítése működik, de az első compositor-surface továbbra is okozhat késést.
- Full launcher keepAlive/hide/SAM-prewarm nem adott megbízható megtartást suspend után.
- Az overlay/popup megőrzi az alatta futó Plex/YouTube appot, de az LG compositoron lassabb és erőforrásigényesebb.
- A háttérben parkolt saját appoknak tilos Back/OK eseményre reagálni; a 0.3.8 utáni lifecycle gate ezt javítja.

### Automatikus Home-helyettesítés

- A TV-local guard power-, boot- és foreground eseményeket figyel, csak ellenőrzött helyzetben indít, és nem floodolja SAM-et.
- Quick Start ébredéshez a CT125 párosított natív WSS/SSAP gyorsítója korábban látja az OFF→Active átmenetet. Csak 20 másodperces wake ablakban, LG Home/HDMI/Live TV esetén indít; valódi appot békén hagy, bizonytalan timeoutot nem ismétel.
- Teljes OS rebootkor a 3001-es port korán megnyílik, de a párosított SSAP kapcsolat sokáig nem használható. Emiatt ez a külső gyorsító nem oldja meg a hideg bootot; a TV-local guard csak a Homebrew root startup után indul.
- Boot mérésben: natív port kb. 22–24 s, root SSH kb. 37–42 s, launcher renderer kb. 42–48 s, natív launcher surface kb. 47–54 s. Ezek teljes OS reboot mérések, nem Quick Start.

### Távirányító és stabilitás

- A régi széles LG InputHook `micomservice` SIGSEGV-t okozott; a szűkített `lginput2` injekció is bizonyítottan összeomlott. Ezeket nem szabad újra engedélyezni.
- Az új megoldás saját userspace broker: az LG fizikai evdev eseményeit olvassa/grabolja, kontrolláltan továbbítja a gyári virtuális input felé, és a saját kötéseket külön indítja. Nem injektál kódot LG folyamatba.
- A supervisor heartbeat/fail-open/recovery logikát használ. A jelenlegi futó natív folyamatokban nincs `libphp.so`.
- A Home/long Home/Back kezelés ezzel stabilabb, de minden új broker változtatást előbb passzív és watchdogos tesztben kell kipróbálni.

### Ismert hibák és veszélyes zsákutcák

- Ne futtasd újra a régi `deploy-stability-v037.py` vagy széles InputHook telepítést.
- Ne állítsd vissza `/var/lib/webosbrew/init.d/inputhook` fájlt.
- Ne módosítsd a Homebrew `startup.sh`, `jumpstart.sh`, bootloader vagy immutable rootfs fájlokat. Ezek a root-hozzáférés részei és TV-bricket okozhatnak.
- Ne tekintsd a launch ACK-ot fizikai megjelenésnek; külön mérd dispatch, ACK, WAM navigation/paint és Surface Manager láthatóság időpontját.
- A TV snapshot firmware reboot után megtarthatja a `boot_id` értéket; valódi rebootot uptime/disconnect/process lifetime alapján mérj.

## 7. Mi van még hátra, ígéretes sorrendben

1. **Activity Manager boot callback próba** – a cél TV firmware-e támogat `bootup` requirementet, és a gyári `demo.smartdemokit.launch` activity bizonyítja a bootManager/`firstAppLaunched` mintát. Részletes, rollbackes terv: `AUTOSTART-ACTIVITYMANAGER-KISERLET.md`.
2. **Csak mérő service** – előbb launch nélküli callback írjon időbélyeget, így kiderül, mennyivel indul a Homebrew `init.d` előtt. Csak bizonyított előny után indítson minimal probe appot.
3. **Guard kettőzés kizárása** – a próba idején egyetlen launch-tulajdonos legyen; automatikus, időkorlátos TV-local recovery marker állítsa vissza a guardot kapcsolatvesztéskor.
4. **Quick popup első surface mérése** – retained renderer ID, WAM first paint és native surface külön. A már meglévő popupot ne építsd újra, csak aktiváld.
5. **UI finomítás** – TV-s beállítások fókuszrendje és kategóriái tovább javíthatók, de ez nem a 10–15 s boot késés fő oka.

## 8. Naplók és diagnosztika

```sh
# CT125
systemctl status lgtv-control.service lgtv-launcher-early.service
journalctl -u lgtv-control.service -u lgtv-launcher-early.service --since today

# TV
tail -n 100 /tmp/hu.szabi.launcher-wake.log
tail -n 100 /tmp/hu.szabi.remote-broker.log
cat /var/log/bootd.log
luna-send -t 1 -f -w 1000 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}'
luna-send -t 1 -f -w 1000 luna://com.webos.service.tvpower/power/getPowerState '{}'
```

A mentés `private-live/diagnostics` könyvtára tartalmazza a mai állapotot és az Activity Manager read-only lekérdezését.

## 9. Restore ellenőrzőlista

1. Ellenőrizd: `sha256sum -c SHA256SUMS.txt`.
2. Jegyezd fel az aktuális PVE/CT/TV IP-ket és host key-ket.
3. Mentsd a restore előtti állapotot külön mappába.
4. CT125 restore után ellenőrizd a fájljogokat és mindkét service-t.
5. CT120 restore után ellenőrizd a `1985/healthz` endpointot.
6. TV restore után először csak app manifesteket, guard/broker marker állapotot és shell syntaxot ellenőrizz.
7. InputHook maradjon tiltva; ellenőrizd, hogy `micomservice` és `lginput2` nincs hookolva.
8. Előbb kézi app launch, aztán Home/Back, végül egyetlen engedélyezett Quick Start próba.
9. Teljes rebootot csak kifejezett felhasználói engedéllyel végezz.
