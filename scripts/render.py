#!/usr/bin/env python3
"""Render outputs to out/ (PDF via WeasyPrint if installed, otherwise HTML). Each output belongs to a disclosure
channel (data/bragdoc/disclosure_policy.json) and is linted before it is written; a lint failure writes nothing.
  render.py bragdoc                  -> out/<name>_BragDoc.pdf             internal: full detail, all contacts
  render.py resume-extensive         -> out/<name>_Resume_Extensive.pdf    resume: resume_summary + resume contacts
  render.py public-resume            -> out/<name>_Resume_Public.pdf       public: public_summary + public contacts, public entries only
<name> is the channel's name form from profile.json -> names (policy channels.<c>.names.form), spaces as underscores.
An all-caps name is CSS text-transform on h1.name; the text itself is never changed.
  render.py editorial <folder> <N>   -> <folder>/editorial-v<N>.html (side by side)
"""
import html, json, os, re, shutil, subprocess, sys, tempfile, pathlib
from collections import defaultdict
from _common import ROOT, DATA, read_jsonl
from disclosure_lint import (context as lint_context, lint_text, check as lint_check, report as lint_report, channel_contacts,
                             pdf_lines, leak_hits)

OUT = ROOT / "out"
CSS = (ROOT / "templates/resume.css").read_text(encoding="utf-8")
esc = html.escape
# PDF fallback when WeasyPrint is missing: a headless Chromium browser, header and footer OFF
# (the default footer prints the local file path)
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "google-chrome", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge"]

def leak_patterns():
    """Local paths and usernames that must never be inside a rendered file: the fourthwall deny list's path regexes and
    its local_identity terms, plus any file:// URL or drive-letter user path."""
    d = json.loads((DATA / "fourthwall/denylist.json").read_text(encoding="utf-8")) if (DATA / "fourthwall/denylist.json").exists() else {}
    pats = [re.compile(r) for r in d.get("regex", [])] + [re.compile(r"(?i)file:/{2,3}"), re.compile(r"(?i)\b[A-Z]:[\\/]Users[\\/]")]
    pats += [re.compile(rf"(?i)(?<![\w]){re.escape(t)}(?![\w])") for t in d.get("local_identity", [])]
    return pats

def browser_pdf(html_path, pdf_path, header_footer=False):
    """Try each installed browser until one prints (some managed Edge installs exit without printing)."""
    for b in BROWSERS:
        exe = b if os.path.isfile(b) else shutil.which(b)
        if not exe: continue
        with tempfile.TemporaryDirectory() as profile:   # a throwaway profile, so a running browser instance doesn't interfere
            args = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profile}",
                    f"--print-to-pdf={pdf_path}"]
            if not header_footer: args += ["--no-pdf-header-footer", "--print-to-pdf-no-header"]
            subprocess.run(args + [pathlib.Path(html_path).resolve().as_uri()], capture_output=True, timeout=180)
        if pathlib.Path(pdf_path).is_file() and pathlib.Path(pdf_path).stat().st_size > 0: return True
    return False

def pdf_gate(pdf, channel):
    """What a reader of the PDF sees (its text and its metadata) must pass the channel and carry no local path or username."""
    text, meta, pages = pdf_lines(pdf)
    ctx = lint_context()
    found = lint_check(text, channel, ctx, whole_doc=True) + [(n, l, f"metadata: {w}") for n, l, w in lint_check(meta, channel, ctx)]
    found += leak_hits(text + meta, leak_patterns())
    return found, pages

