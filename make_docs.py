#!/usr/bin/env python3
"""Laver docs_N.json (grupper af uploadede dokumenter) til match-subagenterne.

    python3 make_docs.py 4        # 4 grupper -> docs_1.json .. docs_4.json
Bruger files.json, state.json (numina attachment_id) og vouchers.json (Dinero-bilagsinfo).
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
files = json.load(open(os.path.join(HERE, "files.json")))
state = json.load(open(os.path.join(HERE, "state.json")))
vp = os.path.join(HERE, "vouchers.json")
vouchers = json.load(open(vp)) if os.path.exists(vp) else {}
docs = []
for f in sorted(files, key=lambda f: f["uploadedAt"]):
    st = state.get(f["fileGuid"], {})
    if not st.get("attachment_id"):
        continue
    vs = [vouchers.get(l["voucherGuid"]) for l in f.get("linkedVouchers", []) if l.get("voucherGuid")]
    vs = [v for v in vs if v and not v.get("error")]
    docs.append({"fileGuid": f["fileGuid"], "file_name": f["name"], "dinero_uploaded": f["uploadedAt"][:10],
                 "dinero_voucher_guids": [l["voucherGuid"] for l in f.get("linkedVouchers", []) if l.get("voucherGuid")],
                 "dinero_vouchers": vs, "numina_attachment_id": st["attachment_id"]})
size = -(-len(docs) // n)
for i in range(n):
    chunk = docs[i * size:(i + 1) * size]
    json.dump(chunk, open(os.path.join(HERE, f"docs_{i+1}.json"), "w"), ensure_ascii=False, indent=1)
    print(f"docs_{i+1}.json: {len(chunk)} dokumenter")
