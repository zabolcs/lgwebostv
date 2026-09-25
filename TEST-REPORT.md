# webOS vezérlő Suite 0.4.1 kiadási jelentés

Dátum: 2026-08-27  
Cél TV: LG 65UP78003LB, webOS 6.5, `192.168.0.240`  
go2rtc: CT 120, `192.168.0.150`  
lgtv-control: CT 125, `192.168.0.223:8765`

## Kiadási artifactok

| App | Méret | SHA-256 |
|---|---:|---|
| `hu.szabi.cameraviewer_0.3.9_all.ipk` | 29 860 B | `92052778086e38356fd74d09882ff0ecd208bf6e0d460086b4365d9c8518d5b4` |
| `hu.szabi.launcher_0.1.7_all.ipk` | 20 784 B | `c44256521d553d9708939c883e02f556e3f8967901319b74e294f098af96c962` |
| `hu.szabi.mediaoverlay_0.3.6_all.ipk` | 23 614 B | `72441a848714416f51b10ea6f494a90f213f67f31bf301277152a0d89ee4c319` |
| `hu.szabi.remotemapper_0.1.3_all.ipk` | 20 168 B | `10a18c7893e41f4c9223b28647a98fa393bc18d1d4705f21b12f69303963d05d` |

Az outer IPK-sorrend mind a négy csomagnál `debian-binary`, `control.tar.gz`, `data.tar.gz`. A control,
appinfo és generált packageinfo app-ID-ja és a csomag saját verziója egyezik. Az explicit runtime allowlist
miatt teszt, dokumentáció, SVG-forrás, kulcs és service nem kerül a TV-csomagokba.

## A 0.4.1 végső ellenőrzése és telepítése

- Minden runtime JavaScript szintaxisellenőrzése: PASS.
- URL-policy, app-életciklus, Media Overlay, Camera Viewer és hosted player tesztek: PASS.
- `lgtv-control` validáció/API/state/UI tesztek: 29/29 PASS.
- Launcher D-pad navigáció, sorváltáskor mindig az új sor első csempéjének fókuszálása,
  soronkénti egész oldalas vízszintes görgetés, rejtett alapértelmezett címke és ötös
  kedvenc-/kamerasor statikus regressziós kapuja: PASS.
- A kedvencek és kamerák egy oldalon pontosan 5, az appok 7, a kisebb link-/segédsorok 8 teljes
  csempét mutatnak. A fókusz körvonal nélkül, választható 5/10/15/20%-os nagyítással jelenik meg;
  22 px-es egységes oldaltér védi a legelső elemet, a nagyobb címke a csempe alatt marad.
  A böngésző natív vízszintes scroll-snapje tiltott; a teljes lapozást a D-pad navigáció kezeli,
  ezért túlcsorduló sorban sem vágódik le az első kijelölt csempe és nem marad fél csempe a szélen.
