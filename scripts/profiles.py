#!/usr/bin/env python3
"""EXTROVERT profile copy: LinkedIn (headline, About, one Experience per role), Medium bio and About page, GitHub bio.
Copy is written by the assistant from the public channel only; this script does all the deterministic work: the source
material, the platform limits, the gates (limits, public disclosure lint, voice lint), versions, what's applied, and
the staleness policy that renovate runs at its end.
  profiles.py inputs                    the public-channel material copy may use (current employer: public wording only)
  profiles.py check <platform> <file>   parse the sections, count characters against the limits, run both lints
  profiles.py save <platform> <file>    check, then store as data/extrovert/profiles/<platform>/v<N>.md (+ a snapshot of
                                        the inputs it was written from)
  profiles.py applied <platform|all> [--version N]
                                        record that the user pasted that version (default: the latest) onto the platform
  profiles.py status                    per platform: latest version, applied version, and what's stale since
  profiles.py policy [--force]          renovate's closing check: which pieces are stale (triggers in config); at most one
                                        reminder per throttle period (14 days) unless a job/role change is among them
Platforms: linkedin (sections: headline, about, "experience: <employer> · <role>" for every role), medium (bio, about),
github (bio). Config: data/extrovert/config.json -> profiles. State: data/extrovert/profiles/state.json.
COCKPIT_NOW=<ISO> overrides the clock (tests).
"""
import datetime as dt, hashlib, json, os, re, sys
from _common import DATA, read_jsonl
from disclosure_lint import check as lint_check, context as lint_context, NO_ENTRY
import voice_lint

PROFILES = DATA / "extrovert/profiles"
STATE = PROFILES / "state.json"
CONFIG = DATA / "extrovert/config.json"
PLATFORMS = ("linkedin", "medium", "github")

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def die(msg): print(f"BLOCKED: {msg}"); sys.exit(1)
def cfg(): return json.loads(CONFIG.read_text(encoding="utf-8"))
def pcfg(): return cfg()["profiles"]
def load_state(): return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {p: {} for p in PLATFORMS} | {"last_reminded": None}
def save_state(st):
    PROFILES.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