def save(html_str, stem, channel):
    """Lint the HTML, make the PDF in a scratch folder, gate the PDF, and only then write both into out/."""
    found = lint_text(html_str, channel)
    if found:
        print(f"BLOCKED: {stem} fails the {channel} channel ({len(found)} problem(s)); nothing written.\n" + lint_report(found))
        sys.exit(2)
    OUT.mkdir(exist_ok=True); (OUT / stem).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        hp, pdf = pathlib.Path(tmp) / "page.html", pathlib.Path(tmp) / "page.pdf"
        hp.write_text(html_str, encoding="utf-8")
        made = False
        try:
            from weasyprint import HTML
            HTML(string=html_str, base_url=str(ROOT)).write_pdf(pdf); made = True
        except ImportError:
            made = browser_pdf(hp, pdf, header_footer=os.environ.get("COCKPIT_PDF_HEADER_FOOTER") == "1")   # env: tests only
        if made:
            bad, pages = pdf_gate(pdf, channel)
            if bad:
                print(f"BLOCKED: {stem}.pdf fails its gate ({len(bad)} problem(s)); nothing written.\n" + lint_report(bad))
                sys.exit(2)
        shutil.copyfile(hp, OUT / f"{stem}.html")
        if made:
            shutil.copyfile(pdf, OUT / f"{stem}.pdf"); print(f"{OUT / f'{stem}.pdf'}  ({pages} page(s))")
        else:
            print(f"{OUT / f'{stem}.html'}  (no PDF engine: install weasyprint, or Edge/Chrome for headless printing)")

def page(title, body):
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title><style>{CSS}</style></head><body>{body}</body></html>"

def channel_name(channel):
    """The name form this channel uses (policy channels.<c>.names.form -> profile.json names). Never hard-coded."""
    ctx = lint_context()
    form = ctx["policy"]["channels"][channel].get("names", {}).get("form", "short")
    return ctx["names"].get(form, "")

def stem(channel, suffix):
    name = channel_name(channel)
    return f"{name.replace(' ', '_')}_{suffix}" if name else suffix

def header(channel):
    p = json.loads((DATA / "profile.json").read_text(encoding="utf-8"))
    shown = [re.sub(r"^https://(www\.)?", "", v) for _, v in channel_contacts(channel, lint_context())]
    return f"<h1 class='name'>{esc(channel_name(channel))}</h1><p class='contact'>" + " | ".join(esc(x) for x in [p.get("location", "")] + shown if x) + "</p>"

COMMUNITY = "Community & Leadership"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

def load(rel, default):
    p = DATA / rel
    return json.loads(p.read_text(encoding="utf-8") or "null") or default if p.exists() else default

def ym(s):
    if not s: return "Present"
    y, m = s.split("-")[:2]
    return f"{MONTHS[int(m) - 1]} {y}"

def ranked(es): return sorted(es, key=lambda e: -e["rank_score"])

def visible(channel):
    """Entries a channel may show: the public channel only ever sees visibility "public"; the others see everything."""
    es = read_jsonl(DATA / "bragdoc/entries.jsonl")
    return [e for e in es if e.get("visibility") == "public"] if channel == "public" else es

def by_category(channel="internal"):
    """Ranked achievement categories, highest-ranked category first. Community & Leadership has its own section."""
    cats = defaultdict(list)
    for e in visible(channel):
        if e["category"] != COMMUNITY: cats[e["category"]].append(e)
    return sorted(((c, ranked(es)) for c, es in cats.items()), key=lambda kv: -kv[1][0]["rank_score"])

def community_entries(channel="internal"): return ranked([e for e in visible(channel) if e["category"] == COMMUNITY])

