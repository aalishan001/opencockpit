#!/usr/bin/env python3
"""Validate everything in data/. Run by the PostToolUse hook; exit 2 surfaces errors to Claude."""
import datetime as dt, json, re, sys
from _common import DATA, read_jsonl
from disclosure_lint import name_problems

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACTIONS = {"check", "replace", "clean", "adjust", "lubricate", "inspect"}
KINDS = {"work", "personal_project", "product", "open_source", "community"}
TIERS = {"T0", "T1", "T2", "T3"}
METRIC_TYPES = {"scale", "impact"}
EVIDENCE = {"measured", "git", "estimate", "memory"}   # extractor tags: [measured] [from git/logs/docs] [estimate] [from my memory]
EXTRACTOR_SOURCE = re.compile(r"^extractor:(session|incident|project|period):\d{4}-\d{2}-\d{2}$")
PASSIVE = re.compile(r"\b(worked on|helped|assisted|was responsible for)\b", re.I)
WAIVABLE = {"scale", "impact", "stack", "problem"}   # probe parts the user answered "don't know" to (probe.waived)
YM = re.compile(r"^\d{4}-\d{2}$")
IP_KINDS, IP_STATUS = {"study", "certification", "project"}, {"planned", "in_progress", "paused", "done", "dropped"}
# never allowed anywhere in data/: phone numbers outside profile.json contacts, and the policy's always_banned terms
PHONE = re.compile(r"(?<!\w)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
CHANNELS = {"internal", "resume", "public"}
POLICY_FILE, PROFILE_FILE = "bragdoc/disclosure_policy.json", "profile.json"
NAME_FORMS = ("short", "public_full", "formal")   # profile.json names; channels pick one in the disclosure policy
VISIBILITY = {"private", "public"}
LINK_KEYS = ("repo", "live", "landing", "demo", "docs")
PLATFORMS = {"medium", "linkedin"}  # post targets; add more here and in the extrovert skill
HTTPS = re.compile(r"^https://[^\s/?#]+\.[^\s]+$", re.I)
HEX = re.compile(r"^[0-9a-f]+$")
errors = []

def need(obj, keys, where):
    for k in keys:
        if k not in obj or obj[k] in ("", None, []):
            errors.append(f"{where}: missing required '{k}'")

def chassis():
    mpath = DATA / "chassis/manual.json"
    try:
        manual = json.loads(mpath.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError as e:
        errors.append(f"manual.json invalid JSON: {e}"); return
    ids = set()
    for i, j in enumerate(manual):
        w = f"manual.json[{i}]"
        need(j, ["id", "name", "action", "source"], w)
        if j.get("id") in ids: errors.append(f"{w}: duplicate id {j.get('id')}")
        ids.add(j.get("id"))
        if j.get("action") and j["action"] not in ACTIONS: errors.append(f"{w}: bad action {j['action']}")
        has_km, has_mo = "interval_km" in j, "interval_months" in j
        if has_km == has_mo:
            errors.append(f"{w}: needs exactly one of interval_km / interval_months")
        for k in ("interval_km", "interval_months"):
            if k in j and (not isinstance(j[k], int) or isinstance(j[k], bool) or j[k] <= 0):
                errors.append(f"{w}: {k} must be a positive int")
    services = read_jsonl(DATA / "chassis/services.jsonl")
    prev = None
    for i, s in enumerate(services, 1):
        w = f"services.jsonl:{i}"
        need(s, ["date", "odo", "jobs", "source"], w)
        if s.get("date") and not DATE.match(s["date"]): errors.append(f"{w}: bad date")
        for jid in s.get("jobs", []):
            if ids and jid not in ids: errors.append(f"{w}: unknown job id '{jid}'")
        if prev and s.get("date", "") < prev.get("date", ""): errors.append(f"{w}: not sorted by date")
        if prev and isinstance(s.get("odo"), int) and isinstance(prev.get("odo"), int) and s["odo"] < prev["odo"]:
            errors.append(f"{w}: odo decreases ({prev['odo']} -> {s['odo']})")
        prev = s
    for i, r in enumerate(read_jsonl(DATA / "chassis/odometer.jsonl"), 1):
        need(r, ["date", "odo", "source"], f"odometer.jsonl:{i}")

def staging_item(s, pr, w, qids):
    for i, c in enumerate(s.get("source_claims", [])):
        if not all(c.get(k) not in (None, "") for k in ("claim", "value", "source", "tier")):
            errors.append(f"{w}: source_claims[{i}] needs claim, value, source, tier")
        if c.get("tier") not in TIERS: errors.append(f"{w}: source_claims[{i}].tier must be T0-T3")
        if "evidence" in c and c["evidence"] not in EVIDENCE: errors.append(f"{w}: source_claims[{i}].evidence must be one of {sorted(EVIDENCE)}")
    src = str(s.get("source", ""))
    if src.startswith("extractor") and not EXTRACTOR_SOURCE.match(src):
        errors.append(f"{w}: extractor source must be extractor:<session|incident|project|period>:<YYYY-MM-DD> (got '{src}')")
    open_conflicts = 0
    for i, c in enumerate(s.get("conflicts", [])):
        cw = f"{w}: conflicts[{i}]"
        if len(c.get("values", [])) < 2: errors.append(f"{cw} needs at least 2 values")
        if c.get("status") not in ("open", "resolved"): errors.append(f"{cw}.status must be open|resolved")
        if c.get("status") == "resolved" and not c.get("resolution"): errors.append(f"{cw}: resolved without a resolution")
        if c.get("status") == "open":
            open_conflicts += 1
            if c.get("question_id") not in qids: errors.append(f"{cw}: open conflict needs a question_id in questions.jsonl")
    for i, m in enumerate(pr.get("metrics", [])):
        if m.get("type") not in METRIC_TYPES: errors.append(f"{w}: probe.metrics[{i}].type must be scale|impact")
    # probe.waived: what the user answered they don't have ("don't know", AS-IS). Only the user waives, and only these parts.
    wv = pr.get("waived")
    waived = set()
    if wv is not None:
        if not (isinstance(wv, dict) and isinstance(wv.get("fields"), list) and set(wv["fields"]) <= WAIVABLE and wv["fields"]):
            errors.append(f"{w}: probe.waived needs fields (a non-empty subset of {sorted(WAIVABLE)}), source and reason")
        elif not (str(wv.get("source", "")).startswith("user") and str(wv.get("reason", "")).strip()):
            errors.append(f"{w}: probe.waived needs a source starting with 'user' and a reason")
        else: waived = set(wv["fields"])
    if s.get("status") == "probed":  # completeness criterion: fast-path fields + metrics minimum standard
        for k in ("problem", "action", "result", "my_role", "stack"):
            if not pr.get(k) and k not in waived: errors.append(f"{w}: probed but probe.{k} is empty")
        types = {m.get("type") for m in pr.get("metrics", [])} | (waived & {"scale", "impact"})
        if not {"scale", "impact"} <= types: errors.append(f"{w}: probed needs at least one scale and one impact metric (or the user's waiver)")
        if open_conflicts: errors.append(f"{w}: probed with {open_conflicts} open conflict(s)")
        if any(c.get("needs_confirmation") for c in s.get("source_claims", [])):
            errors.append(f"{w}: probed with unconfirmed (T3-only/assumed) claims")
        if pr.get("open_gaps"): errors.append(f"{w}: probed with open_gaps")
        for k in ("action", "result", "my_role"):
            if PASSIVE.search(str(pr.get(k, ""))): errors.append(f"{w}: passive verb in probe.{k}")

def questions():
    qids = set()
    for i, q in enumerate(read_jsonl(DATA / "bragdoc/questions.jsonl"), 1):
        w = f"questions.jsonl:{i}"
        need(q, ["id", "ref", "question", "status"], w)
        if q.get("id") in qids: errors.append(f"{w}: duplicate id")
        if q.get("status") not in ("open", "answered"): errors.append(f"{w}: status must be open|answered")
        if q.get("status") == "answered" and not q.get("answer"): errors.append(f"{w}: answered without an answer")
        qids.add(q.get("id"))
    return qids

def load_json(rel, default):
    p = DATA / rel
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding="utf-8") or json.dumps(default))
    except json.JSONDecodeError as e: errors.append(f"{rel}: invalid JSON: {e}"); return default