def digest(o): return hashlib.sha256(json.dumps(o, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

def roles():
    emp = json.loads((DATA / "bragdoc/employment.json").read_text(encoding="utf-8"))
    return emp if isinstance(emp, list) else emp.get("roles", [])
def role_key(r): return f"{r['employer']} · {r['role']}"
def current_roles(): return [r for r in roles() if not r.get("end")]

# ---------------------------------------------------------------- the signals staleness is measured against
def signals():
    """What the copy depends on: the top-impact public entries (id -> payload), the top 5 public entries (the profile
    README's selection), the current role(s), and the skill groups."""
    sys.path.insert(0, os.path.dirname(__file__))
    import runway, bragdoc_public as bp
    c = runway.cfg(); data, ids, problems, _ = runway.build()
    ents = {e["id"]: e for e in read_jsonl(DATA / "bragdoc/entries.jsonl")}
    top_min = pcfg()["policy"].get("top_impact_min", 3)
    top_impact = {i: bp.payload_hash(ents[i]) for r, i in zip(data["entries"], ids) if r["impact"] >= top_min}
    top5 = [e["id"] for _, e in runway.profile_top(c, data, ids)] if "profile" in c else []
    skills = json.loads((DATA / "bragdoc/skills.json").read_text(encoding="utf-8"))
    groups = sorted({s.get("group") for s in (skills if isinstance(skills, list) else []) if s.get("group")})
    return {"top_impact": top_impact, "top5": top5, "job": [[r["employer"], r["role"], r.get("start")] for r in current_roles()],
            "skill_groups": groups}

def triggered(snap, cur):
    """Which policy triggers fired between a snapshot and now."""
    out = []
    if not snap: return out
    if cur["top_impact"] != snap.get("top_impact"): out.append("top_impact")
    if cur["top5"] != snap.get("top5"): out.append("top5")
    if cur["job"] != snap.get("job"): out.append("job")
    if set(cur["skill_groups"]) - set(snap.get("skill_groups", [])): out.append("skill_group")
    return out

# ---------------------------------------------------------------- inputs (public channel only)
def inputs():
    """The material copy may use. Current employer: only employment.json public_summary / public_context."""
    sys.path.insert(0, os.path.dirname(__file__))
    import runway
    data, ids, problems, _ = runway.build()
    if problems: die("the public site data doesn't build:\n  " + "\n  ".join(problems))
    cur = {r["employer"] for r in current_roles()}
    names = json.loads((DATA / "profile.json").read_text(encoding="utf-8"))["names"]
    out = {"name": names.get("short"), "roles": [], "public_entries": [], "skill_groups": {}}
    for r in roles():
        row = {"key": role_key(r), "start": r.get("start"), "end": r.get("end")}
        if r["employer"] in cur:
            row["current_employer"] = True
            row["public_summary"] = r.get("public_summary"); row["public_context"] = r.get("public_context", [])
            row["rule"] = pcfg().get("current_employer_rule") or "current employer: only public_summary and public_context"
        out["roles"].append(row)
    ents = {e["id"]: e for e in read_jsonl(DATA / "bragdoc/entries.jsonl")}
    for row, i in zip(data["entries"], ids):
        out["public_entries"].append({"id": i, "employer": ents[i].get("employer"), "where": row["where"], "year": row["year"],
                                      "impact": row["impact"], "metric": row["metric"], "title": row["title"], "summary": row["summary"],
                                      "stack": row["stack"]})
    skills = json.loads((DATA / "bragdoc/skills.json").read_text(encoding="utf-8"))
    for s in skills:
        out["skill_groups"].setdefault(s.get("group") or "Other", []).append(s.get("skill"))
    return out

# ---------------------------------------------------------------- parsing and gates
def parse(text):
    """{section: text} from '## <section>' headings; everything after a '<!-- notes -->' line is ignored."""
    text = text.replace("\r\n", "\n").split("\n<!-- notes -->")[0]
    out, cur = {}, None
    for line in text.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m: cur = m.group(1).strip(); out[cur] = []; continue
        if cur is not None: out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}

def expected_sections(platform):
    if platform == "linkedin": return ["headline", "about", *[f"experience: {role_key(r)}" for r in roles()]]
    return ["bio", "about"] if platform == "medium" else ["bio"]

def limit_for(platform, section):
    lim = pcfg()["limits"][platform]
    return lim["experience"] if section.startswith("experience: ") else lim[section]

def gates(platform, text):
    """(rows, problems). rows: (section, characters, limit)."""
    if platform not in PLATFORMS: die(f"platform must be one of {', '.join(PLATFORMS)}")
    secs, problems, rows = parse(text), [], []
    want = expected_sections(platform)
    missing, extra = [s for s in want if s not in secs], [s for s in secs if s not in want]
    if missing: problems.append(f"missing sections: {missing}")
    if extra: problems.append(f"unexpected sections (headings must match exactly): {extra}")
    ctx = lint_context(read_jsonl(DATA / "bragdoc/entries.jsonl"))
    vcfg = cfg()
    by_key = {role_key(r): r for r in roles()}
    for s in want:
        body = secs.get(s, "")
        if not body: continue
        n, lim = len(body), limit_for(platform, s)
        rows.append((s, n, lim))
        if n > lim: problems.append(f"{s}: {n} characters, limit {lim}")
        # Experience copy is checked with its employer as context (past-employer figures allowed, never the current
        # employer's); everything else as one document (figures only verbatim from an allowed entry).
        entry = {"employer": by_key[s[len("experience: "):]]["employer"]} if s.startswith("experience: ") else NO_ENTRY
        # Markdown list markers aren't part of the text (the site's gate lints plain strings too)
        plain = [re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", l) for l in body.split("\n") if l.strip()]
        for _, line, why in lint_check(plain, "public", ctx, entry=entry):
            problems.append(f"{s}: public lint: {why} | {line[:90]}")
        problems += [f"{s}: voice lint: {v}" for v in voice_lint.lint(body, vcfg)]
    return rows, problems

def report(rows):
    for s, n, lim in rows: print(f"  {s:<70} {n:>5} / {lim}")

# ---------------------------------------------------------------- commands
def cmd_check(platform, path):
    rows, problems = gates(platform, open(path, encoding="utf-8").read())
    report(rows)
    if problems: print("PROBLEMS:\n  " + "\n  ".join(problems)); return 1
    print("OK: within limits; public lint and voice lint pass"); return 0

def cmd_save(platform, path):
    text = open(path, encoding="utf-8").read()
    rows, problems = gates(platform, text)
    if problems: report(rows); die("not saved:\n  " + "\n  ".join(problems))
    st = load_state(); ps = st.setdefault(platform, {})
    n = max([int(v) for v in ps.get("versions", {})] or [0]) + 1
    d = PROFILES / platform; d.mkdir(parents=True, exist_ok=True)
    (d / f"v{n}.md").write_text(text.replace("\r\n", "\n").rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    ps.setdefault("versions", {})[str(n)] = {"date": now().isoformat(timespec="seconds"), "snapshot": signals()}
    ps["latest"] = n
    save_state(st); report(rows)
    print(f"Saved data/extrovert/profiles/{platform}/v{n}.md"); return 0

def cmd_applied(target, version=None):
    st = load_state(); done = []
    for p in (PLATFORMS if target == "all" else [target]):
        if p not in PLATFORMS: die(f"platform must be one of {', '.join(PLATFORMS)} or all")
        ps = st.get(p, {})
        v = version or ps.get("latest")
        if not v: (print(f"{p}: nothing saved yet") if target == "all" else die(f"{p}: nothing saved yet")); continue
        if str(v) not in ps.get("versions", {}): die(f"{p}: no version {v}")
        ps["applied"] = {"version": int(v), "date": now().date().isoformat()}; st[p] = ps; done.append(f"{p} v{v}")
    save_state(st); print("Applied: " + (", ".join(done) or "nothing")); return 0

def stale(st, cur):
    """{platform: (applied version or None, [triggers], [stale pieces])} against the applied (else latest) version."""
    pol, out = pcfg()["policy"], {}
    for p in PLATFORMS:
        ps = st.get(p, {})
        v = (ps.get("applied") or {}).get("version") or ps.get("latest")
        snap = ps.get("versions", {}).get(str(v), {}).get("snapshot") if v else None
        fired = triggered(snap, cur)
        pieces = sorted({x for t in fired for x in pol["triggers"].get(t, []) if x.startswith(p + ".")})
        out[p] = ((ps.get("applied") or {}).get("version"), fired, pieces)
    return out

def cmd_status():
    st, cur = load_state(), signals()
    for p, (applied, fired, pieces) in stale(st, cur).items():
        ps = st.get(p, {})
        latest = ps.get("latest")
        line = f"{p:<9} latest v{latest}" if latest else f"{p:<9} nothing saved yet"
        if latest: line += f", applied v{applied} ({ps['applied']['date']})" if applied else ", not applied yet"
        if latest and applied and latest != applied: line += f"; v{latest} is ready to paste"
        if fired: line += f"; stale since: {', '.join(fired)} -> {', '.join(pieces) or 'no piece of this platform'}"
        print(line)
    return 0

def cmd_policy(force=False):
    """Renovate's closing check. Prints a reminder of the stale pieces, at most once per throttle period, except that a
    job/role change always reminds. Records when it reminded."""
    pol, st, cur = pcfg()["policy"], load_state(), signals()
    res = stale(st, cur)
    fired = {t for _, f, _ in res.values() for t in f}
    pieces = sorted({x for _, _, ps in res.values() for x in ps})
    if not pieces: print("Profile copy: current."); return 0
    last = st.get("last_reminded")
    throttled = last and (now().date() - dt.date.fromisoformat(last)).days < pol.get("throttle_days", 14)
    if throttled and not (fired & set(pol.get("exempt", []))) and not force:
        print(f"Profile copy: stale ({', '.join(pieces)}), already reminded on {last}; next reminder after the {pol.get('throttle_days', 14)}-day throttle.")
        return 0
    st["last_reminded"] = now().date().isoformat(); save_state(st)
    print("REMINDER: profile copy is stale. Run /extrovert profiles for: " + ", ".join(pieces))
    print("  because: " + ", ".join(sorted(fired)))
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "inputs": print(json.dumps(inputs(), indent=1, ensure_ascii=False)); return 0
    if cmd == "check" and len(rest) == 2: return cmd_check(*rest)
    if cmd == "save" and len(rest) == 2: return cmd_save(*rest)
    if cmd == "applied" and rest: return cmd_applied(rest[0], int(rest[rest.index("--version") + 1]) if "--version" in rest else None)
    if cmd == "status": return cmd_status()
    if cmd == "policy": return cmd_policy("--force" in rest)
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
