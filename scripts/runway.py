#!/usr/bin/env python3
"""RUNWAY: builds a website's data from the bragDoc's public channel and ships it to the site repo, one way only.
The site can be any static site in its own git repo, hosted anywhere that builds `main` for production and gives
branches a preview URL. Everything specific to the site and its host lives in data/runway/config.json.
  runway.py table                       the site data as it would publish: id, field, impact, metric, title (+ showcase)
  runway.py build [--out FILE]          build + every gate; print a summary (or write the JSON to FILE)
  runway.py preview                     write the site data + PDF into the site repo's working tree (no git), build + check
  runway.py publish [--if-pending]      gates -> content branch: write data + PDF, build + check, commit, push, print the
                                        preview URL. --if-pending: do nothing when no public payload changed (renovate's call)
  runway.py publish --initial           the very first commit: the same, but straight onto an empty repo's main
  runway.py promote [--initial]         after the user approves the preview: merge content -> main, push, then set every
                                        published entry's published_hash. --initial: main already holds the first publish
  runway.py ship "<summary>" [--slug S] site code changes (uncommitted on main): the same gates (build, check, all
                                        tests), then a code/<slug> branch, commit, push, print the preview URL
  runway.py promote code/<slug>         after the user approves that preview: merge main in if it moved (gates again),
                                        fast-forward main, push
  runway.py showcase <entry_id>...      homepage case studies (max 3; public; never the current employer's)
  runway.py showcase intent <staging_id> [--replaces <entry_id>]
                                        once that staging item is probed, renovated and public, its entry takes the place
  runway.py status                      live vs pending, plus launch blockers
  runway.py release current-employer    the user's one instruction: make every private current-employer entry public, publish
  runway.py confirm email               the user confirmed a test email to the site address arrived
  runway.py rebuild [--no-wait]         POST the host's deploy hook from the gitignored local file (never printed), then wait
                                        for the production deploy and run the site's live smoke tests
  runway.py await-post <post-url> [--no-wait] [--interval S] [--max S]
                                        poll the posts feed until that post appears (default every 2 min, 30 min max),
                                        then rebuild; on timeout, rebuild anyway (the daily rebuild catches a slow feed)
  runway.py verify-action               watch production while the user runs Actions -> daily-rebuild -> Run workflow;
                                        a redeploy proves the GitHub secret works, recorded in state
  runway.py live-check                  wait for nothing: just run the live smoke tests against production now
  runway.py profile [--write]           the profile README's cockpit block (top public entries, intro, links):
                                        print it with its gates and whether the README is current; --write updates it
                                        (pull --rebase, merge between the markers only, commit, push). Every promote
                                        runs --write when the block changed
Promote, rebuild and await-post wait for the production deploy (Last-Modified moves past its pre-trigger value), then run
the site's live tests (config live_test_cmd). --no-wait skips both.
Config: data/runway/config.json. State: data/runway/state.json. COCKPIT_NOW=<ISO> overrides the clock (tests).
"""
import datetime as dt, email.utils, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.parse
import urllib.request, pathlib
import xml.etree.ElementTree as ET
from _common import ROOT, DATA, read_jsonl, write_jsonl
from disclosure_lint import (check as lint_check, context as lint_context, leak_terms, report as lint_report, current_employers,
                             NO_ENTRY)
import bragdoc_public as bp

CONFIG, STATE = DATA / "runway/config.json", DATA / "runway/state.json"
ENTRIES, STAGING = DATA / "bragdoc/entries.jsonl", DATA / "bragdoc/staging.jsonl"
CARD_TEXT = ("metric", "title", "summary", "context", "did", "result", "where")
REQUIRED = ("id", "field", "year", "metric", "title", "summary", "context", "did", "result", "where")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
STATE_DEFAULT = {"showcase": [], "showcase_intents": [], "retired_slugs": [], "email_verified": False,
                 "published_site_hash": None, "last_publish": None, "last_promote": None,
                 "last_rebuild": None, "last_live_check": None, "rebuild_action_verified": None, "ships": {}}
# The host's deploy hook: config deploy_hook_pattern says what a valid one looks like (default: any https URL).
# RUNWAY_ALLOW_LOCAL_HOOK=1 also accepts a 127.0.0.1 stub (tests only, never a real POST).
def hook_pattern(c): return re.compile(c.get("deploy_hook_pattern") or r"^https://\S+$")
LOCAL_HOOK_URL = re.compile(r"^http://127\.0\.0\.1:\d+/[\w/.-]*$")

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def die(msg, code=1): print(f"BLOCKED: {msg}"); sys.exit(code)
def cfg(): return json.loads(CONFIG.read_text(encoding="utf-8"))
def state(): return {**STATE_DEFAULT, **(json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {})}
def save_state(st): STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
def site_dir(c): p = pathlib.Path(c["site_repo"]); return (p if p.is_absolute() else ROOT / p).resolve()
def digest(obj): return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def site_hash(data): return digest({k: v for k, v in data.items() if k != "updated"})

def git(*a, cwd, check=True):
    p = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode: die(f"git {' '.join(a)} failed: {(p.stderr or p.stdout).strip()}")
    return p

def run_cmd(cmd, cwd, env=None):
    exe = shutil.which(cmd[0]) or cmd[0]   # npm / npx are .cmd shims on Windows
    p = subprocess.run([exe, *cmd[1:]], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, **(env or {})})
    return p.returncode, (p.stdout or "") + (p.stderr or "")

def names(): return json.loads((DATA / "profile.json").read_text(encoding="utf-8")).get("names", {})
def pdf_name(c): return c["pdf"]["file"].format(short=names().get("short", "").replace(" ", "_"))

def impact(rank, c):
    for b in c["impact_bands"]:
        if b["min"] <= rank <= b["max"]: return b["impact"]
    return None

# ---------------------------------------------------------------- build + gates
def resolve_showcase(st, entries, c):
    """state.showcase, with each showcase intent applied once its staging item lives in a public, showable entry."""
    cur, show, notes = current_employers(), list(st.get("showcase", [])), []
    for it in st.get("showcase_intents", []):
        e = next((e for e in entries if it["staging_id"] in e.get("staging_ids", [])), None)
        ok = e and e.get("visibility") == "public" and e.get("employer") not in cur and e.get("site_card") and e.get("site_slug")
        if not ok:
            notes.append(f"intent {it['staging_id']}: waiting (" + ("not renovated yet" if not e else "not public / not showable yet") + ")"); continue
        if e["id"] in show: notes.append(f"intent {it['staging_id']}: resolved ({e['id']} is showcased)"); continue
        if it.get("replaces") in show: show[show.index(it["replaces"])] = e["id"]
        elif len(show) < c["max_highlights"]: show.append(e["id"])
        notes.append(f"intent {it['staging_id']}: {e['id']} " + (f"replaces {it['replaces']}" if it.get("replaces") else "added"))
    return show, notes

