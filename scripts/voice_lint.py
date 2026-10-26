#!/usr/bin/env python3
"""Check a post or editorial against the Extrovert voice rules: the ban list in data/extrovert/config.json and the
voice profile in data/extrovert/voice/profile.json (its banned phrases and patterns, and the register's limits).
  voice_lint.py <file.md> [--register public|raw]   prints violations; exit 1 if any. public (default) = Medium, LinkedIn
  voice_lint.py --brief [--register public|raw]     the drafting brief from the profile: read it before every draft
  voice_lint.py --stats <file>                       sentence-length and rhetoric statistics of any text (calibration)
  voice_lint.py --site <dist>                        the em-dash rule on a built site's copy (titles, meta, visible text,
                                                     alt/aria-label); text marked data-source (from Medium, GitHub) only warns
Checks the body only: everything after a '<!-- notes -->' line is ignored, and so is everything before an
'<!-- article starts here -->' line (a paste sheet). Code blocks, inline code, URLs and HTML comments are never prose.
Always: banned phrases and patterns, engagement bait, emoji, "not just X, it's Y", British spellings (US spelling
always), em dashes (limit from config; 0 = none).
Register limits (profile registers.<r>.limits; a missing key = no limit): words to drop (slang, profanity, typography),
spaced-hyphen connectors, capitals for emphasis, theatrical one-line paragraphs, question-and-answer pairs,
exclamation marks, hashtags, habitual groups of three, runs of same-length sentences.
"""
import json, re, statistics, sys, pathlib
from _common import DATA
from post_stats import body, WORD

PROFILE = DATA / "extrovert/voice/profile.json"
UK_US = {  # British form (regex) -> US spelling; explicit suffixes so "programmer" or the noun "analyses" never match
    r"optimis(?:e|ed|es|ing|ation)": "optimize", r"organis(?:e|ed|es|ing|ation)": "organize", r"analys(?:e|ed|ing)": "analyze",
    r"recognis(?:e|ed|es|ing)": "recognize", r"prioritis(?:e|ed|es|ing|ation)": "prioritize", r"realis(?:e|ed|es|ing)": "realize",
    r"minimis(?:e|ed|es|ing)": "minimize", r"maximis(?:e|ed|es|ing)": "maximize", r"utilis(?:e|ed|es|ing|ation)": "utilize",
    r"colour(?:s|ed|ing|ful)?": "color", r"behaviour(?:s|al)?": "behavior", r"favourite(?:s)?": "favorite", r"centre(?:s|d)?": "center",
    r"licence(?:s)?": "license", r"catalogue(?:s|d)?": "catalog", r"modell(?:ing|ed)": "modeling", r"travell(?:ing|ed|er|ers)": "traveling",
    r"cancell(?:ed|ing)": "canceled", r"defence(?:s)?": "defense"}
# pictographs, symbols & dingbats, flags, plus a few common standalone emoji; arrows like "→" are deliberately allowed
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F1E6-\U0001F1FF⭐⬆✅❌]")
NOT_JUST = [re.compile(p, re.I) for p in (
    r"\b(?:is\s*n[o']t|not)\s+(?:just|only|merely|simply)\b[^.!?\n]{0,80}?[,;:\u2014\u2013-]\s*(?:it'?s|it is|this is|that'?s)\b",
    r"\b(?:is\s*n[o']t|not)\s+(?:just|only|merely|simply)\b[^.!?\n]{0,80}?[.!?]\s+(?:it'?s|it is|this is|that'?s)\b",
    r"\bit'?s not\b[^.!?\n]{1,60}?[,;\u2014\u2013-]\s*it'?s\b")]

# The profile's vocabulary: limit keys a register may set, and the constructions its banned list may name
LIMITS = {"caps_emphasis": int, "one_line_paragraphs": int, "one_line_words": int, "qa_pairs": int, "exclamations": int,
          "hashtags": int, "triads": int, "same_length_run": dict, "spaced_hyphen": bool}
CONSTRUCTIONS = {"not_just_x_its_y", "emoji", "hashtag_wall", "theatrical_one_line_paragraphs", "habitual_triads",
                 "same_length_sentences", "spaced_hyphen", "caps_emphasis", "exclamations", "qa_pairs"}

def load_config(): return json.loads((DATA / "extrovert/config.json").read_text(encoding="utf-8"))

