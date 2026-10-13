#!/usr/bin/env python3
"""FOURTHWALL: documents this repo and exports a public, generalized copy of it. Deterministic work only.
  fourthwall.py log '<json>'|-                    journal entry {kind, title, text, tags[, commit, source, tier, date, date_approx]}
  fourthwall.py journal [--kind K]                list journal entries
  fourthwall.py changelog-commits                 commits since state.last_changelog_commit (to summarize, never copy)
  fourthwall.py changelog-append <ver> '<json>'|- {"date": "YYYY-MM-DD", "entries": [...]}: lint, write CHANGELOG, advance state
  fourthwall.py lint-public <file> [--voice]      public disclosure lint + deny list (+ voice lint)
  fourthwall.py mark-generalized <target>         record the current source hash for a generalized manifest entry
  fourthwall.py export                            build the public tree from the manifest into staging_dir, run every leak check
  fourthwall.py diff                              full diff: staging vs the last published tree (clone_dir)
  fourthwall.py approve <export_hash>             record approval of a clean export (only on the user's explicit word)
  fourthwall.py publish <X.Y.Z> "<summary>"       commit + tag + push an approved export from clone_dir (never automatic);
                                                  the clone's local author = profile names.public_full + commit_email
  fourthwall.py set-ip-checked                    the user confirmed their employer's IP / side-project policy
  fourthwall.py set-commit-email <addr>           commit email for the public clone (must be a GitHub noreply address)
  fourthwall.py status
Paths and the remote live in data/fourthwall/state.json; the allowlist in manifest.json; deny terms in denylist.json.
"""
import datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, pathlib
from _common import ROOT, DATA, read_jsonl, append_jsonl
from disclosure_lint import check as lint_check, context as lint_context, to_lines
from voice_lint import lint as voice_lint

FW = DATA / "fourthwall"
JOURNAL, STATE, MANIFEST, DENY = FW / "journal.jsonl", FW / "state.json", FW / "manifest.json", FW / "denylist.json"
CHANGELOG = ROOT / "fourthwall/CHANGELOG.md"
MARKER = ".fourthwall-staging"
KINDS, TIERS, TRANSFORMS = {"decision", "lesson", "milestone", "bug"}, {"T0", "T1", "T2", "T3"}, {"copy", "generalize", "template"}
TEXT_EXT = {".md", ".py", ".json", ".jsonl", ".txt", ".css", ".html", ".yml", ".yaml", ".toml", ".gitignore", ".gitattributes", ""}
CODE_EXT = {".py", ".json", ".jsonl", ".css"}   # the prose-only "cost word near a number" rule is skipped here; every other check runs
PROSE_ONLY = ("employer cost figure", "current-employer cost figure", "cost figure not from an allowed",
              "revenue or contract figure", "current-employer user/tenant/customer count", "user count not from an allowed",
              "user/tenant/customer count")   # number rules read prose; code files only trip them by accident

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def die(msg, code=1): print(f"BLOCKED: {msg}"); sys.exit(code)
def load(p, default): return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def save(p, obj): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
def payload(raw): return json.loads(sys.stdin.read() if raw == "-" else raw)
def sha(b): return hashlib.sha256(b).hexdigest()
def state(): return load(STATE, {})
def resolve(p): return (ROOT / p).resolve() if not os.path.isabs(p) else pathlib.Path(p)
def git(*a, cwd=ROOT, check=True):
    p = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode: die(f"git {' '.join(a)} failed: {(p.stderr or p.stdout).strip()}")
    return p.stdout

# ---------------- manifest ----------------
def excluded(src, rules):
    """True if a repo source path is structurally excluded from the public copy."""
    s = src.replace("\\", "/")
    while s.startswith("./"): s = s[2:]   # not lstrip("./"): that would turn ".git/x" into "git/x"
    if any(s.startswith(p) for p in rules.get("excluded_prefixes", [])): return True
    low = s.lower()
    if any(t in low for t in rules.get("excluded_substrings", [])): return True
    return pathlib.PurePosixPath(s).name in rules.get("excluded_names", [])