def profile_files(sids, eids):
    for i, j in enumerate(load_json("bragdoc/employment.json", [])):
        w = f"employment.json[{i}]"
        need(j, ["employer", "role", "start", "source"], w)
        for k in ("start", "end"):
            if j.get(k) is not None and not YM.match(str(j.get(k))): errors.append(f"{w}.{k} must be YYYY-MM (end may be null = present)")
        if j.get("end") and j.get("start") and j["end"] < j["start"]: errors.append(f"{w}: end before start")
        if "public_summary" in j and not (isinstance(j["public_summary"], str) and j["public_summary"].strip()): errors.append(f"{w}.public_summary must be a non-empty string")
        if "public_context" in j and not (isinstance(j["public_context"], list) and all(isinstance(x, str) and x.strip() for x in j["public_context"])):
            errors.append(f"{w}.public_context must be a list of non-empty strings (public text only; context stays internal)")
    for i, ed in enumerate(load_json("bragdoc/education.json", [])):
        w = f"education.json[{i}]"
        need(ed, ["degree", "institution", "graduation", "source"], w)
        if ed.get("graduation") and not YM.match(str(ed["graduation"])): errors.append(f"{w}.graduation must be YYYY-MM")
        cap = ed.get("capstone") or {}
        if cap.get("staging_id") and cap["staging_id"] not in sids: errors.append(f"{w}: capstone staging_id not found")
        if cap.get("entry_id") and cap["entry_id"] not in eids: errors.append(f"{w}: capstone entry_id not found")
    seen = set()
    for i, sk in enumerate(load_json("bragdoc/skills.json", [])):
        w = f"skills.json[{i}]"
        need(sk, ["skill", "group", "source"], w)
        key = (str(sk.get("skill", "")).lower(), sk.get("group"))
        if key in seen: errors.append(f"{w}: duplicate skill '{sk.get('skill')}'")
        seen.add(key)
        if sk.get("level") is not None and not isinstance(sk["level"], str): errors.append(f"{w}.level must be a string or null")
        for x in sk.get("evidence_entry_ids", []):
            if x not in eids: errors.append(f"{w}: evidence entry '{x}' not found")
        for x in sk.get("evidence_staging_ids", []):
            if x not in sids: errors.append(f"{w}: evidence staging id '{x}' not found")
    ips = set()
    for i, ip in enumerate(read_jsonl(DATA / "bragdoc/in_progress.jsonl"), 1):
        w = f"in_progress.jsonl:{i}"
        need(ip, ["id", "title", "kind", "status", "source"], w)
        if ip.get("id") in ips: errors.append(f"{w}: duplicate id")
        ips.add(ip.get("id"))
        if ip.get("kind") not in IP_KINDS: errors.append(f"{w}.kind must be one of {sorted(IP_KINDS)}")
        if ip.get("status") not in IP_STATUS: errors.append(f"{w}.status must be one of {sorted(IP_STATUS)}")
        if ip.get("staging_id") and ip["staging_id"] not in sids: errors.append(f"{w}: staging_id '{ip['staging_id']}' not found")
        td = ip.get("target_date")
        if td is not None and not (DATE.match(str(td)) or YM.match(str(td))): errors.append(f"{w}.target_date must be YYYY-MM[-DD] or null")

