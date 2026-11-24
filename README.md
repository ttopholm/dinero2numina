# Dinero → Numina: flyt bilag og knyt dem til bogførte posteringer

> Scripts + vejledning til at flytte bilagsfiler fra Dinero til Numina og knytte dem til de allerede bogførte posteringer. Lavet sammen med Claude (Dinero MCP + Numina MCP). Brug på eget ansvar – tjek stikprøver bagefter.


Sådan flyttede jeg 193 bilag for 2026 fra Dinero til Numina og fik 117 af dem knyttet automatisk til
de rigtige (tomme) bilag i Numina. Hele forløbet kører i Claude med **Dinero MCP** og **Numina MCP**
tilsluttet, plus disse Python-scripts på din egen maskine (Python 3.10+, kun standardbibliotek
bortset fra `pypdf` til trin 6).

Forudsætning: din bogføring er allerede migreret til Numina (posteringerne findes i Numina med
tomme bilag, og teksterne indeholder typisk "Betaling af Køb N" eller "(Dinero N)").

## Den nemme vej: lad en AI-agent køre det
Repoet indeholder `CLAUDE.md` (og `AGENTS.md`, samme indhold) – en kørebog til Claude Code / Claude med
Numina MCP tilsluttet. Klon repoet, læg din `.env` i mappen, åbn mappen i Claude og skriv fx
*"flyt mine bilag fra Dinero til Numina for 2026"*. Agenten tjekker forudsætninger, kører scripts,
starter match-subagenter og spørger dig, før den knytter tvivlsomme matches.

## 0. Opsætning (én gang)
1. Dinero → Indstillinger → Integrationer → API-nøgler → opret en **Personlig integration**.
   Du får Client ID, Client Secret og en API-nøgle.
2. Kopiér `.env.example` til `.env` og udfyld. Find organisations-id: `python3 dinero2numina.py orgs`.
   `.env` bliver kun læst af scriptet på din maskine – giv den aldrig til Claude.
3. Hvis din Claude-konto har en domæne-allowlist, skal `api.dinero.dk`, `authz.dinero.dk` og
   `api.numina.app` være godkendt.
4. `pip install -r requirements.txt` (kun pypdf, til at flette PDF'er i trin 6)

## 1. Hent fil-liste og filer fra Dinero (ingen Claude nødvendig)
```
python3 dinero2numina.py list 2026     # kun 2026 (udelad årstal for alt)
python3 dinero2numina.py download      # -> files/<fileGuid>__<navn>, genoptageligt
python3 dinero2numina.py vouchers      # Dinero-bilagsnummer/dato/beløb for linkede filer -> vouchers.json
```
Dinero tillader 60 kald/min, så 200 filer tager ~4 min. Kig `files.json` igennem og læg filer, der ikke er
bilag (handelsbetingelser, fortrydelsesformularer o.l.), i `skip.json` som en liste af filnavne.

## 2. Upload til Numina som løse dokumenter (Claude + Numina MCP)
Numina laver kun upload-links via MCP, så dette trin styres af Claude. Bed Claude:

> For hver fil i `files.json` (undtagen dem i `skip.json`), kald `mcp__Numina__create_upload_link`
> med `file_name`, `content_type` (pdf → application/pdf, jpg → image/jpeg, png → image/png) og
> `run_ocr: true`. Skriv én linje pr. fil i `tokens.txt`: `<fileGuid> <token>` hvor token er delen af
> upload_url efter `/mcp/uploads/`.

Links udløber efter 10 min, og Numina tillader ca. 60 uploads pr. vindue – tag derfor **højst 50–60 ad gangen**:
```
python3 mklinks.py upload          # tokens.txt -> upload_links.json (springer allerede uploadede over)
python3 dinero2numina.py upload    # state.json husker attachment_id pr. fil
```
Gentag indtil alt er oppe. OCR tager et par minutter pr. batch.

## 3. Hent Numinas bogførte posteringer (Claude + Numina MCP)
Bed Claude kalde `mcp__Numina__list_booked_entries` for perioden (fx 2026-01-01 → i dag) og gemme
hver side råt som `numina_booked_1.json`, `numina_booked_2.json`, … (svaret er for stort at læse direkte).
```
python3 build_tx.py                # -> numina_tx.json (én post pr. transaktion, med dinero_refs)
python3 make_docs.py 4             # -> docs_1..4.json (dokumentgrupper til subagenter)
```

## 4. Match med subagenter (Claude)
Udfyld `{{FIRMA}}`, `{{CVR}}`, `{{MAPPE}}` i `MATCH_INSTRUCTIONS.md`. Bed Claude starte én subagent pr.
`docs_N.json` (Sonnet er rigeligt – det er opslag + sammenligning), kun med læseadgang, der følger
instruktionen og skriver `result_N.json`. Subagenterne henter OCR via `get_document` og matcher på
Dinero-bilagsnummer, beløb, dato og leverandør.

## 5. Byg planen og gennemgå tvivlsomme
```
python3 make_plan.py 0.8 0.7
```
- `attach_plan.json` – confidence ≥ 0.8, knyttes automatisk
- `attach_hold.json` – 0.7–0.8, kig dem igennem manuelt (flyt dem til planen, hvis de er rigtige)
- `unmatched.json` – skal findes/vedhæftes manuelt i Numina

## 6. Knyt filerne til de tomme bilag (Claude + Numina MCP)
```
python3 prep_attach.py             # fletter flere PDF'er pr. bilag til én (Numina: én fil pr. bilag)
```
Scriptet udskriver `attach_to | filnavn | content_type`. Bed Claude:

> For hver linje: `mcp__Numina__create_upload_link(file_name, content_type, attachment_id=<attach_to>)`
> (uden run_ocr). Skriv `<attach_to> <token>` i `tokens.txt`. Max 60 pr. omgang.

Fejlen *"This bilag already has a file"* betyder bare, at Numina selv allerede har fået filen (typisk
de nyeste posteringer) – spring over.
```
python3 mklinks.py attach
python3 dinero2numina.py attach    # attach_state.json husker hvad der er knyttet
```
Tjek stikprøver med `mcp__Numina__get_document(attachment_id)` → `file_count: 1`, rigtigt filnavn.

## Godt at vide
- Den bogførte postering ændres ikke, når et tomt bilag får sin fil.
- De løse dokumenter fra trin 2 bliver liggende i Numinas indbakke som dubletter af de knyttede filer – ryd dem op bagefter.
- Wolt-ordrer: Dinero har ofte to kvitteringer (restaurant + gebyr) og Numina én postering på summen – de flettes i trin 6.
- Løn/A-skat/ATP-bilag fra Dinero er ikke købsbilag (giver 404 i `vouchers`) – de matches på OCR-beløb og dato.
- Alt er genoptageligt; kør samme kommando igen, hvis noget stopper (rate limit, udløbne links).

## Filer
| Script | Gør |
|---|---|
| `dinero2numina.py` | `orgs`, `list`, `download`, `vouchers` (Dinero API) · `upload`, `attach` (Numina) |
| `mklinks.py` | tokens.txt → upload_links.json / attach_links.json |
| `build_tx.py` | Numina list_booked_entries-sider → numina_tx.json |
| `make_docs.py` | dokumentgrupper til subagenter |
| `MATCH_INSTRUCTIONS.md` | prompt til match-subagenterne |
| `make_plan.py` | result_*.json → attach_plan / hold / unmatched |
| `prep_attach.py` | fletter PDF'er, laver attach_items.json |
