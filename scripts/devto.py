#!/usr/bin/env python3
"""EXTROVERT -> dev.to through its API: drafts, updates and publishes a post without copy-paste.
  devto.py key set | status | remove   the dev.to API key, kept in the OS keychain through keyring (never in a file,
                                       never shown); `set` asks with hidden input: run it in its own terminal window
  devto.py draft <post-file.md> --tags a,b,c,d [--series NAME] [--canonical URL] [--cover URL]
                                       gates (voice + public lint, as render.py post), then creates the article as an
                                       unpublished draft, or updates the draft already made from that file
  devto.py publish <post-file.md>      publishes that file's article (the same gates first, from the current file)
  devto.py status                      every article cockpit made: file, id, draft or published, URL
The markdown is render.py's devto_md (front matter + body). dev.to's API has no image upload: images must be https
URLs (e.g. raw.githubusercontent.com from a public repo); a local image stays a visible placeholder and blocks publish.
State: data/extrovert/devto.json. Get a key at https://dev.to/settings/extensions (DEV Community API Keys).
"""
import datetime as dt, getpass, json, pathlib, sys, urllib.error, urllib.request
from _common import DATA, ROOT

class _Vault:
    """The OS keychain through keyring (Windows Credential Manager, macOS Keychain, Secret Service), service "opencockpit"."""
    SERVICE = "opencockpit"
    class Missing(Exception): pass
    def _kr(self):
        try:
            import keyring
            return keyring
        except ImportError: raise self.Missing("the keyring package isn't installed: pip install keyring")
    def get(self, name):
        try: return self._kr().get_password(self.SERVICE, name)
        except self.Missing: raise
        except Exception as e: raise self.Missing(f"the OS keychain couldn't be read ({type(e).__name__})")
    def put(self, name, value): self._kr().set_password(self.SERVICE, name, value)
    def remove(self, name):
        try: self._kr().delete_password(self.SERVICE, name); return True
        except Exception: return False
    def has(self, name):
        try: return bool(self.get(name))
        except self.Missing: return False

vault = _Vault()

API = "https://dev.to/api/articles"
KEY = "devto_api_key"
STATE = DATA / "extrovert/devto.json"
UA = "opencockpit-devto/1.0"

def die(msg): print(f"BLOCKED: {msg}"); sys.exit(1)
def now(): return dt.datetime.now().replace(microsecond=0).isoformat()
def load(): return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"articles": {}}
def save(st): STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
def rel(p): return p.resolve().relative_to(ROOT.resolve()).as_posix()

def key():
    try: k = vault.get(KEY)
    except vault.Missing as e: die(str(e))
    if not k: die("no dev.to API key stored: run `python scripts/devto.py key set` in its own terminal window")
    return k

def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"api-key": key(), "Content-Type": "application/json", "Accept": "application/vnd.forem.api-v1+json",
                                          "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        die(f"dev.to API {method} {e.code}: {detail}")   # the key is a header and never appears here
    except Exception as e: die(f"dev.to API unreachable ({type(e).__name__})")

def markdown(path, opts, published):
    import render, voice_lint
    render.voice_gate(path)
    meta = opts or {}
    text, uploads = render.devto_md(voice_lint.post_body(path.read_text(encoding="utf-8")), meta.get("tags", []),
                                    meta.get("canonical"), meta.get("series"))
    if meta.get("cover"):
        if not meta["cover"].startswith("https://"): die("--cover must be an https URL")
        text = text.replace("\ncover_image:\n", f"\ncover_image: {meta['cover']}\n", 1)
    if published:
        if uploads and any(u.startswith("inline") for u in uploads): die("local images can't be uploaded through the API: " + ", ".join(uploads))
        text = text.replace("\npublished: false\n", "\npublished: true\n", 1)
    return text, uploads

def opt(a, k):
    return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None

def cmd_draft(a):
    p = pathlib.Path(a[0]); p = p if p.is_absolute() else ROOT / p
    st = load(); rec = st["articles"].get(rel(p), {})
    if rec.get("published"): die(f"already published: {rec['url']} (edit it on dev.to, or ask for an update)")
    opts = rec.get("options", {}) | {k: v for k, v in {"tags": [t.strip() for t in (opt(a, "--tags") or "").split(",") if t.strip()] or None,
                                                       "series": opt(a, "--series"), "canonical": opt(a, "--canonical"),
                                                       "cover": opt(a, "--cover")}.items() if v}
    text, uploads = markdown(p, opts, published=False)
    art = call("PUT", f"{API}/{rec['id']}", {"article": {"body_markdown": text}}) if rec.get("id") else \
          call("POST", API, {"article": {"body_markdown": text}})
    st["articles"][rel(p)] = {"id": art["id"], "url": art.get("url"), "published": False, "options": opts,
                              "created": rec.get("created", now()), "updated": now()}
    save(st)
    print(f"Draft {'updated' if rec.get('id') else 'created'}: id {art['id']}. Preview and edit: https://dev.to/dashboard")
    for u in uploads: print(f"  placeholder (upload in dev.to's editor before publishing): {u}")
    return 0

def cmd_publish(a):
    p = pathlib.Path(a[0]); p = p if p.is_absolute() else ROOT / p
    st = load(); rec = st["articles"].get(rel(p))
    if not rec: die("no draft from this file yet: run `devto.py draft` first")
    if rec.get("published"): print(f"Already published: {rec['url']}"); return 0
    text, _ = markdown(p, rec.get("options", {}), published=True)
    art = call("PUT", f"{API}/{rec['id']}", {"article": {"body_markdown": text}})
    rec.update(published=True, url=art.get("url"), published_at=art.get("published_at") or now(), updated=now()); save(st)
    print(f"Published: {art.get('url')}")
    return 0

def cmd_status():
    st = load()
    if not st["articles"]: print("No dev.to articles made by cockpit yet."); return 0
    for f, r in st["articles"].items():
        print(f"{'published' if r.get('published') else 'draft':<10} id {r['id']:<9} {r.get('url') or '-'}  ({f})")
    return 0

def cmd_key(a):
    if not a or a[0] == "status":
        try: print("dev.to API key: " + ("stored (never shown)" if vault.has(KEY) else "not set: run `python scripts/devto.py key set` in its own terminal window"))
        except vault.Missing as e: print(f"ACTION NEEDED  {e}"); return 1
        return 0
    if a[0] == "set":
        if not sys.stdin.isatty():
            print("Run this in its own terminal window (python scripts/devto.py key set), so the key is typed where nobody else sees it."); return 1
        print("Get the key at https://dev.to/settings/extensions -> DEV Community API Keys (description: cockpit).")
        v = getpass.getpass("dev.to API key (typing is hidden; paste and press Enter): ").strip()
        if not v: print("nothing entered; nothing stored"); return 1
        vault.put(KEY, v); print('dev.to API key: stored in the OS keychain (service "opencockpit").'); return 0
    if a[0] == "remove": print("removed" if vault.remove(KEY) else "nothing was stored"); return 0
    print(__doc__); return 1

def main(a):
    if not a: print(__doc__); return 1
    if a[0] == "key": return cmd_key(a[1:])
    if a[0] == "status": return cmd_status()
    if a[0] == "draft" and len(a) > 1: return cmd_draft(a[1:])
    if a[0] == "publish" and len(a) > 1: return cmd_publish(a[1:])
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