def experience_html(channel="internal"):
    """Employers newest first. Every channel except internal (resume, public) shows only each role's public_summary and
    public_context; the internal context notes appear in the internal BragDoc only."""
    jobs = load("bragdoc/employment.json", [])
    if not jobs: return ""
    out, order = "<h2>Experience</h2>", []
    for j in sorted(jobs, key=lambda j: j["start"], reverse=True):
        if j["employer"] not in order: order.append(j["employer"])
    for emp in order:
        roles = sorted([j for j in jobs if j["employer"] == emp], key=lambda j: j["start"])
        out += (f"<h3>{esc(emp)}</h3><p class='meta'>{ym(roles[0]['start'])} – {ym(roles[-1].get('end'))}</p><ul>"
                + "".join(f"<li>{esc(j['role'])} ({ym(j['start'])} – {ym(j.get('end'))})"
                          + (f"<br>{esc(j['public_summary'])}" if channel != "internal" and j.get("public_summary") else "") + "</li>" for j in roles) + "</ul>")
        if channel != "internal":
            out += "".join(f"<p class='meta'>{esc(l)}</p>" for j in roles for l in (j.get("public_context") or []))
            continue
        ctx = [j["context"] for j in roles if j.get("context")]
        if ctx: out += f"<p class='meta'>{esc(' '.join(ctx))}</p>"
    return out

def skills_html(channel="internal"):
    skills = load("bragdoc/skills.json", [])
    if not skills: return ""
    groups, ctx = defaultdict(list), lint_context()
    for s in skills:
        if channel != "internal" and lint_check([s["skill"]], channel, ctx): continue   # e.g. a vulnerability-class skill never reaches public
        groups[s["group"]].append(s["skill"] + (f" ({s['level']})" if s.get("level") else ""))
    return "<h2>Skills</h2><ul>" + "".join(f"<li><b>{esc(g)}:</b> {esc(', '.join(v))}</li>" for g, v in groups.items()) + "</ul>"

def education_html():
    eds = load("bragdoc/education.json", [])
    if not eds: return ""
    out = "<h2>Education</h2>"
    for ed in eds:
        line = f"{ed['degree']} | {ed['institution']} | Graduated {ym(ed['graduation'])}"
        if ed.get("cgpa"): line += f" | CGPA {ed['cgpa']}"
        out += f"<p>{esc(line)}</p>"
        if (ed.get("capstone") or {}).get("title"): out += f"<p class='meta'>Capstone: {esc(ed['capstone']['title'])}</p>"
    return out

def in_progress_html():
    items = [i for i in read_jsonl(DATA / "bragdoc/in_progress.jsonl") if i["status"] not in ("dropped", "done")]
    if not items: return ""
    return "<h2>In Progress</h2><ul>" + "".join(
        f"<li>{esc(i['title'])}: {esc(i['status'].replace('_', ' '))}" + (f", target {esc(i['target_date'])}" if i.get("target_date") else "") + "</li>"
        for i in items) + "</ul>"

def metrics(e):
    return "; ".join(f"{m.get('name','')}: {m.get('before','')} → {m.get('after','')} {m.get('unit','')}".strip() for m in e.get("metrics", []))

LINK_LABELS = [("repo", "Repo"), ("live", "Live"), ("landing", "Landing"), ("demo", "Demo"), ("docs", "Docs")]

def link_items(e):
    ln = e.get("links") or {}
    items = [(label, ln[k]) for k, label in LINK_LABELS if ln.get(k)]
    return items + [(o.get("label", "Link"), o["url"]) for o in ln.get("other", []) if o.get("url")]

def links_html(e):
    items = link_items(e)
    return ("<p class='links'>" + " · ".join(f"{esc(l)}: <a href='{esc(u)}'>{esc(u)}</a>" for l, u in items) + "</p>") if items else ""

def entry_block(e):
    return (f"<h3>{esc(e['title'])}</h3><p class='meta'>{esc(e.get('employer',''))} · {esc(e.get('period',''))} · {esc(', '.join(e.get('stack', [])))}</p><ul>"
            + "".join(f"<li><b>{k}:</b> {esc(str(e[f]))}</li>" for k, f in
                      [("Problem","problem"),("What I did","action"),("Result","result"),("Scope","scope"),("My role","my_role")] if e.get(f))
            + (f"<li><b>Metrics:</b> {esc(metrics(e))}</li>" if e.get("metrics") else "") + "</ul>"
            + links_html(e))

