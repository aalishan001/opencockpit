---
name: bragdoc
description: In-depth, metric-backed brag document of the user's engineering and career work (a performance-review and career record). Commands - dump, stage, probe, renovate, brag, extractor. Use whenever the user mentions achievements, brain dumps, work they did, weekly wins, updating their brag doc, an extensive resume, or summaries from coding sessions - even without saying "bragdoc".
---

# BRAGDOC

**No command given** (bare `/bragdoc`): read `COMMANDS.md` and print its `## BRAGDOC` section verbatim (heading through the line before the next `## `) in a fenced code block. Nothing else, no commit.

"An in-depth, detailed brag document of all my engineering and career work."

Pipeline: `dump → staging (raw) → probe → staging (probed) → renovate → entries.jsonl → rendered PDF`

- `data/bragdoc/entries.jsonl` is the source of truth. The PDF is always rendered from it by script, never hand-written.
- Facts in an entry change only through **probe** or my explicit correction, and always shown as a diff.
- Every staging item and every probe transcript is kept: `data/bragdoc/probes/<staging-id>.md`.

## Impressiveness scoring (`rank_score` 1–10)
Measured relative to an engineer in the same field with my tenure (`career_start` in `data/profile.json` → today). Ask: "For someone this far into their career, how cool is this?"
- 9–10: rare at this tenure (owned a system end to end at scale, a significant measurable business or perf impact, novel design)
- 7–8: clearly above peers (led a feature across services, strong metrics)
- 5–6: solid, expected of a good engineer at this level
- 1–4: routine; keep it for completeness
Always write a one-line `rank_rationale`. My override wins; record it as `rationale: "user override: ..."`.

## Commands

