#!/usr/bin/env python3
"""Flyt bilag fra Dinero til Numina.

  python3 dinero2numina.py orgs                 # viser dine Dinero-organisationer (id + navn)
  python3 dinero2numina.py list [2026]          # henter fil-liste fra Dinero -> files.json (evt. kun ét år)
  python3 dinero2numina.py download             # henter filerne -> files/<fileGuid>__<navn>
  python3 dinero2numina.py vouchers             # henter købsbilag-info for linkede filer -> vouchers.json
  python3 dinero2numina.py upload               # sender filer til Numina via upload_links.json (løse dokumenter)
  python3 dinero2numina.py attach               # knytter filer til tomme bilag via attach_links.json

Credentials læses fra .env i samme mappe (se .env.example) eller miljøvariabler.
Alt er genoptageligt: state.json husker, hvad der er hentet/uploadet.
"""
import base64, json, os, re, sys, time, urllib.request, urllib.parse, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(HERE, "files")
STATE = os.path.join(HERE, "state.json")
CT = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if v.strip():
                    os.environ.setdefault(k.strip(), v.strip())


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(s):
    json.dump(s, open(STATE, "w"), indent=1, ensure_ascii=False)


def local_name(f):
    return f"{f['fileGuid']}__{f['name']}"


def org():
    o = os.environ.get("DINERO_ORG")
    if not o:
        sys.exit("Sæt DINERO_ORG i .env (find det med: python3 dinero2numina.py orgs)")
    return o


# ---------- Dinero ----------
_tok = {"t": None, "at": 0}


