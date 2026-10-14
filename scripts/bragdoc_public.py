#!/usr/bin/env python3
"""Public layer for bragDoc entries. Deterministic, no model calls. Never publishes anything (RUNWAY does).
  bragdoc_public.py hash <entry_id>                    source hash of the entry's private fields
  bragdoc_public.py payload-hash <entry_id>            hash of the site payload (what runway promote stores as published_hash)
  bragdoc_public.py stale [--channel public|resume|card|all]   entries whose public_summary / resume_summary / site_card
                                                       is missing or out of date
  bragdoc_public.py pending                            public entries whose site payload != published_hash
  bragdoc_public.py missing-links [--add-questions]    non-work entries with no repo/live/landing link
  bragdoc_public.py set-summary <entry_id> '<json>'|- [--channel public|resume]
                                                       write public_summary (default) or resume_summary {headline, summary,
                                                       highlights, stack}; stamps generated + source_hash; rejects anything
                                                       disclosure_lint blocks on that channel
  bragdoc_public.py set-card <entry_id> '<json>'|-     write site_card {metric, context, did, result, where} under the public
                                                       channel's rules; stamps generated + source_hash
  bragdoc_public.py set-visibility <entry_id> public|private   only on the user's explicit instruction
  bragdoc_public.py default-visibility <employer|->    the standing default for a new entry (data/runway/config.json)
  bragdoc_public.py add-entry '<json>'|-               renovate's way to create an entry: next e-NNNN id, the standing
                                                       visibility default, empty links/constraints, published_hash null
  bragdoc_public.py finalize                           end of renovate: years for entries + staging, slugs, then list every
                                                       entry still missing a summary, card or year (exit 1 if any)
  bragdoc_public.py years [--apply]                    year per entry / staging item from period, project_years.json, tenure
  bragdoc_public.py change <before> <after>            relative change for public wording, e.g. 1200 450 -> -62.5%
"""
import datetime as dt, hashlib, json, os, re, sys, unicodedata
from _common import DATA, read_jsonl, write_jsonl, append_jsonl
from disclosure_lint import check as lint_check, context as lint_context, leak_terms, report as lint_report, current_employers

SUMMARY_FIELD = {"public": "public_summary", "resume": "resume_summary", "card": "site_card"}

ENTRIES, QUESTIONS, STAGING = DATA / "bragdoc/entries.jsonl", DATA / "bragdoc/questions.jsonl", DATA / "bragdoc/staging.jsonl"
YEARS, EMPLOYMENT = DATA / "bragdoc/project_years.json", DATA / "bragdoc/employment.json"
RUNWAY_CONFIG, RUNWAY_STATE = DATA / "runway/config.json", DATA / "runway/state.json"
# private fields every channel summary and card is built from, with their empty value (absent == empty)
PRIVATE = {"title": "", "problem": "", "action": "", "result": "", "metrics": [], "scope": "", "my_role": "",
           "stack": [], "public_constraints": [], "kind": "", "links": {}, "employer": "", "period": ""}
# what the site shows: a change to any of these makes a public entry pending
PAYLOAD = ("public_summary", "site_card", "links", "kind", "category", "rank_score", "year", "site_slug")
VOLATILE = ("generated",)  # excluded from the payload hash: only content changes make an entry pending
CARD_KEYS = ("metric", "context", "did", "result", "where")
KEY_LINKS = ("repo", "live", "landing")
LINKED_KINDS = {"personal_project", "product", "open_source"}  # work and community entries aren't expected to have links
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_STOP = {"a", "an", "the", "of", "to", "and", "with", "for", "in", "on", "by", "from", "its", "at", "into", "over", "under", "s",
             "so", "that", "where", "than", "more", "after", "ms", "sec", "seconds", "minute", "minutes", "hour", "hours", "x"}
