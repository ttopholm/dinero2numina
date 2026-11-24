# Dinero → Numina: flyt dine bilag og få dem knyttet til de rigtige posteringer

Sådan flyttede jeg 193 bilag for 2026 fra Dinero til Numina og fik 117 af dem knyttet automatisk til de
rigtige (tomme) bilag i Numina. Hele forløbet kører i Claude med **Dinero MCP** og **Numina MCP** tilsluttet,
plus disse Python-scripts på din egen maskine (Python 3.10+, kun standardbibliotek bortset fra `pypdf` til
trin 6).

**Forudsætning:** din bogføring er allerede migreret til Numina. Det vil sige, at posteringerne findes i Numina
med *tomme* bilag, og at posteringsteksterne typisk indeholder `Betaling af Køb N` eller `(Dinero N)` – det er
Dinero-bilagsnummeret, og det er den stærkeste nøgle til at finde den rigtige postering igen.

> Brug på eget ansvar. Scriptsene bogfører ikke, retter ikke og sletter ikke noget – de uploader filer og
> knytter dem til tomme bilag. Men tjek stikprøver bagefter.

## Problemet

Numinas migrering tager dine posteringer med fra Dinero, men ikke selve bilagsfilerne. Så står du med 800
bogførte posteringer, der hver har et tomt bilag, og et arkiv i Dinero med PDF'er og billeder, der skal den
rigtige vej over. Tre ting gør det bøvlet:

1. **Dinero MCP kan ikke hente filer.** Den kan liste dem, men ikke downloade. Dineros REST API kan
   (`GET /v1/{org}/files/{fileGuid}`) – det kræver bare en personlig integration og en lille smule kode.
2. **Numina laver kun upload-links via MCP**, og et link gælder 10 minutter. Man kan altså ikke bare lave et
   script, der kører i baggrunden; Claude skal lave links i batches, og scriptet skal skynde sig at bruge dem.
3. **Et Numina-bilag tager præcis én fil.** Dinero har tit to filer til samme køb (Wolt: restaurantbon +
   gebyrkvittering; faktura + kvittering fra samme leverandør). De skal flettes til én PDF, før de knyttes.

Og så selve matchningen: hvilken af 800 posteringer hører `voucher.pdf` nr. 14 til? Det løses med
Dinero-bilagsnummeret når det findes, og ellers med OCR-beløb + dato + leverandørnavn.

## Sådan hænger det sammen

```
 Dinero (REST API)                  din maskine                        Numina (MCP)
 ───────────────                    ───────────                        ────────────
 fil-liste ──────────────▶ files.json
 filer ──────────────────▶ files/                 ──── upload ────▶  løse dokumenter (+OCR)
 købsbilag-info ─────────▶ vouchers.json
                                                  ◀── list_booked_entries ── bogførte posteringer
                          numina_tx.json  +  docs_N.json
                                   │
                          Claude-subagenter matcher (get_document = OCR)
                                   │
                          result_N.json ─▶ attach_plan.json
                          prep_attach: flet PDF'er ──── attach ────▶  tomme bilag får deres fil
```

Alt er genoptageligt: `state.json` og `attach_state.json` husker, hvad der er hentet, uploadet og knyttet.
Stopper noget (rate limit, udløbne links, en shell der timer ud), kører du bare samme kommando igen.

## Den nemme vej: lad en AI-agent køre det

Repoet indeholder `CLAUDE.md` (og `AGENTS.md`, samme indhold) – en kørebog til Claude Code / Claude med
Numina MCP tilsluttet. Klon repoet, læg din `.env` i mappen, åbn mappen i Claude og skriv fx
*"flyt mine bilag fra Dinero til Numina for 2026"*. Agenten tjekker forudsætninger, kører scripts, starter
match-subagenter og spørger dig, før den knytter tvivlsomme matches. Resten af denne README er det samme
forløb, forklaret til mennesker.

## Trin for trin

