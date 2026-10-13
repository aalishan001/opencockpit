#!/usr/bin/env python3
"""Append one raw staging item the way `bragdoc dump` does (used by the dump command and by other domains' handoffs).
  bragdoc_stage.py add '<json>'|-     {raw, project, source[, employer, kind, links, source_claims, open_gaps, batch]}
  bragdoc_stage.py add-in-progress '<json>'|-   {title, kind, source[, status, target_date, notes, staging_id]}
add assigns the next s-NNNN id and the created timestamp, sets status "raw", and prints the item. add-in-progress
appends to in_progress.jsonl with the next ip-NNNN id (status defaults to in_progress). Never edits existing rows.
"""
import datetime as dt, json, os, re, sys
from _common import DATA, read_jsonl, append_jsonl

STAGING = DATA / "bragdoc/staging.jsonl"
KINDS = {"work", "personal_project", "product", "open_source", "community"}
IN_PROGRESS = DATA / "bragdoc/in_progress.jsonl"
IP_KINDS, IP_STATUS = {"study", "certification", "project"}, {"planned", "in_progress", "paused", "done", "dropped"}

def now(): return dt.datetime.fromisoformat(os.environ["COCKPIT_NOW"]) if os.environ.get("COCKPIT_NOW") else dt.datetime.now().replace(microsecond=0)
def slug(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "item"

def add(raw):
    d = json.loads(sys.stdin.read() if raw == "-" else raw)
    for k in ("raw", "project", "source"):
        if not str(d.get(k, "")).strip(): sys.exit(f"REJECTED: {k} is required")
    if d.get("kind") and d["kind"] not in KINDS: sys.exit(f"REJECTED: kind must be one of {sorted(KINDS)}")
    rows = read_jsonl(STAGING)
    n = max([int(m.group(1)) for r in rows if (m := re.match(r"s-(\d+)$", r.get("id", "")))] or [0]) + 1
    probe = {"problem": "", "action": "", "result": "", "metrics": [], "stack": [], "scope": "", "my_role": "", "evidence": [],
             "open_gaps": d.get("open_gaps") or ["probe pending"], "transcript": ""}
    if d.get("kind"): probe["kind"] = d["kind"]
    if d.get("links"): probe["links"] = d["links"]
    item = {"id": f"s-{n:04d}", "created": now().isoformat(), "batch": d.get("batch") or f"b-{now().date().isoformat()}-{slug(d['project'])}",
            "project": d["project"], "employer": d.get("employer"), "source": d["source"], "raw": d["raw"], "status": "raw",
            "source_claims": d.get("source_claims", []), "conflicts": [], "probe": probe}
    append_jsonl(STAGING, item)
    print(json.dumps(item, indent=1, ensure_ascii=False))

def add_in_progress(raw):
    d = json.loads(sys.stdin.read() if raw == "-" else raw)
    for k in ("title", "kind", "source"):
        if not str(d.get(k, "")).strip(): sys.exit(f"REJECTED: {k} is required")
    if d["kind"] not in IP_KINDS: sys.exit(f"REJECTED: kind must be one of {sorted(IP_KINDS)}")
    status = d.get("status") or "in_progress"
    if status not in IP_STATUS: sys.exit(f"REJECTED: status must be one of {sorted(IP_STATUS)}")
    td = d.get("target_date")
    if td is not None and not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", str(td)): sys.exit("REJECTED: target_date must be YYYY-MM[-DD] or null")
    sid = d.get("staging_id")
    if sid and sid not in {r.get("id") for r in read_jsonl(STAGING)}: sys.exit(f"REJECTED: staging_id {sid} not found")
    rows = read_jsonl(IN_PROGRESS)
    n = max([int(m.group(1)) for r in rows if (m := re.match(r"ip-(\d+)$", r.get("id", "")))] or [0]) + 1
    row = {"id": f"ip-{n:04d}", "title": d["title"], "kind": d["kind"], "status": status, "target_date": td,
           "notes": d.get("notes", ""), "source": d["source"]}
    if sid: row["staging_id"] = sid
    append_jsonl(IN_PROGRESS, row)
    print(json.dumps(row, ensure_ascii=False))

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "add": add(a[1])
    elif len(a) == 2 and a[0] == "add-in-progress": add_in_progress(a[1])
    else: print(__doc__); sys.exit(1)