SLUG_LEAD_VERBS = {"built", "cut", "made", "moved", "migrated", "resolved", "extended", "designed", "rebuilt", "re", "architected",
                   "led", "owned", "created", "added", "fixed", "shipped", "wrote", "replaced", "reduced", "raised", "improved"}

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def load(p, default): return json.loads(p.read_text(encoding="utf-8") or "null") or default if p.exists() else default

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

def source_hash(e): return digest({k: e.get(k) or empty for k, empty in PRIVATE.items()})
def payload_hash(e):
    p = {k: e.get(k) for k in PAYLOAD}
    for k in ("public_summary", "site_card"):
        if isinstance(p[k], dict): p[k] = {kk: v for kk, v in p[k].items() if kk not in VOLATILE}
    return digest(p)

def stale_reason(e, field="public_summary"):
    ps = e.get(field)
    if not ps: return "missing"
    if ps.get("source_hash") != source_hash(e): return "changed"
    return None

def find(entries, eid):
    for e in entries:
        if e.get("id") == eid: return e
    sys.exit(f"No entry with id '{eid}'.")

def missing_links(entries):
    return [e for e in entries if e.get("kind") in LINKED_KINDS
            and not any((e.get("links") or {}).get(k) for k in KEY_LINKS)]

def summary_lines(ps):
    return [ps.get("headline", ""), ps.get("summary", "")] + list(ps.get("highlights", [])) + [", ".join(ps.get("stack", []))]

def absolute_numbers(text):
    return [m.group(0) for m in re.finditer(r"(?<![\w.~])\d[\d,]*(?:\.\d+)?", text)   # whole numbers only, no backtracking
            if not re.match(r"\s*(?:%|x\b|×|percent)", text[m.end():])]

def payload(raw): return json.loads(sys.stdin.read() if raw == "-" else raw)

def set_summary(eid, raw, channel="public"):
    if channel not in ("public", "resume"): sys.exit("channel must be public or resume (cards use set-card)")
    field = SUMMARY_FIELD[channel]
    entries = read_jsonl(ENTRIES); e = find(entries, eid)
    s = payload(raw)
    missing = [k for k in ("headline", "summary", "highlights", "stack") if k not in s]
    if missing: sys.exit(f"REJECTED: missing {missing}")
    problems = []
    if len(s["headline"].split()) > 12: problems.append(f"headline has {len(s['headline'].split())} words (max 12)")
    if not 2 <= len(s["highlights"]) <= 4: problems.append(f"{len(s['highlights'])} highlights (need 2-4)")
    found = lint_check(summary_lines(s), channel, lint_context(entries), leak_terms(e.get("public_constraints", [])), entry=e)
    if problems or found:
        sys.exit("REJECTED: " + "; ".join(problems) + (f"\n{channel} channel blocked:\n" + lint_report(found) if found else ""))
    sentences = len([x for x in re.split(r"(?<=[.!?])\s+", s["summary"].strip()) if x])
    if not 2 <= sentences <= 4: print(f"WARN: summary looks like {sentences} sentence(s) (aim for 2-4)")
    if channel == "public" and e.get("employer") in current_employers() and (nums := absolute_numbers(" ".join(summary_lines(s)))):
        print(f"WARN: current-employer entry has absolute numbers {nums}: engineering figures only (no user, tenant or customer counts)")
    e[field] = {"headline": s["headline"], "summary": s["summary"], "highlights": s["highlights"],
                "stack": s["stack"], "generated": now().isoformat(timespec="seconds"), "source_hash": source_hash(e)}
    write_jsonl(ENTRIES, entries)
    print(json.dumps(e[field], indent=1, ensure_ascii=False))

