#!/usr/bin/env python3
"""EXTROVERT repo metadata: suggestions for every public repo of mine (forks excluded): the GitHub description and
topics, PyPI keywords and classifiers for packages, the release tag and version scheme, and a one-line pyproject note
for the repo's own session. The assistant writes the suggestion; this script does all the deterministic work: the
inputs, the gates, versions, what I applied, and when a repo needs a fresh look.
  repos.py list                          public repos (forks excluded): description, topics, on the site?, tags, releases,
                                         PyPI version, latest suggestion
  repos.py inputs <repo>                 everything a suggestion may use: GitHub metadata, tags and releases, PyPI
                                         metadata, the local clone's pyproject (a sibling folder), bragDoc entries that
                                         link the repo, published posts that name it
  repos.py check <repo> <file>           the suggestion's gates: sections, topic rules, the description cap, valid PyPI
                                         classifiers, the public disclosure lint and the voice lint on the description
  repos.py save <repo> <file>            check, then store as data/extrovert/repos/<repo>/v<N>.md + a snapshot
  repos.py applied <repo> [--version N]  record that I set that version (default: the latest) by hand
  repos.py status                        per repo: latest and applied versions, and why it's stale: a new tag, release or
                                         PyPI version, or a newly published post naming it since the latest suggestion;
                                         repos with no suggestion yet
Suggestion file sections (## headings): github description, github topics (space-separated), release (tag and version
scheme), and for a PyPI package also pypi keywords (comma-separated), pypi classifiers (one per line) and pyproject note.
Limits (data/extrovert/config.json -> repos): GitHub's documented topic rules (at most 20, lowercase letters, digits
and hyphens, 50 characters or fewer) and our own description cap (GitHub documents none). The site's Repos section
lists public repos tagged with config.repos.site_topic.
Network: the public GitHub REST API and the PyPI JSON API, unauthenticated (never gh). COCKPIT_REPOS_FIXTURE=<file.json>
replaces every request with a canned response {url: body} (tests). COCKPIT_NOW=<ISO> overrides the clock.
"""
import datetime as dt, json, os, re, sys, tomllib, urllib.error, urllib.request
from _common import ROOT, DATA
from disclosure_lint import lint_text, report as lint_report
import voice_lint

REPOS = DATA / "extrovert/repos"
STATE = REPOS / "state.json"
TOPIC = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
PACKAGE_SECTIONS = ("pypi keywords", "pypi classifiers", "pyproject note")
BASE_SECTIONS = ("github description", "github topics", "release")

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def die(msg): print(f"BLOCKED: {msg}"); sys.exit(1)
def rcfg():
    c = json.loads((DATA / "extrovert/config.json").read_text(encoding="utf-8")).get("repos", {})
    return {"site_topic": "portfolio", "description_max": 160, "topics_max": 20, **c}
def owner():
    gh = json.loads((DATA / "profile.json").read_text(encoding="utf-8"))["contacts"]["github"]["value"]
    return gh.rstrip("/").rsplit("/", 1)[-1]
def load_state(): return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"repos": {}}
def save_state(st):
    REPOS.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

