#!/usr/bin/env python3
"""Synthetic test suite. Every test runs in a throwaway copy of this repo, never against your data/.
  python tests/test_suite.py
Data comes from the fictional persona in examples/persona/. Canary values (a fake cloud key, a planted employer name,
a planted vulnerability class) are assembled at runtime, so this file never contains them and stays export-clean.
Needs: python, git, and the packages in requirements.txt (detect-secrets for the export checks).
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
RESULTS = []

def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), "" if cond else detail[-600:]))

class Sandbox:
    def __init__(self, persona=True):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="cockpit-test-"))
        self.root = self.tmp / "repo"
        shutil.copytree(REPO, self.root, ignore=shutil.ignore_patterns(".git", "out", "raw", "inbox", "__pycache__"))
        if persona: shutil.copytree(self.root / "examples/persona/data", self.root / "data", dirs_exist_ok=True)
        st = self.read_json("data/fourthwall/state.json")
        st.update(staging_dir=str(self.tmp / "staging"), clone_dir=str(self.tmp / "clone"), remote="")
        self.write_json("data/fourthwall/state.json", st)

    def run(self, script, *args, stdin=None):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), COCKPIT_NOW="2026-10-01T12:00:00", PYTHONIOENCODING="utf-8")
        env.pop("COCKPIT_DRIVE_INBOX", None)
        p = subprocess.run([sys.executable, str(self.root / "scripts" / script), *args], cwd=self.root, input=stdin,
                           capture_output=True, text=True, encoding="utf-8", env=env)
        return p.returncode, p.stdout + p.stderr

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args], cwd=self.root,
                              capture_output=True, text=True, encoding="utf-8")

    def path(self, rel): return self.root / rel
    def read_json(self, rel): return json.loads(self.path(rel).read_text(encoding="utf-8"))
    def write_json(self, rel, obj): self.path(rel).write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8", newline="\n")
    def write(self, rel, text):
        p = self.path(rel); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8", newline="\n")
    def add_to_manifest(self, *rels):
        m = self.read_json("data/fourthwall/manifest.json")
        m["files"] += [{"source": r, "target": r, "transform": "copy"} for r in rels]
        self.write_json("data/fourthwall/manifest.json", m)
    def lines(self, rel):
        p = self.path(rel); return [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
    def close(self): shutil.rmtree(self.tmp, ignore_errors=True)

def export_hash(out):
    return next((l.split(": ", 1)[1].strip() for l in out.splitlines() if l.startswith("export hash:")), None)

# ---------------------------------------------------------------- validation
def test_validation():
    sb = Sandbox(persona=False)
    rc, out = sb.run("validate.py"); check("empty skeleton validates", rc == 0, out); sb.close()
    sb = Sandbox()
    rc, out = sb.run("validate.py"); check("persona data validates", rc == 0, out)
    rows = [json.loads(l) for l in sb.lines("data/bragdoc/staging.jsonl")]
    rows[1]["status"] = "probed"   # s-0002 has no metrics and open gaps
    sb.write("data/bragdoc/staging.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
    rc, out = sb.run("validate.py"); check("validator rejects an incomplete 'probed' item", rc != 0 and "metric" in out, out)
    sb.close()

# ---------------------------------------------------------------- chassis
def test_chassis():
    sb = Sandbox()
    rc, out = sb.run("chassis.py", "deadlines"); check("chassis deadlines lists jobs", rc == 0 and "Engine oil" in out and "Brake fluid" in out, out)
    rc, out = sb.run("chassis.py", "odom", "100"); check("chassis rejects a decreasing odometer", rc != 0, out)
    sb.close()

# ---------------------------------------------------------------- bragdoc
def test_bragdoc():
    sb = Sandbox()
    rc, out = sb.run("bragdoc_public.py", "stale"); check("persona summaries are current", rc == 0 and "None stale" in out, out)
    rc, out = sb.run("bragdoc_public.py", "change", "1200", "450"); check("relative change is computed", "-62.5%" in out, out)
    rc, out = sb.run("bragdoc_stage.py", "add", json.dumps({"raw": "Wrote a CLI", "project": "Tooling", "source": "user"}))
    check("bragdoc_stage appends s-0003", rc == 0 and '"s-0003"' in out, out)
    rc, out = sb.run("render.py", "public-resume"); check("public resume renders and passes its lint", rc == 0, out)
    sb.close()

def test_disclosure_lint():
    sb = Sandbox()
    vuln = "SS" + "RF"
    mail = "sam" + "@" + "gm" + "ail.com"
    sb.write("bad.md", f"Hardened the fetcher against {vuln}.\nContact {mail}\n")
    sb.write("good.md", "Hardened external document fetching.\n")
    rc, out = sb.run("disclosure_lint.py", "--channel", "public", str(sb.path("bad.md")))
    check("public lint blocks a vulnerability class and a personal email", rc == 1 and "vulnerability" in out and "personal email" in out, out)
    rc, out = sb.run("disclosure_lint.py", "--channel", "public", str(sb.path("good.md")))
    check("public lint passes clean text", rc == 0, out)
    sb.close()

def test_names():
    sb = Sandbox()
    names = sb.read_json("data/profile.json")["names"]
    for cmd, form, suffix in (("bragdoc", "short", "BragDoc"), ("resume-extensive", "formal", "Resume_Extensive"),
                              ("public-resume", "public_full", "Resume_Public")):
        rc, out = sb.run("render.py", cmd)
        html = sb.root / "out" / f"{names[form].replace(' ', '_')}_{suffix}.html"
        shown = html.read_text(encoding="utf-8") if html.exists() else ""
        check(f"{cmd} header shows names.{form}", rc == 0 and f"<h1 class='name'>{names[form]}</h1>" in shown, out)
    formal = names["formal"]
    sb.write("pub.md", f"Written by {formal}.\n")
    rc, out = sb.run("disclosure_lint.py", "--channel", "public", str(sb.path("pub.md")))
    check("public channel blocks the formal name", rc == 1 and "formal name form" in out, out)
    sb.write("cv.html", f"<html><body><h1 style='text-transform:uppercase'>{formal}</h1><p>Engineer</p></body></html>")
    rc, out = sb.run("disclosure_lint.py", "--channel", "resume", str(sb.path("cv.html")))
    check("resume with the exact formal name (all caps via CSS) passes", rc == 0, out)
    sb.write("cv2.html", f"<html><body><h1>{formal.upper()}</h1><p>Engineer</p></body></html>")
    rc, out = sb.run("disclosure_lint.py", "--channel", "resume", str(sb.path("cv2.html")))
    check("retyped all-caps formal name is blocked on a resume", rc == 1 and "wrong casing" in out and "must show the name" in out, out)
    sb.write("cv3.html", "<html><body><h1>Someone</h1><p>Engineer</p></body></html>")
    rc, out = sb.run("disclosure_lint.py", "--channel", "resume", str(sb.path("cv3.html")))
    check("resume without the formal name is blocked", rc == 1 and "must show the name" in out, out)
    p = sb.read_json("data/profile.json"); p["names"] = {"short": "Sam", "public_full": "Sam Rivera", "formal": "Dr Sam Rivera"}
    sb.write_json("data/profile.json", p)
    sb.write("x.md", "Notes by DR Sam Rivera.\n"); sb.write("y.md", "By Dr Sam, as ever.\n")
    rc, out = sb.run("disclosure_lint.py", "--channel", "internal", str(sb.path("x.md")))
    check("wrong casing of a formal prefix is flagged on every channel", rc == 1 and "wrong casing" in out, out)
    rc, out = sb.run("disclosure_lint.py", "--channel", "public", str(sb.path("y.md")))
    check("public blocks the formal prefix + short name", rc == 1 and "formal name form" in out, out)
    sb.write("data/extrovert/note.md", "Signed DR Sam Rivera\n")
    rc, out = sb.run("validate.py"); check("validator flags a mis-cased formal name in data/", rc != 0 and "wrong casing" in out, out)
    del p["names"]; p["name"] = "Sam Rivera"; sb.write_json("data/profile.json", p)
    sb.path("data/extrovert/note.md").unlink()
    rc, out = sb.run("validate.py"); check("validator rejects the old 'name' key", rc != 0 and "names" in out, out)
    sb.close()

def test_extractor():
    sb = Sandbox()
    modes = {"session": [], "incident": ["2026-08-27", "search outage after a deploy"], "project": [], "period": ["2026-05", "2026-09", "search rewrite"]}
    for mode, args in modes.items():
        rc, out = sb.run("extractor.py", "prompt", mode, *args)
        need = ["READ-ONLY", "no commits, pushes, branches, stashes", "[measured]", "[from git/logs/docs]", "[estimate]", "[from my memory]",
                "OWNERSHIP, strictly", "CONFIDENTIALITY", '"Notes for you"']
        check(f"extractor {mode}: every required block", rc == 0 and all(n in out for n in need), [n for n in need if n not in out])
        rc, out = sb.run("extractor.py", "prompt", mode, *args, "--personal")
        check(f"extractor {mode} --personal: no confidentiality block", rc == 0 and "CONFIDENTIALITY" not in out, out[:200])
    rc, out = sb.run("extractor.py", "prompt", "incident", "2026-08-27", "x")
    check("incident prompt: timestamps and computed durations, no adjectives", "first symptom, detection" in out and "show the subtraction" in out and '"record time"' in out, out)
    rc, out = sb.run("extractor.py", "prompt", "incident", "2026-02-30", "x"); check("incident rejects an impossible date", rc != 0, out)
    rc, out = sb.run("extractor.py", "prompt", "period", "2026-09", "2026-05", "x"); check("period rejects from after to", rc != 0, out)
    rc, out = sb.run("extractor.py", "durations", "2026-08-27T10:05", "2026-08-27T10:30", "2026-08-27T11:45")
    check("durations computed from timestamps", rc == 0 and "(25 min)" in out and "(100 min)" in out, out)
    rc, out = sb.run("extractor.py", "durations", "2026-08-27T10:45", "unknown", "2026-08-27T11:08")
    check("durations with unknown detection report only what the timestamps support", rc == 0 and "time to detect:    unknown" in out and "(23 min)" in out, out)
    rc, out = sb.run("extractor.py", "overlaps", json.dumps({"raw": "order search latency regression", "employer": "Example Corp", "date": "2026-08-15"}))
    check("overlaps flags the existing order-search entry", "e-0001" in out and "likely" in out, out)
    rc, src = sb.run("extractor.py", "source", "project")
    item = {"raw": "Barcode shelf scanner", "project": "Shelfie scanner", "source": src.strip(), "kind": "personal_project",
            "source_claims": [{"claim": "formats", "value": "2", "source": src.strip(), "tier": "T3", "needs_confirmation": True, "evidence": "git"}]}
    rc, out = sb.run("bragdoc_stage.py", "add", "-", stdin=json.dumps(item)); sid = json.loads(out)["id"] if rc == 0 else ""
    rc2, out2 = sb.run("bragdoc_stage.py", "add-in-progress", json.dumps({"title": "Shelfie scanner", "kind": "project", "source": src.strip(), "staging_id": sid}))
    rc3, out3 = sb.run("validate.py")
    check("paste-back: staging item + linked in-progress record validate", rc == 0 and rc2 == 0 and rc3 == 0, out + out2 + out3)
    sb.close()

# ---------------------------------------------------------------- extrovert
def test_extrovert():
    sb = Sandbox()
    sb.write("post.md", "We shipped it \u2014 and I am excited to share it.\n<!-- notes -->\nignored\n")
    rc, out = sb.run("voice_lint.py", str(sb.path("post.md")))
    check("voice lint flags an em dash and a banned phrase", rc == 1 and "em dash" in out and "excited to share" in out, out)
    sb.write("clean.md", "Here is the fix, in four short steps.\n")
    rc, out = sb.run("voice_lint.py", str(sb.path("clean.md"))); check("voice lint passes clean text", rc == 0, out)
    rc, out = sb.run("post_stats.py", str(sb.path("clean.md"))); check("post_stats counts words", '"word_count": 8' in out, out)
    idea = {"raw": "idea: index-only scans", "gist": "When index-only scans help", "tags": ["postgres", "performance"], "context": "", "links": []}
    rc, out = sb.run("ideas.py", "add", "-", stdin=json.dumps(idea))
    rc2, out2 = sb.run("ideas.py", "list")
    check("ideas add then list", rc == 0 and "index-only scans" in out2, out + out2)
    sb.close()

# ---------------------------------------------------------------- fourthwall
def test_fourthwall_journal():
    sb = Sandbox()
    before = len(sb.lines("data/fourthwall/journal.jsonl"))
    rc, out = sb.run("fourthwall.py", "log", json.dumps({"kind": "lesson", "title": "Hooks beat reminders", "text": "Validation on every edit.", "tags": ["hooks"]}))
    check("fourthwall log adds an entry", rc == 0 and len(sb.lines("data/fourthwall/journal.jsonl")) == before + 1, out)
    rc, out = sb.run("fourthwall.py", "log", json.dumps({"kind": "rant", "title": "x", "text": "y"}))
    check("fourthwall log rejects a bad kind", rc != 0, out)
    with open(sb.path("data/fourthwall/journal.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-10-01T12:00:00", "kind": "rant", "title": "x", "text": "y", "tags": []}) + "\n")
    rc, out = sb.run("validate.py"); check("validator rejects a bad journal kind", rc != 0 and "kind" in out, out)
    sb.close()

def test_changelog():
    sb = Sandbox()
    sb.git("init", "-q"); sb.git("add", "-A"); sb.git("commit", "-q", "-m", "initial import")
    sb.write("notes.txt", "x\n"); sb.git("add", "-A"); sb.git("commit", "-q", "-m", "wire the skunkworks importer into staging")
    sb.write("data/fourthwall/denylist.json", json.dumps({**sb.read_json("data/fourthwall/denylist.json"), "terms": ["skunkworks"]}))
    rc, out = sb.run("fourthwall.py", "changelog-append", "0.1.0", json.dumps({"entries": ["wire the skunkworks importer into staging"]}))
    check("changelog rejects a copied commit message", rc != 0 and "verbatim" in out, out)
    rc, out = sb.run("fourthwall.py", "changelog-append", "0.1.0", json.dumps({"entries": ["Added the Skunkworks importer"]}))
    check("changelog rejects a deny-listed term", rc != 0 and "skunkworks" in out.lower(), out)
    rc, out = sb.run("fourthwall.py", "changelog-append", "0.1.0", json.dumps({"date": "2026-10-01", "entries": ["Added a staging importer for bulk notes."]}))
    text = sb.path("fourthwall/CHANGELOG.md").read_text(encoding="utf-8") if sb.path("fourthwall/CHANGELOG.md").exists() else ""
    check("changelog writes a clean summary", rc == 0 and "## v0.1.0 (2026-10-01)" in text, out)
    sb.close()

def test_export():
    sb = Sandbox()
    rc, out = sb.run("fourthwall.py", "export"); h1 = export_hash(out)
    check("clean export passes every leak check", rc == 0 and "CLEAN" in out, out)
    staged = [p.relative_to(sb.tmp / "staging").as_posix() for p in (sb.tmp / "staging").rglob("*") if p.is_file()]
    check("export holds only manifest files (no data/, raw/)", not any(s.startswith(("data/", "raw/")) for s in staged), str(staged))
    rc, out = sb.run("fourthwall.py", "export")
    check("export twice gives an identical hash", h1 and export_hash(out) == h1, out)

    rc, out = sb.run("fourthwall.py", "publish", "0.1.0", "first")
    check("publish refuses without an approved export", rc != 0 and "approved" in out, out)
    rc, out = sb.run("fourthwall.py", "approve", "0" * 64); check("approve refuses a wrong hash", rc != 0, out)
    sb.run("fourthwall.py", "approve", h1)
    rc, out = sb.run("fourthwall.py", "publish", "0.1.0", "first")
    check("first publish refuses while ip_policy_checked is false", rc != 0 and "policy" in out, out)
    sb.close()

def test_canaries():
    fake_key = "AK" + "IA" + "Z7Q2M4XK" + "P9RTW3NB"
    sb = Sandbox()
    sb.write("scripts/canary_a.py", f'CLOUD = "{fake_key}"\n'); sb.add_to_manifest("scripts/canary_a.py")
    rc, out = sb.run("fourthwall.py", "export")
    check("canary: planted cloud key is caught", rc != 0 and "FAIL  2 secrets" in out, out)
    sb.close()

    sb = Sandbox()
    employer = sb.read_json("data/bragdoc/employment.json")[0]["employer"]
    sb.write("docs/canary_b.md", f"Built at {employer}.\n"); sb.add_to_manifest("docs/canary_b.md")
    rc, out = sb.run("fourthwall.py", "export")
    check("canary: planted employer name is caught", rc != 0 and "FAIL  4 deny list" in out, out)
    sb.close()

    sb = Sandbox()
    d = sb.read_json("data/fourthwall/denylist.json"); d["terms"] = d.get("terms", []) + ["skunkworks"]
    sb.write_json("data/fourthwall/denylist.json", d)
    sb.write("docs/canary_c.md", "Run /skunkworks check first.\n"); sb.add_to_manifest("docs/canary_c.md")
    rc, out = sb.run("fourthwall.py", "export")
    check("canary: planted private-domain name is caught", rc != 0 and "FAIL  4 deny list" in out, out)
    sb.close()

    sb = Sandbox()
    sb.write("docs/canary_d.md", "Fixed an " + "SS" + "RF" + " hole.\n"); sb.add_to_manifest("docs/canary_d.md")
    rc, out = sb.run("fourthwall.py", "export")
    check("canary: planted vulnerability class is caught", rc != 0 and "FAIL  3 public lint" in out, out)
    sb.close()

def test_manifest_rules():
    sb = Sandbox()
    m = sb.read_json("data/fourthwall/manifest.json")
    m["files"].append({"source": "data/profile.json", "target": "profile.json", "transform": "copy"})
    sb.write_json("data/fourthwall/manifest.json", m)
    rc, out = sb.run("fourthwall.py", "export"); check("export refuses an excluded manifest source", rc != 0 and "excluded" in out, out)
    rc, out = sb.run("validate.py"); check("validator refuses an excluded manifest source", rc != 0 and "excluded" in out, out)
    m["files"][-1] = {"source": ".git/config", "target": "git-config", "transform": "copy"}
    sb.write_json("data/fourthwall/manifest.json", m)
    rc, out = sb.run("validate.py"); check("validator refuses a .git source", rc != 0 and "excluded" in out, out)
    sb.close()

# ---------------------------------------------------------------- RUNWAY (no site repo needed)
def runway_module(sb):
    """runway.py imported against the sandbox's data/ (CLAUDE_PROJECT_DIR is read when _common loads)."""
    os.environ["CLAUDE_PROJECT_DIR"] = str(sb.root)
    for m in [m for m in list(sys.modules) if m in ("_common", "disclosure_lint", "bragdoc_public", "runway", "voice_lint")]: del sys.modules[m]
    sys.path.insert(0, str(sb.root / "scripts"))
    try:
        import runway
        return runway
    finally:
        sys.path.remove(str(sb.root / "scripts"))

