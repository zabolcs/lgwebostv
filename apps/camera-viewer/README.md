# Camera Viewer 0.3.21 – full-screen card app

TV-re optimalizált webOS kameraalkalmazás helyi go2rtc profilokhoz. A tárolható kamerák száma nincs
négyre korlátozva. A rács 2×2, 3×3 vagy 4×4 lehet; ha több kamera van, mint amennyi elfér, az app
oldalakra bontja őket. A távirányító jobb nyila az utolsó csempén a következő, bal nyila az első
csempén az előző oldalra lép.

A távirányítóval kijelölt kameracsempe rövid stabil fókusz után JPEG snapshotról MJPEG élőképre vált. Egyszerre pontosan egy grid MJPEG élhet; fókuszvesztéskor a kapcsolat hard-stopot kap. A háttérképek percenként frissülnek, kameránként 9 másodperces fáziseltolással, induláskor pedig a go2rtc snapshot-cache ad képet, amíg az első frissítés megérkezik. Fullscreen nyitásakor a grid MJPEG és minden folyamatban levő snapshot kérés leáll, csak a választott fullscreen transport marad aktív.

A csempék tényleges 16:9 képarányúak. A méretet az app a rendelkezésre álló szélességből és
magasságból számolja, Chrome 79-en is működő módon, így a preview nem nyúlik el és nem vágja le
feleslegesen a kamera képének tetejét vagy alját.

A kamerarács a címsáv alatt rendelkezésre álló magasságot használja. A korábbi nagy alkalmazásnév-
és beállítássáv helyett keskeny felső címsáv maradt appikonnal és jobb oldali fogaskerékkel.
Az alkalmazás- és lejátszási állapotüzenetek öt másodperc után automatikusan eltűnnek.
A lapozó Előző/Következő gombjai és az oldalszám szintén ebben a felső sávban jelennek meg, a
beállításgombtól fix 26 pixeles távolsággal.
A webOS Home launcher `storeCaller:home`
metaadata normál indításnak számít, ezért nem jelenik meg rá hibás launch-paraméter figyelmeztetés.

3×3 és 4×4 layoutnál kijelölhető egy kiemelt kamera. Ez minden oldalon a bal felső 2×2 cellát
foglalja el, a többi kamera a fennmaradó helyeket tölti ki. A rács ritkított JPEG snapshotokat
használ; teljes nézetben egyszerre pontosan egy transport aktív:

Minden preview-n külön szem gomb van. A szem kijelöli a kiemelt kamerát, az aktív kamerán áthúzott
szem látszik, és ugyanazzal a gombbal kapcsolható ki. A választás azonnal mentődik és visszaszinkronizálódik.

1. same-origin hosted WebRTC player, opcionális audióval;
2. MJPEG fallback;
3. frissülő JPEG snapshot fallback.

A WebRTC-lejátszó az első, idő előtti autoplay-elutasításkor némítva újrapróbál, és csak a valódi
12 másodperces kapcsolatindítási timeout vagy signaling/dekóderhiba után vált MJPEG-re. Ha a TV a
hangos autoplayt blokkolja, a teljes nézet Hang gombja felhasználói gesztussal visszakapcsolhatja.

## Full-screen működés

A Camera Viewer normál, nem átlátszó webOS `card` alkalmazásként fut. Ez szándékos teljesítmény-beállítás:
a TV-nek nem kell az alatta futó alkalmazást és a kamera popup rétegét folyamatosan kompozitálnia.
A kamerarácsban és teljes nézetben egyszerre legfeljebb egy folyamatos médiafolyam aktív.
A korábbi rejtett `screen-guard.mp4` fallback megszűnt, így nem foglalhat második videó-dekódert.
A képernyőkímélő-védelem kizárólag a Luna screen-saver API-t használja.

A TV-s felületen az animációk, fókusz-scale és blur effektek ki vannak kapcsolva. A távirányítós
rácsnavigáció előre számolt rácskoordinátákat használ, ezért egy nyílgomb nem kényszerít DOM
layout-mérést.

## Kamerák és gateway

