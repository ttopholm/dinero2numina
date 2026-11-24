#!/usr/bin/env python3
"""result_*.json (fra subagenterne) -> attach_plan.json (klar til prep_attach.py) + attach_hold.json (tvivlsomme).

    python3 make_plan.py [min_confidence=0.8] [hold_from=0.7]
Flere dokumenter til samme postering samles (primær først, sekundære efter).
Dokumenter der matcher en postering, som allerede har fået en fil, lægges i hold.
"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 0.8
HOLD = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
results = []
for p in sorted(glob.glob(os.path.join(HERE, "result_*.json"))):
    results += json.load(open(p))
files = {f["fileGuid"]: f for f in json.load(open(os.path.join(HERE, "files.json")))}
by_tx, hold, unmatched = {}, [], []
for r in results:
    m = r.get("match")
    if not m:
        unmatched.append({"file_name": r["file_name"], "fileGuid": r["fileGuid"], "ocr": r.get("ocr"), "reason": r.get("reason")}); continue
    d = {"fileGuid": r["fileGuid"], "name": r["file_name"], "ext": files[r["fileGuid"]]["extension"].lower(),
         "secondary": bool(m.get("secondary")), "confidence": m["confidence"], "reason": m.get("reason"), "ocr": r.get("ocr")}
    by_tx.setdefault(m["transaction_id"], {"transaction_id": m["transaction_id"], "attach_to": m["target_attachment_id"],
                                           "attachment_number": m["attachment_number"], "date": m["date"], "amount": m["amount"],
                                           "texts": m["texts"], "docs": []})["docs"].append(d)
plan = []
for t in by_tx.values():
    t["docs"].sort(key=lambda d: (d["secondary"], -d["confidence"]))
    t["confidence"] = max(d["confidence"] for d in t["docs"])
    (plan if t["confidence"] >= MIN else hold if t["confidence"] >= HOLD else unmatched).append(t)
plan.sort(key=lambda t: t["date"])
json.dump(plan, open(os.path.join(HERE, "attach_plan.json"), "w"), ensure_ascii=False, indent=1)
json.dump(hold, open(os.path.join(HERE, "attach_hold.json"), "w"), ensure_ascii=False, indent=1)
json.dump(unmatched, open(os.path.join(HERE, "unmatched.json"), "w"), ensure_ascii=False, indent=1)
print(f"{len(plan)} posteringer i attach_plan.json (conf ≥ {MIN}), {len(hold)} i attach_hold.json, {len(unmatched)} umatchede i unmatched.json")
