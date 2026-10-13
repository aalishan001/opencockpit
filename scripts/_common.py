import json, os, pathlib, sys
for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; titles contain →, ₹, ×
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")
ROOT =pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parent.parent)
DATA = ROOT / "data"

def read_jsonl(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{p.name}:{i} invalid JSON: {e}")
    return rows

def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
