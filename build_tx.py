#!/usr/bin/env python3
"""Samler Numinas bogførte posteringer (fra list_booked_entries) til én fil pr. transaktion.

Gem hver side fra Numina MCP list_booked_entries som numina_booked_1.json, numina_booked_2.json, ...
(hver fil = det rå svar med "entries"). Kør derefter:
    python3 build_tx.py            -> numina_tx.json
Kun transaktioner med et TOMT bilag medtages (dem kan få en fil).
"""
import glob, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
entries = []
for p in sorted(glob.glob(os.path.join(HERE, "numina_booked_*.json"))):
    d = json.load(open(p))
    entries += d["entries"] if isinstance(d, dict) else d
tx = {}
for e in entries:
    t = tx.setdefault(e["transaction_id"], {"transaction_id": e["transaction_id"], "date": e["date"], "texts": [],
                                           "attachment_id": e.get("attachment_id"), "attachment_number": e.get("attachment_number"),
                                           "lines": [], "max_abs_amount": 0, "dinero_refs": []})
    if e.get("text") and e["text"] not in t["texts"]:
        t["texts"].append(e["text"])
    t["lines"].append({"account": e.get("account_number"), "name": e.get("account_name"), "amount_dkk": e.get("amount_dkk"),
                       "amount": e.get("amount"), "currency": e.get("currency"), "vat": e.get("is_vat_entry")})
    if not e.get("is_vat_entry"):
        t["max_abs_amount"] = max(t["max_abs_amount"], abs(e.get("amount_dkk") or 0))
    for m in re.findall(r"(?:Køb|Dinero)\s+(\d+)", e.get("text") or ""):
        if int(m) not in t["dinero_refs"]:
            t["dinero_refs"].append(int(m))
out = sorted(tx.values(), key=lambda t: (t["date"], t["attachment_number"] or 0))
json.dump(out, open(os.path.join(HERE, "numina_tx.json"), "w"), ensure_ascii=False, indent=1)
print(len(entries), "posteringslinjer ->", len(out), "transaktioner i numina_tx.json")
