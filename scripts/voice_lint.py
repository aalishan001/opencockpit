#!/usr/bin/env python3
"""Check a post or editorial against the Extrovert voice rules in data/extrovert/config.json.
  voice_lint.py <file.md>      prints violations; exit 1 if any
  voice_lint.py --site <dist>  the em-dash rule on a built site's copy (titles, meta, visible text, alt/aria-label);
                               text marked data-source (from Medium, GitHub) only warns
Checks the body only (everything after a '<!-- notes -->' line is ignored): banned phrases, engagement bait,
emoji, "not just X, it's Y" constructions, British spellings (US spelling always), em dashes (limit from config; 0 = none).
"""
import json, re, sys, pathlib
from _common import DATA
from post_stats import body, WORD

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

def lint(text, cfg):
    ban, out = cfg.get("ban", {}), []
    norm = text.replace("’", "'")
    low = norm.lower()
    for ph in ban.get("phrases", []):
        n = len(re.findall(r"(?<!\w)" + re.escape(ph.lower()), low))
        if n: out.append(f'banned phrase x{n}: "{ph}"')
    for ph in ban.get("engagement_bait", []):
        if ph.lower() in low: out.append(f'engagement bait: "{ph}"')
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
    return out

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

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--site":
        cfg = json.loads((DATA / "extrovert/config.json").read_text(encoding="utf-8"))
        problems, warnings = site_lint(sys.argv[2], cfg)
        for w in warnings: print(f"WARNING (fix at its source): {w}")
        print("\n".join(problems) if problems else "OK: no em dashes in the site's copy")
        sys.exit(1 if problems else 0)
    if len(sys.argv) != 2: print(__doc__); sys.exit(2)
    cfg = json.loads((DATA / "extrovert/config.json").read_text(encoding="utf-8"))
    problems = lint(body(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")), cfg)
    print("\n".join(problems) if problems else "OK: no voice-rule violations")
    sys.exit(1 if problems else 0)
