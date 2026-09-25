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

## Fontos nyitott kérdés: last input tartóssága

Az EIM a TV last-input állapotát használja. A sikeres production mérésben reboot előtt
a launcher volt a kiválasztott EIM input, ezért bootkor elindult. Ha a felhasználó
később más EIM inputra – például HDMI-re – vált, a `/var/lib/eim/lastinput` ismét
arra az inputra mutathat.

A régi `webosbrew-autostart` ezt külön bind-mount/alternatív EIM tárral védte ki.
Ezt a production launcherhez még nem vezettük be. Mielőtt a régi fallback startup
út eltávolítható lenne, külön tesztelni kell:

1. normál webOS app indítása után megmarad-e a launcher last inputként;
2. HDMI-re váltás után mi lesz a last input;
3. Quick Start suspend/resume esetén lefut-e az EIM first-app út;
4. szükséges-e izolált EIM overlay vagy más, kevésbé invazív re-arm mechanizmus.

A fallbackeket addig nem szabad eltávolítani.