### dump (one-off; show a plan with counts and wait for my go before writing data/)
Accept text, files, or folders (brain dumps, old resumes, docs). Move originals to `raw/bragdoc/<YYYYMMDD-HHMM>-<name>` (images via `python scripts/ingest_images.py bragdoc <paths>`). Never edit originals. Single items (and other domains' handoffs) are appended with `python scripts/bragdoc_stage.py add -`.

**Source trust tiers.** Tag every extracted claim with its source file and tier, stored per item as `source_claims: [{claim, value, source, tier}]`:
- **T0**: my explicit statements in chat (`source: "user"`). Always wins.
- **T1**: my own notes (newest first).
- **T2**: resumes I approved (newest first; older versions mostly superseded). Claims that appear only in resumes are true and defensible; stage them for depth, never mark them unverified.
- **T3**: AI-generated text (summaries, other assistants' dumps). Anything only in T3, or marked "assumed", "inferred" or "WEAK", gets `needs_confirmation: true` and must be confirmed in probe before it reaches an entry.
- From T3, extract only facts (numbers, names, events, technologies, outcomes), not reworded purpose statements. A T3 claim restating a T0–T2 fact joins that claim's group, so it isn't flagged.
- When T0 overrides a lower-tier value, keep the old record with `superseded: "<why>"`.

**Deduplication.** One staging item per distinct achievement; merge every mention across files, keeping all variants in `source_claims`. Dedupe against existing `staging.jsonl` and `entries.jsonl` too.

**Batches.** One project per batch: `b-<date>-<project-slug>`. Large projects split by sub-area (e.g. a platform split into access control, report pipeline, ingestion, …). Each item also carries `project` and `employer`.

**Conflicts.** When non-T0 sources disagree, add `conflicts: [{field, values: [{value, source, tier}], status, ...}]`. Open conflicts get a question in `questions.jsonl` (`topic: "conflict"`) citing each value and its source; T0- or script-settled ones are `status: "resolved"` with a `resolution`. Never ask about anything a script can compute (ratios, percentages): run the script and store the result.

**Pre-probed fast path.** Fill `probe` fields from sources for every item (only T0–T2 facts, never T3-only ones). An item goes straight to `status: "probed"` only if it meets the completeness criterion below *and* has no open conflicts, no `needs_confirmation` claims and a known `kind`. Otherwise `status: "raw"` with `open_gaps` listing exactly what's missing, so probe asks only that. For each fast-path item, write `probes/<id>.md` listing the claims each field came from, and add a confidentiality question (`topic: "confidentiality"`): "anything here not OK to say publicly?" (the fast path skips the probe's own question).

**Everything goes in the BragDoc.** Achievements, including community, teaching, leadership and competitions, go through staging (non-engineering ones: `kind: "community"`, category "Community & Leadership" at renovate). Other material goes to its own file (schemas in `scripts/schemas.md`):
- skills → `skills.json` (level only in my own words; evidence via `evidence_staging_ids` until renovate)
- education → `education.json`
- employment history → `employment.json` (employer, role, start, end, source; company awards and team size as `context`, never as my achievement; no salaries, addresses or phone numbers). `context` is internal: only the internal BragDoc shows it. Every resume and the public PDF use the user-approved `public_summary` (one sentence under the role) and `public_context` (lines) instead
- unfinished work → `in_progress.jsonl` (promote to a staging item when completed)

After writing: a table per batch (items, probed/raw, open gaps, conflicts), then all questions grouped by batch with conflicts first. Validate, commit, push.

### stage (one-off)
Table of staging items: id, batch, one-line summary, status, open gaps. Group by batch. Exclude `merged` unless asked.

### probe (back and forth; ends on `/end` or auto when the item has no open gaps)
Take one raw item or batch (I can name one; default is the oldest raw batch).

Before asking anything: read the item's `open_gaps`, `conflicts` and `source_claims`, then look up its project in `data/bragdoc/probe_bank.md` (if present). Skip every bank question the item's data already answers. Order: open conflicts (with their questions in `questions.jsonl`), then `needs_confirmation` claims, then the other gaps, then bank questions. When I answer a conflict or confirm a claim, record my answer as a T0 claim, resolve the conflict or clear the flag, and mark the question answered.

Grill like a senior engineer reviewing me for the next level:
- **Problem:** what was broken or missing, and who felt it
- **Action:** what *I* did versus the team, and the decisions and trade-offs I made
- **Result:** before/after metrics (latency, users, time saved, error rate, revenue), and how I know
- **Scope:** systems, scale, and stakeholders touched
- **Stack:** specific technologies
- **Logic gaps:** call out inconsistencies, vague verbs ("helped", "worked on"), and unverifiable claims

Near the end of each item, ask naturally as part of the conversation (not as a form):
- **Kind:** is this work for an employer/client, a personal project, a product (has users / a landing page), an open-source contribution, or community (teaching, volunteering, competitions, clubs)?
- **Links** (non-work only): repo, live URL, landing page, demo, docs.
- **Confidentiality:** "Is anything here not OK to say publicly: client names, internal numbers, system names, unreleased features?"

One question at a time. Estimated metrics are allowed only if labelled as estimates with the method stated.

**Completeness criterion ("probed")**, enforced by `validate.py`:
- `problem`, `action`, `result`, `my_role` and `stack` filled
- at least one **scale** metric (users, records, requests/day, team size) and one **impact** metric (% improvement, time saved, issues resolved), each tagged `type: "scale" | "impact"` in `probe.metrics`
- an **ownership** signal in `my_role`/`action` (led, designed, owned, independently built)
- **no passive verbs** (worked on, helped, assisted, was responsible for)
- no open conflicts, no `needs_confirmation` claims, empty `open_gaps`
- **Answered without data** (my AS-IS, or "don't know" to a metric or the stack): `probe.waived` = `{fields: [scale|impact|stack|problem], source: "user, <date> (<answers file>)", reason}` exempts exactly those parts, nothing else. Only my answer waives; never fill the gap with an estimate instead

Save the transcript (these answers included, like every other answer), fill `probe` including `kind`, `links`, and `public_constraints` (if I say "nothing", store `[]` explicitly), set `status: probed` (or `probing` if ended early, with `open_gaps` listed). Commit.

### renovate (one-off)
1. For each `probed` item, create or merge into an entry: professional resume-style phrasing, all details kept, no redundancy. Set `status: merged`.
   - Carry over `kind`, `links`, `public_constraints` from the probe (merging items: union of constraints, merge links). Create every new entry with `python scripts/bragdoc_public.py add-entry '<json>'`: it assigns the id, `published_hash: null` and the **standing visibility default** (`data/runway/config.json` → `visibility_default`, the user's own rule; the template ships with every new entry private): for example public, unless the entry is the current employer's (then private). Never set `visibility` by hand; later changes only via set-visibility on the user's word. A merge into an existing entry never changes its visibility, `site_slug` or `published_hash`.
   - Kind unknown: `work` if `employer` is set; otherwise add a `topic: "kind"` question to `questions.jsonl` and leave the item in staging until answered.
   - Carry the staging item's `employer` into the entry. Then swap staging ids for entry ids in `skills.json` (`evidence_staging_ids` → `evidence_entry_ids`) and in `education.json` (`capstone.entry_id`).
2. Recategorize all entries into loose technical categories (e.g. Backend & APIs, Data & Databases, Cloud & DevOps, Mobile, Performance, Architecture). No timeline narrative. `kind: "community"` entries (teaching, volunteering, competitions, clubs, podcast) go in "Community & Leadership", ranked within it like any category.
3. Re-rank within each category by `rank_score`, highest first.
4. Show the diff summary (new, merged, re-ranked, recategorized). Write, validate.
5. **Public layer: everything the site needs, for EVERY entry whatever its visibility** (nothing is generated at publish time):
   - `python scripts/bragdoc_public.py stale` → for each listed entry and channel, write the text under that channel's rules (below) and save it: summaries with `python scripts/bragdoc_public.py set-summary <id> '<json>' --channel public|resume`, site cards with `python scripts/bragdoc_public.py set-card <id> '<json>'` (`{metric, context, did, result, where}` with a short metric, public rules, the entry's own employer deciding which figures it may carry). The scripts stamp `generated` and `source_hash` and reject anything `disclosure_lint` blocks; fix and resave. No approval step.
   - `python scripts/bragdoc_public.py finalize`: sets `year` on entries and staging items (period, else `data/bragdoc/project_years.json`, else a single-year tenure), cuts each missing `site_slug` from the public headline (never changed afterwards), and lists anything still missing; repeat until it reports every entry complete. An entry with no year rule: ask for its year and add it to `project_years.json`.
   - `python scripts/bragdoc_public.py missing-links --add-questions`
   - `python scripts/bragdoc_public.py pending`
6. Run `python scripts/render.py bragdoc`, which produces `out/<names.short>_BragDoc.pdf` (HTML fallback if PDF tooling is missing): Experience (from `employment.json`), the ranked categories, Skills, Education, Community & Leadership, In Progress. Show the path.
7. Commit and push. End the output with:
   ```
   Public layer
   - N summaries generated/refreshed
   - N public entries pending a site update: <titles>
   - N non-work entries missing links
   ```
   Then, automatically: `python scripts/runway.py publish --if-pending`. When any public payload changed, it ships to the site repo's `content` branch and prints the preview URL (add it to the output); otherwise it does nothing. It never touches `main`: promote stays manual (`/runway promote`), the one human gate before anything goes live.
   Then: `python scripts/profiles.py policy`, and add its reminder (if any) to the output: which profile pieces are stale and why (EXTROVERT `profiles`).

Items not yet probed stay in staging.

## Disclosure channels
Everything that leaves the BragDoc goes through one of three channels defined in `data/bragdoc/disclosure_policy.json` and enforced by `python scripts/disclosure_lint.py --channel internal|resume|public <file>`. Renders lint themselves and write nothing on failure; a failure shows the offending lines, which get fixed (usually by regenerating that entry's channel summary). Nothing ships with a lint failure.
- **internal** (`render.py bragdoc`): only me. Full entry detail, security specifics, all contacts, cost figures.
- **resume** (`render.py resume-extensive` and any resume built from the BragDoc): written from `resume_summary` + resume contacts (phone and the personal email; resumes always use the personal email, never the domain email).
- **public** (the website, shipped by RUNWAY; `render.py public-resume` is its PDF, served as `/<names.short>_Resume.pdf`, public entries only): written from `public_summary` and `site_card` + public contacts (the domain email, never phone or personal email).
- **Names** (`data/profile.json` → `names`; each channel's form is in the policy): internal renders show `short`, resume renders `formal` exactly as stored, the public resume `public_full`. Summaries and other public prose use `short`, or `public_full` only where a full name is genuinely required. Never type a name into an output; an all-caps design is CSS `text-transform: uppercase`, never changed text. The lint flags any wrong casing of the formal name on every channel.

## Public layer
Cockpit prepares public data; only RUNWAY ships it (`/runway`). `published_hash` is set only by `runway.py promote`, never by hand or by bragdoc.

Two channel summaries plus one site card per entry (cards follow the public rules below). Summaries share one structure (`headline` ≤ 12 words, `summary` 2–4 sentences, `highlights` 2–4 short bullets, `stack` public tech only) and the same `source_hash`/stale machinery. Both are generated for **every** entry regardless of visibility, from the entry, its probe transcript, `public_constraints`, and common sense.

**Resume summary** (`resume_summary`; anyone reading your resume sees it):
- Remove: internal system/service/table names, proprietary platform internals, exploitable security specifics, anything in `public_constraints` (e.g. no security details tied to a named client).
- Allowed: client/employer names, project/app names, generic vulnerability classes (the categories listed in the policy), engineering metrics (latency, throughput, test counts, coverage like 66/66), business scale (users, records).
- Employer money figures: relative change only, never absolute values.

**Public summary** (`public_summary`) redaction rules, always applied, even when `public_constraints` is empty:
- Everything the resume summary removes, plus: no vulnerability class names (keep the achievement: "hardened external document fetching", not the class name).
- Costs (the user's rule): relative cost changes (a percentage cut in hosting spend, say) from past employers', clients' or personal work are allowed; absolute amounts (currency amounts, per-month figures) never; any cost figure about the current employer never. The current employer is always the open role in `employment.json`, so a job change re-tiers this automatically.
- Never include anything in `public_constraints`.
- Client/employer and project/app names are allowed, but never alongside security details for that client. Work entries: no internal system/service names; no security architecture details or vulnerabilities; no unreleased features or roadmap.
- Business numbers (the user's rule, enforced by disclosure_lint): user counts and usage scale (users, downloads, concurrent users, records, sites) from past employers', clients' or personal work are allowed; the current employer's user, tenant and customer counts never; revenue and contract values never, for any employer. Per-entry `public_constraints` still win.
- Allowed: employer name, the problem type in generic terms, my role, public technologies, and impact as relative change ("cut p95 latency by ~60%") when the absolute numbers aren't sensitive (money figures: see above). Compute the change with `python scripts/bragdoc_public.py change <before> <after>`, never in your head.
- Personal projects, products, open source, community: anything I'd put in a public README is fine; still respect `public_constraints`. Only personal projects, products and open source are expected to have links.
- Never add claims not in the entry. Same truthfulness rules as the rest of BragDoc.
- Tone: confident, concrete, no buzzwords; readable by any engineer or reviewer.

**Visibility:** changes only when I explicitly say so. "make <entry> public|private" (by id or title; if ambiguous, ask which) → `python scripts/bragdoc_public.py set-visibility <id> public|private`, show the entry's `public_summary`, commit, push.

### brag (one-off)
Run `python scripts/render.py resume-extensive`, which produces `out/<names.formal>_Resume_Extensive.pdf` (spaces as underscores) on the **resume channel**: ATS-friendly, single column, standard headings, the whole BragDoc except In Progress, written from each entry's `resume_summary` with resume contacts. The render lints itself; on failure, show the offending lines, fix the summaries, re-render. Show the path.

### extractor (two steps: emit a prompt, then take the summary back as a dump)
Modes, one prompt per kind of source:

| Command | Prompt for |
|---|---|
| `/bragdoc extractor` | **session** (default): the work done in the current AI pair session / repo |
| `/bragdoc extractor incident <date> <short description>` | one incident: timeline with timestamps (first symptom, detection, diagnosis, mitigation, resolution), durations computed from the timestamps, impact, root cause, fix, prevention added, what I'd do differently |
| `/bragdoc extractor project` | one project: what it is, owner (personal / employer / client), status and dates from git, architecture and data flow, decisions and trade-offs, evaluation, metrics, what's novel, stack, links |
| `/bragdoc extractor period <from> <to> <topic>` | multi-month work (e.g. a quarter-long migration or a pipeline rebuilt over several iterations): phases, the problem before, what changed and why per phase, metrics then vs now (still true?), ownership, decisions, what went wrong and the fix, stack |

1. **Emit (one-off, writes nothing, no commit):** `python scripts/extractor.py prompt <mode> [args] [--personal]`, shown verbatim in one fenced block, ready to paste. The script writes every prompt; never hand-write, trim or reword it. Every prompt carries: a READ-ONLY block (no file edits, no commits/pushes/branches/stashes, no migrations, builds, tests, scripts or DB queries; read files and read-only git only; answer in chat, save nothing), evidence tags on every number and claim (`[measured]`, `[from git/logs/docs]`, `[estimate]`, `[from my memory]`), strict ownership (mine vs others'), a confidentiality block, and a closing "Notes for you" (what was left out and why, what's unverified). The confidentiality block (no code, hostnames/IPs/URLs, credentials or env values, table/service names, client names, exploitable specifics) stays unless the work clearly belongs to no employer or client; only then pass `--personal`. If unsure, keep it. Incident dates and period bounds are checked by the script.
2. **Paste-back** (when I paste the summary): it is a **dump**, so every dump rule applies (tiers, dedupe, conflicts, show the plan and wait for my go), plus:
   - **Source:** `python scripts/extractor.py source <mode>` → `extractor:<mode>:<date>` on every item.
   - **Evidence:** each claim keeps its tag in `source_claims[].evidence` (`measured` | `git` | `estimate` | `memory`). The summary is AI-written, so claims are T3 with `needs_confirmation` as usual; in probe, confirm the `measured` and `git` ones in one batch question. An untagged number is not stored; it becomes a question.
   - **Overlaps first, before creating anything:** for each item, `python scripts/extractor.py overlaps '<json>'` (raw, project, employer, and the incident date or period bounds). Show every likely/possible overlap and ask: merge into the existing item (new claims added to it) or create a new one. Example: an incident write-up vs an existing entry that already mentions the same failed migration that month.
   - **Incidents:** recompute time to detect / mitigate / resolve with `python scripts/extractor.py durations <first_symptom> <detected|unknown> <resolved> [--mitigated <ts>]` (pass `unknown` when there's no detection timestamp; the script then reports only the intervals the timestamps support). If the summary's numbers differ, the script's win and the mismatch becomes a question. Store the timestamps and durations as claims; never "record time" or similar.
   - **Create** with `python scripts/bragdoc_stage.py add -` (status raw; the summary's gaps and its "Notes for you" unverified claims go into `open_gaps`; what it left out for confidentiality stays out). A project whose status is in progress also gets `python scripts/bragdoc_stage.py add-in-progress -` (`kind: project`, `staging_id` = the new item).
   - Validate, commit `bragdoc: extractor: <mode>: <n> items`, push. Offer to probe them.
