# Launcher webhook használata

A SzabiLauncher 0.3.29-től a **Web** sor csempéi kétféleképpen működhetnek:

- **Weboldal**: a csempe megnyitja a megadott URL-t a webOS böngészőben.
- **Webhook**: a launcher a háttérben HTTP-kérést küld a megadott URL-re, és nem nyit böngészőt.

A webhookot maga a TV-s launcher küldi, ezért a funkcióhoz nincs szükség külön NAS/LXC backend-frissítésre.

## Webhook csempe létrehozása

1. Nyisd meg a teljes launchert.
2. A **Web** sorban adj hozzá új csempét, vagy egy meglévő webcsempén tartsd nyomva az **OK** gombot és válaszd a szerkesztést.
3. A **Művelet** mezőben válaszd a **Webhook** értéket.
4. Add meg a teljes HTTP/HTTPS URL-t.
5. Válaszd ki a metódust:
   - **GET**
   - **POST**
6. POST esetén opcionálisan töltsd ki a **Body** mezőt.
7. Mentsd el a csempét.

A csempe ezután normál ikonként jelenik meg. Megnyomásakor a kérés a háttérben indul el.

## Visszajelzés

Kattintáskor a launcher röviden jelzi:

- `Webhook küldése…`
- majd `Webhook elküldve.`

A TV böngészőmotorja a háttérkérést `no-cors` módban küldi. Emiatt az `elküldve` azt jelenti, hogy a böngésző a kérést elindította; a cél HTTP válaszkódját a launcher nem tudja megbízhatóan visszaolvasni.

## GET példa

Egy egyszerű helyi végpont:

```text
http://192.168.0.223:8123/api/webhook/mozi
```

Beállítás:

```text
Művelet: Webhook
Metódus: GET
Body: üres
```

## POST példa

```text
http://192.168.0.223:8123/api/webhook/mozi
```

Beállítás:

```text
Művelet: Webhook
Metódus: POST
Body: {"scene":"movie"}
```

A POST body egyszerű szöveges törzsként kerül elküldésre. Ha a fogadó rendszer szigorúan `application/json` Content-Type fejlécet követel, célszerű GET webhookot vagy olyan végpontot használni, amely a szöveges body-t is elfogadja.

## Home Assistant

A legegyszerűbb megoldás egy Home Assistant webhook trigger, például:

```yaml
automation:
  - alias: TV - Mozi mód
    triggers:
      - trigger: webhook
        webhook_id: tv_mozi
        allowed_methods:
          - GET
          - POST
        local_only: true
    actions:
      - action: scene.turn_on
        target:
          entity_id: scene.mozi
```

A launcher csempe URL-je ezután a Home Assistant webhook URL-je lehet.

## Fontos működési részletek

- A webhook csempe **nem zárja be** a gyorslaunchert, ezért több művelet egymás után is indítható.
- A webhook nem kerül a **Folytatás** előzménybe.
- A régi webcsempék automatikusan **Weboldal** módban maradnak.
- A webhook beállításai a NAS-kompatibilitás miatt belső query-paraméterekben tárolódnak. A launcher ezeket szerkesztéskor automatikusan elrejti és visszaalakítja.
- A `__sl_mode`, `__sl_method` és `__sl_body` query-paraméterneveket ne használd saját célra webhook URL-ben.
- A teljes URL a belső metaadatokkal együtt legfeljebb körülbelül 2000 karakter lehet, ezért a POST body-t érdemes röviden tartani.

## Weboldal mód

Ha egy webhook csempét visszaállítasz **Weboldal** módra, a launcher ismét a webOS böngészőt indítja a megadott URL-lel. A webhook-specifikus metódus és body ilyenkor nem kerül végrehajtásra.
