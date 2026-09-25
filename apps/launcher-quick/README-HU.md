# Quick launcher host

Ez a könyvtár csak a transzparens `hu.szabi.launcher.quick` webOS-host manifestjét tartalmazza.
A futásidejű HTML, CSS és JavaScript kizárólag az `apps/launcher` könyvtárból kerül mindhárom
launcher IPK-ba, ezért a full, full-overlay és quick felület közös alkalmazáslogikát használ.

A `scripts/build-all.py` csomagoláskor hostonként előállítja a `launcher-host.js` fájlt. A közös
runtime ebből olvassa a `window.__LAUNCHER_HOST__` objektum `host` (`full`, `full-overlay` vagy `quick`) és
`appId` mezőjét. A könyvtárba ne kerüljön másolat az `apps/launcher` runtime-fájljaiból.

A natív elrejtés és a meleg újranyitás korlátait a [közös launcher dokumentációja](../launcher/README-HU.md) írja le.
