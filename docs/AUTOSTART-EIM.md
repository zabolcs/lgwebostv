# EIM production autostart

## Állapot – 2026-09-25

A cél LG webOS TV-n az EIM (External Input Manager / Input Apps) út bizonyítottan
korábbi production launcher-indítást ad, mint a korábbi Homebrew guard / NAS SSAP
cold-boot út.

Production app:

- app ID: `hu.szabi.launcher`
- version: `0.3.12`
- manifest: `supportGIP:true`
- EIM device: `MVPD_IP-hu.szabi.launcher`

A korábbi TV-local guard és a NAS native SSAP accelerator változatlanul megmaradt
fallbackként. Az első production EIM boot során a TV-local guard nem küldött második
launchot (`TV_GUARD_LAST_LAUNCH` üres maradt).

## Mért cold-boot eredmény

GitHub Actions run: `36168068457`.

- BootSequencer: `Try to launch first app`: **15.07 s**
- production launcher navigation: **29.712 s**
- production launcher JavaScript start: **30.100 s**
- production launcher ready marker: **30.410 s**
- foreground `hu.szabi.launcher`: **31.221 s**
- `firstapp-launched`: **31.255 s**
- root SSH visszatéréskor uptime: kb. **44.99 s**

Korábbi production cold-boot mérésben a launcher natív felülete kb. **53.6 s**
körül jelent meg, ezért az EIM út nagyságrendileg több mint 20 másodpercet nyer.

## Első production EIM backup

A production aktiválás előtti állapot:

```text
/media/lgtv/eim-autostart-backup-20260925-36168068457
```

A könyvtár tartalmazza az EIM mentést, az eredeti `lastinput` állapotot és a
production launcher aktiválás előtti csomagfájljait. A globális, Activity Manager
előtti rollback baseline továbbra is:

```text
/media/lgtv/rollback-20260925-pre-activity-manager
```

## Bootloop-védelem

A launcher maga nem rebootol és nem ír bootloader/gyári `/usr` fájlokat. Az EIM
csak a webOS saját first-app útján indítja az alkalmazást. Az integrációs workflow-k
manual-only állapotban maradnak.

Hiba esetén az EIM device törölhető, az eredeti input (a méréskor HDMI2) visszaállítható,
és a korábbi guard/SSAP út változatlanul használható.

## Végleges startup-architektúra

A last-input problémát production EIM overlay oldja meg.

- A valódi, persistent boot-EIM `/var/lib/eim` alatt a launcher marad a last input.
- Boot után a Homebrew startup hook egy külön runtime EIM másolatot bind-mountol a
  `/var/lib/eim` helyére.
- A runtime EIM normál használat közben szabadon követheti a HDMI1/HDMI2 inputot.
- A befagyasztott boot-EIM ettől nem változik, ezért a következő teljes boot ismét
  a launchert választja first appként.
- A hook bootloop-védett: persistent `boot-pending` markerrel indul, és csak stabil
  mount után ír `last-good` állapotot. Ha az előző boot nem jut el a megerősítésig,
  a következő booton az overlay saját magát letiltja, és fail-open módon a normál EIM
  marad látható.
- A TV-local guard és a NAS SSAP launcher továbbra is fallback.

### Végleges cold-boot ellenőrzés

GitHub Actions run: `36175082037`.

- reboot uptime-reset: PASS
- `firstAppId = hu.szabi.launcher`
- launcher first appként indul
- runtime overlay felmountolódik
- frozen boot-EIM: `hu.szabi.launcher`
- runtime EIM: HDMI2
- HDMI2 használat nem írja felül a frozen boot-EIM-et
- launcher visszaindítása nem clobbereli a runtime HDMI állapotot
- 45 s stabilitás után `last-good` létrejön és `boot-pending` eltűnik
- `EIM_OVERLAY_COLD_BOOT=PASS`

A tesztben látható launcher → HDMI2 → launcher váltás szándékos volt: a cold-test
direkt elindította a HDMI2-t, majd a launchert, hogy bizonyítsa az overlay izolációját.
Normál bootban ez a tesztlépés nincs jelen.

### Quick Start ellenőrzés

GitHub Actions run: `36175896582`.

- standby állapot elérve: PASS
- wake után a launcher foreground: **14.863 s**
- uptime nem resetelt
- boot ID változatlan maradt
- runtime EIM overlay mount megmaradt
- frozen boot-EIM továbbra is `hu.szabi.launcher`
- runtime EIM továbbra is HDMI2
- a TV-local guard logja igazolja a wake launchot:
  `source=default-home-guard`
- `QUICK_START_LAUNCHER_WAKE=PASS`

Ez alapján a launcher mindkét támogatott startup-ágon rendelkezik működő úttal:

```text
cold boot / reboot / áramtalanítás után
    -> persistent EIM first-app
    -> hu.szabi.launcher
    -> runtime EIM overlay

Quick Start / standby wake
    -> TV-local guard
    -> NAS SSAP fallback
    -> hu.szabi.launcher
```

A power-cycle és overlay-install workflow-k push eseményen job-szinten le vannak
tiltva; csak explicit `workflow_dispatch` indíthatja a TV-t érintő műveletet.


### Quick Start fast lane

A TV-local guard v0.3.9 egy külön, egyszeri Quick Start fast lane-t használ.
Csak akkor aktiválódik, ha a TV már futó sessionből tényleges natív
`Active Standby` állapotba ment, majd visszatér `Active` állapotba. Cold boot,
egyszerű `unknown` power-state ingadozás és screensaver kilépés nem armolja.

A fast lane feltételei:

- egészséges, `last-good` EIM overlay;
- nincs `boot-pending` vagy failsafe tiltás;
- friss `Active` power-state közvetlenül a launch előtt;
- wake-enként legfeljebb egy fast-lane dispatch.

Sikertelen vagy túl korai fast dispatch esetén a korábbi konzervatív TV-local guard
és a NAS SSAP fallback változatlanul tovább működik.

Mérés: GitHub Actions run `36179577293`.

- korábbi Quick Start foreground: **14.863 s**
- fast lane foreground: **11.975 s**
- javulás: kb. **2.9 s**
- `quick fast lane dispatch`: PASS
- `quick fast lane accepted`: PASS
- uptime continuity: PASS
- EIM overlay persisted: PASS

A teszt szándékosan HDMI2-ről indult. A webOS a wake során visszaállította a HDMI2-t,
majd kb. 1 másodperccel később a fast lane már elküldte a launcher launchot. A
launcher tényleges surface-e csak később vált láthatóvá; innentől a fő késleltetés
már nem a power-state guard, hanem a full webapp/WAM surface aktiválási ideje.
