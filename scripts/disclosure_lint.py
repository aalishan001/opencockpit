#!/usr/bin/env python3
"""Check rendered output against data/bragdoc/disclosure_policy.json. Non-zero exit = blocked.
  disclosure_lint.py --channel internal|resume|public <file>      (.html is reduced to text first)
Checks, by channel (see the policy's "checks"):
  all       excluded-employer terms
  resume    current-employer internal names, public_constraints terms, absolute cost figures,
            the domain email (resumes always use the personal email)
  public    all of resume, plus vulnerability class names, phone numbers and personal email addresses;
            revenue / contract figures never ("revenue_figures"); user, tenant and customer counts and relative cost
            changes only where the channel's "user_counts" / "relative_costs" allow them (e.g. "past_employers":
            past employers', clients' and personal work, never the current employer from employment.json);
            without that key, no cost figure at all. Absolute amounts are never allowed.
  names     (per channel, from profile.json -> names) a wrong casing of the formal name is an error everywhere;
            public blocks the formal form; a whole resume must contain the formal name exactly
Client/employer and project/app names are allowed on every channel.
Also importable: render.py and bragdoc_public.py set-summary use the same checks.
"""
import html, json, re, sys, pathlib
from _common import DATA, read_jsonl

PHONE = re.compile(r"(?<!\w)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")
NUMBER = re.compile(r"(?<![\w.])\d")
ANY_GMAIL = re.compile(r"[\w.+-]+@gmail\.com", re.I)
STOP = {"client", "name", "names", "the", "our", "internal", "number", "numbers", "count", "system", "service"}

def leak_terms(constraints):
    """Distinctive tokens of each public_constraints string (proper nouns, numbers) that must not appear."""
    out = set()
    for c in constraints:
        for tok in re.findall(r"[\w$€₹%.-]+", c):
            tok = tok.strip(".-")
            if len(tok) > 1 and tok.lower() not in STOP and (tok[0].isupper() or any(ch.isdigit() for ch in tok)):
                out.add(tok)
    return out

def current_employers():
    """Employers with an open role (end: null) in employment.json. Never hard-coded: a job change re-tiers every rule."""
    p = DATA / "bragdoc/employment.json"
    jobs = json.loads(p.read_text(encoding="utf-8") or "[]") if p.exists() else []
    return {j["employer"] for j in jobs if j.get("employer") and j.get("end") is None}

def norm(s): return re.sub(r"\s+", " ", s).strip().strip(".;:!? ").lower()

def card_strings(e):
    out = []
    for f in ("public_summary", "site_card"):
        v = e.get(f) or {}
        for k in ("headline", "summary", "metric", "context", "did", "result", "where"):
            if isinstance(v.get(k), str): out.append(v[k])
        out += [h for h in v.get("highlights", []) if isinstance(h, str)]
    return out

def context(entries=None):
    policy = json.loads((DATA / "bragdoc/disclosure_policy.json").read_text(encoding="utf-8"))
    prof = json.loads((DATA / "profile.json").read_text(encoding="utf-8"))
    entries = read_jsonl(DATA / "bragdoc/entries.jsonl") if entries is None else entries
    terms = set()
    for e in entries: terms |= leak_terms(e.get("public_constraints", []))
    cur = current_employers()
    # public text of entries whose relative costs may appear in a whole document (no current-employer entries)
    allow = [norm(s) for e in entries if e.get("employer") not in cur for s in card_strings(e)]
    return {"policy": policy, "contacts": prof.get("contacts", {}), "constraint_terms": terms, "names": prof.get("names") or {},
            "current_employers": cur, "cost_allow": allow}

NO_ENTRY = object()   # check() called on a whole document: no entry context

def relative_cost_ok(sentence, rule, ctx, entry):
    """A scoped figure (relative cost, user count): allowed only where the channel's rule for it says "past_employers"."""
    if rule != "past_employers": return False
    if entry is NO_ENTRY:   # whole document: only text that came from an allowed entry, verbatim
        s = norm(sentence)
        return bool(s) and any(s in a for a in ctx.get("cost_allow", []))
    return (entry or {}).get("employer") not in ctx.get("current_employers", set())

