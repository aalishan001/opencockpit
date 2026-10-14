# Data schemas

All `.jsonl` files: one JSON object per line. Dates are `YYYY-MM-DD`. Timestamps are ISO 8601 local time.
`validate.py` enforces everything marked **required**.

## CHASSIS

`data/chassis/manual.json`: array of maintenance jobs.
```json
{"id": "engine_oil", "name": "Engine oil", "action": "replace", "interval_km": 3000,
 "source": "raw/chassis/manual.pdf p.42 | web:<url>", "notes": ""}
```
- required: `id` (unique snake_case), `name`, `action` (`check|replace|clean|adjust|lubricate|inspect`), `source`, and exactly one of:
  - `interval_km` (int > 0): the normal case
  - `interval_months` (int > 0): only for jobs the manual gives no km interval for and the web search found none; `deadlines` lists these in a separate time-based section

`data/chassis/services.jsonl`: one line per service visit.
```json
{"date": "2026-03-14", "odo": 12450, "jobs": ["engine_oil", "chain_lube"],
 "source": "raw/chassis/20260314-slip.jpg", "workshop": "", "notes": ""}
```
- required: `date`, `odo` (int), `jobs` (ids that exist in manual.json), `source`
- file order: ascending by `date`; `odo` must not decrease.

`data/chassis/odometer.jsonl`: plain readings (services also count as readings).
```json
{"date": "2026-10-06", "odo": 15230, "source": "user"}
```
- required: `date`, `odo`, `source`. Must not decrease vs any earlier reading or service.

`data/chassis/anomalies.jsonl`: anomaly decisions (append-only).
```json
{"ts": "...", "kind": "decrease|jump|rollover|unreadable", "detail": "...", "resolution": "...", "source": "user"}
```

## bragDoc

`data/bragdoc/staging.jsonl`
```json
{"id": "s-0001", "created": "...", "batch": "b-2026-10-07-shelfie", "project": "Shelfie", "employer": "Example Corp",
 "source": "raw/bragdoc/...", "raw": "one-line summary of the achievement",
 "status": "raw|probing|probed|merged",
 "source_claims": [{"claim": "users", "value": "15,000+", "source": "user", "tier": "T0"},
                   {"claim": "users", "value": "1,000+", "source": "raw/bragdoc/...", "tier": "T2", "superseded": "T0: 15,000+"},
                   {"claim": "launch", "value": "live since Mar 27", "source": "raw/bragdoc/...", "tier": "T3", "needs_confirmation": true}],
 "conflicts": [{"field": "", "values": [{"value": "", "source": "", "tier": ""}], "status": "open", "question_id": "q-0001"},
               {"field": "", "values": [], "status": "resolved", "resolution": "T0 (user, date): ..."}],
 "probe": {"problem": "", "action": "", "result": "",
           "metrics": [{"name": "", "before": "", "after": "", "unit": "", "type": "scale|impact", "note": ""}],
           "stack": [], "scope": "", "my_role": "", "evidence": [], "open_gaps": [], "transcript": "data/bragdoc/probes/<id>.md",
           "kind": "", "links": {}, "public_constraints": []}}
```
- required: `id`, `created`, `source`, `raw`, `status`
- `batch`: `b-<date>-<project-slug>`. `project`, `employer` (null when none): context carried into the entry.
- `source_claims` (optional, written by dump): each needs `claim`, `value`, `source`, `tier` (`T0` chat statement, `T1` my notes, `T2` approved resumes, `T3` AI-generated). `needs_confirmation: true` = only T3 (or marked assumed/inferred/WEAK) backs it; `superseded` = overridden by T0. `evidence` (optional, from extractor summaries): `measured` | `git` | `estimate` | `memory` (the tags `[measured]`, `[from git/logs/docs]`, `[estimate]`, `[from my memory]`).
- `source` of an extractor paste-back: `extractor:<session|incident|project|period>:<YYYY-MM-DD>` (from `scripts/extractor.py source <mode>`; validated).
- `conflicts` (optional): each needs ≥ 2 `values` and `status` `open|resolved`. Open → `question_id` must exist in `questions.jsonl`. Resolved → `resolution` required.
- `probe.metrics[].type` **required**: `scale` (users, records, requests, team size) or `impact` (% change, time saved, cost cut, issues resolved).
- **`status: probed` requires** (validate.py): problem, action, result, my_role, stack filled; ≥ 1 scale and ≥ 1 impact metric; no open conflicts; no `needs_confirmation` claims; empty `open_gaps`; no passive verbs (worked on, helped, assisted, was responsible for) in action/result/my_role. `probe.waived` (optional) `{fields, source, reason}`: the parts the user answered they have no data for (a non-empty subset of scale, impact, stack, problem; source starts with `user`): those parts are not required.
- `probe.kind`, `probe.links`, `probe.public_constraints`: optional, same rules as on entries; renovate carries them into the entry.

