# go2rtc TV-player híd

Ez a külön, korlátozott szolgáltatás oldja meg, hogy a webOS csomagolt
Camera Viewer appja ugyanarról az originről tölthesse be a mini lejátszót és
nyithassa meg a go2rtc WebSocket fogyasztói végpontját.

- Cím: `http://192.168.0.150:1985/webos-player.html`
- Engedélyezett kliens: kizárólag a TV (`192.168.0.240`) és localhost.
- Proxyzott go2rtc út: kizárólag `GET /api/ws?src=<engedélyezett-kamera-alias>`.
- Bármely 1–64 karakteres, biztonságos `A-Za-z0-9._-` go2rtc alias használható, így új kamera
  hozzáadásakor nem kell a gateway service-t átírni; IP-alakú `src` értéket elutasít.
- A `/screen-guard.mp4` apró, néma H.264 videó a kapcsolható képernyőkímélő-védelemhez.
- Nincs konfigurációs, adminisztrációs vagy stream-létrehozó API.
- A go2rtc `api.origin: "*"` beállítására nincs szükség.
- A `192.168.0.100` gépet nem használja és nem éri el.

A Proxmox hoston, a teljes `webos-pip-suite` forrásfából futtatandó telepítés:

```sh
sh gateway/go2rtc-tv-player/install-on-proxmox.sh 120
```

A telepítő ellenőrzi a forrás- és célfájlok SHA-256 értékét, Python
szintaxispróbát futtat, majd tranzakciósan cseréli a szolgáltatást. Az új
verzió csak a `/healthz` próba és az aktív systemd állapot után lesz végleges;
hiba esetén a korábbi fájlok és szolgáltatás-állapot visszaáll.

## Telepített állapot és ellenőrzés

A 2026-08-14-i kontrollált telepítés eredménye:

- LXC: CT 120, `192.168.0.150`;
- runtime: `/opt/go2rtc-tv-player`;
- systemd unit: `/etc/systemd/system/go2rtc-tv-player.service`;
- installer: PASS;
- service enabled/active: PASS;
- TV-ről `GET http://192.168.0.150:1985/healthz`: `ok` – PASS;
- tartós, képernyős WebRTC-próba: a kiadási tesztjelentés szerint.

Ellenőrzés a Proxmox hoston:

```sh
pct exec 120 -- systemctl is-enabled go2rtc-tv-player.service
pct exec 120 -- systemctl is-active go2rtc-tv-player.service
pct exec 120 -- python3 -c "import urllib.request; print(urllib.request.urlopen('http://192.168.0.150:1985/healthz', timeout=2).read().decode())"
```