def bragdoc():
    """Experience, ranked achievement categories, Skills, Education, Community & Leadership, In Progress."""
    body = header("internal") + "<h2 class='doc'>Engineering Brag Document</h2>" + experience_html()
    for cat, es in by_category():
        body += f"<h2>{esc(cat)}</h2>" + "".join(entry_block(e) for e in es)
    body += skills_html("internal") + education_html()
    comm = community_entries()
    if comm: body += f"<h2>{esc(COMMUNITY)}</h2>" + "".join(entry_block(e) for e in comm)
    body += in_progress_html()
    save(page("BragDoc", body), stem("internal", "BragDoc"), "internal")

SUMMARY_FIELD = {"resume": "resume_summary", "public": "public_summary"}

def resume_line(e, channel):
    """One bullet per entry, written only from that channel's summary (never the internal entry text)."""
    s = e.get(SUMMARY_FIELD[channel])
    if not s: sys.exit(f"BLOCKED: {e['id']} has no {SUMMARY_FIELD[channel]}; generate it (bragdoc renovate) before rendering the {channel} channel.")
    line = f"<b>{esc(s['headline'])}.</b> {esc(s['summary'])}"
    links = link_items(e) if e.get("kind", "work") != "work" else []  # links only for non-work kinds
    return f"<li>{line}" + "".join(f" | {esc(l)}: <a href='{esc(u)}'>{esc(u)}</a>" for l, u in links) + "</li>"

def channel_resume(channel, title, stem):
    """Everything the channel may show except In Progress, from the channel's summaries and contacts."""
    body = header(channel) + experience_html(channel)
    for cat, es in by_category(channel):
        body += f"<h2>{esc(cat)}</h2><ul>" + "".join(resume_line(e, channel) for e in es) + "</ul>"
    body += skills_html(channel) + education_html()
    comm = community_entries(channel)
    if comm: body += f"<h2>{esc(COMMUNITY)}</h2><ul>" + "".join(resume_line(e, channel) for e in comm) + "</ul>"
    save(page(title, body), stem, channel)

def resume_extensive(): channel_resume("resume", "Resume", stem("resume", "Resume_Extensive"))
def public_resume(): channel_resume("public", "Resume", stem("public", "Resume_Public"))

def md_to_html(md):
    out, in_list = [], False
    for line in md.splitlines():
        s = line.strip()
        inline = lambda t: re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<a href='\2'>\1</a>",
                                  re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(t)))
        if s.startswith(("- ", "* ")):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(s[2:])}</li>"); continue
        if in_list: out.append("</ul>"); in_list = False
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m: n = len(m.group(1)); out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
        elif s: out.append(f"<p>{inline(s)}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)

def editorial(folder, n):
    from pathlib import Path
    d = Path(folder); d = d if d.is_absolute() else ROOT / d
    left = md_to_html((d / "transcript.md").read_text(encoding="utf-8"))
    right = md_to_html((d / f"editorial-v{n}.md").read_text(encoding="utf-8"))
    css = ("body{font-family:Georgia,serif;margin:0} .grid{display:grid;grid-template-columns:1fr 1fr;gap:2rem;padding:2rem}"
           ".col{overflow-wrap:anywhere} .col h1{font-size:1rem;text-transform:uppercase;letter-spacing:.1em;color:#666}"
           ".t{color:#444;font-size:.92rem} @media(max-width:800px){.grid{grid-template-columns:1fr}}")
    doc = (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<style>{css}</style></head><body><div class='grid'><div class='col t'><h1>Transcript</h1>{left}</div>"
           f"<div class='col'><h1>Edited v{n}</h1>{right}</div></div></body></html>")
    p = d / f"editorial-v{n}.html"; p.write_text(doc, encoding="utf-8"); print(p)

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    {"bragdoc": lambda: bragdoc(), "resume-extensive": lambda: resume_extensive(), "public-resume": lambda: public_resume(),
     "editorial": lambda: editorial(a[1], a[2])}.get(a[0], lambda: (print(__doc__), sys.exit(1)))()