def test_runway():
    sb = Sandbox()
    rc, out = sb.run("runway.py", "build")
    check("runway build: the persona passes every gate (its one entry is private)", rc == 0 and "OK: 0 entries" in out, out)
    e = [json.loads(l) for l in sb.lines("data/bragdoc/entries.jsonl")]
    e[0]["visibility"] = "public"
    sb.write("data/bragdoc/entries.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in e))
    rc, out = sb.run("runway.py", "build", "--out", str(sb.tmp / "site.json"))
    data = json.loads((sb.tmp / "site.json").read_text(encoding="utf-8")) if rc == 0 else {}
    row = (data.get("entries") or [{}])[0]
    check("runway build: a public entry becomes one contract row from its summary and card",
          rc == 0 and row.get("id") == e[0]["site_slug"] and row.get("metric") == e[0]["site_card"]["metric"]
          and row.get("year") == e[0]["year"] and row.get("impact") in (1, 2, 3), out)
    rw = runway_module(sb)
    readme = "## Me\r\nMy own words.\r\n\r\n<!-- POSTS:START -->\r\nlist\r\n<!-- POSTS:END -->\r\n"
    first = rw.merge_profile(readme, f"{rw.P_START}\nblock one\n{rw.P_END}")
    again = rw.merge_profile(first, f"{rw.P_START}\nblock two\n{rw.P_END}")
    check("runway profile: the block is replaced, everything else kept byte for byte (CRLF too)",
          again.startswith(readme.rstrip("\r\n")) and "block two" in again and "block one" not in again and "\n" not in again.replace("\r\n", ""), again)
    c = {"preview_url": "https://site-git-{branch}.example.app"}
    check("runway preview URL: branch names become hostname-safe", rw.preview_url(c, "code/New-Header") == "https://site-git-code-new-header.example.app")
    hook = sb.path("data/runway/deploy-hook.local"); hook.write_text("https://hooks.example.com/abc", encoding="utf-8")
    c = {"deploy_hook_file": "data/runway/deploy-hook.local", "deploy_hook_pattern": r"^https://deploy\.example\.net/\S+$"}
    check("runway deploy hook: a URL that doesn't match the pattern is invalid", rw.hook_state(c) == ("invalid", None))
    c["deploy_hook_pattern"] = r"^https://hooks\.example\.com/\S+$"
    check("runway deploy hook: a matching URL is valid", rw.hook_state(c)[0] == "ok")
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    sb.close()

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        try: t()
        except Exception as e: check(t.__name__, False, f"{type(e).__name__}: {e}")
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {detail}" if detail else ""))
    failed = sum(not ok for _, ok, _ in RESULTS)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} passed")
    sys.exit(1 if failed else 0)