def dinero_token():
    if _tok["t"] and time.time() - _tok["at"] < 3300:
        return _tok["t"]
    cid, sec, key = (os.environ.get(k) for k in ("DINERO_CLIENT_ID", "DINERO_CLIENT_SECRET", "DINERO_API_KEY"))
    if not all((cid, sec, key)):
        sys.exit("Mangler DINERO_CLIENT_ID / DINERO_CLIENT_SECRET / DINERO_API_KEY (se .env.example)")
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "password", "scope": "read write", "username": key, "password": key}).encode()
    req = urllib.request.Request("https://authz.dinero.dk/dineroapi/oauth/token", data=body, method="POST",
                                 headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        _tok.update(t=json.load(r)["access_token"], at=time.time())
    return _tok["t"]


def dinero_get(path, raw=False):
    for attempt in range(4):
        req = urllib.request.Request("https://api.dinero.dk" + path, headers={"Authorization": f"Bearer {dinero_token()}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read() if raw else json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                print("429 – venter 30 s"); time.sleep(30); continue
            raise
        finally:
            time.sleep(1.1)  # Dinero: 60 kald/min


def orgs():
    load_env()
    for o in dinero_get("/v1/organizations?fields=id,name"):
        print(o.get("Id") or o.get("id"), "-", o.get("Name") or o.get("name"))


def list_files(year=None):
    load_env()
    out, page = [], 0
    q = {"pageSize": 500, "fileStatus": "All"}
    if year:
        q["uploadedAfter"] = f"{int(year)-1}/12/31"
        q["uploadedBefore"] = f"{int(year)+1}/01/01"
    while True:
        q["page"] = page
        batch = dinero_get(f"/v1/{org()}/files?" + urllib.parse.urlencode(q))
        if not batch:
            break
        for f in batch:
            g = {k[0].lower() + k[1:]: v for k, v in f.items()}  # FileGuid -> fileGuid
            links = g.pop("linked", None) or []
            g["linkedVouchers"] = [{"voucherId": l.get("VoucherId"), "voucherGuid": l.get("VoucherGuid"), "linkedAt": l.get("LinkedAt")} for l in links]
            out.append(g)
        print(f"side {page}: {len(batch)} filer")
        if len(batch) < q["pageSize"]:
            break
        page += 1
    if year:  # uploadedAfter/Before er på dato-niveau; filtrér præcist
        out = [f for f in out if str(f.get("uploadedAt", "")).startswith(str(year))]
    json.dump(out, open(os.path.join(HERE, "files.json"), "w"), indent=1, ensure_ascii=False)
    print(f"{len(out)} filer skrevet til files.json")


def download():
    load_env()
    files = json.load(open(os.path.join(HERE, "files.json")))
    os.makedirs(FILES_DIR, exist_ok=True)
    state = load_state()
    ok = skipped = failed = 0
    for i, f in enumerate(files, 1):
        dest = os.path.join(FILES_DIR, local_name(f))
        if os.path.exists(dest) and os.path.getsize(dest) == f["size"]:
            skipped += 1
            continue
        try:
            data = dinero_get(f"/v1/{org()}/files/{f['fileGuid']}", raw=True)
            open(dest, "wb").write(data)
            state.setdefault(f["fileGuid"], {}).update({"name": f["name"], "downloaded": True, "bytes": len(data)})
            ok += 1
            print(f"[{i}/{len(files)}] hentet {f['name']} ({len(data)} B)")
        except urllib.error.HTTPError as e:
            print(f"[{i}/{len(files)}] FEJL {e.code} {f['name']}: {e.read()[:200]!r}"); failed += 1
        if i % 10 == 0:
            save_state(state)
    save_state(state)
    print(f"Færdig: {ok} hentet, {skipped} fandtes allerede, {failed} fejlede")


def vouchers():
    """Henter Dinero-købsbilag (bilagsnummer, dato, total) for alle linkede filer -> vouchers.json."""
    load_env()
    files = json.load(open(os.path.join(HERE, "files.json")))
    p = os.path.join(HERE, "vouchers.json")
    out = json.load(open(p)) if os.path.exists(p) else {}
    guids = sorted({l["voucherGuid"] for f in files for l in f.get("linkedVouchers", []) if l.get("voucherGuid")} - set(out))
    for i, g in enumerate(guids, 1):
        try:
            v = dinero_get(f"/v1/{org()}/vouchers/purchase/{g}")
            tot = v.get("VoucherTotals") or {}
            out[g] = {"voucherNumber": v.get("VoucherNumber"), "voucherDate": v.get("VoucherDate"), "paymentDate": v.get("PaymentDate"),
                      "currency": v.get("CurrencyKey"), "totalInclVat": tot.get("TotalInclVat"), "totalExclVat": tot.get("TotalExclVat"),
                      "contactGuid": v.get("ContactGuid"), "status": v.get("Status"), "fileGuid": v.get("FileGuid")}
            print(f"[{i}/{len(guids)}] bilag {out[g]['voucherNumber']} {out[g]['voucherDate']} {out[g]['totalInclVat']}")
        except urllib.error.HTTPError as e:
            out[g] = {"error": e.code}  # 404 = ikke et købsbilag (fx løn/skat) – fint
            print(f"[{i}/{len(guids)}] {e.code} (ikke et købsbilag)")
        if i % 10 == 0:
            json.dump(out, open(p, "w"), indent=1, ensure_ascii=False)
    json.dump(out, open(p, "w"), indent=1, ensure_ascii=False)
    print(f"{len(out)} bilag i vouchers.json")


# ---------- Numina ----------
def post_file(url, path, ct):
    data = open(path, "rb").read()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": ct})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                print("429 – venter 45 s"); time.sleep(45); continue
            raise


def upload():
    """upload_links.json: [{fileGuid, upload_url}] – lavet af mklinks.py ud fra tokens.txt."""
    links = json.load(open(os.path.join(HERE, "upload_links.json")))
    state = load_state()
    files = {f["fileGuid"]: f for f in json.load(open(os.path.join(HERE, "files.json")))}
    ok = skipped = failed = 0
    for i, l in enumerate(links, 1):
        g = l["fileGuid"]; st = state.setdefault(g, {})
        if st.get("attachment_id"):
            skipped += 1; continue
        f = files[g]; path = os.path.join(FILES_DIR, local_name(f))
        if not os.path.exists(path):
            print(f"[{i}] mangler lokalt: {f['name']}"); failed += 1; continue
        try:
            res = post_file(l["upload_url"], path, CT.get(f["extension"].lower(), "application/octet-stream"))
            st.update({"name": f["name"], "attachment_id": res.get("attachment_id"), "duplicate": res.get("duplicate")})
            ok += 1
            print(f"[{i}/{len(links)}] uploadet {f['name']} -> {res.get('attachment_id')}{' (dublet)' if res.get('duplicate') else ''}")
        except urllib.error.HTTPError as e:
            print(f"[{i}/{len(links)}] FEJL {e.code} {f['name']}: {e.read()[:300]!r}"); failed += 1
        save_state(state)
        time.sleep(1.0)
    print(f"Færdig: {ok} uploadet, {skipped} var allerede oppe, {failed} fejlede")


def attach():
    """attach_links.json: [{attach_to, upload_url}] + attach_items.json fra prep_attach.py."""
    items = {i["attach_to"]: i for i in json.load(open(os.path.join(HERE, "attach_items.json")))}
    links = json.load(open(os.path.join(HERE, "attach_links.json")))
    p = os.path.join(HERE, "attach_state.json")
    st = json.load(open(p)) if os.path.exists(p) else {}
    ok = skip = fail = 0
    for n, l in enumerate(links, 1):
        a = l["attach_to"]; it = items[a]
        if st.get(a, {}).get("ok"):
            skip += 1; continue
        try:
            res = post_file(l["upload_url"], os.path.join(HERE, it["src"]), it["content_type"])
            st[a] = {"ok": True, "file": it["file_name"], "result": res}; ok += 1
            print(f"[{n}/{len(links)}] bilag {it['attachment_number']} <- {it['file_name'][:60]}")
        except urllib.error.HTTPError as e:
            body = e.read()[:200]
            st[a] = {"ok": False, "error": e.code, "body": body.decode(errors="replace")}; fail += 1
            print(f"[{n}/{len(links)}] FEJL {e.code} bilag {it['attachment_number']}: {body!r}")
        json.dump(st, open(p, "w"), indent=1, ensure_ascii=False)
        time.sleep(1.0)
    print(f"Færdig: {ok} knyttet, {skip} allerede, {fail} fejlede")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "list":
        list_files(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        {"orgs": orgs, "download": download, "vouchers": vouchers, "upload": upload, "attach": attach}.get(cmd, lambda: sys.exit(__doc__))()
