# Átadási jegyzet – webOS vezérlő Suite 0.4.1

Dátum: 2026-08-27  
Camera Viewer: 0.3.9  
Media Overlay: 0.3.6  
Remote Mapper: 0.1.3  
Launcher: 0.1.7

- Végleges, dátumozott célmappa: `/media/download2/Data/System/LGTV_root/development-2026-08-25/webos-control-suite-0.4.1-webhook-config`.
- A forrás az eredeti LGTV_root tartalom felülírása nélkül, külön fejlesztési mappában van.
- CT 120: szűk go2rtc hosted-player gateway, tetszőleges validált alias és screen-guard asset.
- CT 125: `lgtv-control`, tokenmentes LAN webfelület, TV-állapot szinkronnal.
- A Launcher minden sora elrejthető, átrendezhető és a NAS-os felületen szerkeszthető. Van kedvenc-,
  app-, webcím-, kamera-preset- és segédsor, összes app overlay, folytatás, időjárás, diagnosztika,
  háttérképváltás, fényerő és import/export.
- A TV-s Launcher távirányítóval navigálható. A kedvenc- és kameraoldal 5 teljes csempés, az appsor 7,
  a kisebb sorok 8 teljes csempések; oldalváltáskor a teljes sor igazodik, fél csempe nem marad a szélen.
  A cím csak a fókuszált csempe alatt látszik, a fókuszált elem enyhén nagyobb.
- A Launcher 0.1.7 a webOS 6 régi böngészőmotorjával kompatibilis explicit csempepozíciókat használ,
  és a hiányos utolsó oldalakat láthatatlan helykitöltőkkel egészíti ki, ezért azok is balra igazíthatók.
  A TV-n az egér-hover nem maradhat második kijelölésként aktív; a kijelölés körvonal helyett
  5/10/15/20%-os beállítható nagyítást használ, 40 px-es oldalbiztonsági hellyel és nagyobb alsó címmel.
  A kamera-csempékhez a NAS percenként kivesz egy JPEG képkockát a működő MJPEG-forrásból és
  gyorsítótárazza; a TV-n maga a launcher nem tart nyitva MJPEG-et.
  kattintásuk a Camera Viewert indítja a megfelelő kamerával. A CPU-terhelés százalékosan látszik,
  az alap háttérkép-készlet 40 elemű. Az ismert és saját appokhoz átlátszó, egységes SVG ikoncsomag
  választható az automatikus, gyári és saját URL-es mód mellett; az ikonok illesztése csempénként
  `kicsi`, `arányos` vagy `teljes kitöltés` módra állítható.
  A kamera-preview-k a launcherben és a NAS szerkesztőben kényszerített `cover` illesztéssel töltik ki
  a csempét. A TV-s bal/jobb mozgatás csak a szükséges DOM-elemeket rendezi át, így nincs teljes
  felületi villódzás, a lefelé mentés pedig a frissített sorrendet tartja meg.
  A Launcher beállításai között külön kapcsolható a TV-szerkesztő mód; bekapcsolva minden sor végén
  `+` csempe jelenik meg, és sorfüggő hozzáadási modal kezeli az új elemeket.
  A `+` csempe ugyanazt a csempe-cellát, méretet, gapet és D-pad navigációt használja, mint a sor többi eleme;
  a meglévő elemek megjelenése szerkesztőmód-kapcsoláskor változatlan marad.
- Rövid OK indítja a csempét; 700 ms-os hosszú OK a TV-n helyi szerkesztőmódot nyit két műveletikonnal.
  Bal/jobb mozgat, lefelé ment, a Vissza visszavon; a védett rendszer-csempék törlés helyett elrejthetők.
  A NAS-felület kompakt, húzható csempesorokat és külön csempeszerkesztő ablakot használ.
- Az indulás 1920×1080 fekete webOS splash képpel, majd az ikonok és a háttér betöltéséig fekete
  fedőréteggel történik. A diagnosztika folyamatlistája rendezett táblázat.
- A `Távirányító gombok` fülön keret nélküli vizuális Magic Remote-on választható ki a gomb, és a jobb oldali
  panelen tölthető be/módosítható a kötése. Ugyanez a felület a TV-n külön appként is elérhető.
  A Home gomb kiemelt, figyelmeztetett, de szerkeszthető; a védett gomboknál a módosítási űrlap rejtve marad.
- Egy gomb közvetlenül szinkronizált PiP presetet vagy kamerát is nyithat. Haladó módban telepített
  apphoz JSON launch-paraméter adható; nyers shell-parancs a tokenmentes LAN-felületen nem futtatható.
- Az élő TV-n 5 kamera és 6 PiP preset van szinkronban; a hiányzó `kapu2`, `udvar` és `udvar2`
  preset 2026-08-25-én létrejött a kameraapp előnézeti streamjeiből.
- A Remote Mapper a már telepített LG Input Hook 1.4.0 motort használja; új hookot nem injektál.
  Csak a kevésbé fontos gombok módosíthatók, a teljes régi JSON megmarad, az első és az előző állapot
  külön biztonsági mentésből állítható vissza. Tetszőleges shell-parancs nem állítható be.
- A TV-s felület írás előtt egyszeri szerkesztésfeloldást és külön megerősítést kér, majd minden mentés
  után visszazár; a PC-s helyi felület továbbra is közvetlenül szerkeszthető.
- A Camera Viewer csempéi 16:9-esek; minden csempén szemgomb kapcsolja a kiemelést. PiP gomb nincs benne.
- A Media Overlay 0.3.5 a launcher/payload/params borítékot és a `webOSLaunch` eseményt is kezeli.
  Az aktív Camera Viewert a CT 2,5 másodperces heartbeatje alapján felismeri, és ilyenkor a PiP
  megjelenítése nélkül bezár. Egy már futó vagy betöltődő PiP-et újabb `show` relaunch nem ír felül.
- A feloldott utolsó `show` tartalom és layout külön localStorage-kulcsban megmarad. Üres vagy egzakt
  `storeCaller:home` menüindítás ezt nyitja újra; explicit `action:settings` továbbra is beállítást nyit.
- Az `overlay` réteg firmware-korlátját a visszafordítható `popup` ablakréteg kerüli el; az élő
  nulla-TTL próba 5 perc 30 másodpercig látható maradt, majd távoli `dismiss` kérésre bezárult.
- A Camera Viewer 0.3.8 keskeny felső címsávot használ appikonnal, lapozóval és jobb oldali fogaskerékkel;
  a lapozó és a fogaskerék között 26 px rés marad, lebegő üzenetei öt másodperc után eltűnnek.
- A snapshot-előnézet a beállított 1–60 másodperces értéket kéréskezdetek között alkalmazza;
  a kép letöltési ideje már nem adódik hozzá még egyszer az intervallumhoz.
- A kamerák sorrendje az `lgtv-control` felület külön listájában drag-and-droppal vagy fel/le
  gombokkal módosítható; mentéskor a TV alkalmazásprofiljainak sorrendje változik meg.
- A képernyőkímélő-védelem a cél TV-n ellenőrzött két fix, public `tvpower` Luna-metódussal vétózza
  az indulási kérést; felfüggesztéskor leiratkozik, a régi videós megoldás csak fallback.
- A 0.3.9 kiadáson helyi Media Overlay- és életciklusteszt futott; post-install TV-app launch nem fut.
  A telepítési eredmény a `TEST-REPORT.md` fájlban van.
- Artifact-ellenőrzés: `sha256sum -c SHA256SUMS.txt`.