def contacts_and_policy():
    """profile.json contacts (value + channels) and the disclosure policy agree; returns contact values to protect."""
    policy, prof = load_json(POLICY_FILE, {}), load_json(PROFILE_FILE, {})
    chans = policy.get("channels", {})
    for c in chans:
        if c not in CHANNELS: errors.append(f"{POLICY_FILE}: unknown channel '{c}'")
    for kind in ("always_banned", "client_names", "project_names", "current_employer_internal_names", "vulnerability_classes"):
        for pat in policy.get("terms", {}).get(kind, []):
            try: re.compile(pat)
            except re.error as e: errors.append(f"{POLICY_FILE}: bad regex in terms.{kind}: {pat} ({e})")
    contacts = prof.get("contacts", {})
    for k, c in contacts.items():
        w = f"{PROFILE_FILE}: contacts.{k}"
        if not isinstance(c, dict) or "value" not in c or not isinstance(c.get("channels"), list): errors.append(f"{w} needs value and channels"); continue
        for ch in c["channels"]:
            if ch not in CHANNELS: errors.append(f"{w}: unknown channel '{ch}'")
            elif chans and k not in chans.get(ch, {}).get("contacts", []): errors.append(f"{w}: channel '{ch}' doesn't allow {k} (disclosure_policy.json)")
        v = str(c["value"])
        if not v: continue
        if k == "phone" and not PHONE.search(v): errors.append(f"{w}: not a phone number")
        if k.startswith("email") and not EMAIL.match(v): errors.append(f"{w}: not an email address")
        if k in ("linkedin", "github", "medium", "website") and not HTTPS.match(v): errors.append(f"{w}: must be an https URL")
    if "public" in contacts.get("phone", {}).get("channels", []): errors.append(f"{PROFILE_FILE}: phone must never be in the public channel")
    if "public" in contacts.get("email_personal", {}).get("channels", []): errors.append(f"{PROFILE_FILE}: personal email must never be in the public channel")
    banned = [re.compile(p) for p in policy.get("terms", {}).get("always_banned", [])]
    personal = [c["value"].lower() for k, c in contacts.items() if k == "email_personal" and isinstance(c, dict) and c.get("value")]
    if "name" in prof: errors.append(f"{PROFILE_FILE}: 'name' is replaced by names {{short, public_full, formal}}")
    names = prof.get("names")
    if not isinstance(names, dict) or not all(isinstance(names.get(k), str) and names[k].strip() for k in NAME_FORMS):
        errors.append(f"{PROFILE_FILE}: names needs non-empty {', '.join(NAME_FORMS)}"); names = {}
    for c, ch in chans.items():
        form = (ch.get("names") or {}).get("form")
        if form is not None and form not in NAME_FORMS: errors.append(f"{POLICY_FILE}: channels.{c}.names.form must be one of {NAME_FORMS}")
    return banned, personal, names