def manifest_problems(man):
    out, targets = [], set()
    rules = man.get("rules", {})
    for i, f in enumerate(man.get("files", [])):
        w = f"files[{i}] ({f.get('target')})"
        t, tr, src = f.get("target", ""), f.get("transform"), f.get("source", "")
        if tr not in TRANSFORMS: out.append(f"{w}: transform must be copy|generalize|template")
        if not t or t.startswith(("/", "..")) or ".." in pathlib.PurePosixPath(t).parts: out.append(f"{w}: bad target path")
        if t in targets: out.append(f"{w}: duplicate target")
        targets.add(t)
        if any(t.startswith(p) for p in ("raw/", "inbox/", "out/", ".git/")): out.append(f"{w}: target in an excluded folder")
        if t.startswith("data/") and tr != "template": out.append(f"{w}: data/ targets may only come from templates")
        if tr in ("copy", "generalize"):
            if src.startswith("fourthwall/") and tr == "copy":
                pass   # generated public files (README, CHANGELOG)
            elif excluded(src, rules): out.append(f"{w}: source '{src}' is structurally excluded")
            if not (ROOT / src).is_file(): out.append(f"{w}: source '{src}' not found")
        if tr == "template" and not (src.startswith("fourthwall/templates/") and (ROOT / src).is_file()):
            out.append(f"{w}: template source must be an existing file under fourthwall/templates/")
        if tr == "generalize":
            g = f.get("generalized", "")
            if not (g.startswith("fourthwall/generalized/") and (ROOT / g).is_file()): out.append(f"{w}: generalized copy missing under fourthwall/generalized/")
    return out

def file_bytes(f):
    if f["transform"] == "generalize":
        cur = sha((ROOT / f["source"]).read_bytes())
        if f.get("source_hash") != cur:
            return None, f"STALE: {f['source']} changed since its generalized copy was written; regenerate {f['generalized']} and run mark-generalized {f['target']}"
        return (ROOT / f["generalized"]).read_bytes(), None
    return (ROOT / f["source"]).read_bytes(), None

# ---------------- deny list ----------------
def deny_terms():
    """[(label, compiled_regex)] from denylist.json plus terms derived from profile, employment, staging and the disclosure policy."""
    d = load(DENY, {})
    terms = []
    def add(label, rx): terms.append((label, re.compile(rx)))
    for t in d.get("terms", []): add(t, rf"(?i)(?<![\w]){re.escape(t)}(?![\w])")
    for t in d.get("exact_terms", []): add(t, rf"(?<![\w]){re.escape(t)}(?![\w])")
    for r in d.get("regex", []): add(r, r)
    prof = load(DATA / "profile.json", {})
    if d.get("derive", {}).get("profile", True):
        forms = {v for k, v in (prof.get("names") or {}).items() if k in ("short", "public_full", "formal") and isinstance(v, str)}
        variants = set()
        for full in forms | ({prof["name"]} if prof.get("name") else set()):
            variants |= {full, " ".join(full.split()[-2:]), *(w for w in full.split() if len(w) >= 5)}
        for v in sorted(variants - {""}):
            add(f"name: {v}", rf"(?i){re.escape(v)}")
        for k, c in (prof.get("contacts") or {}).items():
            v = (c or {}).get("value", "")
            if not v: continue
            if k == "phone":
                digits = re.sub(r"\D", "", v)[-10:]
                add("phone", r"[\s-]?".join(digits))
            elif k.startswith("email"): add(f"{k}", rf"(?i){re.escape(v)}")
        if prof.get("location"): add("location", rf"(?i){re.escape(prof['location'].split(',')[0])}")
    if d.get("derive", {}).get("employers", True):
        for j in load(DATA / "bragdoc/employment.json", []):
            add(f"employer: {j['employer']}", rf"(?i){re.escape(j['employer'])}")
            first = j["employer"].split()[0]
            if len(first) >= 5: add(f"employer: {first}", rf"(?i)(?<!\w){re.escape(first)}(?!\w)")
    if d.get("derive", {}).get("projects", True):
        ignore = {x.lower() for x in d.get("derive_ignore", [])}
        seen = set()
        for s in read_jsonl(DATA / "bragdoc/staging.jsonl"):
            p = (s.get("project") or "").split(":")[0].strip()
            if not p or p.lower() in ignore or p.lower() in seen: continue
            seen.add(p.lower())
            exact = len(p) <= 4 or p in d.get("exact_terms", [])
            add(f"project: {p}", rf"(?<!\w){re.escape(p)}(?!\w)" if exact else rf"(?i)(?<!\w){re.escape(p)}(?!\w)")
    if d.get("derive", {}).get("policy", True):
        pol = load(DATA / "bragdoc/disclosure_policy.json", {})
        for k in ("always_banned", "current_employer_internal_names"):
            for r in pol.get("terms", {}).get(k, []): add(f"policy {k}: {r}", r)
    return terms

