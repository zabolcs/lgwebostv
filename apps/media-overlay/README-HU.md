# Media Overlay – hu.szabi.mediaoverlay 0.3.5

Átlátszó webOS overlay app szöveghez, képhez/MJPEG-hez és HTML5 videóhoz. A méret, sarok, margó,
TTL és médiaforrás indításonként átadható. A `ttlMs: 0` szigorúan kézi bezárást jelent: egy késői
MJPEG-/képhiba sem indít automatikus hibabezárást. A megszakadt képstream 1,5 másodpercenként,
cache-bustolt URL-lel próbál újracsatlakozni, miközben a nulla TTL változatlan marad.

## Dinamikus megjelenítés

```json
{
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
  "ttlMs": 20000
}
```

`kind` értéke `text`, `image` vagy `video`. Szövegnél `text`, médiánál `url` (vagy kompatibilitási
aliasként `src`) szükséges. A `fit` `contain` vagy `cover`. A layoutmezők opcionálisak; a TV-n
mentett alapértékből öröklődnek. `margin` egyszerre állítja mindkét margót, a külön `marginX` vagy
`marginY` elsőbbséget élvez.

A közvetlen kép- vagy videóindításhoz is adható `clickAction:"openCamera"` és validált `cameraId`.
Kattintásra ugyanaz a kamera nyílik meg teljes képernyőn a Camera Viewerben. A Camera Viewer
kameracsempéin nincs PiP gomb, mert a webOS ablaka nem engedi át a bemenetet más appoknak.

A 0.3.5 az átlátszó `popup` ablakréteget használja. Az előző `overlay` réteget a TV Surface Managere
`ttlMs:0` esetén is 1–2 perc után láthatatlanná tette; a `popup` változat az élő próbán 5 perc
30 másodpercig látható maradt, majd az explicit `dismiss` kérésre bezárult.

A `show` kérés előtt az app a LAN-os `lgtv-control` CT rövid életű Camera Viewer-jelenléti állapotát
lekéri, és aktív Camera Viewer esetén látható PiP nélkül bezár. A heartbeat hiányában tartalékként
megpróbálja a TV előtér-app lekérdezését. A launch parser a közvetlen params mellett a teljes
launcher/payload/params borítékot és a `webOSLaunch` eseményt is fogadja.

Ha a PiP már látható, betöltődik, a Camera Viewer ellenőrzésére vár, vagy felfüggesztve megőrizte az
aktív tartalmát, egy újabb `show` relaunch kérés csendben figyelmen kívül marad. A futó PiP-et ezért
nem lehet egy második Home Assistant-hívással felülírni; a `dismiss` továbbra is azonnal bezárja.

Minden, Camera Viewer által nem blokkolt, validált `show` indítás feloldott tartalmát és végleges
layoutját az app külön localStorage-bejegyzésben megjegyzi. A TV alkalmazásmenüjéből érkező üres
indítás vagy az egzakt `{"storeCaller":"home"}` launch ezután az utolsó PiP-et nyitja meg újra.
A `requestId` nem kerül tárolásra. Ha még nincs korábbi PiP, a beállítófelület nyílik meg; az explicit
`{"action":"settings"}` mindig a beállításokat nyitja. Egy már aktív PiP-et az üres relaunch sem
ír felül.

Mentett preset megjelenítése:

```json
{"v":1,"action":"show","presetId":"kapu-preview","ttlMs":12000}
```

Bezárás Home Assistantból vagy más launch kliensből:

```json
{"v":1,"action":"dismiss"}
```

A `close` action kompatibilitási aliasként szintén `dismiss`-re fordul.

## Alapértelmezett layout távoli mentése

```json
{
  "v": 1,
  "action": "configure",
  "corner": "top-left",
  "width": 640,
  "height": 360,
  "marginX": 32,
  "marginY": 32,
  "ttlMs": 0
}
```

Az értékek az app localStorage konfigurációjába kerülnek. A későbbi `show` kérésekből kimaradó
layoutmezők ezeket öröklik. A `defaults` action a `configure` kompatibilitási aliasa.

## Presetek létrehozása, módosítása és törlése

Új preset hozható létre, vagy azonos `presetId` mellett a meglévő módosítható:

```json
{
  "v": 1,
  "action": "preset-save",
  "presetId": "udvar-preview",
  "kind": "image",
  "url": "http://192.168.0.150:1984/api/stream.mjpeg?src=camera_udvar_felso_preview",
  "fit": "cover",
  "clickAction": "openCamera",
  "cameraId": "udvar"
}
```

Törlés:

```json
{"v":1,"action":"preset-delete","presetId":"udvar-preview"}
```

Legfeljebb 32 preset menthető. Az opcionális `clickAction` kizárólag `openCamera` lehet, érvényes
`cameraId` mellett; ekkor kattintásra vagy OK-ra csak a hardcoded `hu.szabi.cameraviewer` indulhat.
Tetszőleges app-ID vagy Luna URI nem adható át.

## URL-szabályok

Képhez és videóhoz numerikus RFC1918 privát IPv4-címes HTTP/HTTPS URL használható. A port opcionális.
A `192.168.0.100` cím, publikus/loopback/link-local host, hostname, IPv6, userinfo, fragment, kódolt
URL-rész és titkot jelző querynév (`token`, `access_token`, `password`, `auth`, `key`, `signature`)
tiltott. A TV által követett redirectet az app nem tudja újra validálni, ezért megbízható helyi
média-gateway használata szükséges.

## Helyi beállítás és vezérlés

Normál appindításkor a TV-s beállítófelület nyílik meg. Ugyanezek a műveletek a külön
`lgtv-control` CT `http://CT_IP:8765/` webfelületéről is elérhetők anélkül, hogy a TV-n állandó
webszerver futna.

Teszt:

```sh
node --check core.js
node --check app.js
node tests/media-overlay.test.js
```