def set_card(eid, raw):
    """site_card: the site's card and popup text, written under the public channel's rules for this entry."""
    entries = read_jsonl(ENTRIES); e = find(entries, eid)
    c = payload(raw)
    problems = [f"'{k}' must be a non-empty string" for k in CARD_KEYS if not (isinstance(c.get(k), str) and c[k].strip())]
    if problems: sys.exit("REJECTED: " + "; ".join(problems))
    if len(c["metric"]) > 40: problems.append(f"metric is {len(c['metric'])} chars (max 40: it is the card's headline number)")
    found = lint_check([c[k] for k in CARD_KEYS], "public", lint_context(entries), leak_terms(e.get("public_constraints", [])), entry=e)
    if problems or found:
        sys.exit("REJECTED: " + "; ".join(problems) + ("\npublic channel blocked:\n" + lint_report(found) if found else ""))
    if e.get("employer") in current_employers() and (nums := absolute_numbers(" ".join(c[k] for k in CARD_KEYS))):
        print(f"WARN: current-employer card has absolute numbers {nums}: engineering figures only (no user, tenant or customer counts)")
    e["site_card"] = {**{k: c[k].strip() for k in CARD_KEYS}, "generated": now().isoformat(timespec="seconds"), "source_hash": source_hash(e)}
    write_jsonl(ENTRIES, entries)
    print(json.dumps(e["site_card"], indent=1, ensure_ascii=False))

def set_visibility(eid, vis):
    if vis not in ("public", "private"): sys.exit("visibility must be public or private")
    entries = read_jsonl(ENTRIES); e = find(entries, eid)
    e["visibility"] = vis
    write_jsonl(ENTRIES, entries)
    print(f"{eid} \"{e.get('title','')}\" -> {vis}")
    print(json.dumps(e.get("public_summary"), indent=1, ensure_ascii=False) if e.get("public_summary") else "No public_summary yet.")
    if vis == "public":
        for f in ("public_summary", "site_card"):
            if stale_reason(e, f): print(f"WARN: {f} is {stale_reason(e, f)}; renovate regenerates it.")
        if payload_hash(e) != e.get("published_hash"): print("Pending a site update: runway publish (preview), then promote.")

# ---------------------------------------------------------------- standing visibility default
def default_visibility(employer):
    """New entries: the standing default in data/runway/config.json -> visibility_default (the user's own rule).
    Current employer = an open role in employment.json, so a job change re-tiers it; existing entries never flip."""
    rule = load(RUNWAY_CONFIG, {}).get("visibility_default") or {}
    if employer and employer in current_employers(): return rule.get("current_employer", "private")
    return rule.get("new_entries", "private")

def add_entry(raw):
    d = payload(raw)
    if "visibility" in d: sys.exit("REJECTED: visibility comes from the standing default (use set-visibility on the user's word)")
    for k in ("title", "category", "result", "my_role", "rank_score", "rank_rationale", "staging_ids"):
        if d.get(k) in (None, "", []): sys.exit(f"REJECTED: {k} is required")
    entries = read_jsonl(ENTRIES)
    n = max([int(m.group(1)) for r in entries if (m := re.match(r"e-(\d+)$", r.get("id", "")))] or [0]) + 1
    e = {"id": f"e-{n:04d}", **{k: v for k, v in d.items() if k != "id"}}
    e.setdefault("links", {}); e.setdefault("public_constraints", []); e.setdefault("updated", now().isoformat(timespec="seconds"))
    e["kind"] = e.get("kind") or ("work" if e.get("employer") else "")
    e["visibility"] = default_visibility(e.get("employer")); e["published_hash"] = None
    entries.append(e); write_jsonl(ENTRIES, entries)
    print(json.dumps({k: e[k] for k in ("id", "title", "employer", "visibility") if k in e}, ensure_ascii=False))

# ---------------------------------------------------------------- years
def tenure_year(employer, jobs):
    """The year of an employer's tenure, when all of it sits in one calendar year (the current role ends today)."""
    spans = [(j["start"], j.get("end") or now().strftime("%Y-%m")) for j in jobs if j.get("employer") == employer]
    years = {s[:4] for s, _ in spans} | {e[:4] for _, e in spans}
    return years.pop() if len(years) == 1 else None

def staging_year(s, rules, jobs):
    proj = (s.get("project") or "").strip()
    for key in (proj, proj.split(":")[0].strip()):
        if key in rules.get("projects", {}): return rules["projects"][key], "project_years"
    emp = s.get("employer")
    if emp in rules.get("employer_default", {}): return rules["employer_default"][emp], "employer_default"
    if emp and (y := tenure_year(emp, jobs)): return y, "tenure"
    return None, None