def forbidden_content():
    """Phone numbers and the personal email may appear only in profile.json contacts; excluded-employer terms nowhere
    (except the policy file that defines them)."""
    banned, personal, names = contacts_and_policy()
    for p in sorted(DATA.rglob("*")):
        if p.suffix not in (".json", ".jsonl", ".md") or not p.is_file(): continue
        rel = p.relative_to(DATA).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        if rel == PROFILE_FILE:
            try:
                prof = json.loads(text); prof.pop("contacts", None); text = json.dumps(prof, ensure_ascii=False)
            except json.JSONDecodeError: pass
        if rel != POLICY_FILE:
            for rx in banned:
                m = rx.search(text)
                if m: errors.append(f"{rel}: contains excluded employer reference ('{m.group(0)}')")
        m = PHONE.search(text)
        if m: errors.append(f"{rel}: contains a phone number ('{m.group(0)}'); allowed only in profile.json contacts")
        for em in personal:
            if em in text.lower(): errors.append(f"{rel}: contains the personal email; allowed only in profile.json contacts")
        for why in sorted({w for line in text.splitlines() for w in name_problems(line, {}, names)}):
            errors.append(f"{rel}: {why}")

def bragdoc():
    staging = read_jsonl(DATA / "bragdoc/staging.jsonl")
    qids = questions()
    sids = set()
    for i, s in enumerate(staging, 1):
        w = f"staging.jsonl:{i}"
        need(s, ["id", "created", "source", "raw", "status"], w)
        if s.get("status") not in {"raw", "probing", "probed", "merged"}: errors.append(f"{w}: bad status")
        pr = s.get("probe") or {}
        if pr.get("kind") and pr["kind"] not in KINDS: errors.append(f"{w}: probe.kind must be one of {sorted(KINDS)}")
        if "links" in pr: check_links(pr["links"], f"{w}: probe.links")
        if s.get("id") in sids: errors.append(f"{w}: duplicate id")
        sids.add(s.get("id"))
        staging_item(s, pr, w, qids)
    eids = set()
    for i, e in enumerate(read_jsonl(DATA / "bragdoc/entries.jsonl"), 1):
        w = f"entries.jsonl:{i}"
        need(e, ["id", "title", "category", "result", "my_role", "rank_score", "rank_rationale", "staging_ids"], w)
        if e.get("id") in eids: errors.append(f"{w}: duplicate id")
        eids.add(e.get("id"))
        rs = e.get("rank_score")
        if not isinstance(rs, int) or not 1 <= rs <= 10: errors.append(f"{w}: rank_score must be int 1-10")
        for sid in e.get("staging_ids", []):
            if sid not in sids: errors.append(f"{w}: staging id '{sid}' not found")
        public_layer(e, w)
    profile_files(sids, eids)
    return eids

def check_links(links, w):
    if not isinstance(links, dict): errors.append(f"{w} must be an object"); return
    for k, v in links.items():
        if k == "other":
            if not isinstance(v, list): errors.append(f"{w}.other must be a list"); continue
            for i, o in enumerate(v):
                if not isinstance(o, dict) or not o.get("label") or not HTTPS.match(str(o.get("url", ""))):
                    errors.append(f"{w}.other[{i}] needs a label and an https url")
        elif k not in LINK_KEYS: errors.append(f"{w}: unknown link key '{k}'")
        elif v and not HTTPS.match(str(v)): errors.append(f"{w}.{k} must be an https URL (got '{v}')")

def public_layer(e, w):
    if e.get("kind") not in KINDS: errors.append(f"{w}: kind must be one of {sorted(KINDS)}")
    if e.get("visibility") not in VISIBILITY: errors.append(f"{w}: visibility must be private|public")
    if "links" not in e: errors.append(f"{w}: missing 'links' (use {{}})")
    else: check_links(e["links"], f"{w}: links")
    pc = e.get("public_constraints")
    if not isinstance(pc, list) or not all(isinstance(x, str) for x in pc):
        errors.append(f"{w}: public_constraints must be a list of strings (use [])")
    if "published_hash" not in e: errors.append(f"{w}: missing 'published_hash' (use null)")
    elif e["published_hash"] is not None and not (isinstance(e["published_hash"], str) and HEX.match(e["published_hash"])):
        errors.append(f"{w}: published_hash must be null or a hex string")
    for f in ("public_summary", "resume_summary"):   # same structure; each generated under its channel's rules
        ps = e.get(f)
        if ps is None: continue
        if not isinstance(ps, dict): errors.append(f"{w}: {f} must be an object"); continue
        for k in ("headline", "summary", "highlights", "stack", "generated", "source_hash"):
            if k not in ps: errors.append(f"{w}: {f} missing '{k}'")
        if len(str(ps.get("headline", "")).split()) > 12: errors.append(f"{w}: {f}.headline over 12 words")
        hl = ps.get("highlights")
        if not isinstance(hl, list) or not 2 <= len(hl) <= 4: errors.append(f"{w}: {f}.highlights needs 2-4 items")
        if not isinstance(ps.get("stack", []), list): errors.append(f"{w}: {f}.stack must be a list")
        if "source_hash" in ps and not HEX.match(str(ps["source_hash"])): errors.append(f"{w}: {f}.source_hash must be hex")

