#!/usr/bin/env python3
"""Word count and read time of a post.  post_stats.py <post-file.md>  ->  {"word_count": N, "read_time_min": M}
Counts the post body only: everything after a '<!-- notes -->' line (media suggestion, tags, canonical
advice), everything before an '<!-- article starts here -->' line (a paste sheet) and any front matter is ignored. Markdown syntax, images, link URLs and HTML tags are not words;
link text is. Read time = word_count / 230 wpm, rounded up, minimum 1.
"""
import json, math, pathlib, re, sys

WPM = 230
WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")

def body(text):
    text = re.split(r"(?m)^\s*<!--\s*notes\s*-->\s*$", text)[0]
    text = re.split(r"(?m)^\s*<!--\s*article starts here\s*-->\s*$", text)[-1]   # a paste sheet above the article

    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)        # front matter
    text = re.sub(r"(?m)^\s*```.*$", "", text)                        # code fences (code itself counts)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)                 # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)              # links -> their text
    text = re.sub(r"<[^>]+>", " ", text)                              # html tags / comments
    return re.sub(r"https?://\S+", " ", text)                         # bare URLs

def stats(text):
    wc = len(WORD.findall(body(text)))
    return {"word_count": wc, "read_time_min": max(1, math.ceil(wc / WPM))}

if __name__ == "__main__":
    if len(sys.argv) != 2: print(__doc__); sys.exit(1)
    print(json.dumps(stats(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))))