`data/bragdoc/probes/<staging-id>.md`: probe transcript, or for fast-path items the list of source claims each field came from.

`data/bragdoc/probe_bank.md`: question bank per project (headings match `project`); probe skips questions the item already answers.

`data/bragdoc/entries.jsonl`: the bragDoc's source of truth.
```json
{"id": "e-0001", "title": "", "category": "", "employer": "", "period": "2025-06..2025-09",
 "problem": "", "action": "", "result": "", "metrics": [{"name": "", "before": "", "after": "", "unit": ""}],
 "stack": [], "scope": "", "my_role": "", "evidence": [],
 "rank_score": 7, "rank_rationale": "", "staging_ids": ["s-0001"], "updated": "...",
 "kind": "work", "visibility": "private",
 "links": {"repo": "", "live": "", "landing": "", "demo": "", "docs": "", "other": [{"label": "", "url": ""}]},
 "public_constraints": [],
 "public_summary": {"headline": "", "summary": "", "highlights": [], "stack": [],
                    "generated": "2026-10-07T12:00:00", "source_hash": "<sha256 hex>"},
 "published_hash": null}
```
- required: `id`, `title`, `category`, `result`, `my_role`, `rank_score` (1–10), `rank_rationale`, `staging_ids` (non-empty)
- **Public layer** (what RUNWAY ships to the site; written only by renovate and the bragdoc_public.py commands):
  - `kind` **required**: `work` (employer/client) | `personal_project` (mine, not a product) | `product` (has users or a landing page) | `open_source` (contributions to others' repos) | `community` (teaching, volunteering, competitions, clubs, podcast; category "Community & Leadership")
  - `visibility` **required**: `private` (default) | `public`. Changed only by `bragdoc_public.py set-visibility`, only on explicit instruction.
  - `links` **required object** (may be `{}`): optional keys `repo`, `live`, `landing`, `demo`, `docs` (each `""` or an `https://` URL) and `other` (list of `{label, url}`, both required, url `https://`). Non-work kinds are expected to have at least one of repo/live/landing; if missing, `missing-links --add-questions` queues a question (not a validation error).
  - `public_constraints` **required list of strings** (may be `[]`): things stated during probing that must not be public.
  - `resume_summary` optional until generated: same structure and `source_hash` machinery as `public_summary`, written under the resume channel's rules (`disclosure_policy.json`). Written only via `bragdoc_public.py set-summary <id> '<json>' --channel resume`.
  - `public_summary` optional until generated (renovate generates it for every entry): `headline` (≤ 12 words), `summary` (2–4 sentences), `highlights` (2–4 items), `stack` (public tech only), `generated` (ISO ts), `source_hash` (hex). Written only via `bragdoc_public.py set-summary`.
  - `source_hash` = sha256 of canonical JSON (sorted keys, compact) of `title, problem, action, result, metrics, scope, my_role, stack, public_constraints, kind, links, employer, period` (absent = empty value).
  - `published_hash` **required key**, `null` or hex: set only by `runway.py promote`, never by bragdoc. An entry is *pending* when `visibility == public` and its payload hash ≠ `published_hash`. Payload hash: see Site fields below; `bragdoc_public.py payload-hash <id>` prints it.

- **Site fields** (renovate writes them for every entry; RUNWAY only reads them):
  - `site_card` `{metric (≤ 40 chars), context, did, result, where, generated, source_hash}`: the site's card and popup text, public rules, written only via `bragdoc_public.py set-card`; stale by the same `source_hash`.
  - `site_slug`: the site's `id` and deep link (`/bragdoc#<slug>`). Cut once from the public headline by `bragdoc_public.py finalize` (lowercase-hyphen), unique, never changed; slugs in `data/runway/state.json` → `retired_slugs` are never reused.
  - `year` (`YYYY`) + `year_source` (`period` | `staging` | `project_years` | `employer_default` | `tenure`): set by `bragdoc_public.py finalize` / `years --apply`; staging items carry them too.
  - The payload hash covers `public_summary` and `site_card` (minus `generated`), `links`, `kind`, `category`, `rank_score`, `year`, `site_slug`; `runway.py promote` sets `published_hash` to it.
- New entries are created only by `bragdoc_public.py add-entry`, which applies the standing visibility default (`data/runway/config.json` → `visibility_default`).

`data/bragdoc/project_years.json`: `{source, updated, projects: {<project>: "YYYY"}, employer_default: {<employer>: "YYYY"}}` (user). Year rule order: an entry's `period` end year; else its staging items' year; for a staging item: `projects` (full project name, then the part before `:`), then `employer_default`, then an employer tenure that sits in one calendar year.

`data/bragdoc/questions.jsonl`: open questions from extraction/probing.
```json
{"id": "q-0001", "ref": "s-0001", "topic": "", "question": "", "status": "open|answered", "answer": ""}
```
- required: `id` (unique), `ref`, `question`, `status` (`open|answered`; answered needs `answer`).
- `ref`: a staging/entry id, an in-progress id (`ip-…`), or a file/area name (`skills.json`, `community`).
- `topic` optional: `conflict`, `confidentiality`, `links` (personal project/product/open source without links), `kind` (kind unknown), `in_progress`, `skills`, or free text.

`data/bragdoc/employment.json`: employment timeline (Experience section).
```json
[{"employer": "", "role": "", "start": "2025-03", "end": "2025-06", "source": "user", "context": ""}]
```
- required: `employer`, `role`, `start` (`YYYY-MM`), `source`. `end`: `YYYY-MM` or `null` (present), not before `start`.
- `context`: team size, company awards and other company-level facts, never personal achievements. No salaries, addresses or phone numbers. Internal: shown only in the internal bragDoc.
- `public_summary` (one sentence under the role) and `public_context` (list of lines), both optional, user-approved: the employment wording every resume and the public PDF use instead of `context`.

`data/bragdoc/education.json`
```json
[{"degree": "", "institution": "", "graduation": "2025-06", "cgpa": "8.0 / 10.0",
  "capstone": {"title": "", "staging_id": "s-0045", "entry_id": null}, "source": ""}]
```
- required: `degree`, `institution`, `graduation` (`YYYY-MM`), `source`. `capstone.staging_id`/`entry_id` must exist; renovate fills `entry_id`.

`data/bragdoc/skills.json`
```json
[{"skill": "PostgreSQL", "group": "Databases & Data", "level": null, "evidence_entry_ids": [], "evidence_staging_ids": ["s-0003"], "source": ""}]
```
- required: `skill`, `group`, `source`; unique per (skill, group). `level`: `null` or my own words ("proficient", "personally learned", "introductory"), never invented.
- evidence ids must exist. Staging ids are used until renovate creates entries, then swapped for entry ids.

`data/bragdoc/in_progress.jsonl`
```json
{"id": "ip-0001", "title": "", "kind": "study|certification|project", "status": "planned|in_progress|paused|done|dropped",
 "target_date": null, "notes": "", "source": ""}
```
- required: `id`, `title`, `kind`, `status`, `source`. `target_date`: `YYYY-MM[-DD]` or `null`. Promote to a staging item when done.
- `staging_id` (optional): the staging item this record tracks (an in-progress project from an extractor paste-back); must exist. Written by `bragdoc_stage.py add-in-progress`.

**Forbidden in `data/`** (validate.py): phone numbers and the personal email anywhere except `profile.json` → `contacts`; the policy's `always_banned` terms anywhere (the policy file that defines the banned terms is exempt).

`data/profile.json` → `names` **required**: `{"short": "", "public_full": "", "formal": ""}`, all non-empty (the old `name` key is rejected). `short`: internal output and everyday public prose. `public_full`: public, only where a full name is genuinely required (copyright line, author credit, a resume header). `formal`: resumes and formal applications only, exactly as stored. Renders and skills read these; nothing hard-codes a name. An all-caps design is CSS `text-transform: uppercase`, never changed text. Anywhere in `data/`, a wrong casing of `formal` (or of its leading token before `short`) is a validation error.

`data/profile.json` → `contacts`: each field `{value, channels}`; channels ⊆ `internal|resume|public` and must be allowed by the disclosure policy.
```json
"contacts": {"phone": {"value": "", "channels": ["internal", "resume"]},
             "email_personal": {"value": "", "channels": ["internal", "resume"]},   // resumes always use this
             "email_domain": {"value": "", "channels": ["internal", "public"]},       // public channel only
             "linkedin": {"value": "https://...", "channels": ["internal", "resume", "public"]}, "github": {}, "medium": {}, "website": {}}
```
- phone must be a phone number, emails valid, link fields `https://`. Phone and personal email can never list `public`.

`data/bragdoc/disclosure_policy.json`: the three disclosure channels, read by every render and every output built from the bragDoc.
- `channels.<internal|resume|public>`: `contacts` (allowed contact fields), `summary_field` (`resume_summary` / `public_summary`), `checks` (which lint checks apply), `cost_figures` (`relative_only` / `none`), `names` (`form`: which `profile.names` form the channel's renders show; `require: true` = a whole output must contain that form exactly; `block_formal: true` = the formal form is blocked).
- `terms`: regex lists `always_banned`, `current_employer_internal_names`, `vulnerability_classes`; `cost_patterns`: `absolute`, `cost_words`. Client/employer and project/app names are allowed on every channel; per-entry `public_constraints` still forbid security details tied to a named client.
- Per-entry `public_constraints` apply to the resume and public channels. Enforced by `scripts/disclosure_lint.py --channel <c> <file>` (exit 1 = blocked).

## RUNWAY

`data/runway/config.json` (user; the template ships with the site parts empty):
- **The site repo:** `site_repo` (a path, usually a sibling of this repo), `remote`, `main_branch`, `content_branch`, `data_path` (where the site reads its data, e.g. `src/content/bragdoc.json`), `pdf {file: "{short}_Resume.pdf", dir}` (the public resume the site serves).
- **Gates:** `build_cmd`, `check_cmd`, `test_cmd` (argv lists, run in the site repo; null skips one), `test_port` + `test_port_env` (the port the tests serve the fresh build on), `dist_dir` (the build output the voice lint reads), `synced_files` (files the build may rewrite, e.g. a hosting config whose CSP hashes follow the pages; committed with the data when they change).
- **Previews and production:** `preview_url` (a pattern with `{branch}`; null until the host builds branches), `code_slug_max` (preview hostnames cap a label at 63 characters), `site_url`, `live_test_cmd`, `deploy_hook_file` (gitignored; validate.py fails if tracked) + `deploy_hook_pattern` (regex a valid hook matches), `deploy_wait_s` / `deploy_poll_s` (how long and how often to wait for a production deploy, read from its `Last-Modified`), `daily_rebuild_utc` (HH:MM UTC of a scheduled rebuild, if any), `warm_paths` + `warm_asset_regex` (fetched once before the live tests), `medium {feed, poll_s, max_s}` (any RSS posts feed; await-post polling).
- **What the site shows:** `max_highlights` (3), `impact_bands` (rank → impact 1–3, covering 1–10 once), `fields [{id, name, color}]` (the site's design), `category_to_field`, `visibility_default {new_entries, current_employer, source}` (the standing default for new entries).
- **Extras:** `commit_trailer` (appended to `ship` and profile commits), `repos {owner, topic, max}` (if the site lists GitHub repos by topic), `profile {repo, remote, branch, readme, insert, top, per_project, intro[2]}` (a profile README's cockpit block; selection rules in the runway skill).

**Site data** (`data_path`, written by `runway.py publish`, linted on the public channel; the site reads exactly this):
```json
{"updated": "YYYY-MM-DD", "pdf": "/<short>_Resume.pdf",
 "fields": [{"id": "backend", "name": "Backend", "color": "#7aa2f7"}],
 "entries": [{"id": "<site_slug>", "field": "<fields[].id>", "impact": 1, "year": "YYYY", "metric": "≤ 40 chars",
              "title": "", "summary": "", "context": "", "did": "", "result": "", "stack": [""], "where": "Project · Employer",
              "highlight": true}]}
```
Public entries only. `highlight` appears on at most `max_highlights` entries (`state.showcase`), never the current employer's. Every string comes from the entry's `public_summary` and `site_card`; nothing is generated at publish.

`data/runway/state.json`: `showcase` (≤ 3 entry ids), `showcase_intents [{staging_id, replaces?, added, source}]`, `retired_slugs`, `email_verified` (true only on the user's word), `published_site_hash`, `last_publish {date, branch, commit, site_hash, entries: {id: payload_hash}, pushed}`, `last_promote {date, commit, entries}`, `last_rebuild {date, reason}`, `last_live_check {date, trigger, deployed (ISO or null when production did not redeploy in time), passed, failed}`, `rebuild_action_verified` (date a manual scheduled-rebuild run was seen to redeploy production), `ships {"code/<slug>": {date, summary, commit, pushed, status: "preview"|"promoted", promoted?, main_commit?}}` (site code branches made by `ship`). Written by `scripts/runway.py`.

## EXTROVERT

`data/extrovert/config.json` (written by `configure`; validated):
```json
{"source": "user", "updated": "YYYY-MM-DD", "news_fields": ["..."],
 "platforms": {"medium": "canonical", "linkedin": "native summary"},
 "voice_notes": [{"date": "YYYY-MM-DD", "lesson": "", "conversation": "<folder>"}],
 "ban": {"phrases": [], "engagement_bait": [], "emoji": true, "not_just_x_its_y": true, "em_dash_max": 0},
 "allowed": [], "defaults": {}, "exclusions": {}, "notes": []}
```
- `news_fields`: list of strings (search clusters). `platforms` keys: `medium|linkedin` only.
- `voice_notes`: lessons learned from editorial corrections, each with `lesson` and `date`. Starts empty.
- `ban` is enforced by `scripts/voice_lint.py <file.md>` (exit 1 on any violation).


`data/extrovert/profiles/<platform>/v<N>.md` (linkedin, medium, github): profile copy, `## <section>` per piece (linkedin: `headline`, `about`, `experience: <employer> · <role>` for every role in employment.json; medium: `bio`, `about`; github: `bio`). Written only by `profiles.py save` after its gates. `data/extrovert/profiles/state.json`: per platform `{latest, versions {N: {date, snapshot {top_impact {id: payload hash}, top5 [ids], job [[employer, role, start]], skill_groups [..]}}}, applied {version, date}}` plus `last_reminded`. Config: `data/extrovert/config.json` → `profiles {limits {linkedin {headline, about, experience}, medium {bio, about}, github {bio}, checked, sources, note}, policy {throttle_days, exempt, top_impact_min, triggers {trigger: [platform.piece]}, source}, current_employer_rule, role_attribution {source, "<employer> · <role>": [entry ids]}}` (the user's answers on which role an entry belongs to when its dates don't say).

`data/extrovert/ideas.jsonl`: idea backlog, an **append-only event log** (never rewrite past lines). Current state is derived by `scripts/ideas.py`.
```json
{"ts": "2026-10-08T09:00:00", "idea_id": "i-0001", "event": "add",
 "data": {"raw": "verbatim text", "gist": "", "tags": ["postgres", "security"], "context": "",
          "links": [{"url": "https://...", "title": "", "summary": "", "fetched": true}], "sensitive": false}}
{"ts": "...", "idea_id": "i-0001", "event": "edit", "data": {"set": {"gist": ""}, "note": ""}}
{"ts": "...", "idea_id": "i-0001", "event": "status", "data": {"from": "new", "to": "developing", "conversation": "<folder>", "urls": [], "note": ""}}
{"ts": "...", "idea_id": "i-0004", "event": "merge", "data": {"merged_from": ["i-0002", "i-0003"], "raw": "...", "gist": "", "tags": [], "links": []}}
{"ts": "...", "idea_id": "i-0002", "event": "status", "data": {"from": "new", "to": "merged", "merged_into": "i-0004"}}
```
- `idea_id`: `i-NNNN`. `event`: `add|edit|status|merge`. `ts` (ISO 8601) never goes backwards.
- `add`/`merge` create an idea: `raw` (verbatim, never rewritten) and `gist` required, `tags` 2–5, links `https` with `fetched` (fetched links need `title` + `summary`). `merge` lists 2+ existing ideas in `merged_from`.
- `edit.set` may change `raw` (only to text the user supplied), `gist`, `tags`, `context`, `links`, `sensitive`; each edit is a new version.
- `status.to`: `new|developing|posted|parked|dropped|merged`; `merged` only via merge and needs `merged_into` pointing at a real idea; `urls` are https.
- `sensitive: true` (or naming the current employer) = captured privately, flagged before use in suggest/start.

`data/extrovert/conversations/<YYYYMMDD-HHMM>-<slug>/`
- `meta.json`: `{"name": "", "slug": "", "created": "", "renamed_from": [], "links": [], "humor": false, "ideas": [], "status": "open|edited|posted", "published": [], "related_entries": []}` (`humor`: asked per post at `start`)
- `transcript.md`: verbatim, append-only during Conversation
- `editorial-v<N>.html` and `editorial-v<N>.md`
- `post-v<N>-<platform>.md`: the post body, then a `<!-- notes -->` line, then non-post notes (media suggestion, tags, canonical advice). `post_stats.py` counts only the body.

`meta.json` publication fields (validated for every conversation folder):
```json
"published": [
  {"platform": "medium", "url": "https://...", "title": "", "subtitle": "",
   "published_date": "2026-10-07", "read_time_min": 4, "word_count": 812, "tags": [],
   "cover_image_suggestion": "", "excerpt": "", "canonical": true}
],
"related_entries": ["e-0001"]
```
- `status` **required**: `open|edited|posted`. If `posted`, `published` must be non-empty.
- each `published` item **required**: `platform` (`medium|linkedin`; GitHub is not a post target), `url` (`https://`), `title`, `published_date` (`YYYY-MM-DD`), `read_time_min` and `word_count` (integers from `post_stats.py`, never estimated), `canonical` (boolean). Optional: `subtitle`, `tags`, `cover_image_suggestion`, `excerpt` (≤ 40 words).
- exactly one `canonical: true` item per conversation (the platform hosting the full piece). New platforms are appended, never overwritten.
- `related_entries` optional: bragDoc entry ids; each must exist in `entries.jsonl`.

## FOURTHWALL

`data/fourthwall/journal.jsonl`: private, append-only.
```json
{"ts": "2026-10-06T09:00:00", "kind": "decision|lesson|milestone|bug", "title": "", "text": "", "tags": [],
 "commit": "1e10491", "source": "git|ideation-chat|user", "tier": "T0", "date_approx": true}
```
- required: `ts` (ISO 8601), `kind`, `title`, `text`. `tags` list. `commit` (git hash) when a commit confirms it; `date_approx: true` when no commit does. `tier` T0–T3 if present.

`data/fourthwall/state.json`: `last_changelog_commit`, `last_export_hash`, `last_export_clean`, `approved_export_hash`, `published_versions: [{version: "X.Y.Z", date, export_hash, commit}]`, `ip_policy_checked` (bool, false until the user confirms), `commit_email` (GitHub noreply address only), `staging_dir`, `clone_dir` (both outside the repo), `remote`.

`data/fourthwall/manifest.json`: the allowlist for the public copy.
```json
{"rules": {"excluded_prefixes": ["data/", "raw/"], "excluded_substrings": ["..."], "excluded_names": ["profile.json"]},
 "files": [{"source": "scripts/chassis.py", "target": "scripts/chassis.py", "transform": "copy"},
           {"source": ".claude/skills/chassis/SKILL.md", "target": ".claude/skills/chassis/SKILL.md", "transform": "generalize",
            "generalized": "fourthwall/generalized/_claude/skills/chassis/SKILL.md", "source_hash": "<sha256 of the source>"},
           {"source": "fourthwall/templates/LICENSE", "target": "LICENSE", "transform": "template"}]}
```
- `transform`: `copy` (zero personal content, proven by the leak checks), `generalize` (reviewed rewrite under `fourthwall/generalized/`, with `.claude/` stored as `_claude/` so the copies never load as skills; `source_hash` must match the current source or export blocks as stale), `template` (under `fourthwall/templates/`).
- Excluded sources are rejected by validate.py and export; `data/` targets only from templates; targets unique and relative.

`data/fourthwall/denylist.json`: `terms` (case-insensitive whole word), `exact_terms` (exact-case whole word), `regex`, `derive` (profile, employers, projects, policy), `derive_ignore`, `author_line_exemptions [{file, line_regex}]`, `lint_exempt [{path, checks}]`. Contact data is derived from `profile.json`, never stored here.

`data/fourthwall/case_study.md`: public-linted draft for a later website showcase. `fourthwall/CHANGELOG.md`, `fourthwall/README.md`: generated public files that ship in the public copy.
