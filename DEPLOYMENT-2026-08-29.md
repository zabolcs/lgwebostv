# Átadási jegyzet – 2026-08-29

Ez a mappa a 2026-08-29-i, TV-re telepített kiadás forrásmentése.

## TV-re telepített csomagok

- `hu.szabi.launcher` 0.1.14 — `ee819f5410d51f16cae83cb5d7faf23fdb6e33c558d3435f75c673595898ce4d`
- `hu.szabi.cameraviewer` 0.3.10 — `e7037722a77dccf1cc3a882b7878e41f15fc9ea678b763f994a90588e5eca9ff`
- `hu.szabi.remotemapper` 0.1.4 — `2f2109d40fadaf0b348e897965bb5a21adf3699987d6fb715233b28749264925`

A telepítés ellenőrzött `statusValue 30` állapotig futott; egyik appot sem indítottam el a TV-n.

## Fő változások

- A launcher fallback ikonja/kezdőbetűje induláskor rejtett, és csak 1,8 másodperc sikertelen ikonbetöltés után jelenik meg.
- A launcher fekete induló takarása alapból legfeljebb 2 másodperc; ez kikapcsolható, illetve 1–10 másodpercre állítható. Az animációk külön kikapcsolhatók.
- A „Folytatás” ikon valódi, beágyazott SVG; a launcher meleg újraaktiválást használ, ha a webOS háttérben életben tartotta.
- A TV-s appkatalógus tartós gyorsítótárat kapott, így a launcher indulása nem vár minden alkalommal TV-s SSH-listázásra.
- Az Input Hookhöz alacsony terhelésű, visszafordítható watchdog került a Homebrew init rendszerébe.
- A Home-őr új verziója nem írja felül az utolsó appot a launcher saját előtérbe kerülésekor, és a bekapcsoláskori utolsó-app folytatást kezeli.
- A Camera Viewer és Remote Mapper fekete, 1920×1080-as splash képet kapott. A Media Overlay átlátszó PiP app maradt splash nélkül, hogy induláskor ne takarja ki a műsort.
- A launcher csempeszerkesztője sikeres mentés után teljesen kilép szerkesztőmódból: eltűnik a szerkesztés/törlés eszköztár és a csempe szerkesztési jelölése.
- A launcher a NAS nélkül is el tud indulni a TV-n tárolt konfigurációból; a NAS a kényelmes beállítást és háttérszinkront adja.
- A TV/HDMI bemenet többé nem kerül az „utolsó alkalmazás” helyére, ezért a gyorsindítás nem ragad az élő TV bemeneten a launcher helyett.
- A teljesen fekete rendszer-splash helyett visszafogott launcher betöltőképernyő látszik; a HTML-takarásnak külön, legfeljebb 1–10 másodperces hibabiztos időzítője is van.
- A `0,0` időjárási koordinátát bekapcsolt időjárás mellett a rendszer elutasítja. Kótaj koordinátája `48.05, 21.7167` értékre javítva.
- A „Folytatás” állapot a TV guard által utoljára előtérben használt valódi alkalmazásból is frissíthető; az élő TV/HDMI továbbra sem kerülhet bele.
- A wallpaper betöltés TV-n először a NAS-közvetítőt, majd közvetlen URL-t próbál, így a webOS külső URL-kezelési hibái nem hagynak üres hátteret.
- Az indulóképernyőn csak az ikon és a „Betöltés…” felirat maradt.

## Ellenőrzés

- Helyi Python tesztek: 33/33 PASS.
- Helyi Node életciklus- és kamera tesztek: PASS.
- Helyi 1920×1080 vizuális ellenőrzés: fallback késleltetés, 2 mp-es takarási korlát, Folytatás SVG és beállítások.
- A dátumozott mentés helye: `/media/download2/Data/System/LGTV_root/development-2026-08-29/webos-control-suite-0.4.1-webhook-config`.