def contract(data, c):
    """The site data contract (scripts/schemas.md -> RUNWAY -> site data). The site reads exactly this shape."""
    p, field_ids, seen = [], {f["id"] for f in data["fields"]}, set()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["updated"]): p.append("updated must be YYYY-MM-DD")
    if not str(data["pdf"]).startswith("/"): p.append("pdf must be a site path")
    for f in data["fields"]:
        if not all(isinstance(f.get(k), str) and f[k] for k in ("id", "name", "color")): p.append(f"field {f}: needs id, name, color")
    for e in data["entries"]:
        w = f"entry {e.get('id')}"
        for k in REQUIRED:
            if not (isinstance(e.get(k), str) and e[k].strip()): p.append(f"{w}: '{k}' must be a non-empty string")
        if e.get("field") not in field_ids: p.append(f"{w}: field '{e.get('field')}' is not a fields[].id")
        if e.get("impact") not in (1, 2, 3): p.append(f"{w}: impact must be 1-3")
        if not re.fullmatch(r"\d{4}", str(e.get("year", ""))): p.append(f"{w}: year must be YYYY")
        if not SLUG.match(str(e.get("id", ""))): p.append(f"{w}: id must be a slug")
        if not (isinstance(e.get("stack"), list) and all(isinstance(s, str) for s in e["stack"])): p.append(f"{w}: stack must be a list of strings")
        if e.get("id") in seen: p.append(f"{w}: duplicate id")
        seen.add(e.get("id"))
    if sum(bool(e.get("highlight")) for e in data["entries"]) > c["max_highlights"]: p.append(f"more than {c['max_highlights']} highlights")
    return p

def build():
    """(data, published entry ids, problems, notes). Nothing is generated here: renovate already wrote every field."""
    c, st = cfg(), state()
    entries, cur = read_jsonl(ENTRIES), current_employers()
    show, notes = resolve_showcase(st, entries, c)
    ctx, problems, out, ids = lint_context(entries), [], [], []
    for e in sorted((e for e in entries if e.get("visibility") == "public"), key=lambda e: e["id"]):
        miss = [f for f in ("public_summary", "site_card", "site_slug", "year") if not e.get(f)]
        old = [f for f in ("public_summary", "site_card") if bp.stale_reason(e, f) == "changed"]
        field, imp = c["category_to_field"].get(e.get("category")), impact(e.get("rank_score", 0), c)
        if miss or old or not field or not imp:
            problems.append(f"{e['id']}: " + "; ".join(([f"missing {miss}"] if miss else []) + ([f"out of date {old}"] if old else [])
                            + ([f"no field for category '{e.get('category')}'"] if not field else []) + (["no impact band"] if not imp else []))
                            + " (renovate writes these; nothing is generated at publish)")
            continue
        ps, card = e["public_summary"], e["site_card"]
        row = {"id": e["site_slug"], "field": field, "impact": imp, "year": e["year"], "metric": card["metric"],
               "title": ps["headline"], "summary": ps["summary"], "context": card["context"], "did": card["did"],
               "result": card["result"], "stack": list(ps["stack"]), "where": card["where"]}
        if e["id"] in show: row["highlight"] = True
        found = lint_check([row[k] for k in CARD_TEXT] + [", ".join(row["stack"]), row["id"].replace("-", " ")], "public", ctx,
                           leak_terms(e.get("public_constraints", [])), entry=e)
        problems += [f"{e['id']} public lint: {why} | {line[:100]}" for _, line, why in found]
        out.append(row); ids.append(e["id"])
    for i in show:
        e = next((x for x in entries if x["id"] == i), None)
        if not e: problems.append(f"showcase {i}: no such entry")
        elif e.get("visibility") != "public": problems.append(f"showcase {i}: not public")
        elif e.get("employer") in cur: problems.append(f"showcase {i}: current-employer entries are never highlighted")
    data = {"updated": now().date().isoformat(), "pdf": "/" + pdf_name(c), "fields": c["fields"], "entries": out}
    problems += contract(data, c)
    # every string once more as one document (no entry context: relative costs pass only verbatim from an allowed entry)
    strings = [f["name"] for f in data["fields"]] + [v for r in out for v in [r[k] for k in CARD_TEXT] + r["stack"]]
    problems += [f"document lint: {why} | {line[:100]}" for _, line, why in lint_check(strings, "public", ctx, entry=NO_ENTRY)]
    return data, ids, problems, notes

def pending(data, st):
    entries = read_jsonl(ENTRIES)
    changed = [e["id"] for e in entries if e.get("visibility") == "public" and bp.payload_hash(e) != e.get("published_hash")]
    removed = [e["id"] for e in entries if e.get("visibility") != "public" and e.get("published_hash")]
    return changed, removed, site_hash(data) != st.get("published_site_hash")