### 0. Opsætning (én gang)
1. Dinero → Indstillinger → Integrationer → API-nøgler → opret en **Personlig integration**. Du får Client
   ID, Client Secret og en API-nøgle.
2. Kopiér `.env.example` til `.env` og udfyld. Organisations-id finder du med `python3 dinero2numina.py orgs`.
   `.env` læses kun af scriptet på din maskine – giv den aldrig til Claude, og commit den aldrig
   (`.gitignore` sørger for det).
3. Har din Claude-konto en domæne-allowlist, skal `api.dinero.dk`, `authz.dinero.dk` og `api.numina.app` godkendes.
4. `pip install -r requirements.txt` (kun `pypdf`).

### 1. Hent alt fra Dinero (ingen Claude nødvendig)
```
python3 dinero2numina.py list 2026     # fil-liste for 2026 -> files.json (udelad årstal for alle år)
python3 dinero2numina.py download      # filerne -> files/<fileGuid>__<navn>
python3 dinero2numina.py vouchers      # bilagsnummer, dato og beløb for linkede filer -> vouchers.json
```
Dinero tillader 60 kald i minuttet, så 200 filer tager omkring fire minutter. `vouchers` giver 404 på
løn-, A-skat- og ATP-bilag – de er ikke købsbilag, og det er helt fint; de matches senere på OCR.

Kig `files.json` igennem. Der ligger typisk ting, der ikke er bilag (handelsbetingelser, fortrydelsesformularer,
webshop-policies). Skriv deres filnavne i `skip.json` som en JSON-liste, så de ikke kommer med.

### 2. Upload til Numina som løse dokumenter (Claude + Numina MCP)
Bed Claude:

> For hver fil i `files.json` (undtagen dem i `skip.json`), kald `mcp__Numina__create_upload_link` med
> `file_name`, `content_type` (pdf → application/pdf, jpg → image/jpeg, png → image/png) og `run_ocr: true`.
> Skriv én linje pr. fil i `tokens.txt`: `<fileGuid> <token>`, hvor token er delen af upload_url efter
> `/mcp/uploads/`.

Links udløber efter 10 minutter, og Numina tillader omkring 60 uploads pr. vindue, så tag **højst 50–60 ad
gangen**:
```
python3 mklinks.py upload            # tokens.txt -> upload_links.json (springer allerede uploadede over)
python3 dinero2numina.py upload      # POST'er filerne; state.json husker attachment_id pr. fil
```
Gentag indtil alt er oppe. "(dublet)" i output betyder, at Numina allerede havde præcis den fil – ingen skade sket.
OCR kører i baggrunden og tager et par minutter pr. batch.

### 3. Hent Numinas bogførte posteringer (Claude + Numina MCP)
Bed Claude kalde `mcp__Numina__list_booked_entries` for perioden og gemme hver side råt som
`numina_booked_1.json`, `numina_booked_2.json`, … (svaret er for stort til at læse direkte i chatten).
```
python3 build_tx.py          # -> numina_tx.json: én post pr. transaktion med tekster, beløb og dinero_refs
python3 make_docs.py 4       # -> docs_1..4.json: dokumenterne delt i fire grupper til subagenterne
```

### 4. Match med subagenter (Claude)
Udfyld `{{FIRMA}}`, `{{CVR}}` og `{{MAPPE}}` i `MATCH_INSTRUCTIONS.md`, og bed Claude starte én subagent
pr. `docs_N.json` – parallelt, kun med læseadgang, og gerne på en billig model (Sonnet-klassen er rigeligt;
det er opslag og sammenligning). Hver subagent henter OCR for sine dokumenter med `get_document` og
leder efter posteringen efter disse regler, i prioriteret rækkefølge:

| Signal | Confidence |
|---|---|
| Dinero-bilagsnummer fra `vouchers.json` == tal i posteringstekst ("Køb 37") | 0.95+ |
| OCR-beløb == posteringens beløb (±1 kr / ±3 % ved valuta) **og** dato inden for ±7 dage | 0.8–0.9 |
| …plus leverandørnavn i posteringsteksten | styrker |
| Kun beløb, eller kun leverandør + dato | ≤ 0.6 → ikke match |