_FIX = None
def get(url):
    """JSON (or text, for non-JSON bodies) from url; None on 404. A fixture file replaces the network in tests."""
    global _FIX
    if os.environ.get("COCKPIT_REPOS_FIXTURE"):
        if _FIX is None: _FIX = json.loads(open(os.environ["COCKPIT_REPOS_FIXTURE"], encoding="utf-8").read())
        return _FIX.get(url)
    req = urllib.request.Request(url, headers={"User-Agent": "cockpit-repos", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        die(f"{url.split('?')[0]}: HTTP {e.code}")
    except urllib.error.URLError as e: die(f"{url.split('?')[0]}: {e.reason}")
    try: return json.loads(body)
    except json.JSONDecodeError: return body

GH = "https://api.github.com"
def public_repos():
    rows = get(f"{GH}/users/{owner()}/repos?per_page=100&type=owner") or []
    return sorted((r for r in rows if not r.get("fork") and not r.get("private")), key=lambda r: r["name"].lower())
def gh_repo(name): return get(f"{GH}/repos/{owner()}/{name}")
def tags(name): return [t["name"] for t in (get(f"{GH}/repos/{owner()}/{name}/tags?per_page=100") or [])]
def releases(name): return [{"tag": r["tag_name"], "published": (r.get("published_at") or "")[:10], "draft": r.get("draft", False)}
                            for r in (get(f"{GH}/repos/{owner()}/{name}/releases?per_page=100") or [])]
def pypi(name):
    """The PyPI project of the same name, only when its metadata points back at this repo (names can collide)."""
    d = get(f"https://pypi.org/pypi/{name}/json")
    if not isinstance(d, dict): return None
    i = d["info"]
    home = f"github.com/{owner()}/{name}".lower()
    if not any(home in (u or "").lower() for u in list((i.get("project_urls") or {}).values()) + [i.get("home_page")]): return None
    return {"version": i.get("version"), "keywords": i.get("keywords"), "classifiers": i.get("classifiers", []),
            "requires_python": i.get("requires_python"), "summary": i.get("summary"),
            "releases": {v: (fs[0]["upload_time_iso_8601"][:10] if fs else None) for v, fs in d.get("releases", {}).items()}}
def local_pyproject(name):
    p = ROOT.parent / name / "pyproject.toml"
    if not p.exists(): return None
    proj = tomllib.loads(p.read_text(encoding="utf-8")).get("project", {})
    return {k: proj.get(k) for k in ("name", "version", "description", "keywords", "classifiers", "requires-python", "urls")}
def entries_for(name):
    url = f"https://github.com/{owner()}/{name}"
    out = []
    for line in (DATA / "bragdoc/entries.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        e = json.loads(line)
        links = e.get("links") or {}
        urls = [links.get(k, "") for k in ("repo", "live", "landing", "demo", "docs")] + [o.get("url", "") for o in links.get("other", [])]
        if any(u.rstrip("/") == url or u.startswith(url + "/") for u in urls):
            out.append({"id": e["id"], "visibility": e.get("visibility"), "headline": (e.get("public_summary") or {}).get("headline", e["title"])})
    return out
def posts_for(name):
    """Published posts (meta.published URLs) whose post files or links name the repo."""
    out = []
    for mp in sorted((DATA / "extrovert/conversations").glob("*/meta.json")):
        m = json.loads(mp.read_text(encoding="utf-8"))
        if not m.get("published"): continue
        text = " ".join(m.get("links", [])) + " ".join(f.read_text(encoding="utf-8") for f in mp.parent.glob("post-v*-*.md"))
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
            out += [p["url"] for p in m["published"]]
    return sorted(set(out))

def snapshot(name):
    pk = pypi(name)
    return {"tags": tags(name), "releases": [r["tag"] for r in releases(name)], "pypi_version": pk["version"] if pk else None,
            "posts": posts_for(name)}

# ---------------------------------------------------------------- commands
def cmd_list():
    st = load_state()["repos"]
    site = rcfg()["site_topic"]
    for r in public_repos():
        n = r["name"]; s = st.get(n, {}); pk = pypi(n)
        print(f"{n:32} on site: {'yes' if site in (r.get('topics') or []) else 'no ':3}  topics {len(r.get('topics') or []):2}  "
              f"tags {','.join(tags(n)[:3]) or '-':18} releases {len(releases(n))}  PyPI {pk['version'] if pk else '-':8} "
              f"suggestion v{s.get('latest', '-')}  applied v{(s.get('applied') or {}).get('version', '-')}")
        print(f"{'':32} {(r.get('description') or '(no description)')[:110]}")

def cmd_inputs(name):
    r = gh_repo(name)
    if not r: die(f"no public repo {owner()}/{name}")
    out = {"repo": {k: r.get(k) for k in ("full_name", "description", "homepage", "topics", "language", "license", "pushed_at",
                                         "created_at", "stargazers_count", "forks_count", "default_branch", "fork", "archived")},
           "tags": tags(name), "releases": releases(name), "pypi": pypi(name), "local_pyproject": local_pyproject(name),
           "bragdoc_entries": entries_for(name), "published_posts": posts_for(name),
           "site": {"topic": rcfg()["site_topic"], "listed": rcfg()["site_topic"] in (r.get("topics") or [])},
           "limits": {"description_max": rcfg()["description_max"], "topics_max": rcfg()["topics_max"], "topic": "lowercase letters, digits, hyphens; 50 chars or fewer"}}
    if out["repo"]["license"]: out["repo"]["license"] = out["repo"]["license"].get("spdx_id")
    print(json.dumps(out, indent=1, ensure_ascii=False))

def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m: cur = m.group(1).strip().lower(); out[cur] = []; continue
        if cur is not None: out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}

_CLASSIFIERS = None
def known_classifiers():
    global _CLASSIFIERS
    if _CLASSIFIERS is None:
        body = get("https://pypi.org/pypi?%3Aaction=list_classifiers")
        _CLASSIFIERS = set(l.strip() for l in body.splitlines() if l.strip()) if isinstance(body, str) else set()
    return _CLASSIFIERS

def check(name, path, quiet=False):
    """Problems with a suggestion file (empty = it passes), plus the parsed sections."""
    c, probs = rcfg(), []
    sec = sections(open(path, encoding="utf-8").read())
    package = pypi(name) is not None or local_pyproject(name) is not None
    need = BASE_SECTIONS + (PACKAGE_SECTIONS if package else ())
    for s in need:
        if not sec.get(s): probs.append(f"missing section: ## {s}")
    for s in sec:
        if s not in BASE_SECTIONS + PACKAGE_SECTIONS: probs.append(f"unknown section: ## {s}")
    d = sec.get("github description", "")
    if "\n" in d: probs.append("github description: one line")
    if len(d) > c["description_max"]: probs.append(f"github description: {len(d)} characters (cap {c['description_max']}, ours)")
    topics = sec.get("github topics", "").split()
    if len(topics) > c["topics_max"]: probs.append(f"github topics: {len(topics)} (GitHub allows {c['topics_max']})")
    for t in topics:
        if not TOPIC.match(t): probs.append(f"github topic '{t}': lowercase letters, digits and hyphens, starting with a letter or digit, 50 characters or fewer")
    if len(set(topics)) != len(topics): probs.append("github topics: duplicates")
    if package:
        kws = [k.strip() for k in sec.get("pypi keywords", "").split(",") if k.strip()]
        if not kws: probs.append("pypi keywords: none")
        known = known_classifiers()
        for cl in [l.strip() for l in sec.get("pypi classifiers", "").splitlines() if l.strip()]:
            if known and cl not in known: probs.append(f"pypi classifier not on PyPI's list: '{cl}'")
        if not known: probs.append("pypi classifiers: PyPI's classifier list could not be fetched; nothing verified")
        if "\n" in sec.get("pyproject note", ""): probs.append("pyproject note: one line, to forward to the repo's own session")
    found = lint_text(d, "public")
    if found: probs.append("github description fails the public channel:\n" + lint_report(found))
    v = voice_lint.lint(d, voice_lint.load_config(), voice_lint.load_profile())
    probs += [f"github description: voice lint: {x}" for x in v]
    if not quiet:
        print(f"  github description  {len(d)} / {c['description_max']} (our cap)")
        print(f"  github topics       {len(topics)} / {c['topics_max']}" + (f"  (site topic '{c['site_topic']}' {'included' if c['site_topic'] in topics else 'NOT included: not on the site'})"))
        print("\n".join(probs) if probs else "OK: passes every gate")
    return probs, sec

def cmd_save(name, path):
    probs, sec = check(name, path, quiet=True)
    if probs: die("\n" + "\n".join(probs))
    st = load_state(); r = st["repos"].setdefault(name, {"versions": {}})
    n = int(r.get("latest") or 0) + 1
    out = REPOS / name / f"v{n}.md"; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(open(path, encoding="utf-8").read().rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    r["latest"] = n
    r["versions"][str(n)] = {"date": now().date().isoformat(), "snapshot": snapshot(name)}
    save_state(st)
    print(f"saved {out.relative_to(ROOT).as_posix()}")

def cmd_applied(name, version=None):
    st = load_state(); r = st["repos"].get(name)
    if not r or not r.get("latest"): die(f"no suggestion saved for {name}")
    v = int(version or r["latest"])
    if str(v) not in r["versions"]: die(f"{name} has no v{v}")
    r["applied"] = {"version": v, "date": now().date().isoformat()}
    save_state(st); print(f"{name}: applied v{v}")

def stale_reasons(name, r):
    if not r.get("latest"): return ["no suggestion yet"]
    snap = r["versions"][str(r["latest"])]["snapshot"]
    cur, why = snapshot(name), []
    for t in cur["tags"]:
        if t not in snap["tags"]: why.append(f"new tag {t}")
    for t in cur["releases"]:
        if t not in snap["releases"]: why.append(f"new release {t}")
    if cur["pypi_version"] != snap["pypi_version"]: why.append(f"PyPI {snap['pypi_version']} -> {cur['pypi_version']}")
    for u in cur["posts"]:
        if u not in snap["posts"]: why.append(f"new post {u}")
    return why

def cmd_status():
    st, stale = load_state()["repos"], []
    for repo in public_repos():
        n = repo["name"]; r = st.get(n, {})
        why = stale_reasons(n, r)
        ap = (r.get("applied") or {}).get("version")
        print(f"{n:32} latest v{r.get('latest', '-')}  applied v{ap or '-'}  " + ("; ".join(why) if why else "current"))
        if why: stale.append(n)
    if stale: print(f"\nREMINDER: repo metadata to (re)suggest: {', '.join(stale)} (/extrovert repos <repo>)")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    cmd, rest = a[0], a[1:]
    if cmd == "list": cmd_list()
    elif cmd == "inputs" and len(rest) == 1: cmd_inputs(rest[0])
    elif cmd == "check" and len(rest) == 2: sys.exit(1 if check(rest[0], rest[1])[0] else 0)
    elif cmd == "save" and len(rest) == 2: cmd_save(*rest)
    elif cmd == "applied" and rest: cmd_applied(rest[0], rest[2] if len(rest) == 3 and rest[1] == "--version" else None)
    elif cmd == "status": cmd_status()
    else: print(__doc__); sys.exit(1)