Az alkalmazás nem tartalmaz gyárilag beégetett kamerát, NAS-címet, TV-címet vagy portot. A kamerák
és a gateway adatai a TV-n vagy az `lgtv-control` Kapcsolatok/Kamerák felületén állíthatók be.
A player és a WebSocket azonos originű:

```text
http://<gateway>:<player-port>/<player-path>
ws://<gateway>:<player-port>/api/ws?src=<validált-kamera-alias>
```

A parent app az URL-fragmentben adja át az aliast, a session-ID-t és az audio kapcsolót. A
`ready`, `playing`, `muted`, `audio-state` és `error` üzenetet csak egyező origin, forrásablak és
session esetén fogadja el. Az iframe sandboxolt; a go2rtc admin API nem érhető el a 1985-ös porton.

## Képernyőkímélő-védelem

A kapcsolható védelem a TV `registerScreenSaverRequest` kérésére iratkozik fel, és csak az app látható
futása alatt válaszol `ack:false` értékkel. Felfüggesztéskor leiratkozik. A cél TV introspekciója
szerint a regisztráció és válasz is nyilvános Luna-metódus, de az LG alkalmazásfejlesztői API-jában
nem dokumentált. Ha a Luna-híd nem érhető el vagy hibát ad, tartalékként a gateway
`/screen-guard.mp4` néma H.264 videóját használja.

A rács snapshot-előnézete alapból öt másodpercenként frissül; ez a TV-app és a LAN-os webfelület
beállításaiban 1–60 másodperc között módosítható. A TV-s mentés azonnal visszalép a rácsba és az új
intervallummal újraindítja az előnézeti időzítőket.
Az eltárolt kamerák sorrendje teljes, duplikációmentes kamera-ID listával módosítható; a böngészős
`lgtv-control` felületen drag-and-drop és fel/le gombok is elérhetők hozzá.

## Tárolás, migráció és távoli beállítás

A v3 konfiguráció együtt tárolja a `profiles` listát és a layout-beállításokat. A v1/v2 adatok első
induláskor migrálódnak, a korábbi streamalias-kameraazonosítók a kanonikus alap profilokba olvadnak.
V3-tól a felhasználó törlései és a korlátlan egyedi profilok változatlanul megmaradnak.

Az app a fix, validált `syncUrl` callbackre képes visszaküldeni a teljes beállítását. Ezt használja a
külön `lgtv-control` CT tokenmentes LAN-felülete kamera létrehozásra, módosításra, törlésre, layout
mentésre és megnyitásra. Látható futás közben az app 2,5 másodpercenként rövid jelenléti heartbeatet
küld ugyanennek a CT-nek; felfüggesztéskor leáll. Az app maga továbbra sem futtat listenert vagy
háttérdaemont.

## Biztonsági szabályok

- Csak kanonikus RFC1918 IPv4 host állítható be; DNS, publikus cím és `192.168.0.100` tiltott.
- A forrásalias kizárólag rövid `A-Za-z0-9._-` azonosító, és nem lehet IP-alakú.
- A hosted player path nem lehet teljes URL, query, dot-segment vagy kódolt útvonal.
- Felhasználónév, jelszó vagy aláírt kamera-URL nem kerül az appba.
- Launch paraméterből tetszőleges URL, app-ID vagy Luna URI nem indítható.

## Launch

```json
{
  "v": 1,
  "action": "open",
  "cameraId": "kapu",
  "view": "full",
  "requestId": "0123456789abcdef0123456789abcdef"
}
```

A `profileId` használható a `cameraId` helyett, de együtt nem. A `requestId` opcionális, pontosan
32 hexadecimális karakter.

## Teszt

```text
node tests/camera-viewer.test.js
node tests/webos-player.test.js
```

A tesztek ellenőrzik a popup/átlátszó manifestet, a külső megnyitás utáni közvetlen bezárást,
a korlátlan profillistát, a lapozás és kiemelés kapacitását, a migrációt,
a launch/sync/CRUD sémákat, a Chrome 79 korlátokat, a WebRTC audio transceivert, az autoplay
újrapróbálását, a signalingot, az origin/session-védelmet és a teljes cleanupot.