def render_pdf(c):
    """The full public bragDoc (render.py public-resume, which lints its HTML and its PDF and writes nothing on failure)."""
    p = subprocess.run([sys.executable, str(ROOT / "scripts/render.py"), "public-resume"], capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if p.returncode: die("public PDF gate failed:\n" + (p.stdout + p.stderr).strip())
    form = json.loads((DATA / "bragdoc/disclosure_policy.json").read_text(encoding="utf-8"))["channels"]["public"]["names"]["form"]
    pdf = ROOT / "out" / f"{names().get(form, '').replace(' ', '_')}_Resume_Public.pdf"
    if not pdf.is_file(): die("no PDF engine produced the public PDF (install WeasyPrint, or Chrome/Edge for headless printing)")
    return pdf

# ---------------------------------------------------------------- writing to the site repo
def write_site(c, site, data, pdf):
    """Write the data and the PDF; build, check, then the site's tests against the fresh build. Files the build may rewrite
    (config synced_files, e.g. a hosting config whose CSP hashes follow the pages) are committed with the data when they
    change. On any failure, restore what was there and stop: nothing is written."""
    targets = {c["data_path"]: (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
               f"{c['pdf']['dir']}/{pdf_name(c)}": pdf.read_bytes()}
    synced = list(c.get("synced_files") or [])
    backup = {rel: (site / rel).read_bytes() if (site / rel).exists() else None for rel in [*targets, *synced]}
    def restore():
        for rel, b in backup.items():
            if b is None: (site / rel).unlink(missing_ok=True)
            else: (site / rel).write_bytes(b)
    for rel, b in targets.items():
        (site / rel).parent.mkdir(parents=True, exist_ok=True); (site / rel).write_bytes(b)
    failed = run_gates(c, site)
    if failed: restore(); die(f"site {failed[0]} failed; nothing written:\n" + failed[1][-2500:])
    return list(targets) + [rel for rel in synced if (site / rel).exists() and (site / rel).read_bytes() != backup[rel]]

def run_gates(c, site):
    """The site's gates on its working tree: build, check, tests. test_cmd gets its own port (test_port, passed in the
    env var test_port_env), so it starts a server for this build instead of reusing a running one.
    -> None when all pass, else (command, output)."""
    port_env = {c.get("test_port_env", "TEST_PORT"): str(c.get("test_port", 4329))}
    for name, env in (("build_cmd", None), ("check_cmd", None), ("test_cmd", port_env)):
        if not c.get(name): continue
        rc, out = run_cmd(c[name], site, env)
        if rc: return " ".join(c[name]), out
        dist = site / c.get("dist_dir", "dist")
        if name == "build_cmd" and dist.is_dir():
            # the voice rules' em-dash limit covers the site's own copy too (text marked data-source only warns)
            import voice_lint
            problems, warnings = voice_lint.site_lint(dist, json.loads((DATA / "extrovert/config.json").read_text(encoding="utf-8")))
            for w in warnings: print(f"site copy WARNING (fix at its source): {w}")
            if problems: return "voice lint (site copy)", "\n".join(problems)
    return None

def preview_url(c, branch):
    """config preview_url: a pattern with {branch} (most hosts alias a branch lowercased, anything else as '-':
    code/foo -> code-foo). None until it is set."""
    if not c.get("preview_url"): return None
    return c["preview_url"].format(branch=re.sub(r"[^a-z0-9-]", "-", branch.lower()))

# ---------------------------------------------------------------- site code: ship -> preview -> promote
# Code changes are made in the site repo's working tree (on main, uncommitted) on the user's explicit instruction, then
# shipped to their own preview branch. Content never ships this way: publish owns bragdoc.json and the resume PDF.
def max_code_slug(c):
    """config code_slug_max: a preview hostname label is at most 63 characters, so a host that puts the branch in the
    hostname caps the slug (63 minus the rest of the label)."""
    return int(c.get("code_slug_max", 30))

def code_slug(summary, c):
    """The longest run of whole words from the summary that fits the preview hostname."""
    limit, slug = max_code_slug(c), ""
    for w in re.sub(r"[^a-z0-9]+", " ", summary.lower()).split():
        cand = f"{slug}-{w}" if slug else w
        if len(cand) > limit: break
        slug = cand
    return slug or re.sub(r"[^a-z0-9]", "", summary.lower())[:limit] or "change"

def branch_exists(site, branch):
    local = git("rev-parse", "--verify", "--quiet", branch, cwd=site, check=False).returncode == 0
    remote = bool(git("ls-remote", "--heads", "origin", branch, cwd=site, check=False).stdout.strip())
    return local or remote

def porcelain_paths(site):
    out = []
    for l in git("status", "--porcelain", "--untracked-files=all", cwd=site).stdout.splitlines():
        p = l[3:].strip().strip('"')
        out.append(p.split(" -> ")[-1])
    return out

def ship(summary, slug=None):
    c, st = cfg(), state(); site = site_dir(c); main = c["main_branch"]
    if not summary.strip(): die('usage: ship "<summary>" [--slug <slug>]')
    if not (site / ".git").exists(): die(f"{site} is not a git repo")
    head = git("rev-parse", "--abbrev-ref", "HEAD", cwd=site).stdout.strip()
    if head != main: die(f"the site repo is on '{head}': code changes start from {main} (uncommitted)")
    changed = porcelain_paths(site)
    if not changed: die("no code changes in the site repo's working tree")
    owned = {c["data_path"], f"{c['pdf']['dir']}/{pdf_name(c)}"}
    if owned & set(changed): die(f"content files changed ({', '.join(sorted(owned & set(changed)))}): content ships through publish, not ship")
    git("fetch", "--quiet", "origin", main, cwd=site)
    if git("rev-parse", main, cwd=site).stdout != git("rev-parse", f"origin/{main}", cwd=site).stdout:
        die(f"local {main} differs from origin/{main}: bring them level first")
    limit = max_code_slug(c); slug = slug or code_slug(summary, c)
    if not SLUG.match(slug) or len(slug) > limit:
        die(f"slug '{slug}' must be lowercase-hyphen and at most {limit} characters (the preview hostname limit)")
    base, n = slug, 2
    while branch_exists(site, f"code/{slug}"):
        tail = f"-{n}"; slug = base[:limit - len(tail)].rstrip("-") + tail; n += 1
    branch = f"code/{slug}"
    print(f"Gates on {main} + {len(changed)} changed file(s): build, check, tests...", flush=True)
    failed = run_gates(c, site)
    if failed: die(f"site {failed[0]} failed; nothing shipped (your changes are still in the working tree):\n" + failed[1][-2500:])
    git("checkout", "-q", "-b", branch, cwd=site)
    git("add", "-A", cwd=site)
    trailer = c.get("commit_trailer")
    git("commit", "-q", "-m", f"code: {summary}" + (f"\n\n{trailer}" if trailer else ""), cwd=site)
    commit = git("rev-parse", "HEAD", cwd=site).stdout.strip()
    push = git("push", "-q", "-u", "origin", branch, cwd=site, check=False)
    git("checkout", "-q", main, cwd=site)
    st.setdefault("ships", {})[branch] = {"date": now().isoformat(timespec="seconds"), "summary": summary, "commit": commit,
                                          "pushed": push.returncode == 0, "status": "preview"}
    save_state(st)
    print(f"Shipped {branch} ({commit[:7]}): {summary}" + ("" if push.returncode == 0 else f"\nPUSH FAILED: {push.stderr.strip()}"))
    url = preview_url(c, branch)
    print(f"Preview: {url}" if url else "Preview: no URL (set preview_url in data/runway/config.json)")
    print(f"Nothing is live until you approve the preview and run: runway.py promote {branch}")
    return 0 if push.returncode == 0 else 1

def promote_code(branch, wait=True):
    c, st = cfg(), state(); site = site_dir(c); main = c["main_branch"]
    info = (st.get("ships") or {}).get(branch) or die(f"{branch} wasn't shipped by runway.py ship")
    if info.get("status") == "promoted": die(f"{branch} is already promoted")
    if porcelain_paths(site): die("the site repo has uncommitted changes; commit or discard them first")
    if git("rev-parse", "--abbrev-ref", "HEAD", cwd=site).stdout.strip() != main: die(f"the site repo must be on {main}")
    git("fetch", "--quiet", "origin", cwd=site)
    if git("rev-parse", main, cwd=site).stdout != git("rev-parse", f"origin/{main}", cwd=site).stdout:
        die(f"local {main} differs from origin/{main}: bring them level first")
    git("checkout", "-q", branch, cwd=site)
    try:
        if git("merge-base", "--is-ancestor", main, branch, cwd=site, check=False).returncode:
            # main moved since the ship (a content promote or another code branch): merge it in and gate the result
            if git("merge", "--no-edit", "-q", main, cwd=site, check=False).returncode:
                git("merge", "--abort", cwd=site, check=False)
                die(f"{main} doesn't merge cleanly into {branch}: resolve on the branch, then promote again")
            print(f"{main} moved since the ship: merged it into {branch}; gates again...", flush=True)
            failed = run_gates(c, site)
            if failed: die(f"site {failed[0]} failed after merging {main}; {main} untouched:\n" + failed[1][-2500:])
            if porcelain_paths(site):   # the build re-synced a synced file (e.g. CSP hashes) for the merged tree
                git("add", "-A", cwd=site); git("commit", "-q", "-m", "code: re-sync build outputs after merging main", cwd=site)
            push = git("push", "-q", "origin", branch, cwd=site, check=False)
            if push.returncode: die(f"push of {branch} failed: {push.stderr.strip()}")
    finally:
        git("checkout", "-q", main, cwd=site, check=False)
    git("merge", "--ff-only", "-q", branch, cwd=site)
    before = live_stamp(c) if wait else None
    push = git("push", "-q", "origin", main, cwd=site, check=False)
    if push.returncode: die(f"push failed: {push.stderr.strip()}")
    info.update(status="promoted", promoted=now().isoformat(timespec="seconds"), main_commit=git("rev-parse", main, cwd=site).stdout.strip())
    st["ships"][branch] = info; save_state(st)
    print(f"Promoted {branch} to {main} ({info['main_commit'][:7]}). The host deploys {main} to production.")
    rc = after_deploy(c, before, f"promote {branch}") if wait else 0
    return profile_sync(c) or rc

def publish(initial=False, if_pending=False):
    c, st = cfg(), state(); site = site_dir(c)
    data, ids, problems, notes = build()
    if problems: die("gates failed; nothing written:\n  " + "\n  ".join(problems))
    changed, removed, site_changed = pending(data, st)
    if if_pending and not (changed or removed or site_changed): print("Nothing pending: no publish."); return 0
    if not (site / ".git").exists(): die(f"{site} is not a git repo")
    has_commits = git("rev-parse", "--verify", "HEAD", cwd=site, check=False).returncode == 0
    if initial and has_commits: die("--initial is only for an empty repo; use publish")
    if not initial:
        if not has_commits: die("the site repo has no commits yet: run publish --initial first")
        if git("status", "--porcelain", cwd=site).stdout.strip(): die("the site repo has uncommitted changes; commit or discard them first")
    pdf = render_pdf(c)
    branch = c["main_branch"] if initial else c["content_branch"]
    if not initial:
        exists = git("rev-parse", "--verify", branch, cwd=site, check=False).returncode == 0
        git("checkout", branch, cwd=site) if exists else git("checkout", "-b", branch, c["main_branch"], cwd=site)
        git("merge", "--no-edit", c["main_branch"], cwd=site)
    try:
        files = write_site(c, site, data, pdf)
    except SystemExit:
        if not initial: git("checkout", c["main_branch"], cwd=site, check=False)
        raise
    git("add", "-A", cwd=site) if initial else git("add", *files, cwd=site)
    if not git("diff", "--cached", "--name-only", cwd=site).stdout.strip():
        if not initial: git("checkout", c["main_branch"], cwd=site)
        print("Site content unchanged: nothing to commit."); return 0
    msg = (f"site: initial import with content ({len(ids)} entries)" if initial
           else f"content: {now().date().isoformat()}, {len(ids)} entries ({len(changed)} changed, {len(removed)} removed)")
    git("commit", "-q", "-m", msg, cwd=site)
    commit = git("rev-parse", "HEAD", cwd=site).stdout.strip()
    push = git("push", "-u", "origin", branch, cwd=site, check=False)
    if not initial: git("checkout", c["main_branch"], cwd=site)
    entries = {e["id"]: bp.payload_hash(e) for e in read_jsonl(ENTRIES) if e["id"] in ids}
    st["last_publish"] = {"date": now().isoformat(timespec="seconds"), "branch": branch, "commit": commit, "site_hash": site_hash(data),
                          "entries": entries, "pushed": push.returncode == 0}
    save_state(st)
    print(f"Published {len(ids)} entries to {branch} ({commit[:7]})" + ("" if push.returncode == 0 else f"\nPUSH FAILED: {push.stderr.strip()}"))
    for n in notes: print(f"  {n}")
    if initial: print("Initial content is on main. After you approve local testing: runway.py promote --initial")
    else:
        url = preview_url(c, branch)
        print(f"Preview: {url}" if url else "Preview: no URL yet (set preview_url in data/runway/config.json once the host builds branches)")
        print("Nothing is live until you approve the preview and run: runway.py promote")
    return 0

def promote(initial=False, wait=True):
    c, st = cfg(), state(); site = site_dir(c); lp = st.get("last_publish"); before = None
    if not lp: die("nothing published yet")
    data, ids, problems, _ = build()
    if problems: die("gates fail now:\n  " + "\n  ".join(problems))
    if site_hash(data) != lp["site_hash"] or {e["id"]: bp.payload_hash(e) for e in read_jsonl(ENTRIES) if e["id"] in ids} != lp["entries"]:
        die("the bragDoc changed since the last publish: publish again, check the preview, then promote")
    if initial:
        if lp["branch"] != c["main_branch"]: die("--initial promotes the first publish on main only")
        if git("rev-parse", c["main_branch"], cwd=site).stdout.strip() != lp["commit"]: die("main has moved since the first publish")
    else:
        if lp["branch"] != c["content_branch"]: die("the last publish wasn't to the content branch")
        git("checkout", c["main_branch"], cwd=site)
        if git("merge", "--ff-only", c["content_branch"], cwd=site, check=False).returncode:
            git("merge", "--no-edit", c["content_branch"], cwd=site)
        before = live_stamp(c) if wait else None
        push = git("push", "origin", c["main_branch"], cwd=site, check=False)
        if push.returncode: die(f"push failed: {push.stderr.strip()}")
    entries = read_jsonl(ENTRIES); live = 0
    for e in entries:
        if e["id"] in lp["entries"]: e["published_hash"] = lp["entries"][e["id"]]; live += 1
        elif e.get("published_hash"): e["published_hash"] = None   # made private since: no longer on the site
    write_jsonl(ENTRIES, entries)
    st["published_site_hash"] = lp["site_hash"]
    st["last_promote"] = {"date": now().isoformat(timespec="seconds"), "commit": git("rev-parse", c["main_branch"], cwd=site).stdout.strip(), "entries": live}
    save_state(st)
    print(f"Promoted: {live} entries live on {c['main_branch']}; published_hash set." + ("" if initial else " The host deploys main to production."))
    rc = after_deploy(c, before, "promote") if wait and not initial else 0
    return profile_sync(c) or rc

# ---------------------------------------------------------------- showcase, status, release, rebuild
def showcase(args):
    c, st = cfg(), state(); entries = {e["id"]: e for e in read_jsonl(ENTRIES)}
    if args[:1] == ["intent"]:
        sid = args[1] if len(args) > 1 else die("usage: showcase intent <staging_id> [--replaces <entry_id>]")
        if sid not in {s["id"] for s in read_jsonl(STAGING)}: die(f"no staging item {sid}")
        rep = args[args.index("--replaces") + 1] if "--replaces" in args else None
        st["showcase_intents"] = [i for i in st["showcase_intents"] if i["staging_id"] != sid] + [
            {"staging_id": sid, "replaces": rep, "added": now().date().isoformat(), "source": "user"}]
        save_state(st); print(f"intent: {sid}" + (f" replaces {rep}" if rep else "") + " once it is renovated and public"); return 0
    if not 1 <= len(args) <= c["max_highlights"]: die(f"give 1-{c['max_highlights']} entry ids")
    cur = current_employers()
    for i in args:
        e = entries.get(i) or die(f"no entry {i}")
        if e.get("visibility") != "public": die(f"{i} is private")
        if e.get("employer") in cur: die(f"{i} is the current employer's: never highlighted")
        if not e.get("site_card"): die(f"{i} has no site_card yet (renovate writes it)")
    st["showcase"] = list(args); save_state(st); print("showcase: " + ", ".join(args) + " (takes effect at the next publish)"); return 0


# ---------------------------------------------------------------- a profile README (e.g. a GitHub profile repo)
# Cockpit owns only the block between COCKPIT:START/END; everything else in the README is the user's, kept byte for byte.
# Other generated blocks (e.g. a latest-posts list written by the profile repo's own Action) are never touched.
P_START, P_END = "<!-- COCKPIT:START -->", "<!-- COCKPIT:END -->"
P_NOTE = "<!-- Written by cockpit on every website promote. Edit outside the COCKPIT markers; anything inside is replaced. -->"

def profile_dir(c): p = pathlib.Path(c["profile"]["repo"]); return (p if p.is_absolute() else ROOT / p).resolve()

def project_of(row): return row["where"].split(" · ")[0].strip()

def profile_top(c, data, ids):
    """The top public entries for the block: highlighted entries (the homepage case studies) first; then impact; then
    recency (year); then rank score; a metric without a number only breaks the remaining ties; slug last. At most
    `per_project` (2) entries per project, the project being the first part of the card's `where`
    ("Shelfie · Example Corp" -> Shelfie)."""
    ents = {e["id"]: e for e in read_jsonl(ENTRIES)}
    rows = sorted(zip(data["entries"], ids), key=lambda p: (not p[0].get("highlight"), -p[0]["impact"], -int(p[0]["year"]),
                                                            -ents[p[1]].get("rank_score", 0), not re.search(r"\d", p[0]["metric"]), p[0]["id"]))
    top, cap, out, per = c["profile"].get("top", 5), c["profile"].get("per_project", 2), [], {}
    for r, eid in rows:
        k = project_of(r)
        if per.get(k, 0) >= cap: continue
        per[k] = per.get(k, 0) + 1; out.append((r, ents[eid]))
        if len(out) == top: break
    return out

def profile_line(row, site):
    """One line per entry: its public headline, linked to its bragDoc card; the metric only when it adds something."""
    nums = re.findall(r"\d[\d,.]*", row["metric"])
    extra = "" if nums and all(n.rstrip(".,") in row["title"] for n in nums) else f" · {row['metric']}"
    return f"- [{row['title']}]({site}/bragdoc#{row['id']}){extra}"

def profile_block(c):
    """(markdown block, problems): public channel only, linted for disclosure and voice."""
    data, ids, problems, _ = build()
    if problems: return None, ["the site data doesn't build: " + p for p in problems]
    prof = json.loads((DATA / "profile.json").read_text(encoding="utf-8"))["contacts"]
    site = c["site_url"].rstrip("/")
    host = urllib.parse.urlsplit((prof.get("website") or {}).get("value", "")).netloc or "Website"
    links = " · ".join(f"[{label}]({prof[k]['value']})" for k, label in (("website", host), ("medium", "Medium"), ("linkedin", "LinkedIn"))
                       if prof.get(k, {}).get("value") and "public" in prof.get(k, {}).get("channels", []))
    intro, picked = c["profile"]["intro"], profile_top(c, data, ids)
    head = [*[l + ("\\" if i < len(intro) - 1 else "") for i, l in enumerate(intro)], "", f"**Selected work** ([the full bragDoc]({site}/bragdoc))", ""]
    lines = [P_START, P_NOTE, *head, *[profile_line(r, site) for r, _ in picked], "", links, P_END]
    text = "\n".join(lines)
    # disclosure, as the site's own gate does it: each entry's strings with that entry as context (relative cost
    # figures are allowed only from past employers or clients), and the rest of the block as one document
    ctx = lint_context(read_jsonl(ENTRIES))
    found = [x for r, e in picked for x in lint_check([r["title"], r["metric"]], "public", ctx, leak_terms(e.get("public_constraints", [])), entry=e)]
    found += lint_check([l for l in head if l] + [links], "public", ctx, entry=NO_ENTRY)
    problems = [f"public lint: {why} | {line[:100]}" for _, line, why in found]
    visible = [l for l in lines if not l.startswith("<!--")]
    # voice: the EXTROVERT voice rules (no em dashes, banned phrases, US spelling, ...)
    import voice_lint
    vcfg = json.loads((DATA / "extrovert/config.json").read_text(encoding="utf-8"))
    problems += [f"voice lint: {v}" for v in voice_lint.lint("\n".join(visible), vcfg)]
    return text, problems

def merge_profile(readme, block, where="bottom"):
    """The README with the cockpit block replaced (or, the first time, inserted at `where`). Everything outside the
    markers is kept byte for byte, including the user's line endings; other generated blocks are never touched."""
    nl = "\r\n" if "\r\n" in readme else "\n"
    b = block.replace("\n", nl)
    if P_START in readme and P_END in readme:
        i, j = readme.index(P_START), readme.index(P_END) + len(P_END)
        return readme[:i] + b + readme[j:]
    if where == "top": return b + nl + nl + readme
    return readme.rstrip("\r\n") + nl + nl + b + nl

def profile_current_block(c):
    """The cockpit block as it stands in the profile repo's README on origin (None if the markers aren't there)."""
    d = profile_dir(c)
    git("fetch", "--quiet", "origin", cwd=d, check=False)
    text = git("show", f"origin/{c['profile'].get('branch', 'main')}:{c['profile'].get('readme', 'README.md')}", cwd=d, check=False).stdout
    if P_START not in text or P_END not in text: return None
    return text[text.index(P_START):text.index(P_END) + len(P_END)].replace("\r\n", "\n")

def profile_status(c):
    if not c.get("profile"): return "not configured"
    if not (profile_dir(c) / ".git").exists(): return f"{c['profile']['repo']} is not cloned"
    block, problems = profile_block(c)
    if problems: return "the block doesn't pass its gates: " + "; ".join(problems[:3])
    cur = profile_current_block(c)
    if cur is None: return "no COCKPIT block in the profile README yet (it's added at the next promote)"
    return "current" if cur == block else "out of date: the next promote updates it (or run `runway.py profile --write`)"

def profile_write(c):
    """Update the cockpit block in the profile README: pull --rebase first (an Action may commit there too), merge,
    commit, push. Nothing happens if the block is unchanged. -> exit code."""
    d = profile_dir(c); pc = c["profile"]
    if not (d / ".git").exists(): die(f"{pc['repo']} is not cloned")
    block, problems = profile_block(c)
    if problems: die("profile block gates failed; nothing written:\n  " + "\n  ".join(problems))
    if git("status", "--porcelain", cwd=d).stdout.strip(): die(f"{pc['repo']} has uncommitted changes")
    git("pull", "--rebase", "--quiet", "origin", pc.get("branch", "main"), cwd=d)
    path = d / pc.get("readme", "README.md")
    with open(path, encoding="utf-8", newline="") as f: old = f.read()
    new = merge_profile(old, block, pc.get("insert", "bottom"))
    if new == old: print("Profile README: the cockpit block is already current."); return 0
    path.write_text(new, encoding="utf-8", newline="")
    git("add", pc.get("readme", "README.md"), cwd=d)
    trailer = c.get("commit_trailer")
    git("commit", "-q", "-m", "cockpit: update the selected-work block from the public bragDoc" + (f"\n\n{trailer}" if trailer else ""), cwd=d)
    push = git("push", "-q", "origin", pc.get("branch", "main"), cwd=d, check=False)
    print("Profile README: cockpit block updated" + (" and pushed." if push.returncode == 0 else f"; PUSH FAILED: {push.stderr.strip()}"))
    return 0 if push.returncode == 0 else 1

def profile_sync(c):
    """After a promote: update the profile README's cockpit block if it changed. A failure is reported; it never undoes
    the site promote."""
    if not c.get("profile"): return 0
    if not (profile_dir(c) / ".git").exists():
        print(f"Profile README: {c['profile']['repo']} isn't cloned here (a cloud session?); skipped. Run `runway.py profile --write` where it is."); return 0
    try: return profile_write(c)
    except SystemExit: print("Profile README not updated (see above); the site promote stands."); return 1

def status():
    c, st = cfg(), state(); site = site_dir(c)
    data, ids, problems, notes = build()
    entries = read_jsonl(ENTRIES)
    live = [e["id"] for e in entries if e.get("published_hash") and e.get("visibility") == "public" and bp.payload_hash(e) == e["published_hash"]]
    changed, removed, site_changed = pending(data, st)
    print(f"Live: {len(live)} | pending: {len(changed)} changed, {len(removed)} to remove | site data changed since promote: {'yes' if site_changed else 'no'}")
    out = subprocess.run([sys.executable, str(ROOT / "scripts/bragdoc_public.py"), "pending"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    print("bragdoc_public.py pending:\n  " + out.replace("\n", "\n  "))
    if problems: print("Gate problems (publish would block):\n  " + "\n  ".join(problems))
    for n in notes: print(f"Showcase {n}")
    blockers, prof = [], json.loads((DATA / "profile.json").read_text(encoding="utf-8"))
    dom = (prof.get("contacts", {}).get("email_domain") or {}).get("value", "")
    if not dom: blockers.append("profile email_domain is empty")
    if not st.get("email_verified"): blockers.append(f"waiting for your confirmation that a test email to {dom or 'the site address'} arrived (runway.py confirm email)")
    if (site / ".git").exists():
        if git("cat-file", "-e", f"{c['main_branch']}:{c['pdf']['dir']}/{pdf_name(c)}", cwd=site, check=False).returncode:
            blockers.append(f"{c['pdf']['dir']}/{pdf_name(c)} is not on {c['main_branch']} yet")
    else: blockers.append(f"site repo {site} not found")
    if not preview_url(c, c["content_branch"]): blockers.append("preview URL not configured (preview_url in data/runway/config.json)")
    print("Launch blockers:\n  " + ("\n  ".join(blockers) if blockers else "none"))
    print("Rebuilds and production:\n  " + "\n  ".join(rebuild_status(c, st)))
    if c.get("repos"): print("Repos section: " + repos_status(c["repos"]))
    print("Profile README (cockpit block): " + profile_status(c))
    return 0

def tagged_repos(owner, topic, fetch=None):
    """Public, non-fork, non-archived repos of owner with the topic, most recently pushed first (the site's own rule)."""
    status, _, body = (fetch or http_get)(f"https://api.github.com/users/{owner}/repos?type=owner&sort=pushed&per_page=100")
    repos = json.loads(body)
    keep = [r for r in repos if not r.get("fork") and not r.get("archived") and not r.get("private") and topic in (r.get("topics") or [])]
    return [r["name"] for r in sorted(keep, key=lambda r: r.get("pushed_at") or "", reverse=True)]

def repos_status(r):
    """config repos {owner, topic, max}: the repos a site lists by GitHub topic (if it has such a section)."""
    owner, topic, mx = r.get("owner"), r.get("topic"), int(r.get("max", 6))
    if not (owner and topic): return "repos.owner / repos.topic not set"
    try: names = tagged_repos(owner, topic)
    except Exception as e: return f"GitHub API unreachable ({type(e).__name__})"
    if not names: return f"no public repos of {owner} tagged '{topic}' yet (tag repos on GitHub: About -> Topics)"
    return f"{len(names)} tagged '{topic}' (the site shows the first {min(len(names), mx)}, most recently pushed first): " + ", ".join(names)

def rebuild_status(c, st):
    """Lines for status: the local hook, the daily Action, production freshness, the Medium feed, the last live check."""
    out, hs = [], hook_state(c)[0]
    out.append({"ok": "deploy hook (local file): present and valid (never shown)",
                "missing": f"deploy hook (local file): missing ({c['deploy_hook_file']}); /runway rebuild falls back to Actions -> Run workflow",
                "invalid": f"deploy hook (local file): present but doesn't match deploy_hook_pattern; fix {c['deploy_hook_file']}"}[hs])
    v = st.get("rebuild_action_verified")
    out.append(f"daily-rebuild Action (its deploy-hook secret): " + (f"verified {v} (a manual run redeployed production)" if v
               else "not verified yet; the secret can't be read from here: run `runway.py verify-action`, then Actions -> Run workflow"))
    stamp, sched = live_stamp(c), last_daily_run(c)
    if stamp:
        fresh = stamp >= sched
        late = (dt.datetime.now(dt.timezone.utc) - sched) < dt.timedelta(hours=1)
        out.append(f"production last built {when(stamp)}: " + ("after" if fresh else "before") + f" the last scheduled daily rebuild ({when(sched)})"
                   + ("" if fresh else (" (GitHub schedules can lag up to ~1 h)" if late else "; the daily rebuild didn't run or failed")))
    else: out.append(f"production ({c['site_url']}): unreachable")
    h = feed_health(c)
    out.append({"ok": lambda: f"posts feed: ok, {h[1]} posts; latest \"{h[2]['title']}\" ({h[2]['date'][:16]})",
                "empty": lambda: "posts feed: ok but empty (0 posts)",
                "failing": lambda: f"posts feed: FAILING ({h[1]})",
                "off": lambda: "posts feed: not configured"}[h[0]]())
    lc = st.get("last_live_check")
    out.append("last live check: " + ("none yet" if not lc else f"{lc['date']} after {lc['trigger']}: " +
               ("production did not redeploy in time" if not lc.get("deployed") else f"{lc.get('passed', 0)} passed, {lc.get('failed', 0)} failed")))
    return out

def release_current():
    """The user's one instruction ('release current-employer entries'): every private current-employer entry -> public."""
    cur = current_employers(); entries = read_jsonl(ENTRIES)
    held = [e for e in entries if e.get("employer") in cur and e.get("visibility") != "public"]
    if not held: print("No held current-employer entries."); return 0
    for e in held: e["visibility"] = "public"
    write_jsonl(ENTRIES, entries)
    print(f"Released {len(held)}: " + ", ".join(e["id"] for e in held))
    return publish()

# ---------------------------------------------------------------- rebuilds, production checks, the Medium feed
# The deploy hook URL is a secret: it is read here and POSTed, and never printed, logged or put in an error message.
def hook_state(c):
    """('ok', url) | ('missing', None) | ('invalid', None)."""
    p = ROOT / c["deploy_hook_file"]
    if not p.is_file(): return "missing", None
    url = p.read_text(encoding="utf-8").strip()
    if hook_pattern(c).match(url) or (os.environ.get("RUNWAY_ALLOW_LOCAL_HOOK") == "1" and LOCAL_HOOK_URL.match(url)): return "ok", url
    return "invalid", None

def post_hook(url):
    """(ok, short reason). The reason never contains the URL (urllib can echo it in some exceptions)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="POST", data=b""), timeout=30) as r:
            return 200 <= r.status < 300, f"HTTP {r.status}"
    except urllib.error.HTTPError as e: return False, f"HTTP {e.code}"
    except urllib.error.URLError as e: return False, f"network error ({type(e.reason).__name__})"
    except Exception as e: return False, type(e).__name__

def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "cockpit-runway", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.headers, r.read()

def live_stamp(c):
    """When production's home page was built: its Last-Modified (a new deployment moves it). None if unreachable."""
    try:
        _, headers, _ = http_get(f"{c['site_url']}/?runway={int(time.time())}")
        lm = headers.get("Last-Modified")
        return email.utils.parsedate_to_datetime(lm) if lm else None
    except Exception: return None

def wait_live(c, before, timeout=None, poll=None):
    """Wait until production serves a deployment newer than `before` (the pre-trigger Last-Modified). -> datetime | None."""
    timeout = timeout if timeout is not None else c.get("deploy_wait_s", 900)
    poll = poll if poll is not None else c.get("deploy_poll_s", 15)
    end = time.monotonic() + timeout
    while True:
        stamp = live_stamp(c)
        if stamp and (before is None or stamp > before): return stamp
        if time.monotonic() + poll > end: return None
        time.sleep(poll)

def when(d): return d.astimezone().strftime("%d %b %H:%M %Z") if d else "unknown"   # local time
def dur(s): return f"{s // 60} min" + (f" {s % 60} s" if s % 60 else "") if s >= 60 else f"{s} s"

def live_tests(c):
    """config live_test_cmd in the site repo -> (exit code, passed, failed, problems). Reads Playwright-style output;
    problems: one line per failing or flaky (passed only on retry) test: its title and its first error line."""
    rc, out = run_cmd(c["live_test_cmd"], site_dir(c))
    num = lambda w: int(m.group(1)) if (m := re.search(rf"(\d+) {w}\b", out)) else 0
    lines, problems = out.splitlines(), []
    for i, l in enumerate(lines):
        if not re.match(r"\s+\d+\) \[", l): continue
        title = re.sub(r"\s+─+$", "", l.strip())
        err = next((x.strip() for x in lines[i + 1:i + 40] if re.match(r"\s*(Error|TimeoutError|expect)\b.*", x)), "")
        if title not in [p.split(" | ")[0] for p in problems]: problems.append(title + (f" | {err[:160]}" if err else ""))
    if num("flaky"): problems.insert(0, f"{num('flaky')} flaky (passed only on the retry):")
    return rc, num("passed") + num("flaky"), num("failed"), problems

def warm_up(c):
    """Fetch the pages (config warm_paths) and the same-origin assets they reference (config warm_asset_regex) once, so
    the live tests don't run against a cold edge cache right after a deploy. -> count."""
    seen, pages, rx = set(), c.get("warm_paths") or ["/"], c.get("warm_asset_regex")
    for p in pages:
        try: _, _, body = http_get(f"{c['site_url']}{p}", timeout=30)
        except Exception: continue
        if rx: seen.update(re.findall(rx, body.decode("utf-8", "replace")))
    for a in sorted(seen):
        try: http_get(f"{c['site_url']}{a}", timeout=30)
        except Exception: pass
    return len(seen)

def after_deploy(c, before, trigger):
    """Wait for the production deploy, run the live smoke tests, record and report. -> exit code."""
    print(f"Waiting for the production deploy (up to {c.get('deploy_wait_s', 900) // 60} min)...", flush=True)
    stamp = wait_live(c, before)
    st = state()
    if not stamp:
        st["last_live_check"] = {"date": now().isoformat(timespec="seconds"), "trigger": trigger, "deployed": None}
        save_state(st)
        print("Production did not redeploy in time. A failed build usually keeps the previous version live: check the "
              "deployment on your host. Live tests not run."); return 1
    print(f"Production redeployed ({when(stamp)}); warmed the cache ({warm_up(c)} files), running the live tests...", flush=True)
    rc, passed, failed, failing = live_tests(c)
    st["last_live_check"] = {"date": now().isoformat(timespec="seconds"), "trigger": trigger, "deployed": stamp.isoformat(),
                             "passed": passed, "failed": failed}
    save_state(st)
    print(f"Live tests against {c['site_url']}: {passed} passed, {failed} failed"
          + ("" if not failing else "\n  " + "\n  ".join(failing)))
    return 0 if rc == 0 and failed == 0 else 1

def rebuild(wait=True, reason="manual"):
    c = cfg(); hs, url = hook_state(c)
    if hs == "missing":
        print("No local deploy hook here (a cloud session, or not set up yet). Use GitHub instead: the site repo -> Actions -> "
              "daily-rebuild -> Run workflow."); return 0
    if hs == "invalid": die(f"{c['deploy_hook_file']} doesn't hold a deploy-hook URL matching deploy_hook_pattern")
    before = live_stamp(c) if wait else None
    ok, why = post_hook(url)
    if not ok: die(f"the deploy hook request failed: {why}")
    st = state(); st["last_rebuild"] = {"date": now().isoformat(timespec="seconds"), "reason": reason}; save_state(st)
    print(f"Deploy hook accepted ({why}): the host is rebuilding main for production.")
    return after_deploy(c, before, f"rebuild: {reason}") if wait else 0

class FeedError(Exception): pass

def feed_items(c):
    """[{title, link, date}] newest first, from the posts RSS feed (config medium.feed; any RSS feed works).
    Raises FeedError when the feed can't be read."""
    try: status, _, body = http_get(c["medium"]["feed"], timeout=20)
    except urllib.error.HTTPError as e: raise FeedError(f"HTTP {e.code}")
    except Exception as e: raise FeedError(type(getattr(e, "reason", e)).__name__)
    try: root = ET.fromstring(body)
    except ET.ParseError: raise FeedError("not valid RSS")
    if root.find("channel") is None: raise FeedError("not an RSS feed")
    return [{"title": (i.findtext("title") or "").strip(), "link": (i.findtext("link") or "").strip(),
             "date": (i.findtext("pubDate") or "").strip()} for i in root.iter("item")]

def feed_health(c):
    """('ok', n, latest) | ('empty', 0, None) | ('failing', reason, None) | ('off', 0, None)."""
    if not (c.get("medium") or {}).get("feed"): return "off", 0, None
    try: items = feed_items(c)
    except FeedError as e: return "failing", str(e), None
    return ("ok", len(items), items[0]) if items else ("empty", 0, None)

def medium_id(url):
    """A post's id (for Medium, the hex tail of the slug) so any form of a post's URL matches its feed link."""
    path = urllib.parse.urlsplit(url.strip()).path.rstrip("/")
    m = re.search(r"-([0-9a-f]{8,16})$", path) or re.search(r"/p/([0-9a-f]{8,16})$", path)
    return m.group(1) if m else path.lower()

def await_post(url, wait=True, interval=None, max_s=None):
    """Poll the feed until the post appears (or the time runs out), then rebuild either way."""
    c = cfg(); m = c["medium"]
    interval = interval if interval is not None else m.get("poll_s", 120)
    max_s = max_s if max_s is not None else m.get("max_s", 1800)
    want, start, polls = medium_id(url), time.monotonic(), 0
    while True:
        polls += 1
        try:
            items = feed_items(c); found, note = any(medium_id(i["link"]) == want for i in items), f"{len(items)} posts in the feed"
        except FeedError as e: found, note = False, f"feed failing: {e}"
        waited = int(time.monotonic() - start)
        if found:
            print(f"The post is in the feed (poll {polls}, after {dur(waited)}). Rebuilding.", flush=True); break
        if waited + interval > max_s:
            print(f"The post isn't in the feed after {dur(max_s)} ({polls} polls; {note}). Rebuilding anyway; if the "
                  "feed is slow, the daily rebuild will pick it up.", flush=True); break
        print(f"poll {polls}: not in the feed yet ({note}); next poll in {interval} s", flush=True)
        time.sleep(interval)
    return rebuild(wait=wait, reason=f"post {want}")

def last_daily_run(c, at=None):
    """The most recent scheduled time of the daily-rebuild Action (config daily_rebuild_utc, HH:MM UTC)."""
    at = at or dt.datetime.now(dt.timezone.utc)
    hh, mm = map(int, c.get("daily_rebuild_utc", "00:30").split(":"))
    t = at.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t if t <= at else t - dt.timedelta(days=1)

def verify_action(max_s=None):
    """The repo secret can't be read from here (no GitHub token by design), so prove it: a manual run must redeploy prod."""
    c = cfg(); before = live_stamp(c); max_s = max_s or c.get("deploy_wait_s", 900)
    print("Now run it: GitHub -> the site repo -> Actions -> daily-rebuild -> Run workflow. Watching production for the "
          f"redeploy (up to {dur(max_s)})...", flush=True)
    stamp = wait_live(c, before, timeout=max_s)
    if not stamp: die("production did not redeploy: check the workflow run (a missing secret fails it with a clear message)")
    st = state(); st["rebuild_action_verified"] = now().date().isoformat(); save_state(st)
    print(f"Verified: the Action's deploy hook works (production redeployed {when(stamp)}).")
    return after_deploy(c, stamp - dt.timedelta(seconds=1), "verify-action")

def preview():
    c = cfg(); site = site_dir(c)
    data, ids, problems, notes = build()
    if problems: die("gates failed; nothing written:\n  " + "\n  ".join(problems))
    files = write_site(c, site, data, render_pdf(c))
    print(f"Wrote {', '.join(files)} into {site} (uncommitted); build + check passed. {len(ids)} entries.")
    for n in notes: print(f"  {n}")
    return 0

def table():
    data, ids, problems, notes = build()
    print(f"{'site id':<44} {'field':<9} {'imp':<4} {'year':<5} {'metric':<28} title")
    for (r, eid) in zip(data["entries"], ids):
        print(f"{r['id'][:43]:<44} {r['field']:<9} {r['impact']:<4} {r['year']:<5} {r['metric'][:27]:<28} {'* ' if r.get('highlight') else ''}{r['title']}  [{eid}]")
    for n in notes: print(f"  {n}")
    if problems: print("PROBLEMS:\n  " + "\n  ".join(problems)); return 1
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "table": return table()
    if cmd == "build":
        data, ids, problems, notes = build()
        if problems: die("gates failed:\n  " + "\n  ".join(problems))
        if "--out" in rest: pathlib.Path(rest[rest.index("--out") + 1]).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"OK: {len(ids)} entries, {sum(bool(r.get('highlight')) for r in data['entries'])} highlights, site hash {site_hash(data)[:12]}"); return 0
    if cmd == "preview": return preview()
    if cmd == "publish": return publish(initial="--initial" in rest, if_pending="--if-pending" in rest)
    if cmd == "promote" and rest[:1] and rest[0].startswith("code/"): return promote_code(rest[0], wait="--no-wait" not in rest)
    if cmd == "promote": return promote(initial="--initial" in rest, wait="--no-wait" not in rest)
    if cmd == "ship" and rest and not rest[0].startswith("--"):
        return ship(rest[0], slug=rest[rest.index("--slug") + 1] if "--slug" in rest else None)
    if cmd == "showcase" and rest: return showcase(rest)
    if cmd == "status": return status()
    if cmd == "release" and rest == ["current-employer"]: return release_current()
    if cmd == "confirm" and rest == ["email"]:
        st = state(); st["email_verified"] = True; save_state(st); print("email_verified = true"); return 0
    if cmd == "rebuild": return rebuild(wait="--no-wait" not in rest)
    if cmd == "await-post" and rest and not rest[0].startswith("--"):
        num = lambda f: int(rest[rest.index(f) + 1]) if f in rest else None
        return await_post(rest[0], wait="--no-wait" not in rest, interval=num("--interval"), max_s=num("--max"))
    if cmd == "verify-action": return verify_action(int(rest[rest.index("--max") + 1]) if "--max" in rest else None)
    if cmd == "profile":
        c = cfg()
        if "--write" in rest: return profile_write(c)
        block, problems = profile_block(c)
        print(block or ""); print("Problems:\n  " + "\n  ".join(problems) if problems else "Gates: public lint + voice lint pass")
        print("Profile README: " + profile_status(c)); return 1 if problems else 0
    if cmd == "live-check":
        c = cfg(); rc, passed, failed, failing = live_tests(c)
        print(f"Live tests against {c['site_url']}: {passed} passed, {failed} failed" + ("" if not failing else "\n  " + "\n  ".join(failing)))
        return 0 if rc == 0 and failed == 0 else 1
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
