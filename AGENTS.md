# CLAUDE.md – kørebog for AI-agenten

Du er i repoet **dinero2numina**. Når brugeren siger "gør det" / "flyt mine bilag fra Dinero til Numina",
følger du denne kørebog fra start til slut. Læs README.md for baggrund; denne fil er det, du skal GØRE.

Sprog: svar brugeren på dansk. Vær kort mellem trinnene; en linje pr. trin om status er nok.

## Forudsætninger (tjek først – stop og bed brugeren, hvis noget mangler)
1. **Numina MCP** er tilsluttet (`mcp__Numina__*`). Uden den kan trin 2, 3, 4 og 6 ikke køres.
2. **Shell på brugerens maskine** (fx `mcp__remote-devices__device_bash` eller en lokal Bash) med dette repo
   klonet og Python 3.10+. `pip install -r requirements.txt`.
3. `.env` findes i repo-mappen med `DINERO_CLIENT_ID`, `DINERO_CLIENT_SECRET`, `DINERO_API_KEY`, `DINERO_ORG`.
   **Læs aldrig .env og bed aldrig om nøglerne i chatten** – brugeren laver den selv (se `.env.example`;
   Dinero → Indstillinger → Integrationer → API-nøgler → Personlig integration). Mangler `DINERO_ORG`:
   kør `python3 dinero2numina.py orgs` og lad brugeren vælge.
4. Netværk: shell'en skal kunne nå `api.dinero.dk`, `authz.dinero.dk`, `api.numina.app`. Får du 403 fra alle
   tre, er der en domæne-allowlist – bed brugeren godkende domænerne; prøv ikke omveje.
5. Spørg brugeren om **periode** (typisk indeværende regnskabsår) og **Numina-firma**
   (`mcp__Numina__get_company_info`). Bekræft begge med én sætning før du går i gang.

Al kørsel er genoptagelig. Går noget i stå (timeout, 429, udløbne links): kør samme kommando igen.
Shell-kald kan have en maks-tid (~3 min); kør lange trin i forgrunden med `timeout 170 …` og gentag.
Baggrundsprocesser (`nohup … &`) dør typisk – brug dem ikke.

## Trin 1 – Dinero (kun shell, ingen MCP)
```
python3 dinero2numina.py list <ÅR>      # -> files.json
python3 dinero2numina.py download       # -> files/   (60 kald/min; ~200 filer ≈ 4 min, gentag ved timeout)
python3 dinero2numina.py vouchers       # -> vouchers.json (404 på løn/skat-bilag er normalt)
```
Kig `files.json` igennem efter filer der ikke er bilag (handelsbetingelser, fortrydelsesformular, policy-PDF'er,
tomme testfiler). Skriv deres filnavne i `skip.json` (JSON-liste) og nævn dem for brugeren.

## Trin 2 – Upload til Numina som løse dokumenter
For hver fil i `files.json` der ikke er i `skip.json` og ikke allerede har `attachment_id` i `state.json`:
`mcp__Numina__create_upload_link(file_name=<name>, content_type=<pdf→application/pdf | jpg/jpeg→image/jpeg | png→image/png>, run_ocr=true)`.
Kør kaldene parallelt, **højst 50 pr. omgang** (links udløber efter 10 min; Numina rate-limiter ~60 uploads pr. vindue).
Skriv `tokens.txt` med én linje pr. fil: `<fileGuid> <token>` (token = delen af upload_url efter `/mcp/uploads/`).
Skriv filen via shell (heredoc) – ikke ved at diktere den til brugeren.
```
python3 mklinks.py upload
python3 dinero2numina.py upload
```
Gentag indtil `upload` melder 0 nye. "dublet" i output er fint (samme fil fandtes allerede i Numina).

## Trin 3 – Numinas bogførte posteringer
`mcp__Numina__list_booked_entries` for perioden. Svaret er stort: gem HVER side råt som
`numina_booked_1.json`, `numina_booked_2.json`, … via shell (skriv JSON'en til fil, læs den ikke op).
Fortsæt mens `has_more` er true.
```
python3 build_tx.py          # -> numina_tx.json
python3 make_docs.py 4       # -> docs_1..4.json  (≈50 dokumenter pr. gruppe; brug flere grupper ved >250 filer)
```

## Trin 4 – Match med subagenter
Udfyld `MATCH_INSTRUCTIONS.md`: `{{FIRMA}}`, `{{CVR}}` (fra get_company_info) og `{{MAPPE}}` (absolut sti til repoet).
Start én subagent pr. `docs_N.json`, **parallelt**, med:
- prompten = indholdet af den udfyldte MATCH_INSTRUCTIONS.md + "Du er gruppe N",
- kun læse-værktøjer (`mcp__Numina__get_document`, `mcp__Numina__get_transaction`, fil-læsning, Python),
- en billig model er nok (Sonnet-klassen) – det er opslag og sammenligning, ikke ræsonnement.
Hvis brugeren har en regel om at spørge en evaluator (fx Jev) om modelvalg, så gør det først.
Vent på alle `result_N.json`. Tjek at hvert dokument optræder præcis én gang og at ingen to primære
dokumenter peger på samme transaktion med forskellige beløb (så er mindst ét forkert → sæt det i hold).

## Trin 5 – Plan og gennemgang
```
python3 make_plan.py 0.8 0.7
```
Vis brugeren:
- antal i `attach_plan.json` (knyttes automatisk),
- hver post i `attach_hold.json` som én linje: fil, OCR-beløb/dato → foreslået bilag (nr., dato, beløb, tekst),
- `unmatched.json` som en kort liste.
**Spørg brugeren**, om hold-posterne skal med, før du fortsætter. Flyt godkendte over i `attach_plan.json`.

## Trin 6 – Knyt filerne til de tomme bilag
```
python3 prep_attach.py       # fletter flere PDF'er pr. bilag; udskriver "attach_to | filnavn | content_type"
```
For hver linje: `mcp__Numina__create_upload_link(file_name=<filnavn>, content_type=<ct>, attachment_id=<attach_to>)`
– **uden** run_ocr. Højst 50–60 pr. omgang. Skriv `tokens.txt` som `<attach_to> <token>`.
Fejlen *"This bilag already has a file"* = Numina har allerede filen (typisk nyeste posteringer) → spring over, notér.
```
python3 mklinks.py attach
python3 dinero2numina.py attach
```
Gentag indtil alt i planen er knyttet. Et bilag tager kun ÉN fil – forsøg aldrig at knytte to filer til samme bilag;
det er derfor prep_attach fletter.

## Trin 7 – Verificér og rapportér
- Stikprøve 3–5 bilag med `mcp__Numina__get_document(attachment_id)` → `file_count: 1`, rigtigt filnavn, `is_empty: false`.
- Rapport til brugeren: antal uploadet, antal knyttet, hold-poster (afgjort/ikke afgjort), umatchede med forslag
  til hvad de kan være, og at de løse kopier fra trin 2 stadig ligger i Numinas indbakke og kan ryddes op.

## Må ikke
- Aldrig bogføre, oprette kladder, ændre posteringer eller slette noget i Numina eller Dinero. Dette forløb
  uploader kun filer og knytter dem til tomme bilag. Oprydning i indbakken overlades til brugeren.
- Aldrig knytte et dokument med confidence < 0.8 uden brugerens ok.
- Aldrig committe `.env`, `files/`, `state.json`, `tokens.txt` eller andre lokale data (se `.gitignore`).
- Aldrig gætte Dinero-nøgler, org-id eller Numina-firma.