- A CT 125 `lgtv-control` frissült, service `active`, `/api/health` PASS.
- Launcher 0.1.7: a webOS 6 Chromium motorjával inkompatibilis `inset` rövidítés helyett explicit
  oldalpozíciókat használ, a hiányos utolsó oldalakat láthatatlan csempékkel egészíti ki, TV módban
  csak a valódi fókuszt jelöli. Rövid OK indít, 700 ms-os hosszú OK a csempeszerkesztőt nyitja;
  csempénként `small`/`contain`/`cover`, saját kép-URL és `#RRGGBB` háttérszín állítható.
  Kamera-csempénként legfeljebb percenként egy, az MJPEG-ből NAS-on kivett és gyorsítótárazott JPEG
  töltődik be; közvetlen MJPEG nincs a launcher DOM-jában. Mind az öt élő forrás teljes JPEG-et adott,
  a gyorsítótárazott kérés 6 ms volt. A csempe az adott kamerát nyitja meg a Camera Viewerben.
  A kamera-preview csempe képe kényszerített `cover` illesztést kapott, ezért a teljes csempét kitölti;
  a NAS-os szerkesztő bélyegképe ugyanezt az illesztést használja. A TV-s átrendezés mozgatáskor
  csak az érintett DOM-elemeket rendezi át, mentéskor nem építi újra a teljes felületet.
  A TV-szerkesztő mód külön kapcsolható; bekapcsolásakor minden látható sor végén `+` csempe nyitja
  a sorhoz illő app-, webcím-, kamera-preset- vagy segédcsempe-hozzáadó modalt.
  A diagnosztika százalékos CPU-terhelést, load average értékeket és folyamattáblát mutat; az alaplista 40 háttérkép.
  A csempeszerkesztő automatikus/gyári/saját URL mód mellett 18 beépített, átlátszó SVG ikont kínál,
  köztük külön Moonlight- és HDMI-ikonnal. Az Eszközök sor automatikusan felveszi az Élő TV-t és
  a TV-n valóban létező HDMI-bemeneteket; ezen a készüléken ez a HDMI 1 és HDMI 2.
- A telepített appinfo és az élő vizuális ellenőrzés eredménye az alábbi telepítési bekezdésben található.
- Az Input Hook aktív konfigurációja változatlan,
  SHA-256: `4f6e2851198f5628a092579604b84659ff6872ef7dfeb8306ad49665179d9977`.

## Launcher 0.1.6 élő telepítés és vizuális próba

- A CT 125 frissítése után a service `active`, `/api/health` PASS; a launcher state 18 beépített
  ikont, 40 háttérképet és csak a TV által ténylegesen jelentett HDMI 1/HDMI 2 bemenetet adta vissza.
- Mind a 40 alap háttérkép URL-je a NAS-ról párhuzamos HEAD-próbán HTTP 200 választ adott.
- A `gyerekszoba` statikus előnézet első lekérése 134 310 bájtos JPEG volt; az azonos, CT-n
  gyorsítótárazott második kérés 28 ms alatt ugyanazt a SHA-256 tartalmat adta. MJPEG URL nem kerül
  a launcher state-be vagy a DOM-ba.
- A Launcher 0.1.6 TV-telepítése `statusValue:30`; appinfo ID/verzió visszaolvasva. Az Input Hook
  aktív konfigurációjának SHA-256 értéke a telepítés előtt és után változatlan.
- Élő 1920×1080 VNC-képen a háttérváltás, az ötös kedvencszélesség, a hételemű appsor, az ikonok
  nagyobb egységes megjelenése és az alsó Élő TV/HDMI csempék PASS. A bal szélső 10%-kal nagyított
  csempe és lekerekített sarkai nem lógnak ki; nincs fókuszkörvonal, a nagyobb cím a csempe alatt marad.
- Egérmutató + D-pad, balra/jobbra/le lépegetés és a jobb szélső csempe próbáján egyszerre egyetlen
  csempe maradt nagyítva, a fókusz követte a lépéseket, fél csempe nem maradt a képernyőszélen.
- Hosszú OK-ra a TV-s csempeszerkesztő átfedés nélkül megnyílt. Az összes app rácsban a külön
  Moonlight hold+gamepad ikon megjelent; a diagnosztikai overlay a CPU-terhelést százalékban írta ki.
- HDMI 1 indítása vizuálisan a HDMI 1 bemenetre váltott. A próba után az eredeti `Folytatás: YouTube`
  állapot visszaállt, és a launcher nyitva maradt.

## Korábbi 0.4.0 ellenőrzési állapot

- Remote Mapper JavaScript szintaxis: PASS.
- `lgtv-control` Python fordítás és validáció/API/state/UI tesztek: 23/23 PASS.
- Remote Mapper 0.1.2: szinkronizált PiP preset és kamera közvetlen gombkötése, valamint
  telepített apphoz validált JSON-paraméteres indítás: unit és böngészős folyamat PASS.
