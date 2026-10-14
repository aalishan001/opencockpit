#!/usr/bin/env python3
"""bragDoc extractor: writes the read-only prompt for an AI session, and checks what comes back. Deterministic only.
  extractor.py prompt session [--personal]
  extractor.py prompt incident <YYYY-MM-DD> "<short description>" [--personal]
  extractor.py prompt project [--personal]
  extractor.py prompt period <from> <to> "<topic>" [--personal]    from/to: YYYY-MM or YYYY-MM-DD, from <= to
  extractor.py source <mode>                       the dump source tag: extractor:<mode>:<today>
  extractor.py durations <first_symptom> <detected|unknown> <resolved> [--mitigated <ts>]
                                                   time to detect / mitigate / resolve from ISO timestamps;
                                                   "unknown" detection skips the intervals that need it
  extractor.py overlaps '<json>'|-                 entries and unmerged staging items a pasted-back item may duplicate
                                                   {raw, project?, employer?, date? | from?, to?}
--personal drops the confidentiality block: only for work that belongs to no employer or client.
COCKPIT_NOW=<ISO> overrides the clock (tests).
"""
import calendar, datetime as dt, json, os, re, sys
from _common import DATA, read_jsonl

MODES = ("session", "incident", "project", "period")
EVIDENCE_TAGS = {"measured": "[measured]", "git": "[from git/logs/docs]", "estimate": "[estimate]", "memory": "[from my memory]"}

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def die(msg): print(f"REJECTED: {msg}"); sys.exit(1)

# ---------------------------------------------------------------- prompt blocks
READ_ONLY = """READ-ONLY. While you answer:
- do not create, edit, move or delete any file;
- no commits, pushes, branches, stashes, rebases, resets or merges;
- do not run migrations, builds, tests, scripts, package installs or database queries;
- you may only read files and run read-only git commands (git log, git show, git diff);
- write the answer here in the chat only, and save nothing to disk."""

EVIDENCE = """EVIDENCE. Tag every number and every factual claim with exactly one of:
[measured] you measured it, or read a measured value from output already in this session
[from git/logs/docs] it comes from a commit, log or document: cite which
[estimate] an estimate: say how you estimated it
[from my memory] I told you and you could not verify it
No untagged numbers. If you can't support a claim, leave it out or tag it [from my memory]."""

OWNERSHIP = """OWNERSHIP, strictly. Separate what I did from what teammates, reviewers or you (the AI) did. Credit me only where the history or my own statement shows the work is mine; where it's unclear, say so. Never fold team work into mine."""

CONFIDENTIAL = """CONFIDENTIALITY (this work belongs to an employer or client). Leave out:
- code and code snippets;
- hostnames, IP addresses and URLs;
- credentials, keys, tokens and environment values;
- table, schema, service and internal system names (describe them generically, e.g. "the tenant table", "the report service");
- client and customer names;
- exploitable security specifics (name the kind of fix, never how to exploit the gap).
Commit hashes and PR numbers are fine as evidence."""

STYLE = "Plain, specific language. No marketing words, and no adjectives in place of numbers."

NOTES = """End with a section titled "Notes for you":
- what you left out and why (confidentiality, no evidence, out of scope);
- every claim that is unverified, with its tag."""

def task_session(_):
    return """TASK. Summarize the engineering work done in this session/repo for my brag document. For each distinct achievement give:
1. Problem: what was broken or missing, and who felt it.
2. What I did, versus what you generated or others did.
3. Technical decisions and trade-offs.
4. Measurable results: before and after, with units.
5. Stack.
6. Scope: systems, scale, stakeholders.
7. Evidence: commit hashes and PR numbers.
Output a list of items."""

