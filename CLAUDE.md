# cockpit

Personal command system run inside Claude Code. Five domains, each a skill with explicit commands.
"Agent" here means a division of duties, not a separate process.

| Domain | Skill | Purpose |
|---|---|---|
| CHASSIS | `/chassis` | Example domain: vehicle maintenance from the owner's manual, service slips and odometer readings |
| EXTROVERT | `/extrovert` | Interview-style conversations → edited posts (Medium canonical, LinkedIn summary), ideas backlog, profile copy |
| bragDoc | `/bragdoc` | Probed, metric-backed record of engineering work → bragDoc + extensive resume, with disclosure tiers |
| RUNWAY | `/runway` | Ships the bragDoc's public channel to your own site repo (preview on a content branch, promote on your approval) |
| FOURTHWALL | `/fourthwall` | Documents the system itself (journal, changelog, README, case study) and exports a public, generalized copy |
| HELP | `/cockpit [domain]` | Prints `COMMANDS.md` (or one domain's section) verbatim |

`/end` ends whichever interactive command is active (conversation, editorial, probe) and commits.

If a request doesn't name a command, map it to the closest one and say which you used.
If it maps to nothing, say so and suggest the nearest command. Don't improvise a new workflow.

## Folder contract

- `inbox/`: drop zone (create it). Anything here is unprocessed.
- Optional second inbox (a synced cloud folder for phone uploads): set `COCKPIT_DRIVE_INBOX`. Same rules as `inbox/`; check both. `python scripts/ingest_images.py --pending` lists images waiting in either.
- `raw/`: originals after processing, moved from inbox as `raw/<domain>/<YYYYMMDD-HHMM>-<name>`. Never delete.
- Images are always ingested via `ingest_images.py`, never committed as raw phone photos. `python scripts/ingest_images.py <domain> <paths>` writes compressed JPEGs to `raw/<domain>/` and deletes the inbox originals (the raw/ copy is the archive).
- `data/`: structured truth. Only skills write here, only in the formats in `scripts/schemas.md`.
- `templates/`: rendering templates for PDFs and HTML.
- `out/`: rendered outputs (PDF/HTML). Regenerable; always produced by scripts.
- `examples/persona/`: a fictional user's data. Copy it into `data/` to try every command before using your own.
- Your website repo (optional): a sibling of this repo, never inside it, set in `data/runway/config.json`. Only RUNWAY writes there, one way: content (the site data and the resume PDF) through publish, and site code changes you ask for through ship.

## Global rules (all domains)

1. **No invented facts.** Numbers, dates, metrics, odometer readings, and claims come from me, an image or document I gave, or a cited web source. If unsure, ask. Never fill a gap with a plausible guess and store it as fact.
2. **Provenance.** Every record in `data/` carries a `source` (file name in `raw/`, `web:<url>`, or `user`).
3. **Ask, don't guess.** Low-confidence extractions go to the question queue for that domain and are asked at the end of the command. They never go into `data/` until answered.
4. **Code does exact work.** Arithmetic, dates, sorting, deadlines, hashes, rendering, and validation are done by `scripts/`. Never compute these in your head. Run the script and report its output.
5. **Show then write.** Before changing `data/`, show what will change (a short diff or table). For bulk changes, show a summary and ask once.
6. **Validation is enforced.** A hook runs `scripts/validate.py` after every edit. If it fails, fix the data before doing anything else.
7. **Versioning = git + snapshots.** After every command that changes files, commit: `<domain>: <command>: <short summary>`. Conversations, editorials and probe transcripts are also saved as dated files (each skill names its paths), referenceable by date-time and by name.
8. **Commands end the way their spec says.** One-off commands finish after output. Interactive commands continue until I say `/end` or their auto-end condition is met.
9. **Tone.** Direct, concise, no flattery. If my claim or plan is weak, say so.
10. **Command names.** COMMANDS.md is the source of truth for command names. Whenever a skill's commands change, update COMMANDS.md in the same commit.
11. **Public data.** Only RUNWAY publishes, and nothing goes live until I approve a preview (`/runway promote`). Visibility of a bragDoc entry changes only on my explicit instruction: a specific one (`bragdoc_public.py set-visibility`), or my standing default in `data/runway/config.json` (applied once, when renovate creates an entry). Public summaries and site cards are generated automatically and must follow the redaction rules in the bragdoc skill.
12. **Disclosure channels.** Anything that leaves the bragDoc is internal, resume or public, as defined in `data/bragdoc/disclosure_policy.json`. Every resume and public output passes `scripts/disclosure_lint.py` for its channel before I see it; nothing ships with a lint failure.
13. **Names.** Read them from `data/profile.json` → `names`; never hard-code one. Internal output: `short`. Public channel (website, posts, LICENSE, README, case studies, social): `short` by default, `public_full` only where a full name is genuinely required, such as a copyright line or author credit. Resume channel (resumes and formal applications only): `formal`, exactly as stored. An all-caps design is CSS `text-transform: uppercase`; the stored and linted text never changes.

## Git operations

I never touch git. You own it, under these rules:

1. **Branch:** `main` only. No branches, no PRs.
2. **Session start:** `git pull --rebase` (the SessionStart hook does this; if it failed, do it and resolve conflicts, preferring the newer data line and showing me).
3. **After every command that changes files:** validate, then commit `<domain>: <command>: <summary>` and `git push` immediately. No batching across commands, no asking.
4. **Identity:** before the first push in a session, confirm the repo's local `user.email` and `origin` URL are the ones I set for this repo. If not, stop and tell me. Never fix it by changing global config or credentials.
5. **Never:** force push, rewrite pushed history, `reset --hard`, delete branches (one exception: RUNWAY deletes a site branch once it is fully merged into `main`, rule 7), touch global git config, or commit secrets/tokens/.env.
6. **Push failures** (auth, network, rejected): report the exact error in one line and keep working locally; retry push at the next commit.
7. **Website repo** (if you use RUNWAY): the same rules, through `scripts/runway.py` only. Content: `publish` → branch `content` (preview) → `promote`. Site code (only on my explicit instruction): `ship "<summary>"` → its own branch `code/<slug>` (preview) → `promote code/<slug>`. Both paths run the same gates, and nothing reaches `main` (live) without my approval of the preview. A preview branch exists only while something waits for my approval: every promote deletes the branch it promoted, and `runway.py prune` deletes any other branch already merged into `main`; a branch with commits not in `main` is never deleted without showing me. The deploy hook lives only in the gitignored `data/runway/deploy-hook.local`.

Keep this repo private: `data/` and `raw/` hold your real records. Share only what FOURTHWALL exports.

## Profile

See `data/profile.json`. Tenure baseline for "how impressive is this" judgments: career start in that file → today.