def name_patterns(names):
    """(formal, formal_rx, prefix, prefix_rx). prefix = the formal tokens before names.short (e.g. a title or initial)."""
    formal, short = (names.get("formal") or "").strip(), (names.get("short") or "").strip()
    if not formal: return "", None, "", None
    frx = re.compile(rf"(?i)(?<!\w){re.escape(formal)}(?!\w)")
    toks = formal.split()
    if short and short in toks and toks.index(short) > 0:
        prefix = " ".join(toks[:toks.index(short)])
        return formal, frx, prefix, re.compile(rf"(?i)(?<!\w){re.escape(prefix)}\.?\s+{re.escape(short)}(?!\w)")
    return formal, frx, "", None

def name_problems(line, rule, names):
    """Messages for one line under a channel's name rule ({form, require?, block_formal?})."""
    formal, frx, prefix, prx = name_patterns(names)
    out = []
    if not frx: return out
    for m in frx.finditer(line):
        if m.group(0) != formal: out.append(f"names: wrong casing of the formal name: '{m.group(0)}' (stored form: '{formal}')")
    if prx:
        for m in prx.finditer(line):
            if not m.group(0).startswith(prefix) and not any(m.group(0) in x for x in out):
                out.append(f"names: wrong casing of the formal name: '{m.group(0)}'")
    if rule.get("block_formal"):
        hits = [m.group(0) for m in frx.finditer(line)] + ([m.group(0) for m in prx.finditer(line)] if prx else [])
        if hits: out.append(f"names: the formal name form is not allowed on this channel: '{hits[0]}'")
    return out

def channel_contacts(channel, ctx):
    """[(field, value)] a render may show on this channel: allowed by the policy AND listed in the contact's channels."""
    allowed = ctx["policy"]["channels"][channel]["contacts"]
    contacts, out = ctx["contacts"], []
    for k in ("phone", "email_personal", "email_domain", "linkedin", "github", "medium", "website"):
        c = contacts.get(k) or {}
        if not c.get("value") or k not in allowed or channel not in c.get("channels", []): continue
        out.append((k, c["value"]))
    return out

def to_lines(text):
    if re.search(r"<(p|li|h\d|div|ul|br|body)\b", text, re.I):
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<br\s*/?>|</(p|li|h\d|div|ul|title)>", "\n", text, flags=re.I)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return [l.strip() for l in text.splitlines()]