def task_incident(a):
    return f"""TASK. Write up one incident for my brag document: {a['description']} (on {a['date']}).
1. Timeline. Date, time and timezone for: first symptom, detection, each diagnosis step, mitigation, full resolution. Tag each one.
2. Durations. Time to detect = detection minus first symptom. Time to mitigate = mitigation minus first symptom. Time to resolve = full resolution minus first symptom. Compute each from the timestamps and show the subtraction. Never write "record time", "quickly" or any other adjective in place of a number. If a timestamp is missing, say which one and leave that duration out.
3. Impact: who and what was down or degraded, how many (users, services, requests), and for how long.
4. Root cause.
5. The fix.
6. Prevention added afterwards (tests, alerts, guards, runbooks), with evidence.
7. What I'd do differently.
8. My part versus others' (see OWNERSHIP)."""

def task_project(a):
    links = ("10. Links: say which exist (repo, docs, demo) but give no URLs." if a["confidential"]
             else "10. Links: repo, docs, demo, if they exist.")
    return f"""TASK. Describe one project for my brag document.
1. What it is, in one paragraph.
2. Who owns it: personal, employer or client.
3. Status: shipped, in progress or prototype. First and latest commit dates from git log.
4. Architecture and data flow.
5. Key design decisions and trade-offs.
6. Evaluation: tests (kinds and counts), ground truth, accuracy, confidence calibration, and how each was measured.
7. Metrics, whichever apply: throughput, latency, cost per item, formats supported, fields extracted.
8. What's novel compared with the obvious approach.
9. Stack.
{links}
11. My part versus others' (see OWNERSHIP)."""

def task_period(a):
    return f"""TASK. Summarize my work on {a['topic']} from {a['from']} to {a['to']} for my brag document.
1. Timeline of phases, with dates.
2. The problem before the period started.
3. For each phase: what changed and why.
4. Metrics then vs now: each figure as first measured, its value today, and whether it is still true (re-check read-only where you can; otherwise say it is unchecked).
5. Ownership for each phase.
6. Key decisions and trade-offs.
7. What went wrong and how it was fixed.
8. Stack."""

TASKS = {"session": task_session, "incident": task_incident, "project": task_project, "period": task_period}

def build_prompt(mode, args):
    blocks = [READ_ONLY, TASKS[mode](args), EVIDENCE, OWNERSHIP]
    if args["confidential"]: blocks.append(CONFIDENTIAL)
    return "\n\n".join(blocks + [STYLE, NOTES])

# ---------------------------------------------------------------- argument checks
def parse_day(s, what):
    try: return dt.date.fromisoformat(s)
    except ValueError: die(f"{what} must be a real date YYYY-MM-DD (got '{s}')")

def bound(s, what, end):
    """YYYY-MM or YYYY-MM-DD -> date; a month means its first day (from) or last day (to)."""
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = map(int, s.split("-"))
        if not 1 <= m <= 12: die(f"{what}: bad month '{s}'")
        return dt.date(y, m, calendar.monthrange(y, m)[1] if end else 1)
    return parse_day(s, what)

def prompt_args(mode, rest):
    personal = "--personal" in rest
    pos = [x for x in rest if x != "--personal"]
    a = {"confidential": not personal}
    if mode == "incident":
        if len(pos) < 2: die('usage: prompt incident <YYYY-MM-DD> "<short description>"')
        d = parse_day(pos[0], "incident date")
        if d > now().date(): die(f"incident date {d} is in the future")
        a.update(date=d.isoformat(), description=" ".join(pos[1:]).strip())
        if not a["description"]: die("give a short description")
    elif mode == "period":
        if len(pos) < 3: die('usage: prompt period <from> <to> "<topic>"')
        f, t = bound(pos[0], "from", False), bound(pos[1], "to", True)
        if f > t: die(f"from ({pos[0]}) is after to ({pos[1]})")
        a.update({"from": pos[0], "to": pos[1], "topic": " ".join(pos[2:]).strip()})
        if not a["topic"]: die("give a topic")
    elif pos: die(f"{mode} takes no arguments besides --personal")
    return a

