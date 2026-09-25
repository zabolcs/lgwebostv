# lgtv-control böngészős vezérlő

Ez a kis HTTP-szolgáltatás nem a TV-n, hanem a külön `lgtv-control` Proxmox CT-ben fut. A
böngészőből kapott, szigorúan validált Media Overlay és Camera Viewer beállításokat SSH-n és a TV
helyi `luna-send-pub` parancsán keresztül küldi a két fix alkalmazásnak. A negyedik, vizuális
Távirányító gombok oldal a különálló LG Remote Broker strukturált szerkesztője.

Az első modul az alábbiakat kezeli:

- közvetlen kép/MJPEG- vagy videó-URL, illetve szöveg;
- TV-n mentett preset;
- sarok, szélesség, magasság, vízszintes/függőleges margó;
- `ttlMs`, ahol `0` esetén az overlay nem záródik be magától;
- külön PiP-bezárás (`action: dismiss`);
- az aktuális beállításokból másolható Home Assistant YAML;
- a TV appban tartósan elmenthető alapértelmezett sarok, méret, margó és TTL;
- preset létrehozás, azonos ID-val módosítás és törlés;
- opcionális `openCamera` kattintás/OK és validált kamera-ID a presethez.

A külön Kamera oldalon listából választható, létrehozható, módosítható, törölhető és a TV-n
megnyitható bármely kamera. Ugyanitt állítható a 2×2/3×3/4×4 layout, a kiemelt kamera,
a kameránkénti WebRTC-hang és a képernyőkímélő-védelem. A preset- és kameralista a TV tényleges,
tartós beállításaiból szinkronizálódik; a böngészőnek nem kell előre ismernie az azonosítókat.

A Távirányító gombok oldalon egy valós távirányítót mintázó ábrán egérrel választható ki a gomb.
A jobb oldali panel azonnal betölti a kötését. A Home, Back, navigáció, OK, hangerő, csatorna,
bemenet, beállítás és bekapcsoló gomb látható, de zárolt. A kevésbé fontos színes, szolgáltatói,
asszisztens, Lista és További műveletek gombokhoz telepített app indítása, ismert gombhelyettesítés,
letiltás vagy eredeti működés állítható. Tetszőleges shell-parancs nem adható meg.

A szolgáltatás minden mentésnél csak a kiválasztott keycode bejegyzését változtatja meg. A többi,
akár ismeretlen vagy korábbi `exec` bejegyzést is változatlanul megőrzi. Az első módosítás előtt
`keybinds.before-remotemapper.json`, minden további módosítás előtt `keybinds.previous.json`
visszaállítási pont készül, az új aktív fájl pedig temp fájlból atomikusan kerül a helyére.

A konfiguráció szerkesztése önmagában nem indít TV-s figyelőt. A futtatómotor forrása a
`remote-broker/remote-broker.c`: evdev eseményeket olvas, `grab` módban uinputon továbbítja az
eredeti eseményeket, és csak az allowlistes kötést téríti el. A folyamatba injektáló Input Hooknak
letiltva kell maradnia. Az opcionális launcher guard ettől független háttérfolyamatként fut a TV-n.
A CT-ben a Pillow opcionálisan gyorsítja
és méretezi a képelőnézeteket; nélküle a szerver a Python standard könyvtárával is működik.
A szerver csak a beállított helyi
alhálózatról és csak a várt JSON/text szinkronformátumot fogadja. A gombkötéshez választott app-ID-t
a TV tényleges telepített alkalmazáslistájához ellenőrzi; tetszőleges Luna URI-t vagy parancssort
nem vesz át a klienstől. Hozzáférési tokent nem kér; ezért a helyi hálózat bármely eszköze vezérelheti.

## Telepítés a CT-ben