def extrovert_config():
    cfg = load_json("extrovert/config.json", {})
    w = "extrovert/config.json"
    if not isinstance(cfg.get("news_fields", []), list) or not all(isinstance(x, str) for x in cfg.get("news_fields", [])):
        errors.append(f"{w}: news_fields must be a list of strings")
    for p in (cfg.get("platforms") or {}):
        if p not in PLATFORMS: errors.append(f"{w}: platforms.{p} is not a post target ({sorted(PLATFORMS)})")
    notes = cfg.get("voice_notes", [])
    if not isinstance(notes, list): errors.append(f"{w}: voice_notes must be a list of lessons")
    else:
        for i, n in enumerate(notes):
            if not isinstance(n, dict) or not n.get("lesson") or not DATE.match(str(n.get("date", ""))):
                errors.append(f"{w}: voice_notes[{i}] needs a lesson and a YYYY-MM-DD date")
    ban = cfg.get("ban", {})
    if not isinstance(ban.get("phrases", []), list): errors.append(f"{w}: ban.phrases must be a list")

def voice_profile():
    """data/extrovert/voice/profile.json (optional): registers with known limits, compilable regexes, samples in
    raw/extrovert/voice/ unchanged since they were added (by hash), evidence quoted verbatim from a sample, history."""
    import hashlib
    from _common import ROOT
    from voice_lint import LIMITS, CONSTRUCTIONS
    if not (DATA / "extrovert/voice/profile.json").exists(): return
    p, w = load_json("extrovert/voice/profile.json", {}), "extrovert/voice/profile.json"
    need(p, ["version", "updated", "source", "traits", "registers", "banned", "history"], w)
    if not isinstance(p.get("version"), int) or p.get("version", 0) < 1: errors.append(f"{w}: version must be an integer >= 1")
    if not DATE.match(str(p.get("updated", ""))): errors.append(f"{w}: updated must be YYYY-MM-DD")
    def regex(rx, where):
        try: re.compile(rx)
        except (re.error, TypeError) as e: errors.append(f"{where}: invalid regex: {e}")
    texts = []
    for i, s in enumerate(p.get("samples", [])):
        sw, f = f"{w}: samples[{i}]", str(s.get("file", ""))
        if not f.startswith("raw/extrovert/voice/"): errors.append(f"{sw}.file must be under raw/extrovert/voice/"); continue
        if not s.get("use") or not DATE.match(str(s.get("added", ""))): errors.append(f"{sw}: needs use and added (YYYY-MM-DD)")
        fp = ROOT / f
        if fp.is_file():
            if hashlib.sha256(fp.read_bytes()).hexdigest() != s.get("sha256"): errors.append(f"{sw}: {f} doesn't match its sha256 (a sample never changes)")
            texts.append(fp.read_text(encoding="utf-8"))
        elif (ROOT / "raw").is_dir(): errors.append(f"{sw}: {f} is missing")
    ids = set()
    for i, t in enumerate(p.get("traits", [])):
        tw = f"{w}: traits[{i}]"
        need(t, ["id", "name", "description", "public", "source"], tw)
        if t.get("id") in ids: errors.append(f"{tw}: duplicate id '{t.get('id')}'")
        ids.add(t.get("id"))
        if t.get("public") not in ("keep", "limit", "drop"): errors.append(f"{tw}.public must be keep|limit|drop")
        for e in t.get("evidence", []) if texts else []:
            if not any(e in x for x in texts): errors.append(f"{tw}: evidence not quoted verbatim from a sample: {e[:60]!r}")
    regs = p.get("registers", {})
    if not isinstance(regs, dict) or not regs: errors.append(f"{w}: registers must name at least one register"); regs = {}
    for name, r in regs.items():
        rw = f"{w}: registers.{name}"
        if not r.get("description"): errors.append(f"{rw}: needs a description")
        for pl in r.get("platforms", []):
            if pl not in PLATFORMS: errors.append(f"{rw}.platforms: '{pl}' is not a post target")
        for k, v in (r.get("limits") or {}).items():
            if k not in LIMITS: errors.append(f"{rw}.limits: unknown limit '{k}' (known: {', '.join(sorted(LIMITS))})")
            elif not isinstance(v, LIMITS[k]) or (LIMITS[k] is int and (isinstance(v, bool) or v < 0)):
                errors.append(f"{rw}.limits.{k} must be a{' non-negative' if LIMITS[k] is int else ''} {LIMITS[k].__name__}")
        run = (r.get("limits") or {}).get("same_length_run")
        if isinstance(run, dict) and not all(isinstance(run.get(k), int) and run[k] >= 0 for k in ("sentences", "spread_words")):
            errors.append(f"{rw}.limits.same_length_run needs integer sentences and spread_words")
        for j, d in enumerate(r.get("drop", [])):
            need(d, ["id", "label", "regex"], f"{rw}.drop[{j}]"); regex(d.get("regex"), f"{rw}.drop[{j}]")
    b = p.get("banned", {})
    if not isinstance(b.get("phrases", []), list): errors.append(f"{w}: banned.phrases must be a list")
    for j, pt in enumerate(b.get("patterns", [])):
        need(pt, ["id", "label", "regex"], f"{w}: banned.patterns[{j}]"); regex(pt.get("regex"), f"{w}: banned.patterns[{j}]")
    for c in b.get("constructions", []):
        if c not in CONSTRUCTIONS: errors.append(f"{w}: banned.constructions: unknown '{c}' (known: {', '.join(sorted(CONSTRUCTIONS))})")
    hist = p.get("history", [])
    if not hist or any(not (isinstance(h.get("version"), int) and DATE.match(str(h.get("date", ""))) and h.get("change") and h.get("source")) for h in hist):
        errors.append(f"{w}: history needs items {{version, date, change, source}}")
    elif max(h["version"] for h in hist) != p.get("version"): errors.append(f"{w}: version must equal the latest history version")