def post_body(text):
    """The post body with its structure intact (code fences kept): notes, a paste sheet and front matter removed."""
    text = re.split(r"(?m)^\s*<!--\s*notes\s*-->\s*$", text)[0]
    text = re.split(r"(?m)^\s*<!--\s*article starts here\s*-->\s*$", text)[-1]
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)

def load_profile(): return json.loads(PROFILE.read_text(encoding="utf-8")) if PROFILE.exists() else {}

# ---------------------------------------------------------------- the body as blocks, prose and sentences
BLOCK_KINDS = (("heading", r"#{1,6}\s"), ("quote", r">"), ("list", r"(?:[-*+]|\d+[.)])\s"), ("table", r"\|"),
               ("image", r"!\["), ("rule", r"(?:-{3,}|\*{3,}|_{3,})\s*$"))
EMPHASIZED = re.compile(r"^\s*(\*\*|\*|__|_)(?=\S).*\S\1\s*$")      # a whole line in italics or bold: caption or label
ABBREV = ("e.g.", "i.e.", "vs.", "Mr.", "Mrs.", "Ms.", "Dr.", "St.", "No.", "Fig.", "approx.", "etc.)")
SENT = re.compile(r"(?<=[.!?])[\"”’)\]]*\s+(?=[\"“‘(\[]?[A-Z0-9])")

