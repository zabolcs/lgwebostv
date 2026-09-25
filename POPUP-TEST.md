# Media Overlay popup élettartamteszt

Dátum: 2026-08-22

- Csomag: `hu.szabi.mediaoverlay_0.3.2_all.ipk`
- Kizárólagos változás az előző 0.3.1 futási logikájához képest: a visszafordítható,
  alkalmazásszintű `defaultWindowType` értéke `overlay` helyett `popup`.
- Cél: ellenőrizni, hogy a webOS Surface Manager által az overlay ablakra kényszerített
  körülbelül 1–2 perces láthatósági korlát elkerülhető-e rendszerfájl-módosítás nélkül.
- A csomag csak azután telepíthető a TV-re, hogy ez a mappa és a forrás a dátumozott
  NAS-célmappában létrejött, és az SHA-256 egyezett.

SHA-256: `c2709b4027ca9786316d5db02accecaef6af6e3cac404bbdf3e99db78f826bc9`

## Eredmény

- Telepítés: `statusValue: 30`, PASS.
- Indítás: `ttlMs:0`, `presetId:kapu-preview`, PASS.
- Surface Manager: `visible:true`, `_WEBOS_WINDOW_TYPE_POPUP`.
- 0/30/60/90/120/150/180/210/240/270/300/330 másodpercnél a dokumentum és a megjelenítő
  felület is látható állapotú volt.
- A 330 másodperces mérés után küldött `action:dismiss` hatására a Surface Manager
  `visible:false` állapotot jegyzett, PASS.
- TV-rendszerfájl, service vagy bootkonfiguráció nem változott.