def check(lines, channel, ctx, constraint_terms=None, whole_doc=False, entry=NO_ENTRY):
    """whole_doc=True for a complete output (a rendered resume): enables the channel's 'require' name rule.
    entry: the BragDoc entry these lines describe (decides relative-cost rules); omitted = a whole document."""
    pol, checks = ctx["policy"], set(ctx["policy"]["channels"][channel]["checks"])
    terms = pol.get("terms", {}); costs = pol.get("cost_patterns", {})
    rx = {k: [re.compile(p) for p in terms.get(k, [])] for k in terms}
    absolute, cost_words = re.compile(costs["absolute"]), re.compile(costs["cost_words"], re.I)
    nums = pol.get("number_patterns", {})
    revenue = re.compile(nums["revenue_words"]) if nums.get("revenue_words") else None
    users = re.compile(nums["user_counts"]) if nums.get("user_counts") else None
    cterms = ctx["constraint_terms"] if constraint_terms is None else constraint_terms
    contacts = ctx["contacts"]
    personal = ((contacts.get("email_personal") or {}).get("value") or "").lower()
    domain = ((contacts.get("email_domain") or {}).get("value") or "").lower()
    found = []
    def hit(n, line, why): found.append((n, line, why))
    for n, line in enumerate(lines, 1):
        if not line: continue
        for kind in ("always_banned", "client_names", "project_names", "current_employer_internal_names", "vulnerability_classes"):
            if kind not in checks: continue
            for r in rx.get(kind, []):
                m = r.search(line)
                if m: hit(n, line, f"{kind.replace('_', ' ')}: '{m.group(0)}'")
        if "public_constraints" in checks:
            for t in cterms:
                if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", line, re.I): hit(n, line, f"public_constraints term: '{t}'")
        if "absolute_costs" in checks or "any_costs" in checks:
            m = absolute.search(line)
            if m: hit(n, line, f"absolute cost figure: '{m.group(0)}'")
        if "any_costs" in checks:
            rule = pol["channels"][channel].get("relative_costs")
            for s in re.split(r"(?<=[.!?;])\s+", line):
                if cost_words.search(s) and NUMBER.search(s) and not absolute.search(s) and not relative_cost_ok(s, rule, ctx, entry):
                    why = ("current-employer cost figure (never on this channel)" if rule == "past_employers" and entry is not NO_ENTRY
                           else "cost figure not from an allowed past-employer entry" if rule == "past_employers"
                           else "employer cost figure (none allowed on this channel)")
                    hit(n, line, f"{why}: '{s[:80]}'")
        if "revenue_figures" in checks and revenue:
            for s in re.split(r"(?<=[.!?;])\s+", line):
                if revenue.search(s) and NUMBER.search(s): hit(n, line, f"revenue or contract figure (never on this channel): '{s[:80]}'")
        if "user_counts" in checks and users:
            rule = pol["channels"][channel].get("user_counts")
            for s in re.split(r"(?<=[.!?;])\s+", line):
                if users.search(s) and not relative_cost_ok(s, rule, ctx, entry):
                    why = ("current-employer user/tenant/customer count (never on this channel)" if rule == "past_employers" and entry is not NO_ENTRY
                           else "user count not from an allowed past-employer entry" if rule == "past_employers"
                           else "user/tenant/customer count (none allowed on this channel)")
                    hit(n, line, f"{why}: '{s[:80]}'")
        if "contacts" in checks:
            if channel == "public":
                m = PHONE.search(line)
                if m: hit(n, line, f"phone number: '{m.group(0)}'")
                if (personal and personal in line.lower()) or ANY_GMAIL.search(line): hit(n, line, "personal email address")
            elif channel == "resume" and domain and domain in line.lower():
                hit(n, line, "domain email on a resume (resumes always use the personal email)")
        if "names" in checks:
            for why in name_problems(line, pol["channels"][channel].get("names", {}), ctx.get("names", {})): hit(n, line, why)
    rule, names = pol["channels"][channel].get("names", {}), ctx.get("names", {})
    if whole_doc and "names" in checks and rule.get("require"):
        want = names.get(rule.get("form", "formal"), "")
        if want and not any(want in l for l in lines if l):
            hit(0, "", f"names: this {channel} output must show the name exactly as '{want}' (an all-caps look is CSS text-transform, never changed text)")
    return found

def pdf_lines(path):
    """(text lines, metadata lines, page count) of a PDF, for linting what a reader of the file would see."""
    from pypdf import PdfReader
    r = PdfReader(str(path))
    text = [l.strip() for pg in r.pages for l in (pg.extract_text() or "").splitlines()]
    meta = [f"{k}: {v}" for k, v in (r.metadata or {}).items()]
    return text, meta, len(r.pages)

def leak_hits(lines, patterns):
    """[(n, line, why)] for lines matching any local-path / username pattern (compiled regexes)."""
    return [(n, l, f"local path or username: '{m.group(0)}'") for n, l in enumerate(lines, 1) for rx in patterns if (m := rx.search(l))]

def lint_text(text, channel, ctx=None, constraint_terms=None):
    return check(to_lines(text), channel, ctx or context(), constraint_terms, whole_doc=True)

def report(found):
    return "\n".join(f"  line {n}: {why}\n    > {line[:160]}" for n, line, why in found)

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) != 3 or a[0] != "--channel" or a[1] not in ("internal", "resume", "public"): print(__doc__); sys.exit(2)
    found = lint_text(pathlib.Path(a[2]).read_text(encoding="utf-8"), a[1])
    if found:
        print(f"BLOCKED ({a[1]} channel): {len(found)} problem(s)\n" + report(found)); sys.exit(1)
    print(f"OK: passes the {a[1]} channel")
