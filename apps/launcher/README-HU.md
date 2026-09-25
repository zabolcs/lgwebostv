# LG Launcher 0.3.6

A launcher egyetlen közös runtime-ból három webOS hostként készül el. A `hu.szabi.launcher` normál,
nem átlátszó `card` ablakban adja a teljes felületet, a `hu.szabi.launcher.overlay` pedig `popup`
ablakban jeleníti meg ugyanezt. A `hu.szabi.launcher.quick` a gyorsmenü `popup` hostja.
A quick és overlay könyvtárban csak külön manifest van; a build ugyanebből a könyvtárból
csomagolja mindhárom host teljes runtime-ját.

A popup elrejtéskor natív `hide` és `keepAlive` hívással adja vissza a vezérlést a mögöttes appnak;
ha az elrejtést a webOS nem igazolja vissza, bezárási tartalékút következik. A normál teljes hostot
a saját háttérbe kerülési útvonala nem zárja be. A webOS azonban bármelyik háttérpéldányt
felszabadíthatja, ezért a meleg nyitás és a Quick Start utáni megőrzés nem garantálható.

A rövid/hosszú Home teljes vagy gyors launcherhez rendelése külön beállítás a teljes launcher
`card`/`popup` módjától. Az animációk és a látványeffektek külön kapcsolhatók; a teljes háttérkép
és a csempefelirat átlátszó háttere ettől független marad.

A kapcsolódó guard és az `lginput2` folyamatra szűkített Home-javító verziója 0.3.7, az IPK-ké 0.3.6.
A figyelő alapból nincs engedélyezve; az eredeti, más LG folyamatokat is módosító Input Hook
indítóját nem kell és nem szabad visszakapcsolni hozzá. Az indítási időkorlátok és az üzemeltetés
részletei a [vezérlő dokumentációjában](../../remote-control/README-HU.md) találhatók.

A csomagolás hostonként generált `launcher-host.js` fájlja a közös kódnak a
`window.__LAUNCHER_HOST__` objektumban adja át a `host` és `appId` értéket. Ez elsődlegesebb a launch
paraméternél, ezért egy hibás vagy hiányzó paraméter nem tudja a normál hostot transzparens popupként
vagy a quick hostot teljes alkalmazásként kezelni.

Helyi webOS kezdőfelület az `lgtv-control` CT-n tárolt konfigurációhoz. Öt szabadon rendezhető és
elrejthető sort kezel: kedvencek, alkalmazások, webcímek, kamera-presetek és eszközök. A csempék
szintén rendezhetők, elrejthetők, létrehozhatók és törölhetők a NAS-os élő előnézetben.

A felső sávban dátum/idő, opcionális napi időjárás, Folytatás és diagnosztika található. Az
ikonvezérlők kijelölése körvonal nélkül, 20%-os nagyítással látszik.
Összes alkalmazás csempe a TV látható alkalmazásait ABC-rendű, kereshető, tördelődő rácsban mutatja.
A kamera-előnézetekhez a NAS a működő MJPEG-forrásból egyetlen JPEG képkockát vesz ki és 58
másodpercig gyorsítótárazza; a launcher maga nem tart nyitva MJPEG streamet. Kamera-csempére kattintva a Camera Viewer nyílik meg az adott kamerával,
és csak ekkor indul lejátszás. Az előnézeti sor kikapcsolható. A 40 képes alap háttérkép-lista
1–10 percenként váltható, sötétíthető; a teljes konfiguráció JSON-ként exportálható és importálható.

Az app nem tartalmaz fix NAS-címet. Első indításkor vagy `controlOrigin` launch paraméterből kapja
meg az `lgtv-control` originjét, később ezt helyben megjegyzi és a Kapcsolat ablakban módosítható.

A 0.1.10 Chrome 79-kompatibilis margókkal tartja szét a csempéket és saját térbeli D-pad navigációt
ad. A kijelölés körvonal helyett 5/10/15/20%-os, beállítható nagyítást használ; a szélső biztonsági
margó 20%-os nagyításnál is megőrzi az első csempét. A kijelölt elem neve nagyobb betűvel, a csempe
alatt jelenik meg. Hosszú OK szerkesztőmódba lép: a csempe fölött szerkesztés és törlés/elrejtés
ikon jelenik meg, balra–jobbra mozgatható, lefelé menthető, Vissza gombbal visszavonható.
A 18 elemes beépített, átlátszó SVG ikoncsomag ismert szolgáltatásokat – köztük a Moonlightot és a HDMI-bemenetet –
és a négy saját webOS appot ismeri;
automatikusan használható, de a gyári alkalmazásikon és a saját URL külön is választható.
A NAS-os szerkesztő ugyanezt kompakt, húzható csempesorokkal és külön szerkesztőablakkal adja.
A diagnosztika pillanatnyi CPU-terhelést százalékban, mellette load average értékeket és rendezett
folyamattáblázatot mutat. A webOS splash és a tartalom betöltés alatti fedőréteg egyaránt fekete.