def compute_years():
    rules, jobs = load(YEARS, {}), load(EMPLOYMENT, [])
    stg = read_jsonl(STAGING); entries = read_jsonl(ENTRIES)
    sy = {s["id"]: staging_year(s, rules, jobs) for s in stg}
    ey, problems = {}, []
    for e in entries:
        ends = re.findall(r"\d{4}", str(e.get("period") or ""))
        if ends: ey[e["id"]] = (ends[-1], "period"); continue
        ys = {sy.get(s, (None, None))[0] for s in e.get("staging_ids", [])} - {None}
        if len(ys) == 1: ey[e["id"]] = (ys.pop(), "staging")
        elif len(ys) > 1: problems.append(f"{e['id']}: its staging items disagree on the year {sorted(ys)}")
        else: ey[e["id"]] = (None, None)
    return stg, entries, sy, ey, problems

def apply_years():
    stg, entries, sy, ey, problems = compute_years()
    if problems: sys.exit("REJECTED:\n  " + "\n  ".join(problems))
    changed = 0
    for rows, ys in ((stg, sy), (entries, ey)):
        for r in rows:
            y, src = ys.get(r["id"], (None, None))
            if y and (r.get("year"), r.get("year_source")) != (y, src): r["year"], r["year_source"] = y, src; changed += 1
    write_jsonl(STAGING, stg); write_jsonl(ENTRIES, entries)
    return changed, [e["id"] for e in entries if not ey.get(e["id"], (None,))[0]]