- A webes távirányító külön vizuális panelkerete megszűnt; a hosszúkás Magic Remote forma,
  görgős OK gomb és az átrendezett gombcsoportok böngészős képernyőképen ellenőrizve: PASS.
- Nyers shell-parancs továbbra sem adható meg; a haladó művelet csak telepített app fix
  `applicationManager/launch` hívását állítja elő, shell-escape-pel és 4096 bájtos JSON-limittel.
- Camera Viewer 0.3.8: a preview intervallum kéréskezdetek között értendő, így a snapshot
  letöltési ideje nem adódik hozzá még egyszer. A 2 másodperces és lassú válaszos eset unit PASS.
- A meglévő, nem támogatott Input Hook-bejegyzések változatlan megőrzése: unit PASS.
- Fontos gombok módosításának elutasítása és tetszőleges `exec` tiltása: unit PASS.
- Nem telepített app-ID kötésének elutasítása: unit PASS.
- Vizuális böngészőpróba: kattintható távirányító, aktuális Netflix-kötés automatikus betöltése,
  Home gomb zárolása, piros gomb → Media Overlay szerkesztési/mentési folyamat: PASS.
- A TV-s frontend minden írás előtt egyszeri szerkesztésfeloldást és külön mentési megerősítést kér,
  sikeres mentés után automatikusan visszazár. Ez megakadályozza, hogy egy véletlen távirányító-fókusz/
  OK esemény önmagában kötést írjon.
- A TV-app telepítése és a CT-frissítés után az Input Hook aktív konfigurációja külön ellenőrzendő;
  a Remote Mapper telepítője nem cseréli és nem indítja újra az injektált hook motort.

## Remote Mapper élő telepítés

- 2026-08-25: CT 125 frissítve a paraméterezett kötéseket támogató szerverrel és a keret nélküli
  Magic Remote webfelülettel; service `active`, `/api/health` PASS.
- Remote Mapper 0.1.2 és Camera Viewer 0.3.8 telepítve; a telepített appinfo-verziók visszaolvasva.
  A telepítés során egyik TV-app sem lett kézzel elindítva.
- Az élő PC-felületen a Magic Remote, Input Hook 1.4.0, PiP preset és konkrét kamera műveletek
  betöltése böngészőből PASS. Írásos próba csak helyi mockon történt.
- A felhasználó közben létrehozott paraméterezett gombkötései megmaradtak; a telepítő nem állította
  vissza a konfigurációt. A `kapu2`, `udvar` és `udvar2` PiP preset létrejött, így 6 preset és 5 kamera
  választható közvetlen gombkötéshez.
- Az élő Camera Viewer szinkronállapotban `previewIntervalSeconds: 2`; a 0.3.8 javítás ezt
  kéréskezdetek közötti időként alkalmazza.

- CT 125 frissítés: `lgtv-control.service` aktív, új folyamat indult; `/api/health` PASS.
- Élő Input Hook state: 38 ismert vizuális gomb, 128 telepített app, a hat eredeti kötés pontosan
  visszaolvasva; a Remote Mapper app a telepített alkalmazáslistában megtalálható.
- Telepített PC-felület: 38 gomb, 6 aktív kötés, Netflix → `cdp-30`; konzolhiba nélkül PASS.
- Remote Mapper 0.1.0 telepítés: `statusValue:30`, kézi appindítás nem történt. A TV felől ezután
  váratlan fókusz/OK események több írási kérést okoztak. Az aktív Input Hook konfigurációt azonnal
  visszaállítottuk a telepítés előtt készített, egyező SHA-256-os eredeti mentésből.
- Korrekció: a 0.1.1 TV-frontend alapból csak olvas; minden egyes írás előtt külön szerkesztésfeloldás
  és mentési megerősítés szükséges, majd automatikusan visszazár.
