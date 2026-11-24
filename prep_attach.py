#!/usr/bin/env python3
"""attach_plan.json -> attach_items.json. Flere PDF'er til samme bilag flettes til én fil (Numina tillader én fil pr. bilag).
Kræver: pip install pypdf
Udskriver linjer "<attach_to> | <filnavn> | <content_type>" – dem skal Claude lave create_upload_link for (med attachment_id=attach_to).
"""
import json, os
from pypdf import PdfWriter, PdfReader
HERE = os.path.dirname(os.path.abspath(__file__))
plan = json.load(open(os.path.join(HERE, "attach_plan.json")))
CT = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}
os.makedirs(os.path.join(HERE, "files", "merged"), exist_ok=True)
out = []
for p in plan:
    docs = p["docs"]
    if len(docs) == 1 or any(d["ext"] != "pdf" for d in docs):
        d = docs[0]; src = f"files/{d['fileGuid']}__{d['name']}"; name = d["name"]; ct = CT.get(d["ext"], "application/octet-stream")
    else:
        w = PdfWriter()
        for d in docs:
            for pg in PdfReader(os.path.join(HERE, f"files/{d['fileGuid']}__{d['name']}")).pages:
                w.add_page(pg)
        base = os.path.splitext(docs[0]["name"])[0][:150]
        name = f"{base}+{len(docs)-1}.pdf"; src = f"files/merged/{p['attachment_number']}_{name}"; ct = "application/pdf"
        with open(os.path.join(HERE, src), "wb") as fh:
            w.write(fh)
    out.append({"attach_to": p["attach_to"], "attachment_number": p["attachment_number"], "src": src, "file_name": name,
                "content_type": ct, "fileGuid": docs[0]["fileGuid"]})
json.dump(out, open(os.path.join(HERE, "attach_items.json"), "w"), ensure_ascii=False, indent=1)
print(len(out), "items;", sum(1 for o in out if "/merged/" in o["src"]), "flettede PDF'er\n")
for o in out:
    print(o["attach_to"], "|", o["file_name"], "|", o["content_type"])
