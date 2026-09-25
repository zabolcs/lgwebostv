# Távirányító gombok

A `hu.szabi.remotemapper` a külön folyamatként futó, fail-open LG Remote Broker vizuális
szerkesztője. Nem injektál kódot az `lginput2`, `micomservice` vagy más rendszerfolyamatba.
A helyi `lgtv-control` CT API-ján át kezeli az atomikus gombkiosztást; a korábbi
`keybinds.json` csak visszafelé kompatibilis kötéstár, nem futtatómotor.

A TV-s frontend alapból olvasási módban indul. Egy módosításhoz előbb külön fel kell oldani a
szerkesztést, majd a konkrét mentést is meg kell erősíteni. Sikeres mentés után azonnal visszazár.
A PC-s `lgtv-control` felületen ez a plusz távirányítós védelem nem szükséges.

A távirányító minden fontos gombja megjelenik. Engedélyezett művelet az eredeti működés,
telepített alkalmazás indítása, másik ismert gomb küldése, letiltás, PiP preset, teljes képernyős
kamera, validált app-parancs és helyi Home Assistant webhook. Tetszőleges shell-parancs nem adható
meg. Az első változtatás és minden következő mentés előtt külön visszaállítási pont készül.

A fejléc külön mutatja a broker állapotát, és piros figyelmeztetést ad, ha a veszélyes régi natív
Input Hook mégis betöltve maradt. A broker telepítése és `grab` módú engedélyezése külön,
jóváhagyott bevezetési lépés; a Remote Mapper 0.2.0 önmagában nem kapcsolja be.