- Remote Mapper 0.1.1 telepítés: `statusValue:30`; az appot a telepítő nem indította el. Nyolc másodperces
  utóellenőrzésben nem érkezett új bind POST. Az aktív `keybinds.json` SHA-256 értéke változatlanul
  `409fae674e373e3e74c2c78232a5be43c04be2b1496bf113b382a8cee2c362ed`.
- Telepített appinfo: `hu.szabi.remotemapper` 0.1.1. Az alacsony szintű
  `org.webosbrew.inputhook` továbbra is 1.4.0; nem lett lecserélve vagy újrainjektálva.

A 0.3.9 kiadáson a Media Overlay szintaxisellenőrzése, saját unit tesztje és a közös app-életciklus
tesztje PASS. Az életciklusteszt ellenőrzi az utolsó feloldott PiP mentését és üres/
`storeCaller:home` indításból történő visszajátszását, a `requestId` kihagyását, az explicit Settings
útvonalat, valamint azt, hogy az aktív PiP-et üres relaunch sem írja felül. TV-s appindítás, vizuális
próba vagy PiP-indítás nem futott.

- Camera Viewer 0.3.7 telepítés: `statusValue:30`; a telepítő nem indította el az appot.
- Media Overlay 0.3.5 telepítés: `statusValue:30`; a telepítő nem indította el az appot.
- Az `lgtv-control` szerver- és HTML-fájljai CT 125-re másolva, a service újraindítva; működési
  ellenőrzés a felhasználó kérésére nem futott.

## Korábbi, 0.3.5 kiadási automatikus kapuk

- minden runtime JavaScript `node --check`: PASS;
- URL-policy, Media Overlay, Camera Viewer, hosted player és életciklus tesztek: PASS;
- remote-control validáció/state/UI tesztek: 16/16 PASS;
- gateway proxy-policy teszt: PASS;
- böngészős inline JavaScript fordíthatóság: PASS;
- korlátlan kameralista, 2×2/3×3/4×4 lapozás és 2×2 kiemelt kamera: PASS;
- minden előnézet szemgombja, kiemelés mentése/törlése és a számított 16:9 csempegeometria: PASS;
- Camera Viewer PiP gomb és a hozzá tartozó overlay-indítás eltávolítása: PASS;
- kamera/preset CRUD és TV→CT konfiguráció-visszaszinkron: unit PASS;
- kamerasorrend teljes permutáció-ellenőrzése az appban és a CT API-ban, duplikált/hiányzó/idegen
  kameraazonosító elutasítása: unit PASS;
- böngészős kamerasorrend drag-and-drop és fel/le gombos kezelése, mentési útvonal: statikus/UI kapu PASS;
- WebRTC audio transceiver, autoplay némított újrapróbálás és cleanup: unit PASS;
- gateway tetszőleges biztonságos alias, IP-alakú alias tiltás, screen-guard asset: unit PASS.
- `ttlMs:0` késői MJPEG-hibája nem zár, egyetlen 1,5 másodperces reconnectet indít, siker után takarít: PASS;
- kizárólagos `storeCaller:home` launch-metaadat normál indítás, más érték/plusz mező továbbra is tiltott: PASS;
- teljes magasságú kamerarács, abszolút lebegő beállításgomb és üres üzenetsáv elrejtése: statikus kapu PASS.
- jobb alsó beállításgomb 72 px-es jobb és 30 px-es alsó margóval: statikus kapu PASS;
- screensaver-válasz csak `returnValue:true`, egzakt `Active` és numerikus timestamp esetén,
  fix `ack:false` payload: unit PASS;
- a cél TV `tvpower` introspekciójában a regisztrációs és válaszmetódus egyaránt megtalálható és
  `public`: PASS; a 0.3.4 app futás közbeni screensaver-próbája a felhasználó filmnézése miatt elhalasztva.

## Élő diagnózis a javítás előtt