def blocks(text):
    """[(kind, raw_lines)] in order: heading, quote, list, table, image, rule, code, caption, prose."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    out, cur, fence = [], [], None
    def flush():
        if cur:
            first = cur[0].lstrip()
            k = next((n for n, rx in BLOCK_KINDS if re.match(rx, first)), None)
            if not k: k = "caption" if len(cur) == 1 and EMPHASIZED.match(cur[0]) else "prose"
            out.append((k, cur[:])); cur.clear()
    for ln in text.splitlines():
        if fence is not None:
            if ln.strip().startswith(fence): out.append(("code", cur[:])); cur.clear(); fence = None
            else: cur.append(ln)
            continue
        m = re.match(r"^\s*(```|~~~)", ln)
        if m: flush(); fence = m.group(1); continue
        if not ln.strip(): flush(); continue
        cur.append(ln)
    if fence is not None: out.append(("code", cur[:]))
    else: flush()
    return out

def clean(s, allow_phrases=()):
    """Markdown line(s) -> plain prose: inline code, links, URLs, images, emphasis marks and tags removed."""
    s = re.sub(r"`[^`]*`", "code", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"https?://\S+", "link", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\*\*|__|(?<!\w)\*(?=\S)|(?<=\S)\*(?!\w)|(?<!\w)_(?=\S)|(?<=\S)_(?!\w)", "", s)
    for p in allow_phrases: s = s.replace(p, "Name")
    return re.sub(r"\s+", " ", s).strip()

def sentences(p):
    for a in ABBREV: p = p.replace(a, a.replace(".", "\u2024"))
    return [s.replace("\u2024", ".").strip() for s in SENT.split(p) if WORD.search(s)]

def words(s): return len(WORD.findall(s))

def is_question(s): return s.rstrip(" \"”’)]").endswith("?")

def parse(text, allow_phrases=()):
    """(blocks, prose sentences [(block index, sentence)], plain text of prose + lists + headings + quotes)."""
    bs, sents, plain = blocks(text), [], []
    for i, (k, lines) in enumerate(bs):
        if k == "prose":
            p = clean(" ".join(l.strip() for l in lines), allow_phrases)
            sents += [(i, s) for s in sentences(p)]; plain.append(p)
        elif k in ("list", "heading", "quote"):
            plain += [clean(re.sub(r"^\s*(?:[-*+]|\d+[.)]|#{1,6}|>)\s*", "", l), allow_phrases) for l in lines]
    return bs, sents, plain

# ---------------------------------------------------------------- the register checks
ACRONYMS = set("""AI API APIS AWS CLI CPU CPUS GPU GPUS CSS CSV CVE CVES DB DNS GDPR HTML HTTP HTTPS ID IDS IO JSON JWT LLM LLMS
MIT ML NUL NULL ORM OS PDF PDFS PR PRS QA RAG REST RLS SDK SQL SSH SSO TLS UI URL URLS UX UUID XML YAML HNSW IVF ONNX CRUD ACID
CTO CEO CFO CIO HR OSS README LICENSE TODO FAQ RBAC ABAC SLA SLO KPI ETL RAM SSD VM VMS CI CD GPT NPM PNG JPEG SVG UTC IST GMT
ASCII UTF CPU IOT SAAS B2B SMS OTP OAUTH SAML LDAP CORS CSP VPN WIFI TCP UDP IP USB OK""".split())
SQL_STRONG = set("""NULL SELECT INSERT UPDATE DELETE WHERE CREATE ALTER GRANT REVOKE POLICY FORCE BYPASSRLS NOBYPASSRLS SUPERUSER
NOSUPERUSER DEFINER INVOKER NULLIF COALESCE EXPLAIN ANALYZE RETURNING USING ENABLE TABLE ROW LEVEL SECURITY WITH CHECK JOIN
FROM ORDER LIMIT VALUES COPY TRUNCATE VACUUM INDEX CONSTRAINT""".split())
SQL_JOIN = {"AND", "OR", "NOT", "ON", "IS", "IN", "AS", "BY", "SET", "ALL", "NULL", "TO", "NO", "ONLY"}
COMMON = set("""NOT ALL ANY YES NO NOW BUT AND THE YOU ONE WHY HOW BIG NEW WAS ARE CAN DID HAS HAD GET GOT TOO SO DO BE IS MY WE
ME OR IF OF ON IN AT TO BY AN FOR NOR OFF SEE SAY WHO YET OUT OUR WAY ITS HIS HER SHE HE END BAD ODD""".split())
CAPS = re.compile(r"\b[A-Z][A-Z]+s?\b")
TRIAD = re.compile(r"(?<![\w'’-])([a-z][\w'’-]*(?: [a-z][\w'’-]*)?), ([a-z][\w'’-]*(?: [a-z][\w'’-]*)?),? (?:and|or) "
                   r"([a-z][\w'’-]*(?: [a-z][\w'’-]*)?)(?![\w'’-])")
HASHTAG = re.compile(r"(?<![\w#/&])#[A-Za-z][\w-]*")
SPACED = re.compile(r"(?<=\S)\s+[-\u2013]\s+(?=\S)")

def caps_runs(plain, allow_words):
    """Runs of all-caps words used for emphasis (acronyms, SQL keywords and allowed names don't count)."""
    def ok(t):
        u = t.upper(); base = u[:-1] if t.endswith("s") else u
        return u in ACRONYMS or base in ACRONYMS or t in allow_words or base in allow_words or (len(base) <= 3 and base not in COMMON)
    runs = []
    for line in plain:
        toks = [t for t in CAPS.finditer(line) if not re.match(r"\.[a-z]{1,5}\b", line[t.end():])]   # STATE.md is a file name
        i = 0
        while i < len(toks):
            j = i
            while j + 1 < len(toks) and re.fullmatch(r"[\s,.;:!?'\"“”‘’()/&-]*", line[toks[j].end():toks[j + 1].start()]): j += 1
            run = [t.group(0) for t in toks[i:j + 1]]
            sql = any(t in SQL_STRONG for t in run) and all(t in SQL_STRONG or t in SQL_JOIN or ok(t) for t in run)
            if not (sql or all(ok(t) for t in run)): runs.append(" ".join(run))
            i = j + 1
    return runs

def one_liners(bs, allow_phrases, max_words):
    """Theatrical one-line paragraphs: a lone short sentence. Lead-ins (ending in ':' or followed by a list, code, table,
    quote or image), captions, links and hashtag lines don't count."""
    out = []
    for i, (k, lines) in enumerate(bs):
        if k != "prose": continue
        raw = " ".join(l.strip() for l in lines); p = clean(raw, allow_phrases)
        nxt = bs[i + 1][0] if i + 1 < len(bs) else None
        if (not p or p.endswith(":") or "](" in raw or re.search(r"https?://", raw) or nxt in ("list", "code", "table", "quote", "image")
                or all(w.startswith("#") for w in p.split())): continue
        if len(sentences(p)) == 1 and words(p) <= max_words: out.append(p)
    return out

def qa_pairs(sents):
    """A question (or a run of questions) answered by the next sentence, in the same paragraph or the next block."""
    pairs = []
    for n, (b, s) in enumerate(sents):
        if is_question(s) and n + 1 < len(sents):
            nb, ns = sents[n + 1]
            if not is_question(ns) and nb - b <= 1: pairs.append(f"{s} {ns}")
    return pairs

def triads(sents, plain):
    """Groups of three: 'x, y and z' lists of short lowercase items, and three short sentences in a row (5 words or fewer)."""
    found = [m.group(0) for line in plain for m in TRIAD.finditer(line) if not line[:m.start()].endswith(", ")]   # not a longer list
    n = 0
    while n + 2 < len(sents):
        trio = sents[n:n + 3]
        if len({b for b, _ in trio}) == 1 and all(words(s) <= 5 for _, s in trio):
            found.append(" ".join(s for _, s in trio)); n += 3
        else: n += 1
    return found

def same_length_runs(sents, run, spread):
    """Maximal runs of at least `run` consecutive sentences whose word counts differ by at most `spread`."""
    L, out, i = [words(s) for _, s in sents], [], 0
    while i < len(L):
        j = i
        while j < len(L) and max(L[i:j + 1]) - min(L[i:j + 1]) <= spread: j += 1
        if j - i >= run: out.append((L[i:j], sents[i][1])); i = j
        else: i += 1
    return out

def register_checks(text, reg):
    lim, out = reg.get("limits", {}), []
    allow = reg.get("caps_allow", [])
    phrases = [a for a in allow if not re.fullmatch(r"[A-Z]+", a)]
    bs, sents, plain = parse(text, phrases)
    joined = "\n".join(plain)
    def over(name, items, limit, show=3):
        if limit is not None and len(items) > limit:
            out.append(f"{name}: {len(items)} (limit {limit})")
            out.extend(f'  in: "{x[:90]}"' for x in items[:show])
    for d in reg.get("drop", []):
        hits = [m.group(0) for m in re.finditer(d["regex"], joined, 0 if d.get("case_sensitive") else re.I)]
        if hits: out.append(f'{d["label"]} x{len(hits)}: ' + ", ".join(f'"{h}"' for h in sorted(set(hits))[:6]))
    if lim.get("spaced_hyphen") is False:
        hits = [line for line in plain for _ in SPACED.finditer(line)]
        if hits: out.append(f'spaced " - " connectors: {len(hits)}; use a comma, a colon or a full stop')
        out.extend(f'  in: "{h[:90]}"' for h in hits[:3])
    over("capitals for emphasis", caps_runs(plain, set(a for a in allow if re.fullmatch(r"[A-Z]+", a))), lim.get("caps_emphasis"))
    if "one_line_paragraphs" in lim:
        over("theatrical one-line paragraphs", one_liners(bs, phrases, lim.get("one_line_words", 12)), lim["one_line_paragraphs"])
    over("question-and-answer pairs", qa_pairs(sents), lim.get("qa_pairs"))
    over("exclamation marks", [l for l in plain for _ in range(l.count("!"))], lim.get("exclamations"))
    tags = HASHTAG.findall("\n".join(" ".join(l) for k, l in bs if k != "code"))
    if lim.get("hashtags") is not None and len(tags) > lim["hashtags"]:
        out.append(f"hashtag wall: {len(tags)} hashtags (limit {lim['hashtags']}): {' '.join(tags[:8])}")
    over("habitual groups of three", triads(sents, plain), lim.get("triads"))
    r = lim.get("same_length_run")
    if r:
        for lengths, first in same_length_runs(sents, r.get("sentences", 4), r.get("spread_words", 2)):
            out.append(f"same-length sentences: {len(lengths)} in a row ({', '.join(map(str, lengths))} words); vary the rhythm")
            out.append(f'  from: "{first[:90]}"')
    return out

# ---------------------------------------------------------------- the lint
def lint(text, cfg, profile=None, register=None, structured=None):
    """Violations in a post body. cfg = config.json; profile = profile.json (its banned list always applies);
    register = a profile register name, whose limits then apply too, on `structured` (the body with its code fences,
    from post_body) or else on `text`."""
    ban, out, profile = cfg.get("ban", {}), [], profile or {}
    norm = text.replace("’", "'")
    low = norm.lower()
    pb = profile.get("banned", {})
    seen = set()
    for ph in ban.get("phrases", []) + pb.get("phrases", []):
        if ph.lower() in seen: continue
        seen.add(ph.lower())
        n = len(re.findall(r"(?<!\w)" + re.escape(ph.lower()), low))
        if n: out.append(f'banned phrase x{n}: "{ph}"')
    for ph in ban.get("engagement_bait", []):
        if ph.lower() in low: out.append(f'engagement bait: "{ph}"')
    structured = (structured if structured is not None else text).replace("’", "'")
    if pb.get("patterns"):
        prose = "\n".join(parse(structured)[2])
        for p in pb["patterns"]:
            hits = [m.group(0) for m in re.finditer(p["regex"], prose, re.I)]
            if hits: out.append(f'banned: {p["label"]} x{len(hits)}: "{hits[0]}"')
    if ban.get("emoji") and EMOJI.search(text):
        out.append("emoji: " + "".join(sorted(set(EMOJI.findall(text)))))
    if ban.get("not_just_x_its_y"):
        for rx in NOT_JUST:
            for m in rx.finditer(norm): out.append(f'"not just X, it\'s Y": "{m.group(0)[:70]}"')
    for uk, us in UK_US.items():
        for m in re.finditer(r"\b" + uk + r"\b", low): out.append(f'UK spelling: "{m.group(0)}" (US: {us})')
    limit = ban.get("em_dash_max")
    if limit is not None and text.count("\u2014") > limit:
        lines = [l.strip() for l in text.splitlines() if "\u2014" in l]
        out.append(f"em dashes: {text.count(chr(0x2014))} (limit {limit}); rewrite with commas, periods, colons or parentheses")
        out += [f'  em dash in: "{l[:80]}"' for l in lines]
    if register:
        reg = profile.get("registers", {}).get(register)
        if reg is None and profile: out.append(f"unknown register '{register}' (profile has: {', '.join(profile.get('registers', {}))})")
        elif reg: out += register_checks(structured, reg)
    return out

def lint_file(path, register="public", cfg=None, profile=None):
    """The CLI check: the file's body against config + profile (+ the register's limits)."""
    raw = pathlib.Path(path).read_text(encoding="utf-8")
    return lint(body(raw), cfg if cfg is not None else load_config(), profile if profile is not None else load_profile(), register,
                structured=post_body(raw))

def stats(text):
    """Rhythm and rhetoric of a text's prose, for calibrating a profile (code, not judgment: every number is counted)."""
    bs, sents, plain = parse(text)
    L = [words(s) for _, s in sents]
    if not L: return {"sentences": 0}
    mean, sd = statistics.mean(L), statistics.pstdev(L)
    longest, i = 0, 0
    for i in range(len(L)):
        j = i
        while j < len(L) and max(L[i:j + 1]) - min(L[i:j + 1]) <= 2: j += 1
        longest = max(longest, j - i)
    return {"sentences": len(L), "words": sum(L), "mean_words": round(mean, 1), "median_words": statistics.median(L),
            "stdev_words": round(sd, 1), "variation": round(sd / mean, 2),
            "short_share": round(sum(x <= 6 for x in L) / len(L), 2), "long_share": round(sum(x >= 30 for x in L) / len(L), 2),
            "longest_same_length_run": longest, "questions": sum(is_question(s) for _, s in sents), "qa_pairs": len(qa_pairs(sents)),
            "exclamations": sum(l.count("!") for l in plain), "caps_emphasis": len(caps_runs(plain, set())),
            "spaced_hyphens": sum(len(SPACED.findall(l)) for l in plain)}

def brief(profile, register="public"):
    """The drafting brief: what to keep, limit and drop in this register, the caps, the bans and the manual checks."""
    if not profile: return "No voice profile (data/extrovert/voice/profile.json): only the ban list in config.json applies."
    reg = profile.get("registers", {}).get(register)
    if reg is None: return f"Unknown register '{register}'. Registers: {', '.join(profile.get('registers', {}))}"
    out = [f"VOICE PROFILE v{profile.get('version')} ({profile.get('updated')}) | register: {register}", reg.get("description", "")]
    if reg.get("platforms"): out.append("Platforms: " + ", ".join(reg["platforms"]))
    groups = {"keep": [], "limit": [], "drop": []}
    for t in profile.get("traits", []):
        how = t.get(register, t.get("public", "keep")) if register != "raw" else "keep"
        groups.setdefault(how, []).append(t)
    for how in ("keep", "limit", "drop"):
        if groups.get(how):
            out.append(f"\n{how.upper()}:")
            for t in groups[how]:
                note = t.get(f"{register}_note") or ""
                out.append(f"- {t['name']}: {t['description']}" + (f" ({note})" if note else ""))
    for k in ("person", "humor", "self_descriptions"):
        if profile.get(k): out.append(f"\n{k.replace('_', ' ').title()}: " + "; ".join(f"{a}: {b}" for a, b in profile[k].items() if a != "source"))
    if reg.get("rules"): out += ["\nRULES:"] + [f"- {r}" for r in reg["rules"]]
    if reg.get("limits"): out.append("\nLIMITS (voice_lint.py enforces): " + json.dumps(reg["limits"]))
    if reg.get("drop"): out.append("DROP (linted): " + ", ".join(d["label"] for d in reg["drop"]))
    b = profile.get("banned", {})
    if b: out.append("BANNED: " + ", ".join(b.get("phrases", []) + [p["label"] for p in b.get("patterns", [])] + b.get("constructions", [])))
    if profile.get("checklist"): out += ["\nCHECK BY HAND before showing a draft:"] + [f"- {c}" for c in profile["checklist"]]
    return "\n".join(out)

# ---------------------------------------------------------------- site copy (a built website)
# The em-dash rule (em_dash_max) also covers a site's copy: page titles, meta and link-preview text, visible text, and
# alt / aria-label / title attributes of every built page. Decorative aria-hidden text is skipped. Text inside an element
# with a data-source attribute (e.g. a Medium post title, a GitHub repo description) comes from elsewhere: it's
# reported as a warning, to be fixed at its source, and doesn't fail the check.
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
META_COPY = re.compile(r"^(description|og:title|og:description|og:image:alt|twitter:title|twitter:description|twitter:image:alt)$")

class _Copy(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.stack, self.out = [], []
    def _flags(self):
        skip = any(t in ("script", "style", "template") or a.get("aria-hidden") == "true" for t, a in self.stack)
        return skip, any("data-source" in a for _, a in self.stack)
    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        skip, ext = self._flags()
        if tag == "meta" and META_COPY.match(a.get("name") or a.get("property") or ""): self.out.append((a.get("content", ""), False, "meta"))
        elif not skip and a.get("aria-hidden") != "true":
            for k in ("alt", "aria-label", "title"):
                if a.get(k): self.out.append((a[k], ext or "data-source" in a, f"{tag}[{k}]"))
        if tag not in VOID: self.stack.append((tag, a))
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag: del self.stack[i:]; break
    def handle_data(self, data):
        skip, ext = self._flags()
        if data.strip() and not skip: self.out.append((data.strip(), ext, self.stack[-1][0] if self.stack else "text"))

def site_copy(html):
    """[(text, external, where)] for one built page."""
    p = _Copy(); p.feed(html); return p.out

def site_lint(dist, cfg):
    """(problems, warnings) for every built .html page under dist: the em-dash rule on its copy."""
    limit, problems, warnings = cfg.get("ban", {}).get("em_dash_max"), [], []
    if limit is None: return problems, warnings
    for page in sorted(pathlib.Path(dist).rglob("*.html")):
        rel = page.relative_to(dist).as_posix()
        for text, external, where in site_copy(page.read_text(encoding="utf-8")):
            if text.count("\u2014") > limit:
                (warnings if external else problems).append(f'{rel} {where}: em dash in "{text[:90]}"')
    return problems, warnings

def _register(a):
    if "--register" in a:
        i = a.index("--register"); r = a[i + 1] if i + 1 < len(a) else ""; del a[i:i + 2]; return r
    return "public"

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--site":
        problems, warnings = site_lint(a[1], load_config())
        for w in warnings: print(f"WARNING (fix at its source): {w}")
        print("\n".join(problems) if problems else "OK: no em dashes in the site's copy")
        sys.exit(1 if problems else 0)
    reg = _register(a)
    if a == ["--brief"]: print(brief(load_profile(), reg)); sys.exit(0)
    if len(a) == 2 and a[0] == "--stats":
        print(json.dumps(stats(post_body(pathlib.Path(a[1]).read_text(encoding="utf-8"))), indent=1)); sys.exit(0)
    if len(a) != 1 or a[0].startswith("--"): print(__doc__); sys.exit(2)
    problems = lint_file(a[0], reg)
    print("\n".join(problems) if problems else f"OK: no voice-rule violations ({reg} register)")
    sys.exit(1 if problems else 0)
