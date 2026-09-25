# Feltöltés GitHubra

Ez forrás-only csomag; nincs benne IPK, natív bináris, toolchain, napló, kulcs, párosítási adat, éles konfiguráció vagy rendszer-pillanatkép.

```sh
cd LGTV-github-source-2026-09-25
git init -b main
git add .
git commit -m "Import LG webOS control suite checkpoint 2026-09-25"
gh repo create lgtv-control-suite --private --source=. --remote=origin --push
```

Nyilvános repository előtt válassz licencet, és döntsd el, hogy a dokumentáció helyi IP/MAC adatait anonimizálod-e. Feltöltés előtt a következő keresések legyenek üresek:

```sh
find . -type f \( -name '*.ipk' -o -name '*.zip' -o -name '*.tar.gz' -o -name '*.key' -o -name 'id_rsa*' \)
grep -R -n 'BEGIN .*PRIVATE KEY' .
```