IDEA_EVENTS, IDEA_STATUS = {"add", "edit", "status", "merge"}, {"new", "developing", "posted", "parked", "dropped", "merged"}
IDEA_ID, IDEA_FIELDS = re.compile(r"^i-\d{4}$"), {"raw", "gist", "tags", "context", "links", "sensitive"}

def idea_links(links, w):
    if not isinstance(links, list): errors.append(f"{w}: links must be a list"); return
    for j, l in enumerate(links):
        if not HTTPS.match(str(l.get("url", ""))): errors.append(f"{w}: links[{j}].url must be https")
        if not isinstance(l.get("fetched"), bool): errors.append(f"{w}: links[{j}].fetched must be true|false")
        elif l["fetched"] and not (l.get("title") and l.get("summary")): errors.append(f"{w}: links[{j}] fetched without title/summary")

def ideas_log():
    """Append-only event log: ids exist, statuses valid, merged_into points at a real idea, ts never goes backwards."""
    seen, prev = {}, ""
    for i, e in enumerate(read_jsonl(DATA / "extrovert/ideas.jsonl"), 1):
        w = f"ideas.jsonl:{i}"
        iid, ev, d, t = e.get("idea_id"), e.get("event"), e.get("data") or {}, str(e.get("ts", ""))
        try: dt.datetime.fromisoformat(t)
        except ValueError: errors.append(f"{w}: ts must be ISO 8601"); continue
        if t < prev: errors.append(f"{w}: ts goes backwards (log is append-only)")
        prev = max(prev, t)
        if not IDEA_ID.match(str(iid)): errors.append(f"{w}: idea_id must look like i-0001")
        if ev not in IDEA_EVENTS: errors.append(f"{w}: event must be one of {sorted(IDEA_EVENTS)}"); continue
        if ev in ("add", "merge"):
            if iid in seen: errors.append(f"{w}: {iid} already exists")
            if not str(d.get("raw", "")).strip() or not str(d.get("gist", "")).strip(): errors.append(f"{w}: raw and gist required")
            tags = d.get("tags")
            if not isinstance(tags, list) or not 2 <= len(tags) <= 5: errors.append(f"{w}: tags must be 2-5 strings")
            idea_links(d.get("links", []), w)
            if ev == "merge":
                mf = d.get("merged_from", [])
                if len(mf) < 2 or any(x not in seen for x in mf): errors.append(f"{w}: merged_from must list 2+ existing ideas")
            seen[iid] = "new"
            continue
        if iid not in seen: errors.append(f"{w}: {ev} for unknown idea {iid}"); continue
        if ev == "edit":
            s = d.get("set") or {}
            if not s or set(s) - IDEA_FIELDS: errors.append(f"{w}: edit.set must use {sorted(IDEA_FIELDS)}")
            if "tags" in s and not (isinstance(s["tags"], list) and 2 <= len(s["tags"]) <= 5): errors.append(f"{w}: tags must be 2-5 strings")
            if "links" in s: idea_links(s["links"], w)
        elif ev == "status":
            to = d.get("to")
            if to not in IDEA_STATUS: errors.append(f"{w}: status must be one of {sorted(IDEA_STATUS)}")
            if to == "merged" and d.get("merged_into") not in seen: errors.append(f"{w}: merged_into '{d.get('merged_into')}' is not a real idea")
            for u in d.get("urls", []):
                if not HTTPS.match(str(u)): errors.append(f"{w}: url must be https ({u})")
            seen[iid] = to
    return set(seen)

