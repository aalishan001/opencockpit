#!/usr/bin/env python3
"""Extrovert idea backlog. data/extrovert/ideas.jsonl is an append-only event log; this script derives current state.
  ideas.py list [--status a,b|all] [--tag T] [--since D] [--until D] [--month YYYY-MM] [--oldest]
                                         default: open ideas (new, developing), newest first
  ideas.py find <query> [filters]        all query words must appear in raw, gist, context, tags, link urls/titles/summaries
  ideas.py show <id>                     current state of one idea
  ideas.py history <id>                  every event; content versions numbered v1, v2, ...
  ideas.py tags                          existing tags with counts (reuse them)
  ideas.py add '<json>'|-                {raw, gist, tags[2-5], context, links[{url,title,summary,fetched}], sensitive}
  ideas.py edit <id> '<json>'|-          {"set": {field: value}, "note": ""}; fields: raw gist tags context links sensitive
  ideas.py status <id> <status> [--note T] [--url U]... [--conversation FOLDER]
  ideas.py merge <id> <id>... '<json>'|- {gist, tags, context}; raw = the originals' raw text verbatim; links = union
Dates: YYYY-MM-DD, YYYY-MM (month), Nd (N days ago), today, yesterday. COCKPIT_NOW=<ISO> overrides the clock (tests).
Statuses: new, developing, posted, parked, dropped, merged (merged only via merge).
"""
import datetime as dt, json, os, re, sys
from _common import DATA, read_jsonl, append_jsonl

LOG = DATA / "extrovert/ideas.jsonl"
STATUSES = ["new", "developing", "posted", "parked", "dropped", "merged"]
OPEN = ("new", "developing")
FIELDS = {"raw", "gist", "tags", "context", "links", "sensitive"}

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def ts(): return now().isoformat(timespec="seconds")
def die(msg): sys.exit(f"REJECTED: {msg}")
def payload(raw): return json.loads(sys.stdin.read() if raw == "-" else raw)

def state():
    ideas = {}
    for e in read_jsonl(LOG):
        iid, ev, d = e["idea_id"], e["event"], e.get("data") or {}
        if ev in ("add", "merge"):
            ideas[iid] = {"id": iid, "created": e["ts"], "updated": e["ts"], "status": "new", "version": 1, "raw": d["raw"],
                          "gist": d["gist"], "tags": d["tags"], "context": d.get("context", ""), "links": d.get("links", []),
                          "sensitive": bool(d.get("sensitive")), "merged_from": d.get("merged_from", []), "merged_into": None,
                          "conversations": [], "post_urls": []}
        elif ev == "edit":
            it = ideas[iid]; it.update(d["set"]); it["version"] += 1; it["updated"] = e["ts"]
        elif ev == "status":
            it = ideas[iid]; it["status"], it["updated"] = d["to"], e["ts"]
            if d.get("merged_into"): it["merged_into"] = d["merged_into"]
            if d.get("conversation") and d["conversation"] not in it["conversations"]: it["conversations"].append(d["conversation"])
            it["post_urls"] += [u for u in d.get("urls", []) if u not in it["post_urls"]]
    return ideas

def employer_terms():
    p = DATA / "bragdoc/employment.json"
    jobs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    terms = set()
    for j in jobs:
        if j.get("end") is None:
            terms.add(j["employer"].lower())
            first = j["employer"].split()[0]
            if len(first) >= 4: terms.add(first.lower())
    return terms

def flagged(it, terms=None):
    terms = employer_terms() if terms is None else terms
    hay = " ".join([it["raw"], it["gist"], it["context"]] + [l.get("title", "") for l in it["links"]]).lower()
    return it["sensitive"] or any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", hay) for t in terms)

# ---------- dates ----------
def day(s):
    s = s.strip().lower(); today = now().date()
    if s == "today": return today
    if s == "yesterday": return today - dt.timedelta(days=1)
    if re.fullmatch(r"\d+d", s): return today - dt.timedelta(days=int(s[:-1]))
    return dt.date.fromisoformat(s)
def month_range(m):
    y, mo = map(int, m.split("-"))
    first = dt.date(y, mo, 1); nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
    return first, nxt - dt.timedelta(days=1)

def opts(a):
    o = {"status": None, "tag": None, "since": None, "until": None, "oldest": False, "rest": []}
    i = 0
    while i < len(a):
        k = a[i]
        if k == "--status": o["status"] = a[i + 1]; i += 2
        elif k == "--tag": o["tag"] = a[i + 1].lower(); i += 2
        elif k == "--since": o["since"] = day(a[i + 1]); i += 2
        elif k == "--until": o["until"] = day(a[i + 1]); i += 2
        elif k == "--month": o["since"], o["until"] = month_range(a[i + 1]); i += 2
        elif k == "--oldest": o["oldest"] = True; i += 1
        else: o["rest"].append(k); i += 1
    return o