# ---------------------------------------------------------------- durations
def parse_ts(s, what):
    try: return dt.datetime.fromisoformat(s.replace(" ", "T", 1) if re.match(r"\d{4}-\d{2}-\d{2} \d", s) else s)
    except ValueError: die(f"{what} must be an ISO timestamp like 2026-08-27T10:05 or 2026-08-27T10:05+05:30 (got '{s}')")

def fmt(td):
    total = int(td.total_seconds())
    h, rem = divmod(total, 3600); m, s = divmod(rem, 60)
    return f"{h} h {m} min" + (f" {s} s" if s else "") + f"  ({total // 60} min)"

def durations(rest):
    mit = None
    if "--mitigated" in rest:
        i = rest.index("--mitigated"); mit = rest[i + 1] if i + 1 < len(rest) else die("--mitigated needs a timestamp")
        rest = rest[:i] + rest[i + 2:]
    if len(rest) != 3: die("usage: durations <first_symptom> <detected|unknown> <resolved> [--mitigated <ts>]")
    unknown = rest[1].strip().lower() == "unknown"   # no detection timestamp: say so, never estimate it
    first = parse_ts(rest[0], "first_symptom"); res = parse_ts(rest[2], "resolved")
    det = None if unknown else parse_ts(rest[1], "detected")
    pts = [("first symptom", first)] + ([] if unknown else [("detected", det)]) + ([("mitigated", parse_ts(mit, "mitigated"))] if mit else []) + [("resolved", res)]
    if len({p[1].tzinfo is None for p in pts}) > 1: die("mix of timestamps with and without a timezone; give all with one, or all without")
    for (n1, t1), (n2, t2) in zip(pts, pts[1:]):
        if t2 < t1: die(f"{n2} ({t2}) is before {n1} ({t1})")
    print("time to detect:    unknown (no detection timestamp)" if unknown else f"time to detect:    {fmt(det - first)}   detected - first symptom")
    if mit: print(f"time to mitigate:  {fmt(dict(pts)['mitigated'] - first)}   mitigated - first symptom")
    print(f"time to resolve:   {fmt(res - first)}   resolved - first symptom")
    print("detect to resolve: unknown (no detection timestamp)" if unknown else f"detect to resolve: {fmt(res - det)}   resolved - detected")

# ---------------------------------------------------------------- overlaps
STOP = set("""the and for was but not are has had its our out who how why one two all any new per via got did can may use
with that from into this were have after before about when then than them they their there these those which while what
also just only over under onto upon more most much many some such each every both very been being would could should
made make makes using used work worked works done item items added adding fixed fixing built build""".split())
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MON = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"

def words(text):
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", text.lower()):
        if len(w) < 3 or w in STOP: continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out

def months_in(text, default_year=None):
    """(year, month) pairs mentioned: ISO dates, 'YYYY-MM..YYYY-MM' ranges, '26 Aug 2026', 'Aug 24-27' (default year)."""
    found = set()
    for a, b in re.findall(r"(\d{4}-\d{2})(?:-\d{2})?\s*\.\.\s*(\d{4}-\d{2})", text):
        y, m = map(int, a.split("-")); y2, m2 = map(int, b.split("-"))
        while (y, m) <= (y2, m2):
            found.add((y, m)); m += 1
            if m == 13: y, m = y + 1, 1
    found |= {tuple(map(int, x.split("-"))) for x in re.findall(r"\b(\d{4}-\d{2})(?:-\d{2})?\b", text)}
    # a month name counts only next to a day or a year, or after early/mid/late ("may" alone is a verb)
    for pat in (rf"(?i)\b\d{{1,2}}\s+({MON})[a-z]*\.?(?:\s+(\d{{4}}))?",                          # 26 Aug 2026, 27 Aug
                rf"(?i)\b({MON})[a-z]*\.?\s+\d{{1,2}}(?:\s*[–-]\s*\d{{1,2}})?\b(?:,?\s*(\d{{4}}))?",   # Aug 24–27, Aug 6, 2026
                rf"(?i)\b({MON})[a-z]*\.?\s+(\d{{4}})\b",                                         # Aug 2026
                rf"(?i)\b(?:early|mid|late)[- ]({MON})[a-z]*\b()"):                               # late Aug
        for mon, year in re.findall(pat, text):
            y = int(year) if year else default_year
            if y: found.add((y, MONTHS[mon.lower()[:3]]))
    return {p for p in found if 1 <= p[1] <= 12}