def author_line(rel, line, d):
    for ex in d.get("author_line_exemptions", []):
        if rel == ex["file"] and re.search(ex["line_regex"], line): return True
    return False

# ---------------- leak checks ----------------
def is_text(p): return p.suffix.lower() in TEXT_EXT or p.name in (".gitignore", ".gitattributes", "LICENSE")

def scan_secrets(root, files):
    from detect_secrets import SecretsCollection
    from detect_secrets.settings import default_settings
    hits = []
    with default_settings():
        sc = SecretsCollection()
        for rel in files: sc.scan_file(str(root / rel))
        for fname, secrets in sc.data.items():
            for s in secrets:
                hits.append((pathlib.Path(fname).resolve().relative_to(root.resolve()).as_posix(), s.line_number, s.type))
    return hits

def leak_checks(root, man):
    d = load(DENY, {})
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != MARKER)
    targets = sorted(f["target"] for f in man["files"])
    report = {}
    structural = [f"unexpected file not in manifest: {x}" for x in sorted(set(files) - set(targets))]
    structural += [f"manifest file missing from staging: {x}" for x in sorted(set(targets) - set(files))]
    structural += manifest_problems(man)
    report["1 structural"] = structural
    report["2 secrets"] = [f"{f}:{n}: {t}" for f, n, t in scan_secrets(root, files)]
    ctx, exempt = lint_context(), {e["path"]: set(e["checks"]) for e in d.get("lint_exempt", [])}
    lint, deny, dash, terms = [], [], [], deny_terms()
    for rel in files:
        p = root / rel
        if not is_text(p): continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # the public copy has no em dashes anywhere (prose uses colons, commas or parentheses; code uses "\u2014")
        dash += [f"{rel}:{n}: em dash | {line.strip()[:120]}" for n, line in enumerate(text.splitlines(), 1) if "\u2014" in line]
        for n, line, why in lint_check(to_lines(text) if rel.endswith(".html") else text.splitlines(), "public", ctx):
            kind = why.split(":")[0].replace(" ", "_")
            if kind in exempt.get(rel, set()): continue
            if p.suffix.lower() in CODE_EXT and why.startswith(PROSE_ONLY): continue
            lint.append(f"{rel}:{n}: {why} | {line.strip()[:120]}")
        for n, line in enumerate(text.splitlines(), 1):
            for label, rx in terms:
                if rx.search(line) and not author_line(rel, line, d):
                    deny.append(f"{rel}:{n}: deny '{label}' | {line.strip()[:120]}")
    report["3 public lint"] = lint
    report["4 deny list"] = deny
    report["5 em dashes"] = dash
    return files, report

