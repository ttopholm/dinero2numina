# Opgave: match Dinero-bilag til Numina-posteringer

(Skabelon til match-subagenter. Erstat {{...}} inden brug.)

Du arbejder for {{FIRMA}} (CVR {{CVR}}). Bogføringen er flyttet fra Dinero til Numina.
Bilagsfilerne fra Dinero er allerede uploadet til Numina som løse dokumenter (med OCR).
Numina indeholder bogførte posteringer, der hver har et TOMT bilag (attachment is_empty).
Din opgave: find for hvert dokument i din gruppe den bogførte Numina-postering, det hører til.

## Input (filer)
- Din gruppe: `{{MAPPE}}/docs_N.json` – liste af dokumenter:
  `fileGuid`, `file_name`, `dinero_uploaded` (dato filen blev lagt i Dinero – ofte samme dag som købet, men ikke altid),
  `dinero_vouchers` (Dinero-købsbilag filen var knyttet til: voucherNumber, voucherDate, totalInclVat – kan være tom),
  `numina_attachment_id` (det uploadede dokument i Numina).
- `{{MAPPE}}/numina_tx.json` – alle bogførte Numina-posteringer i perioden:
  `transaction_id`, `date`, `texts` (posteringstekster, fx "Betaling af Køb 37", "Software", leverandørnavn),
  `attachment_id` + `attachment_number` (det tomme bilag), `lines` (konto, beløb DKK, vat-flag), `max_abs_amount`,
  `dinero_refs` (tal udtrukket fra "Køb N"/"Dinero N" i teksten = Dinero-bilagsnummer).
  Læs filen med Python (json) – den er for stor til at læse rå. Brug Python til at søge kandidater på dato ±7 dage og beløb.

## Værktøjer
- `mcp__Numina__get_document(attachment_id=<numina_attachment_id>)` → OCR-facts: vendor, amount, currency, date, invoiceNumber.
  Kald det for HVERT dokument i din gruppe (flere kald parallelt er fint).
- `mcp__Numina__get_transaction(transaction_id)` hvis du vil se detaljer om en kandidat.
- Du må IKKE uploade, ændre, oprette eller slette noget i Numina eller Dinero. Kun læse.

## Matching-regler
1. Stærkest: Dinero-bilagsnummer (`dinero_vouchers[].voucherNumber`) == et tal i `dinero_refs` → confidence 0.95+.
2. Ellers: OCR-beløb == `max_abs_amount` (±1 kr, eller ±3 % for valuta/kortgebyr) OG dato inden for ±7 dage
   (kortbetalinger bogføres ofte 1–3 dage senere) → 0.8–0.9; styrk med leverandørnavn i `texts`.
3. Kun beløb eller kun leverandør/dato → højst 0.6; match ikke under 0.7.
4. Invoice+Receipt-par (fx Invoice-X.pdf og Receipt-X.pdf) hører til samme postering – match begge til den samme
   transaction, markér den ene som `secondary: true`.
5. Flere kvitteringer med samme dato (fx Wolt: restaurant-bon + gebyr-kvittering, eller bon + terminalkvittering)
   hører til samme postering; summen af dem matcher typisk posteringen.
6. Én Numina-postering må gerne få flere dokumenter; men ét dokument må kun matche én postering.
7. Hvis OCR er tom/ubrugelig og der ikke er Dinero-nummer: `match: null` med reason.

## Output
Skriv `{{MAPPE}}/result_N.json` (N = dit gruppenummer) som liste med ét objekt pr. dokument:
```json
{"fileGuid": "...", "file_name": "...", "numina_attachment_id": "...",
 "ocr": {"vendor": "...", "amount": 123.45, "currency": "DKK", "date": "2026-03-11", "invoiceNumber": "..."},
 "dinero_voucher_number": 37,
 "match": {"transaction_id": "...", "target_attachment_id": "...", "attachment_number": 123,
           "date": "2026-03-12", "amount": 123.45, "texts": ["..."], "confidence": 0.9,
           "secondary": false, "reason": "beløb og dato matcher, leverandør i tekst"}
}
```
(`"match": null, "reason": "..."` hvis intet match.)
Returnér til sidst en kort opsummering: antal matchet (≥0.7), antal umatchede, og de 5 mest tvivlsomme matches.
