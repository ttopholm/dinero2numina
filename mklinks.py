#!/usr/bin/env python3
"""tokens.txt -> upload_links.json / attach_links.json

Claude (Numina MCP) laver upload-links med create_upload_link og skriver dem i tokens.txt,
én pr. linje:   <nøgle> <token>
  - til 'upload':  nøgle = fileGuid (Dinero)       -> python3 mklinks.py upload
  - til 'attach':  nøgle = attach_to (Numina attachment_id) -> python3 mklinks.py attach
Token er delen efter https://api.numina.app/mcp/uploads/ (hele URL'en virker også).
Allerede uploadede/knyttede springes over.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
mode = sys.argv[1] if len(sys.argv) > 1 else "upload"
src = sys.argv[2] if len(sys.argv) > 2 else "tokens.txt"
BASE = "https://api.numina.app/mcp/uploads/"
tok = {}
for l in open(os.path.join(HERE, src)):
    l = l.strip()
    if not l or l.startswith("#"):
        continue
    k, t = l.split()[:2]
    tok[k] = t if t.startswith("http") else BASE + t
if mode == "upload":
    skip = set(json.load(open(os.path.join(HERE, "skip.json")))) if os.path.exists(os.path.join(HERE, "skip.json")) else set()
    state = json.load(open(os.path.join(HERE, "state.json"))) if os.path.exists(os.path.join(HERE, "state.json")) else {}
    files = json.load(open(os.path.join(HERE, "files.json")))
    links = [{"fileGuid": f["fileGuid"], "upload_url": tok[f["fileGuid"]]} for f in files
             if f["fileGuid"] in tok and f["name"] not in skip and not state.get(f["fileGuid"], {}).get("attachment_id")]
    json.dump(links, open(os.path.join(HERE, "upload_links.json"), "w"))
else:
    p = os.path.join(HERE, "attach_state.json")
    st = json.load(open(p)) if os.path.exists(p) else {}
    links = [{"attach_to": a, "upload_url": u} for a, u in tok.items() if not st.get(a, {}).get("ok")]
    json.dump(links, open(os.path.join(HERE, "attach_links.json"), "w"))
print(len(links), "links skrevet")