def tree_hash(root, files):
    return sha("\n".join(f"{f}\t{sha((root / f).read_bytes())}" for f in files).encode())

def build(staging, man):
    if staging.exists():
        if not (staging / MARKER).exists() and any(staging.iterdir()):
            die(f"{staging} exists and isn't a fourthwall staging dir (no {MARKER}); refusing to touch it")
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    (staging / MARKER).write_text("generated by fourthwall export; never edit by hand\n", encoding="utf-8")
    stale = []
    for f in sorted(man["files"], key=lambda f: f["target"]):
        data, err = file_bytes(f)
        if err: stale.append(err); continue
        out = staging / f["target"]; out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(data)
    return stale

def compare(staging, clone):
    """(added, modified, removed) vs the last published tree."""
    def listing(r, skip):
        return {p.relative_to(r).as_posix(): sha(p.read_bytes()) for p in r.rglob("*")
                if p.is_file() and not any(part in skip for part in p.relative_to(r).parts)} if r.exists() else {}
    a, b = listing(staging, {MARKER}), listing(clone, {".git"})
    return sorted(set(a) - set(b)), sorted(k for k in a if k in b and a[k] != b[k]), sorted(set(b) - set(a))

def export():
    st, man = state(), load(MANIFEST, {"files": []})
    problems = manifest_problems(man)
    if problems: die("manifest problems:\n  " + "\n  ".join(problems))
    staging = resolve(st["staging_dir"])
    if ROOT.resolve() in staging.resolve().parents or staging.resolve() == ROOT.resolve():
        die("staging_dir must be outside this repo")
    stale = build(staging, man)
    files, report = leak_checks(staging, man)
    if stale: report["0 generalized copies current"] = stale
    clean = not any(report.values())
    h = tree_hash(staging, files)
    added, modified, removed = compare(staging, resolve(st["clone_dir"]))
    print(f"Export: {len(files)} files -> {staging}\nexport hash: {h}\n")
    print("Files:\n" + "\n".join(f"  {f}" for f in files))
    print(f"\nVs last published ({st['clone_dir']}): {len(added)} added, {len(modified)} modified, {len(removed)} removed")
    for lbl, xs in (("+", added), ("~", modified), ("-", removed)):
        for x in xs: print(f"  {lbl} {x}")
    print("\nLeak report:")
    for k in sorted(report):
        print(f"  {'PASS' if not report[k] else 'FAIL'}  {k}" + ("" if not report[k] else "\n" + "\n".join(f"        {x}" for x in report[k])))
    print("\nCLEAN: ready for review. Approve with: fourthwall.py approve " + h if clean else "\nBLOCKED: fix every failure above, then export again.")
    (ROOT / "out").mkdir(exist_ok=True)
    save(ROOT / "out/fourthwall_export_report.json", {"hash": h, "clean": clean, "files": files, "report": report,
                                                       "added": added, "modified": modified, "removed": removed})
    st.update(last_export_hash=h, last_export_clean=clean, last_export_at=now().isoformat(), approved_export_hash=None, approved_at=None)
    save(STATE, st)
    return 0 if clean else 1

