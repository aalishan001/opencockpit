#!/usr/bin/env python3
"""Ingest images: EXIF auto-rotate, max 1600px long edge, JPEG q80 -> raw/<domain>/<YYYYMMDD-HHMM>-<name>.jpg
Usage:
  ingest_images.py <domain> <image|dir>...     prints one new path per line
  ingest_images.py --pending                   lists images waiting in inbox/ and the optional second inbox

After a verified write, the source is deleted if it sits in inbox/ or the second inbox (env COCKPIT_DRIVE_INBOX, e.g. a synced cloud folder)
(the compressed copy in raw/ is the archive). Sources anywhere else are left alone.
EXIF (incl. GPS) is stripped from the output. Exit 1 if any image failed.
"""
import datetime, os, pathlib, re, sys
from PIL import Image, ImageOps
from _common import ROOT

try:  # phone HEIC photos, if pillow-heif is installed
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

DOMAINS = {"chassis", "extrovert", "bragdoc"}
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff"}
MAX_EDGE, QUALITY = 1600, 80
INBOXES = [ROOT / "inbox"] + ([pathlib.Path(os.environ["COCKPIT_DRIVE_INBOX"])] if os.environ.get("COCKPIT_DRIVE_INBOX") else [])

def in_inbox(p):
    p = p.resolve()
    return any(box.exists() and p.is_relative_to(box.resolve()) for box in INBOXES)

def images_in(path):
    p = pathlib.Path(path)
    if p.is_dir():
        return sorted(f for f in p.iterdir() if f.is_file() and f.suffix.lower() in EXTS)
    return [p]

def slug(stem):
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-") or "image"

def target(domain, src, stamp):
    out_dir = ROOT / "raw" / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{stamp}-{slug(src.stem)}"
    out, n = out_dir / f"{base}.jpg", 2
    while out.exists():
        out, n = out_dir / f"{base}-{n}.jpg", n + 1
    return out

def ingest(domain, src, stamp):
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.getchannel("A"))
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)  # only ever shrinks
        out = target(domain, src, stamp)
        im.save(out, "JPEG", quality=QUALITY, optimize=True)
    with Image.open(out) as check:
        check.verify()
    return out

def main(argv):
    if argv[:1] == ["--pending"]:
        for box in INBOXES:
            if box.exists():
                for f in images_in(box):
                    print(f)
        return 0
    if len(argv) < 2 or argv[0] not in DOMAINS:
        print(__doc__, file=sys.stderr)
        return 2
    domain, failed = argv[0], 0
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    for src in (f for a in argv[1:] for f in images_in(a)):
        try:
            if not src.is_file():
                raise FileNotFoundError("not found")
            out = ingest(domain, src, stamp)
        except Exception as e:
            failed += 1
            print(f"FAILED {src}: {e}", file=sys.stderr)
            continue
        if in_inbox(src):
            src.unlink()
        print(out.relative_to(ROOT).as_posix())
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