def fourthwall_data():
    """Manifest allowlist rules, journal enums, state and deny-list shape."""
    if not (DATA / "fourthwall").exists(): return
    from fourthwall import manifest_problems, KINDS as FW_KINDS
    man = load_json("fourthwall/manifest.json", None)
    if man is not None:
        for p in manifest_problems(man): errors.append(f"fourthwall/manifest.json: {p}")
    for i, e in enumerate(read_jsonl(DATA / "fourthwall/journal.jsonl"), 1):
        w = f"fourthwall/journal.jsonl:{i}"
        try: dt.datetime.fromisoformat(str(e.get("ts", "")))
        except ValueError: errors.append(f"{w}: ts must be ISO 8601")
        if e.get("kind") not in FW_KINDS: errors.append(f"{w}: kind must be one of {sorted(FW_KINDS)}")
        if not str(e.get("title", "")).strip() or not str(e.get("text", "")).strip(): errors.append(f"{w}: title and text required")
        if not isinstance(e.get("tags", []), list): errors.append(f"{w}: tags must be a list")
        if e.get("commit") and not re.fullmatch(r"[0-9a-f]{7,40}", str(e["commit"])): errors.append(f"{w}: commit must be a git hash")
        if e.get("tier") and e["tier"] not in TIERS: errors.append(f"{w}: tier must be T0-T3")
    st = load_json("fourthwall/state.json", {})
    for k in ("ip_policy_checked", "last_export_clean"):
        if k in st and not isinstance(st[k], bool): errors.append(f"fourthwall/state.json: {k} must be true|false")
    for v in st.get("published_versions", []):
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(v.get("version", ""))): errors.append("fourthwall/state.json: published version must be X.Y.Z")
    if st.get("commit_email") and not str(st["commit_email"]).endswith("@users.noreply.github.com"):
        errors.append("fourthwall/state.json: commit_email must be a GitHub noreply address")
    deny = load_json("fourthwall/denylist.json", {})
    for k in ("terms", "exact_terms", "regex", "derive_ignore"):
        if not all(isinstance(x, str) for x in deny.get(k, [])): errors.append(f"fourthwall/denylist.json: {k} must be a list of strings")
    for pat in deny.get("regex", []) + [x.get("line_regex", "") for x in deny.get("author_line_exemptions", [])]:
        try: re.compile(pat)
        except re.error as e: errors.append(f"fourthwall/denylist.json: bad regex {pat} ({e})")

YEAR_SOURCES = {"period", "staging", "project_years", "employer_default", "tenure"}
SITE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CARD_KEYS = ("metric", "context", "did", "result", "where")

def runway_data():
    """Site fields on entries/staging, the project -> year map, RUNWAY config + state, and the never-tracked deploy hook."""
    import subprocess
    from _common import ROOT
    entries, stg = read_jsonl(DATA / "bragdoc/entries.jsonl"), read_jsonl(DATA / "bragdoc/staging.jsonl")
    st = load_json("runway/state.json", {})
    slugs, retired = {}, set(st.get("retired_slugs", []))
    for e in entries:
        w = f"entries.jsonl {e.get('id')}"
        s = e.get("site_slug")
        if s is not None:
            if not SITE_SLUG.match(str(s)): errors.append(f"{w}: site_slug must be a lowercase-hyphen slug")
            if s in slugs: errors.append(f"{w}: site_slug '{s}' already used by {slugs[s]}")
            if s in retired: errors.append(f"{w}: site_slug '{s}' is retired and can never be reused")
            slugs[s] = e.get("id")
        card = e.get("site_card")
        if card is not None:
            if not isinstance(card, dict): errors.append(f"{w}: site_card must be an object")
            else:
                for k in CARD_KEYS + ("generated", "source_hash"):
                    if not (isinstance(card.get(k), str) and card[k].strip()): errors.append(f"{w}: site_card.{k} missing")
                if len(str(card.get("metric", ""))) > 40: errors.append(f"{w}: site_card.metric over 40 chars")
                if card.get("source_hash") and not HEX.match(str(card["source_hash"])): errors.append(f"{w}: site_card.source_hash must be hex")
    for rows, name in ((entries, "entries.jsonl"), (stg, "staging.jsonl")):
        for r in rows:
            if "year" in r and not re.fullmatch(r"\d{4}", str(r["year"])): errors.append(f"{name} {r.get('id')}: year must be YYYY")
            if "year_source" in r and r["year_source"] not in YEAR_SOURCES: errors.append(f"{name} {r.get('id')}: year_source must be one of {sorted(YEAR_SOURCES)}")
    py = load_json("bragdoc/project_years.json", {})
    for k in ("projects", "employer_default"):
        for key, y in (py.get(k) or {}).items():
            if not re.fullmatch(r"\d{4}", str(y)): errors.append(f"bragdoc/project_years.json: {k}.{key} must be a YYYY string")
    c = load_json("runway/config.json", None)
    if c is None: return
    w = "runway/config.json"
    fids = {f.get("id") for f in c.get("fields", [])}
    for f in c.get("fields", []):
        if not all(isinstance(f.get(k), str) and f[k] for k in ("id", "name", "color")): errors.append(f"{w}: fields need id, name, color")
    for cat, fid in (c.get("category_to_field") or {}).items():
        if fid not in fids: errors.append(f"{w}: category_to_field.{cat} -> '{fid}' is not a field id")
    covered = sorted(r for b in c.get("impact_bands", []) for r in range(b["min"], b["max"] + 1))
    if covered != list(range(1, 11)): errors.append(f"{w}: impact_bands must cover rank 1-10 exactly once")
    if any(b.get("impact") not in (1, 2, 3) for b in c.get("impact_bands", [])): errors.append(f"{w}: impact must be 1-3")
    vd = c.get("visibility_default") or {}
    if vd.get("new_entries") not in VISIBILITY or vd.get("current_employer") not in VISIBILITY: errors.append(f"{w}: visibility_default values must be public|private")
    if not str((c.get("pdf") or {}).get("file", "")).endswith(".pdf"): errors.append(f"{w}: pdf.file must end in .pdf")
    eids, sids = {e.get("id") for e in entries}, {s.get("id") for s in stg}
    show = st.get("showcase", [])
    if len(show) > c.get("max_highlights", 3): errors.append(f"runway/state.json: showcase has more than {c.get('max_highlights', 3)} entries")
    for i in show:
        if i not in eids: errors.append(f"runway/state.json: showcase entry '{i}' not found")
    for it in st.get("showcase_intents", []):
        if it.get("staging_id") not in sids: errors.append(f"runway/state.json: showcase intent staging id '{it.get('staging_id')}' not found")
        if it.get("replaces") and it["replaces"] not in eids: errors.append(f"runway/state.json: intent replaces unknown entry '{it['replaces']}'")
    hook = c.get("deploy_hook_file", "data/runway/deploy-hook.local")
    if (ROOT / ".git").exists():
        p = subprocess.run(["git", "ls-files", "--error-unmatch", hook], cwd=ROOT, capture_output=True, text=True)
        if p.returncode == 0: errors.append(f"{hook} is tracked by git: it holds a secret; untrack it (git rm --cached) and rotate the hook")
        gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
        if hook not in gi.splitlines(): errors.append(f".gitignore must list {hook}")