# ---------------------------------------------------------------- slugs (the site's deep-link ids: assigned once, never changed)
def slugify(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = [w for w in re.findall(r"[a-z0-9]+", t) if w not in SLUG_STOP and not w.isdigit()]
    while len(words) > 2 and words[0] in SLUG_LEAD_VERBS: words = words[1:]   # "Cut Shelfie's ..." -> "shelfie-..."
    words = words[:5]
    out = ""
    for w in words:
        if len(out) + len(w) + 1 > 48: break
        out = f"{out}-{w}" if out else w
    return out or "entry"

def assign_slugs(entries):
    """Entries with a public_summary and no site_slug get one from the public headline (never the internal title)."""
    retired = set(load(RUNWAY_STATE, {}).get("retired_slugs", []))
    taken = {e["site_slug"] for e in entries if e.get("site_slug")} | retired
    ctx, done = lint_context(entries), []
    for e in entries:
        if e.get("site_slug") or not (e.get("public_summary") or {}).get("headline"): continue
        base = slugify(e["public_summary"]["headline"]); slug, k = base, 2
        while slug in taken: slug, k = f"{base}-{k}", k + 1
        if lint_check([slug.replace("-", " ")], "public", ctx, entry=e): sys.exit(f"REJECTED: slug '{slug}' for {e['id']} fails the public lint")
        e["site_slug"] = slug; taken.add(slug); done.append((e["id"], slug))
    return done

def finalize():
    changed, no_year = apply_years()
    entries = read_jsonl(ENTRIES)
    for e in entries:
        if e.get("visibility") not in ("public", "private"): e["visibility"] = default_visibility(e.get("employer"))
    slugs = assign_slugs(entries); write_jsonl(ENTRIES, entries)
    todo = [(e["id"], f, r) for e in entries for f in ("public_summary", "resume_summary", "site_card") if (r := stale_reason(e, f))]
    todo += [(i, "year", "missing") for i in no_year]
    print(f"years: {changed} set | slugs: {len(slugs)} assigned" + "".join(f"\n  {i} -> {s}" for i, s in slugs))
    if todo:
        print("Still to write (renovate):\n" + "\n".join(f"  {i}  {f:<15} {r}" for i, f, r in todo))
        if any(f == "public_summary" for _, f, _ in todo): print("  (slugs follow once each public_summary exists: run finalize again)")
        return 1
    print("Every entry has its summaries, card, slug and year.")
    return 0

def add_link_questions(entries):
    qs = read_jsonl(QUESTIONS)
    asked = {q.get("ref") for q in qs if q.get("topic") == "links"}  # open, or answered (e.g. "none exist")
    n = max([int(m.group(1)) for q in qs if (m := re.match(r"q-(\d+)$", q.get("id", "")))] or [0])
    added = 0
    for e in missing_links(entries):
        if e["id"] in asked: continue
        n += 1; added += 1
        append_jsonl(QUESTIONS, {"id": f"q-{n:04d}", "ref": e["id"], "topic": "links",
                                 "question": f"\"{e.get('title','')}\" is {e['kind']}: what are its repo / live / landing URLs (https)?",
                                 "status": "open", "answer": ""})
    return added

def main(a):
    if not a: print(__doc__); return 1
    cmd = a[0]
    if cmd == "hash" and len(a) == 2:
        print(source_hash(find(read_jsonl(ENTRIES), a[1])))
    elif cmd == "payload-hash" and len(a) == 2:
        print(payload_hash(find(read_jsonl(ENTRIES), a[1])))
    elif cmd == "stale":
        which = a[a.index("--channel") + 1] if "--channel" in a else "all"
        chans = ["public", "resume", "card"] if which == "all" else [which]
        rows = [(e["id"], r, ch, e.get("title", "")) for e in read_jsonl(ENTRIES) for ch in chans
                if (r := stale_reason(e, SUMMARY_FIELD[ch]))]
        print("\n".join(f"{i}  {r:<8} {ch:<7} {t}" for i, r, ch, t in rows) if rows else "None stale.")
    elif cmd == "pending":
        rows = []
        for e in read_jsonl(ENTRIES):
            if e.get("visibility") == "public" and payload_hash(e) != e.get("published_hash"):
                notes = [f"{f} {r}" for f in ("public_summary", "site_card") if (r := stale_reason(e, f))]
                rows.append(f"{e['id']}  {e.get('title','')}" + (f"  ({'; '.join(notes)})" if notes else ""))
        print("\n".join(rows) if rows else "None pending.")
    elif cmd == "missing-links":
        entries = read_jsonl(ENTRIES); rows = missing_links(entries)
        print("\n".join(f"{e['id']}  {e['kind']:<16} {e.get('title','')}" for e in rows) if rows else "None missing links.")
        if "--add-questions" in a: print(f"{add_link_questions(entries)} question(s) added.")
    elif cmd == "set-summary" and len(a) in (3, 5):
        set_summary(a[1], a[2], a[a.index("--channel") + 1] if "--channel" in a else "public")
    elif cmd == "set-card" and len(a) == 3:
        set_card(a[1], a[2])
    elif cmd == "set-visibility" and len(a) == 3:
        set_visibility(a[1], a[2])
    elif cmd == "default-visibility" and len(a) == 2:
        print(default_visibility(None if a[1] == "-" else a[1]))
    elif cmd == "add-entry" and len(a) == 2:
        add_entry(a[1])
    elif cmd == "finalize":
        return finalize()
    elif cmd == "years":
        if "--apply" in a:
            changed, no_year = apply_years(); print(f"{changed} year(s) set" + (f"; no year for {no_year}" if no_year else ""))
        else:
            _, entries, sy, ey, problems = compute_years()
            for e in entries:
                y, src = ey.get(e["id"], (None, None)); print(f"{e['id']}  {y or '----'}  {src or 'no rule: set period or project_years.json'}")
            if problems: print("\n".join(problems)); return 1
    elif cmd == "change" and len(a) == 3:
        before, after = float(a[1]), float(a[2])
        if before == 0: sys.exit("before is 0: no relative change")
        pct = (after - before) / before * 100
        print(f"{pct:+.1f}%" + (f"  ({after / before:.1f}x)" if after / before >= 2 else ""))
    else:
        print(__doc__); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
