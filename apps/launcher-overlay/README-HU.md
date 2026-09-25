# Teljes launcher popup host

A `hu.szabi.launcher.overlay` a teljes launcher `popup` ablaka. A futtatókód az
`apps/launcher` könyvtárból közös mindhárom launcher hosttal; itt csak a manifest található.

Elrejtéskor a közös életciklus-kezelő natív `hide`/`keepAlive` hívással próbálja megőrizni a
példányt és visszaadni a vezérlést a mögöttes appnak. Ha a webOS nem igazolja az elrejtést,
bezárási tartalékút következik. A memóriafelszabadítás miatt a megőrzés nem garantált.
Részletek: [közös launcher dokumentáció](../launcher/README-HU.md).
