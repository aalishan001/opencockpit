#!/usr/bin/env python3
"""Bike maintenance math. km intervals; jobs the manual gives no km for carry interval_months (separate section).
Usage:
  chassis.py deadlines
  chassis.py history
  chassis.py manual
  chassis.py odom <km> [--date YYYY-MM-DD] [--force]
  chassis.py add-service '<json>'          (or '-' to read JSON from stdin)
  chassis.py check-candidates <file.jsonl>  (anomaly scan before configure-history writes)
"""
import json, sys, datetime as dt
from _common import DATA, read_jsonl, append_jsonl, write_jsonl

MAN = DATA / "chassis/manual.json"; SRV = DATA / "chassis/services.jsonl"; ODO = DATA / "chassis/odometer.jsonl"
JUMP_KM_PER_DAY = 300  # flag readings implying more than this average per day

def manual(): return json.loads(MAN.read_text(encoding="utf-8") or "[]")
def readings():
    r = [{"date": s["date"], "odo": s["odo"], "kind": "service"} for s in read_jsonl(SRV)]
    r += [{"date": o["date"], "odo": o["odo"], "kind": "reading"} for o in read_jsonl(ODO)]
    return sorted(r, key=lambda x: (x["date"], x["odo"]))
def current():
    r = readings(); return r[-1] if r else None

def table(rows, headers):
    w = [max(len(str(h)), *(len(str(r[i])) for r in rows)) if rows else len(str(h)) for i, h in enumerate(headers)]
    line = lambda r: "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r))
    print(line(headers)); print("  ".join("-" * x for x in w))
    for r in rows: print(line(r))

def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    days = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return d.replace(year=y, month=m, day=min(d.day, days))
def every(j): return f"{j['interval_km']} km" if "interval_km" in j else f"{j['interval_months']} months"
def deadlines():
    cur = current()
    if not cur: print("No odometer data yet."); return
    last = {}
    for s in read_jsonl(SRV):
        for j in s["jobs"]: last[j] = s
    rows = []
    timed = [j for j in manual() if "interval_km" not in j]
    for j in manual():
        if "interval_km" not in j: continue
        L = last.get(j["id"])
        base = L["odo"] if L else 0
        rem = base + j["interval_km"] - cur["odo"]
        rows.append((rem, [j["name"], j["action"], j["interval_km"],
                           f"{L['odo']} ({L['date']})" if L else "never recorded",
                           base + j["interval_km"], ("OVERDUE " if rem < 0 else "") + f"{rem:+d}"]))
    rows.sort(key=lambda x: x[0])
    print(f"Current odometer: {cur['odo']} km ({cur['date']})\n")
    table([r for _, r in rows], ["Job", "Action", "Every km", "Last done", "Due at", "km left"])
    if timed:
        today, trows = dt.date.today(), []
        for j in timed:
            L = last.get(j["id"])
            due = add_months(dt.date.fromisoformat(L["date"]), j["interval_months"]) if L else None
            status = "never recorded" if not due else ("OVERDUE" if due < today else f"{(due - today).days} days")
            trows.append((due or dt.date.min, [j["name"], j["action"], f"{j['interval_months']} months",
                          f"{L['date']} ({L['odo']})" if L else "never recorded", due.isoformat() if due else "-", status]))
        trows.sort(key=lambda x: x[0])
        print("\nTime-based (manual gives no km interval)\n")
        table([r for _, r in trows], ["Job", "Action", "Every", "Last done", "Due by", "Left"])

def history():
    names = {j["id"]: j["name"] for j in manual()}
    rows = [[s["date"], s["odo"], ", ".join(names.get(x, x) for x in s["jobs"]), s.get("source", "")] for s in read_jsonl(SRV)]
    table(rows, ["Date", "Odo", "Jobs", "Source"])

def show_manual():
    # shortest interval first; km jobs, then time-based jobs (months aren't comparable to km)
    jobs = sorted(manual(), key=lambda j: ("interval_km" not in j, j.get("interval_km") or j["interval_months"]))
    table([[j["id"], j["name"], j["action"], every(j)] for j in jobs], ["Id", "Name", "Action", "Every"])

def anomalies(seq):
    out = []
    for a, b in zip(seq, seq[1:]):
        if b["odo"] < a["odo"]:
            out.append(f"DECREASE: {a['date']} {a['odo']} -> {b['date']} {b['odo']}")
        else:
            days = max((dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])).days, 1)
            if (b["odo"] - a["odo"]) / days > JUMP_KM_PER_DAY:
                out.append(f"JUMP: {a['date']} {a['odo']} -> {b['date']} {b['odo']} ({(b['odo']-a['odo'])//days} km/day)")
    return out

def odom(km, date, force):
    cur = current()
    if cur and km < cur["odo"] and not force:
        sys.exit(f"REJECTED: {km} < last known {cur['odo']} ({cur['date']}). Resolve as an anomaly, then use --force if needed.")
    new = {"date": date, "odo": km, "source": "user"}
    if cur:
        for a in anomalies([cur, new]): print("FLAG:", a)
    append_jsonl(ODO, new); print(f"Logged {km} km on {date}.\n"); deadlines()

def add_service(raw):
    s = json.loads(sys.stdin.read() if raw == "-" else raw)
    ids = {j["id"] for j in manual()}
    bad = [j for j in s.get("jobs", []) if j not in ids]
    if bad: sys.exit(f"REJECTED: unknown job ids {bad}")
    rows = read_jsonl(SRV) + [s]; rows.sort(key=lambda x: (x["date"], x["odo"]))
    for a in anomalies(rows): print("FLAG:", a)
    write_jsonl(SRV, rows); print("Service added.\n"); deadlines()

def check_candidates(path):
    rows = sorted(read_jsonl(path), key=lambda x: x["date"])
    found = anomalies(rows)
    print("\n".join(found) if found else "No anomalies.")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    cmd = a[0]
    if cmd == "deadlines": deadlines()
    elif cmd == "history": history()
    elif cmd == "manual": show_manual()
    elif cmd == "odom":
        date = a[a.index("--date") + 1] if "--date" in a else dt.date.today().isoformat()
        odom(int(a[1]), date, "--force" in a)
    elif cmd == "add-service": add_service(a[1])
    elif cmd == "check-candidates": check_candidates(a[1])
    else: print(__doc__); sys.exit(1)
