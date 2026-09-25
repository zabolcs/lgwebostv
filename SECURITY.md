# Biztonsági modell

## Hatókör

A suite két jogosultságszegény TV web appot, közös csomagoló/telepítő scripteket és egy külön,
korlátozott go2rtc WebSocket bridge-et, valamint egy opcionális, külön `lgtv-control` CT-ben futó
böngészős vezérlőt tartalmaz. A TV-n nem hoz létre boot hookot, nem ír rootfs-, kernel- vagy
flashpartíciót, és nincs saját Luna/Node service-e. A bridge kizárólag a go2rtc LXC-ben fut systemd
service-ként, kizárólag a TV-ről érkező, validált aliasú WebRTC streamekhez.

## Hálózati célok

Mindkét alkalmazás a saját, felületéhez szűkített runtime validátorával ellenőrzi a média- és
kamera-URL-t közvetlenül a használat előtt. A `common/url-core.js` ugyanennek a szabályzatnak a
közös offline referencia- és regressziós tesztje; nem kerül az IPK-kba. A szabályzat fail-closed:

- kizárólag HTTP/HTTPS;
- kizárólag kanonikus, numerikus RFC1918 IPv4, DNS nélkül;
- `192.168.0.100` hard deny;
- userinfo és fragment tiltott;
- a tiltott cím pathban és queryértékben is tiltott;
- a runtime útvonalakban percent-kódolás tiltott, így dupla kódolás sem csempészhet be elválasztót;
- a Camera Viewer csak rövid streamaliast fogad; IP-alakú és `.100`-at tartalmazó alias tiltott;
- a WebRTC bridge csak biztonságos karakterkészletű, nem IP-alakú aliasokat enged, és nem proxyzza az admin API-t.

Ez SSRF-kockázatot csökkent, de nem tesz megbízhatóvá egy kompromittált LAN-szolgáltatást. Plain HTTP
forgalmat a helyi hálózat támadója módosíthat. HTTPS esetén a TV által elfogadott tanúsítványlánc kell.
Titok sem URL-ben, sem launch paramsban, sem localStorage-ban nem tárolható.

Az app a böngésző által követett HTTP redirectet nem tudja újra validálni. Ezért csak megbízható,
no-redirect kamera-gateway használható; a szó szerinti nulla `.100` kapcsolatot külső hálózati ACL
és TV-oldali forgalommérés tudja garantálni. A Camera Viewer normál indulása a három beépített profil
snapshot-rácsát betölti a `192.168.0.150` go2rtc szerverről; a másik két app nem autostartol.

## Launch params

A launch paraméter külső, nem megbízható adat. Mindkét appnak pontos séma- és allowlist-ellenőrzést kell
végeznie. Az overlay `v:1`, `action:show` mellett ismert `presetId`-t, plain-text tartalmat, vagy a
fenti URL-policynek megfelelő közvetlen kép-/videó-URL-t fogadhat. A sarok, méret, margó, illesztés,
`ttlMs` és opcionális `mode:fullscreen` szűk tartományban felülírható. A `configure` csak az
alaplayoutot mentheti. A `preset-save`/`preset-delete` legfeljebb 32 normalizált presetet kezelhet;
az opcionális `openCamera` művelethez rövid, validált `cameraId` kell. Az opcionális `requestId`
pontosan 32 kisbetűs hexadecimális karakter.

A vezérlési irány egyértelmű: Home Assistant indítja az overlayt. Az overlay csak felhasználói
kattintás/OK hatására indíthatja a hardcoded `hu.szabi.cameraviewer` appot a hardcoded
`action:open`, allowlistelt `cameraId`, `view:full` sémával. Launch paraméterből származó tetszőleges
app-ID, Luna URI vagy parancs indítása tilos; a média-URL kizárólag `<img>`/`<video>` forrás lehet.