# ---------------- publish ----------------
def publish(version, summary):
    st = state()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version): die("version must be X.Y.Z")
    prev = [v["version"] for v in st.get("published_versions", [])]
    if prev and tuple(map(int, version.split("."))) <= tuple(map(int, prev[-1].split("."))): die(f"version must be greater than {prev[-1]}")
    if not st.get("approved_export_hash"): die("no approved export: run export, review it, and approve it first")
    staging = resolve(st["staging_dir"])
    if not (staging / MARKER).exists(): die("staging is missing; export again")
    files = sorted(p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file() and p.name != MARKER)
    h = tree_hash(staging, files)
    if not (st.get("last_export_clean") and h == st.get("last_export_hash") == st.get("approved_export_hash")):
        die("staging no longer matches the approved clean export; export and approve again")
    if not prev and not st.get("ip_policy_checked"):
        die("first publish is blocked until you confirm you've checked your employer's IP / side-project policy (set-ip-checked)")
    email = st.get("commit_email") or ""
    if not email.endswith("@users.noreply.github.com"): die("commit_email must be a GitHub noreply address (set-commit-email); never a personal address")
    author = ((load(DATA / "profile.json", {}).get("names") or {}).get("public_full") or "").strip()
    if not author: die("profile.json names.public_full is required: it is the public commit author name")
    clone, remote = resolve(st["clone_dir"]), st.get("remote", "")
    if not clone.exists():
        if not remote: die("remote is not set in state.json")
        git("clone", remote, str(clone))
    elif remote and git("remote", "get-url", "origin", cwd=clone).strip() != remote:
        die(f"{clone} has a different origin than {remote}")
    git("config", "--local", "user.email", email, cwd=clone)
    git("config", "--local", "user.name", author, cwd=clone)
    for p in list(clone.iterdir()):
        if p.name == ".git": continue
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    for rel in files:
        out = clone / rel; out.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(staging / rel, out)
    git("checkout", "-B", "main", cwd=clone)
    git("add", "-A", cwd=clone)
    git("commit", "-q", "-m", f"release v{version}: {summary}", cwd=clone)
    git("tag", "-a", f"v{version}", "-m", f"v{version}", cwd=clone)
    git("push", "-u", "origin", "main", "--tags", cwd=clone)
    commit = git("rev-parse", "HEAD", cwd=clone).strip()
    st.setdefault("published_versions", []).append({"version": version, "date": now().date().isoformat(), "export_hash": h, "commit": commit})
    st.update(approved_export_hash=None, approved_at=None)
    save(STATE, st)
    print(f"Published v{version} ({commit[:7]}) to {remote or clone}")
    if not prev:
        print("First publish: turn on the template setting yourself (GitHub -> repository -> Settings -> General -> 'Template repository'). This script never uses the GitHub CLI.")
    return 0

# ---------------- changelog / lint ----------------
def public_text_problems(text, voice=False, rel="(text)"):
    d, ctx, out = load(DENY, {}), lint_context(), []
    for n, line, why in lint_check(text.splitlines(), "public", ctx): out.append(f"line {n}: {why} | {line.strip()[:120]}")
    for n, line in enumerate(text.splitlines(), 1):
        for label, rx in deny_terms():
            if rx.search(line) and not author_line(rel, line, d): out.append(f"line {n}: deny '{label}' | {line.strip()[:120]}")
    if voice:
        cfg = load(DATA / "extrovert/config.json", {})
        out += [f"voice: {v}" for v in voice_lint(text, cfg)]
    return out

def commits_since(last):
    rng = f"{last}..HEAD" if last else "HEAD"
    rows = git("log", "--reverse", "--format=%H%x09%ad%x09%s", "--date=short", rng).splitlines()
    return [r.split("\t", 2) for r in rows if r.strip()]