def employer_key(e): return (e or "").strip().lower().split()[0] if (e or "").strip() else ""

def candidate_text(r):
    p = r.get("probe") or {}
    parts = [r.get("title", ""), r.get("raw", ""), r.get("project", ""), r.get("period", ""), r.get("problem", ""), r.get("action", ""),
             r.get("result", ""), r.get("scope", ""), p.get("problem", ""), p.get("action", ""), p.get("result", "")]
    parts += [str(c.get("value", "")) for c in r.get("source_claims", [])] + [m.get("name", "") for m in r.get("metrics", []) + p.get("metrics", [])]
    return " ".join(x for x in parts if x)

def overlaps(item):
    q_text = " ".join(str(item.get(k, "")) for k in ("raw", "project", "description", "topic"))
    q_emp = employer_key(item.get("employer"))
    emp_words = words(item.get("employer") or "")             # scored once, as "same employer"; never as a shared word
    q_words = words(q_text) - emp_words
    q_months = set()
    if item.get("date"): q_months |= months_in(item["date"])
    if item.get("from") or item.get("to"):
        q_months |= months_in(f"{(item.get('from') or item.get('to'))[:7]}..{(item.get('to') or item.get('from'))[:7]}")
    year = min(q_months)[0] if q_months else None
    pool = [(r, "entry") for r in read_jsonl(DATA / "bragdoc/entries.jsonl")]
    pool += [(r, "staging") for r in read_jsonl(DATA / "bragdoc/staging.jsonl") if r.get("status") != "merged"]
    texts = {id(r): candidate_text(r) for r, _ in pool}
    df = {}
    for t in texts.values():
        for w in words(t): df[w] = df.get(w, 0) + 1
    common = {w for w, n in df.items() if n > max(2, len(pool) / 4)}   # e.g. "database" in most entries: no signal
    rows = []
    for r, kind in pool:
        text = texts[id(r)]; score, why = 0, []
        if q_emp and q_emp == employer_key(r.get("employer")): score += 2; why.append("same employer")
        r_emp = words(r.get("employer") or "")
        if item.get("project") and (words(item["project"]) - emp_words - r_emp) & (words(r.get("project", "") + " " + r.get("title", "")) - r_emp):
            score += 2; why.append("same project")
        shared = sorted((q_words & words(text)) - common)
        if shared: score += min(len(shared), 5); why.append("words: " + ", ".join(shared[:6]))
        months = q_months & months_in(text, year)
        if months: score += 2; why.append("month " + ", ".join(f"{y}-{m:02d}" for y, m in sorted(months)))
        if score >= 4 and (shared or months): rows.append((score, r["id"], kind, why, r.get("title") or r.get("raw", "")))
    rows.sort(key=lambda x: (-x[0], x[1]))
    return rows[:8]

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "prompt" and rest and rest[0] in MODES:
        print(build_prompt(rest[0], prompt_args(rest[0], rest[1:])))
    elif cmd == "source" and len(rest) == 1 and rest[0] in MODES:
        print(f"extractor:{rest[0]}:{now().date().isoformat()}")
    elif cmd == "durations":
        durations(rest)
    elif cmd == "overlaps" and len(rest) == 1:
        item = json.loads(sys.stdin.read() if rest[0] == "-" else rest[0])
        rows = overlaps(item)
        if not rows: print("No likely overlaps."); return 0
        print("Overlaps to check before creating anything (likely: score 6+, possible: 4-5):")
        for score, rid, kind, why, title in rows:
            print(f"  {'likely  ' if score >= 6 else 'possible'} {rid}  {kind:<7} score {score:<2} {'; '.join(why)}\n      {title[:110]}")
    else:
        print(__doc__); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