def repo_metadata():
    """data/extrovert/repos/state.json: every recorded version has its v<N>.md, latest is the newest, applied exists."""
    p = DATA / "extrovert/repos/state.json"
    if not p.exists(): return
    w = "extrovert/repos/state.json"
    for name, r in (load_json("extrovert/repos/state.json", {}).get("repos") or {}).items():
        vs = r.get("versions") or {}
        for n, v in vs.items():
            if not (DATA / f"extrovert/repos/{name}/v{n}.md").exists(): errors.append(f"{w}: {name} v{n} has no v{n}.md")
            if not DATE.match(str(v.get("date", ""))) or not isinstance(v.get("snapshot"), dict): errors.append(f"{w}: {name} v{n} needs a date and a snapshot")
        if vs and r.get("latest") != max(int(n) for n in vs): errors.append(f"{w}: {name} latest must be its newest version")
        ap = r.get("applied")
        if ap and str(ap.get("version")) not in vs: errors.append(f"{w}: {name} applied v{ap.get('version')} doesn't exist")

def extrovert(eids):
    extrovert_config()
    voice_profile()
    repo_metadata()
    idea_ids = ideas_log()
    for mp in sorted((DATA / "extrovert/conversations").glob("*/meta.json")):
        w = f"conversations/{mp.parent.name}/meta.json"
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{w}: invalid JSON: {e}"); continue
        status = m.get("status")
        if status not in {"open", "edited", "posted"}: errors.append(f"{w}: status must be open|edited|posted")
        pub = m.get("published", [])
        if not isinstance(pub, list): errors.append(f"{w}: published must be a list"); pub = []
        if status == "posted" and not pub: errors.append(f"{w}: status is posted but published is empty")
        for i, p in enumerate(pub):
            pw = f"{w}: published[{i}]"
            if p.get("platform") not in PLATFORMS: errors.append(f"{pw}.platform must be one of {sorted(PLATFORMS)}")
            if not HTTPS.match(str(p.get("url", ""))): errors.append(f"{pw}.url must be an https URL")
            if not p.get("title"): errors.append(f"{pw}: missing title")
            if not DATE.match(str(p.get("published_date", ""))): errors.append(f"{pw}.published_date must be YYYY-MM-DD")
            for k in ("read_time_min", "word_count"):
                if not isinstance(p.get(k), int) or isinstance(p.get(k), bool): errors.append(f"{pw}.{k} must be an integer")
            if not isinstance(p.get("canonical"), bool): errors.append(f"{pw}.canonical must be true/false")
            if len(str(p.get("excerpt", "")).split()) > 40: errors.append(f"{pw}.excerpt over 40 words")
        if pub and sum(p.get("canonical") is True for p in pub) != 1:
            errors.append(f"{w}: exactly one published item must be canonical")
        for rid in m.get("related_entries", []):
            if rid not in eids: errors.append(f"{w}: related entry '{rid}' not in entries.jsonl")
        for iid in m.get("ideas", []):
            if iid not in idea_ids: errors.append(f"{w}: idea '{iid}' not in ideas.jsonl")

def main():
    eids = set()
    try: chassis()
    except ValueError as e: errors.append(str(e))
    try: eids = bragdoc()
    except ValueError as e: errors.append(str(e))
    try: extrovert(eids)
    except ValueError as e: errors.append(str(e))
    try: fourthwall_data()
    except ValueError as e: errors.append(str(e))
    try: runway_data()
    except ValueError as e: errors.append(str(e))
    forbidden_content()
    if errors:
        print("VALIDATION FAILED:\n- " + "\n- ".join(errors), file=sys.stderr)
        sys.exit(2 if "--hook" in sys.argv else 1)
    if "--hook" not in sys.argv: print("OK")

if __name__ == "__main__":
    main()
