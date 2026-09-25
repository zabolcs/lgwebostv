# Telepítés – 2026-08-31

## Kiadás

- Launcher: `hu.szabi.launcher` 0.1.26
- IPK SHA-256: `a6b008a7ac89fd28563334a6063e9c319da20330f622c3fbbdda7751e787cba7`
- NAS-forrás: `/media/download2/Data/System/LGTV_root/development-2026-08-31-overlay-v8/webos-control-suite-0.4.1-webhook-config`
- Telepítés előtti teljes mentés: `/media/download2/Data/System/LGTV_root/complete-state-2026-08-31-overlay-20260831-070326`

## Elkészült működés

- A meglévő launcher külön `mode=overlay` nézettel indulhat, a PIP app bevált transzparens `popup` ablakbeállítását használva.
- A quick launcher az alsó képernyőharmadot foglalja el, és a futó TV-adás vagy alkalmazás fölött jelenik meg.
- A bővíthető kategóriamodell jelenlegi elemei: Kedvencek, Appok, Inputok és Kamerák.
- A Kedvencek és Appok a meglévő launcher-adatokat és indítási útvonalat használják; az Inputok Live TV-t és az elérhető HDMI-ket adják; a Kamerák a meglévő Media Overlay preseteket indítják.
- A quick nézet teljesen távirányítózható, a fókuszt újrarenderelés nélkül mozgatja, a vízszintes sáv pedig mindig láthatóan tartja az aktív elemet.
- A kijelölés keret nélkül, középpontos nagyítással történik. Csak az aktív kategória és csempe neve látható.
- A régi webOS Chromium flex-`gap` és grid-eltéréseit explicit margókra és egyszerű oszlopos flex-igazításra cseréltük. Az élő TV-n 40 px csempeköz és középre igazított kategóriafelirat látható.
- Back, az átlátszó felső területre kattintás, illetve a már nyitott quick launcher mellett újra megnyomott rövid Home bezárja az overlayt.
- Rövid Home: quick launcher. Hosszú Home: teljes launcher. A hidegindítási és warm-relaunch webOS események 600 ms-os duplikációszűrést kapnak.
- A Home Input Hook segéd BusyBox-kompatibilis `/bin/usleep 50000` várakozást használ.

## Teljesítmény

- Overlay módban nem indul háttérkép-, időjárás- vagy kamera-preview munka, és kamera-stream sem töltődik automatikusan.
- A helyi snapshot adja az első render adatát; a NAS-szinkron csak később fut.
- A teljes launcher dekoratív munkái az interaktív első képkocka után, késleltetve indulnak.
- A quick csempe- és fókusznavigáció nem építi újra feleslegesen a DOM-ot.
- A boot cover overlay módban azonnal eltűnik, teljes módban a tartalék fade rövidebb.

## Ellenőrzés

- Python: 34/34 teszt sikeres.
- JavaScript: URL core, lifecycle contract, quick core és külön Home lifecycle teszt sikeres.
- Launcher JavaScript-fájlok szintaxisellenőrzése sikeres.
- A teljes IPK-build kétszer azonos SHA-256 eredményt adott.
- TV-n telepített launcher-verzió: 0.1.26.
- Élő Home-sorozat: rövid nyitás → rövid zárás → warm rövid újranyitás → rövid zárás sikeres.
- Élő hosszú Home-próba a teljes launchert nyitotta meg; utána a launcher bezárult, a Plex maradt az előtérben.
- CT 125 `lgtv-control.service`: aktív; API elérhető.
- CT 120 `go2rtc.service`: aktív.
- Home Input Hook-kötés: `launcherHome`.
- Google Assistant-kötés változatlan: `overlayPreset`, `gyerekszoba`. A telepítés utáni élő PiP-indítást a Plex zavartalan futása miatt nem hajtottuk végre.

## webOS hot-install megjegyzés

Ha telepítéskor a launcher már fut, a WAM a régi JavaScript-folyamatot életben tarthatja. Az IPK telepítő ezért bezárja a fejlesztői appot, és a telepítés nem indítja automatikusan újra. A következő Home-indítás már az új kódot tölti be.

## Visszaállítás

Elsődleges visszaállítási pont a fenti, hash-ellenőrzött `complete-state-*` mentés. A 2026-08-30-i NAS-forrás továbbra is a változtatások előtti hiteles telepített baseline.