A TV WebAppMgr debug sessionben a hosted player betöltése, a WebSocket 101 handshake, a WebRTC
offer/answer és ICE candidate folyamat sikerült. Ezután a régi player `autoplay` hibát küldött és
az app MJPEG-re váltott. A 0.3.0 ezért az első `play()` elutasításkor némítva újrapróbál, és csak
valódi signaling/dekóderhibára vagy timeout után használ fallbacket.

A Media Overlay 0.3.0 élő `ttlMs:0` indításában a nulla érték bizonyítottan eljutott a TV-apphoz és
az overlay túlélte a mentett 15 másodperces alapértéket, majd az 1–2 perces tartományban eltűnt. A
kódban a késői MJPEG `error` minden TTL-nél feltétel nélkül tíz másodperces hibabezárást indított.
A 0.3.1 ezt reconnectre cserélte, és a nulla TTL hibaképernyőn is kézi bezárás maradt. A futó
`window.close()` teljes semlegesítése és a periodikus `webOSSystem.activate()` sem akadályozta meg
az eltűnést: a Surface Manager az app kérése nélkül állította az overlay ablakot `visible:false`
állapotba. A 0.3.2 ezért kizárólag az alkalmazás metaadatában `popup` ablakrétegre vált.

A Camera Viewer élő normál Home-indítása `{"storeCaller":"home"}` launch-metaadatot kapott. A 0.3.1
ezt ismeretlen műveletnek jelezte a rács fölötti sárga sávban; a 0.3.2 csak ezt az egzakt, egymezős
launcher-borítékot kezeli normál rácsindításként.

## Telepítési és élő kapuk

- CT 120 go2rtc hosted-player gateway: `active`, `/healthz` PASS;
- CT 125 `lgtv-control`: `active`, tokenmentes LAN-felület és TV-szinkron PASS;
- Media Overlay 0.3.2: telepítés `statusValue:30`; nulla-TTL `popup` látható 330 másodpercig, majd
  `action:dismiss` hatására `visible:false`, PASS;
- Camera Viewer 0.3.2: korábbi telepítés `statusValue:30`; Home-launch és teljes magasságú rács geometria PASS;
- Camera Viewer 0.3.4: telepítés `statusValue:30`; a telepített `appinfo.json` verziója SSH-n
  visszaolvasva `0.3.4`. Post-install launch kifejezetten tiltva volt a filmnézés idejére, az app
  nem indult el, ezért a jobb alsó gomb és a screensaver-vétó élő próbája függőben;
- élő rács: 24/18 px kezdőpont, 1872×1038 px hasznos terület; a kiemelt csempe 1224×689 px, a
  normál csempék 604×340 px méretűek, mind 16:9-esek; minden csempén szemgomb, nulla PiP-gomb;
- élő kiemelés: a Gyerekszoba 2×2 cellát foglal, a kijelölés/áthúzott állapot/mentés/szinkron PASS;
- élő teljes nézet: Kapu WebRTC iframe aktív, MJPEG fallback nem indult; a TV némított autoplay után
  a Hang gombbal `Hang kikapcsolása` állapotig visszakapcsolható;
- TV→CT kamera-szinkron: öt profil, layout 3×3, kiemelt kamera `gyerekszoba`,
  képernyőkímélő-védelem bekapcsolva;
- böngészős preset- és kameralista betöltése, CRUD, layoutmentés és a gomb/input térköz vizuális
  ellenőrzése: PASS.

## Platformkorlát

A Media Overlay vizuálisan a TV-tartalom felett maradhat, de a webOS alkalmazás teljes képernyős
inputfelülete miatt nem valódi, kattintást átengedő rendszer-PiP. A Camera Viewer PiP-gombjai ezért
a 0.3.1 Camera Viewer kiadásból kikerültek. A 0.3.2 Media Overlay `popup` rétege az idő előtti
elrejtést megoldja, az input-átengedési platformkorlátot nem; dokumentálatlan rendszerfájl-módosítás
nem készült.