2026-09-21-i életciklus-javítás: a broker felügyelője a natív TV energiaállapotot is figyeli.
Készenlétben leállítja a gyereket és elengedi az inputot, az `enabled` jelző megtartásával.
Ébredéskor két aktív mintára, majd kompatibilis és nyugalmi inputeszközökre vár; ez a
Quick Start és a teljes boot alatt is érvényes. Az aktív TV melletti váratlan kilépés és a
beragadt heartbeat továbbra is tartós letiltást okoz, automatikus hiba-újrapróbálás nélkül.
A kilépési kód, energiaállapot, bootazonosító és az utolsó 8 KB napló megmarad a TV-n:
`/var/lib/webosbrew/remote-broker/last-failure.log`. A NAS külön jelzi a készenléti várakozást
és a kért bekapcsolás ellenére bekövetkezett hibaleállást.

A launcher kezdeti várakozása 2-ről 1 másodpercre csökkent, de a boot manager és a natív
felület készenléti ellenőrzése megmaradt. A Quick előtöltési küszöbe 15-ről 4, a teljes
launcheré 45-ről 8 másodpercre csökkent; ezek legkorábbi időpontok, nem garantált
megjelenési idők. Előtöltés csak lezárt ébredési folyamat után történik. A teljes overlay
is kap rejtett natív előtöltést, ébredésenként legfeljebb egyszer, legalább 128 MB elérhető
memóriával. A tényleges hidegindítási gyorsulást fizikai bekapcsolási próbával kell mérni.

Másold be a `remote-control` mappát és a TV privát SSH-kulcsát, majd:

```sh
chmod +x install-in-ct.sh
./install-in-ct.sh /root/id_rsa
```

A telepítő létrehozza a jogosultságszegény `lgtv-control` felhasználót, a
`/opt/lgtv-control` programkönyvtárat, a `/etc/lgtv-control` védett konfigurációt és az
`lgtv-control.service` systemd unitot.

Az új konfigurációban az `input_hook_watchdog_enabled` és a `remote_broker_enabled` is `false`,
a `remote_broker_mode` pedig `passive`. A régi watchdogot nem szabad visszakapcsolni. A broker csak
telepített, ellenőrzött ARM binárissal és explicit `remote_broker_enabled: true`,
`remote_broker_mode: "grab"` párral indulhat. Hibás típus vagy az engedélyezett+passive kombináció
konfigurációs hibát ad. A launcher `defaultHomeEnabled` beállítása mindkét inputmotortól
függetlenül szabályozza a guard működését.

A broker supervisor 5 másodperces heartbeat-határt és 60 másodperces ablakban háromhibás
megszakítót alkalmaz. Leálláskor a fájlleírók záródnak, ezért a kernel feloldja az input grabot.
A webes gombmentés a strukturált kötésből újragenerálja a szigorú broker-konfigurációt és a fix,
root tulajdonú akciószkripteket; a régi JSON-ban lévő tetszőleges `command` érték nem kerül át.

A 0.3.7 figyelő kizárólag az `lginput2` folyamatra korlátozott `repair-home-hook.sh` segédet
hívja. Az eredeti `org.webosbrew.inputhook.service/start` hívás nem része ennek az útvonalnak;
az eredeti `/var/lib/webosbrew/init.d/inputhook` indító maradjon letiltva. A régi szolgáltatás
indítása a `micomservice` és más LG folyamatok natív módosítását is elvégzi.

A segéd megvárja a kész bootot és az ébredési próba lezárását. Frissen lekért Active állapot,
üres `processing` mező és nem `off` értékű `onOff` mellett, a PID és indulási idő ellenőrzésével
legfeljebb egyszer próbálkozik ugyanazon `lginput2` példányon. A már betöltött hookot nem tölti
be újra. A natív csatolás ettől még beavatkozás, nem pusztán konfigurációs módosítás.