def select(ideas, o, default_status):
    st = default_status if o["status"] is None else (None if o["status"] == "all" else set(o["status"].split(",")))
    out = []
    for it in ideas.values():
        created = dt.date.fromisoformat(it["created"][:10])
        if st and it["status"] not in st: continue
        if o["tag"] and o["tag"] not in it["tags"]: continue
        if o["since"] and created < o["since"]: continue
        if o["until"] and created > o["until"]: continue
        out.append(it)
    return sorted(out, key=lambda it: (it["created"], it["id"]), reverse=not o["oldest"])

def table(rows):
    if not rows: print("No ideas match."); return
    terms = employer_terms()
    cells = [[it["id"], it["created"][:10], it["status"], ", ".join(it["tags"]),
              it["gist"] + ("  [current employer: flag before use]" if flagged(it, terms) else "")] for it in rows]
    head = ["id", "date", "status", "tags", "gist"]
    w = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(head[:-1])]
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(head[:-1])) + "  gist")
    for c in cells: print("  ".join(c[i].ljust(w[i]) for i in range(4)) + "  " + c[4])

def show(it):
    print(f"{it['id']}  [{it['status']}]  v{it['version']}  created {it['created']}  updated {it['updated']}")
    if flagged(it): print("FLAG: mentions current-employer material; flag before using in suggest/start")
    print(f"gist: {it['gist']}\ntags: {', '.join(it['tags'])}")
    if it["context"]: print(f"context: {it['context']}")
    print("raw:\n  " + it["raw"].replace("\n", "\n  "))
    for l in it["links"]:
        print(f"link: {l['url']}" + (f"\n  title: {l.get('title', '')}\n  summary: {l.get('summary', '')}" if l.get("fetched") else "\n  (not fetched)"))
    if it["merged_from"]: print(f"merged from: {', '.join(it['merged_from'])}")
    if it["merged_into"]: print(f"merged into: {it['merged_into']}")
    if it["conversations"]: print(f"conversations: {', '.join(it['conversations'])}")
    if it["post_urls"]: print(f"posted at: {', '.join(it['post_urls'])}")

# ---------- validation of new content ----------
def norm_tags(tags):
    if not isinstance(tags, list) or not 2 <= len(tags) <= 5: die("tags must be a list of 2-5 strings")
    return [re.sub(r"\s+", "-", str(t).strip().lower()) for t in tags]
def check_links(links):
    if not isinstance(links, list): die("links must be a list")
    for l in links:
        if not re.match(r"^https://\S+\.\S+$", str(l.get("url", ""))): die(f"link url must be https: {l.get('url')}")
        if not isinstance(l.get("fetched"), bool): die("each link needs fetched: true|false")
        if l["fetched"] and not (l.get("title") and l.get("summary")): die("a fetched link needs a title and a summary")
    return links

