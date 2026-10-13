---
name: fourthwall
description: Documents the development and use of this cockpit itself (journal, changelog, README, case study) and produces a public, generalized, MIT-licensed copy of the repo. Commands - log, changelog, readme, export, publish, handoff. Use when the user talks about cockpit as a project, wants to record a decision or lesson about the system, or asks about the public version.
---

# FOURTHWALL

**No command given** (bare `/fourthwall`): read `COMMANDS.md` and print its `## FOURTHWALL` section verbatim (heading through the line before the next `## `) in a fenced code block. Nothing else, no commit.

The domain that looks at the system itself: it keeps a private journal of how this cockpit was built and used, and generates a public, generalized copy that is safe for me and for anyone I work for. (This public repo was produced exactly this way.)

## Principles
1. **Allowlist, never strip.** The public copy is *generated* from an explicit manifest of generalized files (`data/fourthwall/manifest.json`). Nothing outside the manifest can reach it. Never copy or mirror the private repo, never make it public, never share git history: the public copy has its own fresh history.
2. **Hand off, don't write.** Fourthwall never writes other domains' data. It uses their commands: `bragdoc_stage.py add` (the bragdoc dump path), `ideas.py add`, and a case-study draft queued for RUNWAY.
3. **Show then push.** Every publish shows me the full diff and the leak report and waits for my explicit approval. Never automatic.
4. **Excluded structurally:** any private domain I list in the manifest rules (its skill, data, rules, scripts), `data/`, `raw/`, `inbox/`, `out/`, probes, `profile.json`, employment, real test fixtures, `.git`, settings with personal paths. The manifest rules reject them; validate.py and export enforce it.

## Data
- `data/fourthwall/journal.jsonl`: append-only `{ts, kind: decision|lesson|milestone|bug, title, text, tags, commit?, source?, tier?, date_approx?}`. Private source material; never exported.
- `data/fourthwall/state.json`: `last_changelog_commit`, `last_export_hash`, approval, `published_versions`, `ip_policy_checked` (false until I confirm), `commit_email`, `staging_dir`, `clone_dir`, `remote`.
- `data/fourthwall/manifest.json`: `rules` (excluded prefixes, substrings, names) + `files: [{source, target, transform: copy|generalize|template, generalized?, source_hash?}]`.
  - `copy`: only for files with zero personal content (proven by the leak checks every export).
  - `generalize`: a hand-written rewrite in `fourthwall/generalized/<target>` (a target under `.claude/` is stored under `_claude/`, so Claude Code never loads the copies as skills), tied to the source's hash. If the private source changes, export blocks as STALE: rewrite the generalized copy (remove my name, my personal assets, my employers, my data paths, private domains; keep the engineering intact), then `python scripts/fourthwall.py mark-generalized <target>`.
  - `template`: hand-maintained public files in `fourthwall/templates/` (CLAUDE.md, LICENSE, CONTRIBUTING, .gitignore, data skeleton, fictional-persona examples, synthetic tests).
- `data/fourthwall/denylist.json`: deny terms (see leak checks). Contact data is derived from `profile.json` at export time and never stored here.
- `fourthwall/CHANGELOG.md`, `fourthwall/README.md`: generated, public-linted, shipped in the public copy.

## Commands
`python scripts/fourthwall.py` does all exact work (ids, hashes, builds, checks, git). I write prose: journal entries, changelog summaries, README, case study, generalized copies.

| Command | Does |
|---|---|
| `/fourthwall log <note>` | Infer `kind` and `tags` (ask only if unclear) → `fourthwall.py log '<json>'` → validate, commit `fourthwall: log: <title>`, push |
| `/fourthwall changelog` | `fourthwall.py changelog-commits` → summarize the new commits into public-safe entries in my own words (never copy a commit message: they can name private items) → `fourthwall.py changelog-append <version> '<json>'` (rejects verbatim subjects, public-lint and deny-list failures) → commit, push |
| `/fourthwall readme` | Regenerate `fourthwall/README.md` from `fourthwall/templates/README.template.md` + journal + changelog: what it is, the harness-first idea with a plain-text diagram, the domains, the folder layout, how to add your own domain, safety rails, setup, how fourthwall builds the repo, license. No raw HTML and no mermaid: it must also render in a sanitized Markdown popup (a site's Repos section), whole if possible (about 6,000 characters of text). `fourthwall.py lint-public fourthwall/README.md --voice` must pass. Goes into the next export. Commit, push |
| `/fourthwall export` | `fourthwall.py export` builds the public copy into `staging_dir` (outside this repo, never committed) from the manifest only, then runs every leak check. Show me: file list, the full diff vs the last published version (`fourthwall.py diff`), the leak report. Never pushes. Stale generalized copies and leak failures block; fix them and export again |
| `/fourthwall publish` | Only after a clean export I approved **in this session**: `fourthwall.py approve <hash>` when I say so, then `fourthwall.py publish <X.Y.Z> "<summary>"` (copies staging into the local clone, commits `release vX.Y.Z: <summary>`, tags, pushes to `remote`). First publish is blocked until `ip_policy_checked` is true: ask me to confirm I've checked my employer's IP / side-project policy, then `set-ip-checked`. The clone commits with `commit_email` (a GitHub noreply address; never a personal email). After the first publish, tell me to turn on Settings → General → "Template repository". The script uses plain git only, never a hosting CLI that may be logged in as another account |
| `/fourthwall handoff` | Queue outward work without doing it: (1) `python scripts/bragdoc_stage.py add '<json>'`: the public repo as a `personal_project` with `links.repo`, citing journal entries (I probe it later); (2) `python scripts/ideas.py add -`: the story of the repo, linking it (I run start later); (3) `data/fourthwall/case_study.md` (problem, constraints, architecture, decisions, results) for a RUNWAY showcase later, passing `fourthwall.py lint-public data/fourthwall/case_study.md --voice`. Validate, commit, push |

## Leak checks (export blocks on any failure; each reported pass/fail with offending lines)
1. **Structural:** the staging tree holds exactly the manifest's targets; no excluded source; `data/` targets only from templates.
2. **Secrets:** detect-secrets scan of the staging tree.
3. **Public lint:** `disclosure_lint` public channel on every text file (explicit per-file exemptions only in `denylist.json` → `lint_exempt`).
4. **Deny list** (case-insensitive by default; short or common-word terms go in `exact_terms`, exact-case whole-word): my name variants, phone, emails, location (derived from `profile.json`), employers (`employment.json`), project names (staging), internal identifiers + excluded-employer terms (disclosure policy), clients, personal assets, user paths, private domains and their tools. My handle and name are allowed only on LICENSE and README author lines (`author_line_exemptions`).
5. **No em dashes** anywhere in the public copy (prose uses colons, commas or parentheses; code writes the `\u2014` escape).
6. **Canary** (tests only): a planted fake secret, employer name and private-domain name in a temp copy must all be caught.

The journal is private, but anything drawn from it (README, changelog, case study) passes the public lint and the deny list.