def changelog_append(version, raw):
    st, d = state(), payload(raw)
    entries = [e.strip() for e in d.get("entries", []) if e.strip()]
    if not entries: die("no entries")
    subjects = [s.lower() for _, _, s in commits_since(st.get("last_changelog_commit"))]
    problems = []
    for e in entries:
        el = e.lower()
        if any(s and (s in el or (len(el) >= 20 and el in s)) for s in subjects): problems.append(f"copies a commit message verbatim: {e[:80]}")
        problems += [f"{e[:60]}… -> {p}" for p in public_text_problems(e)]
    if problems: die("changelog entries rejected:\n  " + "\n  ".join(problems))
    head = git("rev-parse", "HEAD").strip()
    date = d.get("date") or now().date().isoformat()
    section = f"## v{version} ({date})\n\n" + "\n".join(f"- {e}" for e in entries) + "\n"
    old = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Changelog\n"
    head_part, _, rest = old.partition("\n")
    CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    CHANGELOG.write_text(head_part + "\n\n" + section + ("\n" + rest.strip() + "\n" if rest.strip() else ""), encoding="utf-8", newline="\n")
    st["last_changelog_commit"] = head; save(STATE, st)
    print(section + f"\nlast_changelog_commit -> {head[:7]}")

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "log":
        e = payload(rest[0]) if rest else die("give the entry JSON")
        if e.get("kind") not in KINDS: die(f"kind must be one of {sorted(KINDS)}")
        if not str(e.get("title", "")).strip() or not str(e.get("text", "")).strip(): die("title and text required")
        if e.get("tier") and e["tier"] not in TIERS: die("tier must be T0-T3")
        when = e.pop("date", None)
        row = {"ts": (dt.datetime.fromisoformat(when).isoformat(timespec="seconds") if when else now().isoformat()), **e}
        row.setdefault("tags", [])
        append_jsonl(JOURNAL, row); print(json.dumps(row, ensure_ascii=False))
    elif cmd == "journal":
        k = rest[rest.index("--kind") + 1] if "--kind" in rest else None
        for e in read_jsonl(JOURNAL):
            if k and e["kind"] != k: continue
            print(f"{e['ts'][:10]}{'~' if e.get('date_approx') else ' '} {e['kind']:<9} {e['title']}" + (f"  [{e['commit'][:7]}]" if e.get("commit") else ""))
    elif cmd == "changelog-commits":
        for h, d, s in commits_since(state().get("last_changelog_commit")): print(f"{h[:7]}  {d}  {s}")
    elif cmd == "changelog-append" and len(rest) == 2: changelog_append(rest[0], rest[1])
    elif cmd == "lint-public" and rest:
        p = pathlib.Path(rest[0]); rel = p.name
        probs = public_text_problems(p.read_text(encoding="utf-8"), "--voice" in rest, rel)
        print("OK: public-safe" if not probs else "BLOCKED:\n  " + "\n  ".join(probs)); return 1 if probs else 0
    elif cmd == "mark-generalized" and rest:
        man = load(MANIFEST, {"files": []})
        f = next((x for x in man["files"] if x["target"] == rest[0] and x["transform"] == "generalize"), None) or die(f"no generalize entry for {rest[0]}")
        f["source_hash"] = sha((ROOT / f["source"]).read_bytes()); save(MANIFEST, man); print(f"{rest[0]}: source hash recorded")
    elif cmd == "export": return export()
    elif cmd == "diff":
        st = state()
        p = subprocess.run(["git", "diff", "--no-index", "--", str(resolve(st["clone_dir"])), str(resolve(st["staging_dir"]))], capture_output=True, text=True, encoding="utf-8")
        print(p.stdout or "(no differences, or nothing published yet: every file is new)")
    elif cmd == "approve" and rest:
        st = state()
        if not (st.get("last_export_clean") and rest[0] == st.get("last_export_hash")): die("can only approve the latest clean export, by its hash")
        st.update(approved_export_hash=rest[0], approved_at=now().isoformat()); save(STATE, st); print(f"approved {rest[0][:12]}")
    elif cmd == "publish" and len(rest) == 2: return publish(rest[0], rest[1])
    elif cmd == "set-ip-checked":
        st = state(); st["ip_policy_checked"] = True; save(STATE, st); print("ip_policy_checked = true")
    elif cmd == "set-commit-email" and rest:
        if not rest[0].endswith("@users.noreply.github.com"): die("use your GitHub noreply address (…@users.noreply.github.com)")
        st = state(); st["commit_email"] = rest[0]; save(STATE, st); print("commit_email set")
    elif cmd == "status":
        st = state(); print(json.dumps({k: v for k, v in st.items() if k != "remote"}, indent=1))
    else:
        print(__doc__); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