A konfiguráció `false` értékre állítása csak a későbbi automatikus beállítást tiltja;
a korábban létrehozott TV-s indítókat külön kell letiltani. A figyelő letiltó művelete a saját
engedélyező jelzőjét és indítóját törli, a ciklus magától fejeződik be. Nem küld jelet a mentett
PID-nek és nem szakít félbe már folyamatban lévő natív csatolást. A már betöltött könyvtár
ettől nem tűnik el; a tiszta állapotot szabályos rendszer-újraindítás után a folyamatok
memóriatérképével kell ellenőrizni. A Quick Start ki-/bekapcsolás önmagában nem bizonyítja ezt.

A guard a bekapcsolástól legfeljebb 180 másodperces készenléti várakozást enged. A boot és a
natív előtér elkészültekor azonnal megkezdődhet az indítás, ekkor indul a külön 40 másodperces
próbaidő. A kérések között legalább nyolc másodperc telik el az előző válasz óta. A készenlétre
várás nem fogyasztja el az indítási időkeretet; egyik időkorlát sem kötelező késleltetés.
A közben megfigyelt valódi app lezárja a próbát, és lejárt próba nem indul újra egy későbbi
HDMI/Live TV váltástól. Az LG Home normál leváltása továbbra is a guard feladata.

A unit az unprivileged LXC-vel kompatibilis hardeninget használ: külön rendszerfelhasználó,
`NoNewPrivileges`, üres capability-készlet, címtér-, task- és 128 MB memóriakorlát. A mount namespace-t
igénylő systemd kapcsolókat szándékosan nem ismétli meg, mert ezt az izolációt maga az LXC adja, és
az ilyen kapcsolókat a Proxmox unprivileged konténere elutasítja.

Alap URL: `http://CT_IP:8765/`. Az IP-t a DHCP-szerveren érdemes a CT MAC-címéhez rögzíteni.

## TV ki-/bekapcsolás és Home Assistant

A főoldali **TV energia** kapcsoló nem a vezetékes interfész klasszikus WoL-címét használja.
Bekapcsoláskor a CT a konfigurált `tv_wifi_mac` címre Wake-on-Wireless-LAN magic packetet küld
a `tv_wake_broadcasts` listában megadott helyi broadcast címek 9-es és 7-es UDP portjára.
Kikapcsoláskor SSH-n a rootolt TV fix webOS `tvpower/powerOff` metódusát hívja. Az állapotlekérés
a natív `tvpower/power/getPowerState` válaszát és a TV elérhetőségét együtt használja.

REST API (csak az `allowed_networks` hálózatokból):

```text
GET  http://192.168.0.223:8765/api/tv/power
POST http://192.168.0.223:8765/api/tv/power
Content-Type: application/json

{"state":"on"}
{"state":"off"}
```

A GET és POST válasz `power.state` mezője `on`, `off`, `turning_on`, `turning_off` vagy `unknown`;
a `power.on` logikai mező közvetlenül használható Home Assistant állapotsablonban. Példa
`configuration.yaml` részlet:

```yaml
switch:
  - platform: rest
    name: "Nappali LG TV"
    resource: "http://192.168.0.223:8765/api/tv/power"
    method: post
    body_on: '{"state":"on"}'
    body_off: '{"state":"off"}'
    is_on_template: "{{ value_json.power.on }}"
    availability: "{{ value_json.ok and value_json.power.state != 'unknown' }}"
    headers:
      Content-Type: application/json
```

A böngészős POST csak azonos originről fogadható; a Home Assistant szerveroldali REST kéréseinek
nincs böngészős `Origin` fejléce, ezért azok a helyi hálózatról működnek. Internet felé ezt a
végpontot ne publikáld.

## Ellenőrzés

```sh
python3 -m py_compile server.py
python3 tests/test_server.py
systemctl status lgtv-control.service
curl http://127.0.0.1:8765/api/health
```

Mivel a felület tokent nem kér és HTTP-t használ, csak megbízható helyi hálózaton használd; vendég
Wi-Fi-ről tűzfallal válaszd le. Nem megbízható LAN esetén reverse proxy mögötti HTTPS és hitelesítés
ajánlott.