def add(raw_json, merged_from=None):
    d = payload(raw_json)
    if not str(d.get("raw", "")).strip(): die("raw is empty: ask for the idea text")
    if not str(d.get("gist", "")).strip(): die("gist is empty")
    data = {"raw": d["raw"], "gist": d["gist"].strip(), "tags": norm_tags(d.get("tags")), "context": d.get("context", ""),
            "links": check_links(d.get("links", [])), "sensitive": bool(d.get("sensitive", False))}
    ideas = state()
    iid = f"i-{max([int(k[2:]) for k in ideas] or [0]) + 1:04d}"
    when = ts()
    if merged_from:
        data["merged_from"] = merged_from
        append_jsonl(LOG, {"ts": when, "idea_id": iid, "event": "merge", "data": data})
        for src in merged_from:
            append_jsonl(LOG, {"ts": when, "idea_id": src, "event": "status",
                               "data": {"from": ideas[src]["status"], "to": "merged", "merged_into": iid}})
    else:
        append_jsonl(LOG, {"ts": when, "idea_id": iid, "event": "add", "data": data})
    show(state()[iid])

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    ideas = state()
    def get(iid):
        if iid not in ideas: die(f"no idea '{iid}'")
        return ideas[iid]
    if cmd == "list":
        o = opts(rest); table(select(ideas, o, set(OPEN)))
    elif cmd == "find":
        o = opts(rest); words = " ".join(o["rest"]).lower().split()
        if not words and not (o["since"] or o["until"] or o["tag"]): die("give a query, a tag or a date filter")
        hits = []
        for it in select(ideas, o, None):
            hay = " ".join([it["raw"], it["gist"], it["context"], " ".join(it["tags"])] +
                           [" ".join([l.get("url", ""), l.get("title", ""), l.get("summary", "")]) for l in it["links"]]).lower()
            if all(w in hay for w in words): hits.append(it)
        table(hits)
    elif cmd == "show": show(get(rest[0]))
    elif cmd == "history":
        iid = rest[0]; get(iid); v = 0
        for e in read_jsonl(LOG):
            if e["idea_id"] != iid: continue
            d = e.get("data") or {}
            if e["event"] in ("add", "merge", "edit"):
                v += 1
                what = (f"{e['event']}: {d.get('gist', '')}" + (f" (from {', '.join(d['merged_from'])})" if d.get("merged_from") else "")
                        if e["event"] != "edit" else f"edit: {', '.join(sorted(d['set']))}" + (f" ({d['note']})" if d.get("note") else ""))
                print(f"v{v}  {e['ts']}  {what}")
            else:
                extra = "".join([f" -> {d['merged_into']}" if d.get("merged_into") else "",
                                 f" conversation {d['conversation']}" if d.get("conversation") else "",
                                 f" urls {', '.join(d['urls'])}" if d.get("urls") else "", f" ({d['note']})" if d.get("note") else ""])
                print(f"    {e['ts']}  status {d.get('from')} -> {d['to']}{extra}")
    elif cmd == "tags":
        counts = {}
        for it in ideas.values():
            for t in it["tags"]: counts[t] = counts.get(t, 0) + 1
        print("\n".join(f"{t}  {n}" for t, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))) or "No tags yet.")
    elif cmd == "add":
        if not rest: die("raw is empty: ask for the idea text")
        add(rest[0])
    elif cmd == "edit":
        it = get(rest[0])
        if it["status"] == "merged": die(f"{it['id']} was merged into {it['merged_into']}; edit that idea instead")
        d = payload(rest[1]); s = d.get("set") or {}
        if not s or set(s) - FIELDS: die(f"set must use fields {sorted(FIELDS)}")
        if "tags" in s: s["tags"] = norm_tags(s["tags"])
        if "links" in s: check_links(s["links"])
        if "raw" in s and not str(s["raw"]).strip(): die("raw can't be empty")
        append_jsonl(LOG, {"ts": ts(), "idea_id": it["id"], "event": "edit", "data": {"set": s, **({"note": d["note"]} if d.get("note") else {})}})
        show(state()[it["id"]])
    elif cmd == "status":
        it = get(rest[0]); to = rest[1] if len(rest) > 1 else ""
        if to not in STATUSES: die(f"status must be one of {STATUSES}")
        if to == "merged": die("use 'merge' to merge ideas")
        if it["status"] == "merged": die(f"{it['id']} is merged into {it['merged_into']}")
        o, urls, note, conv = rest[2:], [], None, None
        i = 0
        while i < len(o):
            if o[i] == "--url": urls.append(o[i + 1]); i += 2
            elif o[i] == "--note": note = o[i + 1]; i += 2
            elif o[i] == "--conversation": conv = o[i + 1]; i += 2
            else: die(f"unknown option {o[i]}")
        for u in urls:
            if not re.match(r"^https://\S+\.\S+$", u): die(f"url must be https: {u}")
        data = {"from": it["status"], "to": to}
        if urls: data["urls"] = urls
        if note: data["note"] = note
        if conv: data["conversation"] = conv
        append_jsonl(LOG, {"ts": ts(), "idea_id": it["id"], "event": "status", "data": data})
        print(f"{it['id']}: {it['status']} -> {to}" + (f" ({', '.join(urls)})" if urls else ""))
    elif cmd == "merge":
        ids, js = rest[:-1], rest[-1] if rest else ""
        if len(ids) < 2 or len(set(ids)) != len(ids): die("merge needs 2+ distinct idea ids, then the JSON")
        srcs = [get(i) for i in ids]
        for s in srcs:
            if s["status"] == "merged": die(f"{s['id']} is already merged into {s['merged_into']}")
        d = payload(js)
        links, seen = [], set()
        for s in srcs:
            for l in s["links"]:
                if l["url"] not in seen: seen.add(l["url"]); links.append(l)
        d.update(raw="\n\n---\n\n".join(f"[{s['id']}] {s['raw']}" for s in srcs), links=links,
                 sensitive=any(s["sensitive"] for s in srcs))
        add(json.dumps(d, ensure_ascii=False), merged_from=ids)
    else:
        print(__doc__); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