Par (faktura + kvittering, bon + Wolt-gebyr) matches til samme postering med den ene som `secondary`.
Resultatet er `result_N.json` pr. gruppe.

### 5. Byg planen og kig på de tvivlsomme
```
python3 make_plan.py 0.8 0.7
```
- `attach_plan.json` – confidence ≥ 0.8, knyttes automatisk i trin 6
- `attach_hold.json` – 0.7–0.8, kig dem igennem; flyt de rigtige over i planen
- `unmatched.json` – skal findes manuelt i Numina (hos mig: 8 ud af 193, mest småbeløb i USD/EUR)

### 6. Knyt filerne til de tomme bilag (Claude + Numina MCP)
```
python3 prep_attach.py       # fletter flere PDF'er til samme bilag; udskriver "attach_to | filnavn | content_type"
```
Bed Claude:

> For hver linje: `mcp__Numina__create_upload_link(file_name, content_type, attachment_id=<attach_to>)`
> – uden run_ocr. Skriv `<attach_to> <token>` i `tokens.txt`. Højst 60 pr. omgang.

Fejlen *"This bilag already has a file"* betyder, at Numina selv allerede har filen (typisk de nyeste
posteringer, hvor du har sendt bilaget direkte til Numina) – spring over.
```
python3 mklinks.py attach
python3 dinero2numina.py attach     # attach_state.json husker, hvad der er knyttet
```
Den bogførte postering ændres ikke; bilaget får bare sin fil.

### 7. Tjek
Stikprøver med `mcp__Numina__get_document(attachment_id)` → `file_count: 1`, `is_empty: false`, rigtigt filnavn.

## Hvad jeg lærte undervejs

- **Dinero-bilagsnummeret er guld.** Numinas migrering skriver det ind i posteringsteksten, og Dineros API
  giver det for alle linkede filer. Dér sidder de fleste sikre matches.
- **Kortbetalinger bogføres 1–3 dage efter kvitteringen.** Dato-vinduet skal være mindst ±7 dage.
- **Wolt er et specialtilfælde:** to kvitteringer i Dinero, én postering i Numina på summen. Match på summen,
  flet PDF'erne.
- **Udenlandske småbeløb (USD/EUR-abonnementer) er de sværeste.** Bankens kurs og gebyr gør, at beløbet
  ikke rammer præcist – ±3 % og leverandørnavn redder de fleste, resten ender i hold eller unmatched.
- **Baggrundsprocesser dør i en agent-shell.** Kør alt i forgrunden med `timeout`, og lad scriptsene være
  genoptagelige i stedet for at prøve at holde dem i live.
- **De løse dokumenter fra trin 2 bliver liggende** i Numinas indbakke som dubletter af de knyttede filer.
  Ryd dem op bagefter – det er hurtigt gjort i Numina, og det er bevidst ikke automatiseret.

## Filer

| Fil | Gør |
|---|---|
| `dinero2numina.py` | `orgs`, `list`, `download`, `vouchers` (Dinero API) · `upload`, `attach` (Numina) |
| `mklinks.py` | `tokens.txt` → `upload_links.json` / `attach_links.json` |
| `build_tx.py` | `numina_booked_*.json` → `numina_tx.json` |
| `make_docs.py` | dokumentgrupper (`docs_N.json`) til subagenterne |
| `MATCH_INSTRUCTIONS.md` | prompt til match-subagenterne |
| `make_plan.py` | `result_*.json` → `attach_plan.json` / `attach_hold.json` / `unmatched.json` |
| `prep_attach.py` | fletter PDF'er, laver `attach_items.json` |
| `CLAUDE.md` / `AGENTS.md` | kørebog, så en agent kan køre hele forløbet |
| `.env.example` | skabelon til dine Dinero-nøgler |