Az utolsó sikeresen elfogadott PiP feloldott tartalma és layoutja külön localStorage-kulcsba kerül,
hogy az üres TV-menüs indítás visszajátszhassa. Csak a már normalizált `show` mezők tárolhatók;
`requestId`, `syncUrl`, tetszőleges app-ID és Luna URI nem. Visszaolvasáskor a teljes launch- és
URL-validáció újra lefut, sérült vagy régi bejegyzés pedig nem indul el.

A Media Overlay a `show` művelet előtt elsődlegesen a fix `lgtv-control` jelenléti végpontot kérdezi.
A Camera Viewer látható futás közben 2,5 másodpercenként csak `{\"active\":true}` heartbeatet küld;
a CT kizárólag a konfigurált TV-forráscímtől fogadja el, és nyolc másodperc után automatikusan
inaktívnak tekinti. Aktív állapotnál az overlay rejtve marad és bezár. Hálózati hiba esetén csak a
fix `com.webos.applicationManager/getForegroundAppInfo` Luna-metódust próbálja tartalékként; ennek
hibája fail-open, hogy a CT kiesése ne tiltsa le az összes Home Assistant előnézetet. Más Luna URI
vagy cél app-ID launch paraméterből továbbra sem adható meg.

A Camera Viewer képernyőkímélő-védelme kizárólag a fix
`com.webos.service.tvpower/power/registerScreenSaverRequest` és
`com.webos.service.tvpower/power/responseScreenSaverRequest` címeket hívja. A cél TV saját
introspekciója mindkettőt `public` elérésűként jelöli. A válasz csak egzakt `Active` állapotú,
legfeljebb 24 számjegyes timestampre készül, fix kliensnévvel és `ack:false` értékkel. A feliratkozás
felfüggesztéskor megszűnik, és nem módosít tartós TV-beállítást.

A `lgtv-control` HTTP-szolgáltatás tokent nem kér, ezért kizárólag megbízható LAN-on használható.
Forráscím szerint csak a konfigurált `192.168.0.0/24` és loopback hálózatot fogadja, JSON
Content-Type-ot követel. A normál böngészős API JSON-t, a kizárólag a TV IP-jéről engedett
visszaszinkronizálás és a pontos `{\"active\":true}` heartbeat text/plain törzset használ. A heartbeat
GET és POST végpontja kizárólag a konfigurált TV IP-jéről érhető el, állapota csak memóriában él és
nyolc másodperc után lejár. Ugyanazt a szűk mező- és URL-validációt a TV
előtt megismétli, majd SSH-n kizárólag a fix alkalmazáskezelő Luna URI-t és app-ID-t hívja.
A kamerasorrend mentése csak a TV-ről frissen szinkronizált kameraazonosítók pontos, duplikációmentes
permutációját fogadja el; hiányzó vagy idegen azonosító esetén nem küld launch parancsot.

## Telepítési korlátok

Az install script abszolút, szűk karakterkészletű IPK-utat és pontos SHA-256 egyezést kér, majd csak
terminális `statusValue:30` esetén sikeres. Nem launchol appot. A remove script csak a suite két fix
app-ID-jét távolíthatja el és `statusValue:31` végállapotot követel.

Az IPK-build staging területre dolgozik. Az app-forrásokat nem módosítja, apponkénti `tests/` és build
artifact nem kerül a csomagba. A kiadási fájllistát telepítés előtt ettől függetlenül auditálni kell.

## Platformkockázatok

A `transparent` appinfo tulajdonság dokumentált webOS TV API, a `defaultWindowType: popup` és a
fullscreen/HDMI fölötti rétegezés viszont commercial webOS TV-n nem nyilvános kompatibilitási
szerződés. Az előző `overlay` típust ezen a firmware-en a Surface Manager 1–2 perc után elrejtette;
a `popup` csak alkalmazásszintű, visszafordítható váltás. Firmware-változás eltérő stackinget vagy
teljes appbezárást okozhat. A biztos kilépési út a Home gomb; az appok nem fedhetik el vagy írhatják
felül ezt a rendszervezérlést.

A telepített gateway állapotát, a release hash-eket és a még nyitott élő próbákat a `TEST-REPORT.md`
rögzíti.
