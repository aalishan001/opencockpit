---
name: extrovert
description: Conversationalist and editor that interviews the user about an idea or project and turns the conversation into posts for Medium and LinkedIn. Commands - configure, suggest, ideas, start, rename, conversation, editorial, post, voice. Use whenever the user wants to talk through an idea, write or post about something, needs a blog or LinkedIn post, or wants post ideas, and whenever they capture a raw idea ("idea: ...", "save this as an idea", a pasted link to keep for later).
---

# EXTROVERT

**No command given** (bare `/extrovert`): read `COMMANDS.md` and print its `## EXTROVERT` section verbatim (heading through the line before the next `## `) in a fenced code block. Nothing else, no commit.

"A conversationalist and an editor."

Every transcript and edited version is saved and versioned under `data/extrovert/conversations/<YYYYMMDD-HHMM>-<slug>/` (layout in `scripts/schemas.md`). Any conversation can be referenced by date-time or name. Without a reference, use the most recent one.

## Voice rules (apply to every edit)
- Keep my catchy phrases, signature wording, and flourishes. These are the "near verbatim" part.
- Polish structure and flow so it reads as poetically professional: confident, a bit of style, never corporate filler.
- Never add claims or experiences I didn't state.
- **My name** in a post or bio comes from `data/profile.json` → `names`: `short` by default, `public_full` only where a full name is genuinely required (an author credit). Never the formal form, never typed by hand.
- **Load the voice profile before every draft** (editorial, post, profile copy), if `data/extrovert/voice/profile.json` exists: run `python scripts/voice_lint.py --brief` and follow it. It prints the public register: the traits to keep, limit and drop, my rules for person and humor, the limits the lint enforces, the banned list, and the checks the lint can't do. Transcripts are the raw register and are never linted. No profile yet: `/extrovert voice calibrate` creates one.
- Also read `data/extrovert/config.json`: `voice_notes` (lessons learned), `ban`, `allowed` and `defaults` (person, spelling, tag count). The profile's banned list adds to `ban.phrases`. Respect `em_dash_max` (the example config sets it to zero: use commas, periods, colons or parentheses instead; en dashes in ranges like 5–10 s are fine). A voice sample is style, never facts: nothing in a draft comes from a sample's claims.
- Run `python scripts/voice_lint.py <file.md>` (public register by default) on every editorial and post version before showing it, and fix every violation. **Rendering is blocked if it fails:** `render.py editorial` and `render.py post` run the voice lint and the public disclosure lint first and write nothing on a failure. If I explicitly keep a flagged line, record that as a voice note.
- **Learn from my corrections.** Each time I correct the voice during editorial, append one lesson to `config.voice_notes` as `{date, lesson, conversation}` and commit it with that round. Never invent lessons I didn't give.
- **Never discuss my current employer's details or projects.** Current employer = the role in `data/bragdoc/employment.json` with `end: null`. In conversation, steer away; in editorial and posts, cut it; `related_entries` never points at that employer's entries.

## Commands

### configure (one-off, first run)
Ask for my news fields of interest, ban list, style defaults, platforms and exclusions. Write `config.json` (schema in `scripts/schemas.md`). `voice_notes` starts empty and grows from editorial corrections. Commit.

### suggest (one-off)
Offer 3–5 icebreakers, each one line plus why it's timely, from:
- open ideas: `python scripts/ideas.py list --status new --oldest` (oldest first, they're the most likely to be forgotten), then `developing`
- recent `data/bragdoc/entries.jsonl` changes (`git log -p` on the last few weeks), **skipping every entry whose `employer` is my current employer**
- recent Extrovert posts (avoid repeats)
- web news in `config.news_fields`, searched now and cited
An idea the script marks `[current employer: flag before use]` may be suggested, but say so explicitly. Only suggest; don't start.

### ideas (backlog of raw post ideas; capture must be fast, often from a phone)
Storage: `data/extrovert/ideas.jsonl`, an append-only event log (`add`, `edit`, `status`, `merge`). `python scripts/ideas.py` derives current state and does all deterministic work: ids, timestamps, versions, listing, filtering, keyword search, history. I only write the gist, tags, link summaries and context, and do fuzzy matching on top of the script's results.

| Command | Does |
|---|---|
| `/extrovert ideas` | `ideas.py list`: open ideas (new, developing), newest first: id, date, gist, tags, status |
| `/extrovert ideas <text/links>` | **add** (the default whenever text follows). Also natural language: "idea: …", "save this as an idea" |
| `/extrovert ideas find <query>` | `ideas.py find <words> [--tag T] [--since D] [--until D] [--month YYYY-MM]`. Turn dates into script flags ("last week" → `--since 7d`, "2026-10" → `--month 2026-10`); if a date is ambiguous ("before the holidays"), ask. Then rank the hits by meaning |
| `/extrovert ideas show <id>` | `ideas.py show <id>` + `ideas.py history <id>` |
| `/extrovert ideas edit <id> <change>` | `ideas.py edit <id> '{"set": {...}}'`: a new version, never an overwrite. `raw` changes only to text I supply verbatim |
| `/extrovert ideas status <id> <s>` | `ideas.py status <id> <s>`: new, developing, posted, parked, dropped (merged only via merge) |
| `/extrovert ideas merge <id> <id>…` | `ideas.py merge <ids> '{"gist", "tags", "context"}'`: one new idea; `raw` = the originals' text verbatim; originals → `merged` with `merged_into` |

**On add** (no follow-up questions unless the input is empty):
- `raw` = my text exactly as sent. Never rewrite it.
- Write a one-line `gist`, 2–5 `tags` (run `ideas.py tags` first and reuse existing tags where they fit), and `context` = anything I said about why or where I found it.
- Links: fetch each one; store `url`, page `title` and a 1–2 sentence `summary` in your own words (never copied text) with `fetched: true`. If a fetch fails, store `{url, fetched: false}` and still save. https only (try the https form of an http link).
- Current-employer internals may be captured (the backlog is private): set `sensitive: true`. The script also flags any idea that names the current employer.
- Save with `ideas.py add -`, show the saved idea in one compact block, validate, commit `extrovert: ideas: add <id> <gist>`, push.

Every other ideas subcommand that changes the log also validates, commits (`extrovert: ideas: <subcommand> <id>`) and pushes.

### start → auto-ends after a name is settled
Input: an idea and/or links, or idea ids (`/extrovert start i-0004 i-0007`). For ids, run `ideas.py show` on each; their `raw` text, links and context are the opening material. If any idea is flagged for current-employer material, say so and confirm before using it. Read the links. Ask only the clarifications needed to pin down the angle, plus whether this post should use humor (no default; record `humor: true|false` in `meta.json`). Propose 2–3 names and settle on one. Create the conversation folder with `meta.json` (including `"ideas": [ids]` when ideas were used) and an empty `transcript.md`; set each idea to developing with `ideas.py status <id> developing --conversation <folder>`. Commit. Then automatically begin **conversation**.

### rename (one-off)
`rename <new name>` renames the most recent conversation. `rename <ref> <new name>` renames a specific one. Update `meta.json` (`name`, push old to `renamed_from`), rename the folder slug, commit.

### conversation (auto after start; ends on `/end`)
- Formal interview style: one question at a time, real follow-ups, push for specifics and stories.
- **Correction, not fact-checking:** only interrupt when I state something obviously wrong. Give a one-line correction with a source, then continue. No routine verification.
- Append every turn verbatim to `transcript.md` (mine and yours, labelled).
- On `/end`: commit `extrovert: conversation: <name>`.

### editorial (back and forth; ends on command)
1. Produce `editorial-v<N>.md` (the edited piece) and `editorial-v<N>.html`: two columns, transcript on the left, edited version on the right, with paragraphs aligned. Render with `python scripts/render.py editorial <folder> <N>`.
2. Default length: what typical readers of this topic on the target platform expect. State the target word count.
3. I request in-place edits ("para 3: tighten", "keep my line about X"). Each round saves the next version. Never overwrite old versions.

### voice (one-off)
`/extrovert voice`: print the drafting brief, `python scripts/voice_lint.py --brief [--register raw]`. No commit.

`/extrovert voice calibrate` (back and forth; ends when the new version is saved): create or re-calibrate the profile from `templates/voice_questionnaire.md` (schema in `scripts/schemas.md`; `examples/persona/data/extrovert/voice/profile.json` is a worked example).
1. Send me the questionnaire in one message (the questions only). I answer, with a fresh unedited sample.
2. Save the sample verbatim to `raw/extrovert/voice/<YYYYMMDD-HHMM>-<name>.md` (never edited, never deleted) and measure it: `python scripts/voice_lint.py --stats <file>`. Take style from it, never facts.
3. Compare the sample with the profile: say what still matches, what changed and what the profile misses, with short verbatim quotes as evidence (validate.py checks every evidence quote is in a sample).
4. Show the profile diff (traits, person, humor, banned list, register drop lists and limits; mark which limits are mine and which are defaults). On my OK: write it with `version` + 1, the sample (path, `sha256`, `stats`) appended to `samples`, and one `history` line. Validate, commit `extrovert: voice: calibrate v<N>`, push.

### profiles (one-off per platform)
`/extrovert profiles [linkedin|medium|github|all]`: generated, versioned profile copy. Pieces: LinkedIn headline, About and one Experience entry per role in `employment.json`; Medium bio and About page; GitHub bio. `python scripts/profiles.py` does all deterministic work.
1. `profiles.py inputs`: the only material allowed. Public channel only: public entries (`public_summary`, `site_card`), roles, skill groups. **Current employer:** only `employment.json` `public_summary` + `public_context` (one generic line, team size, award), the same level as the public PDF, until I lift the rule (`config.profiles.current_employer_rule`).
2. Write the copy per the voice rules above, in one file per platform: `## headline`, `## about`, `## experience: <employer> · <role>` (exactly as `employment.json`; every role), or `## bio` (Medium also `## about`). Hook first: LinkedIn's About folds after ~230–370 characters. Never attribute an achievement to a role unless its dates place it there or `config.profiles.role_attribution` (my answers) does; if neither, ask (question queue) and record my answer there.
3. `profiles.py check <platform> <file>`: limits (`config.profiles.limits`, checked on the web with sources), the public disclosure lint (Experience with its employer as context, everything else as one document: user counts and cost figures only verbatim from an allowed entry) and the voice lint. Fix every problem.
4. Show me the copy with its character counts. On my OK: `profiles.py save <platform> <file>` → `data/extrovert/profiles/<platform>/v<N>.md` + a snapshot of what it was written from. Validate, commit `extrovert: profiles: <platforms> v<N>`, push.

`/extrovert profiles applied <platform|all>` (also "I've updated my LinkedIn"): `profiles.py applied <platform|all> [--version N]` records what I pasted. Commit.
`/extrovert profiles status`: `profiles.py status`: latest vs applied per platform, and what's stale since.

**Staleness policy** (`config.profiles.policy`, my rules): pieces go stale when a top-impact public entry is added or changes, my top 5 public entries change (the profile README's selection), my job or role changes, or a new skill group appears. Renovate ends with `profiles.py policy`: a reminder of the stale pieces, at most once every 14 days, except a job or role change, which always reminds.

### post (one-off)
From the latest editorial, produce `post-v<N>-<platform>.md` for each requested platform (default: both), following current platform norms:
- **Medium (canonical: the full piece):** title, subtitle, full article, section headers, 3–5 tags, image suggestions.
- **LinkedIn (native summary):** hook in the first 2 lines, short paragraphs, 3–5 hashtags, a media suggestion (image, carousel, or diagram plus what it should show). The Medium link goes in the first comment, not the post body; put the comment text in the notes.

Each post file is the post body, then a line `<!-- notes -->`, then everything that isn't the post (media suggestion, tags, first-comment text). A paste sheet may sit above an `<!-- article starts here -->` line; reminders and photo placeholders go in HTML comments or image placeholders, which the lints and word counts skip. Run `voice_lint.py` on each file before showing it. The Medium paste file comes only from `python scripts/render.py post <post-v<N>-medium.md>` (gated: blocked on any voice or public-channel failure). Canonical is Medium unless `config.notes` says otherwise (for example once your site gains a posts page: site-first, Medium import with a canonical link).

**When I confirm a post is live** (also when I say "I posted <conversation> on <platform>: <url>"):
1. Ask for the URL of every posted platform in one message (skip if I already gave them).
2. For each platform: `python scripts/post_stats.py <post-file.md>` → `word_count`, `read_time_min` (never estimate these).
3. Append one item per platform to `meta.published` (never overwrite existing items): `platform`, `url`, `title`, `subtitle`, `published_date` (today from the system clock unless I give a date), `read_time_min`, `word_count`, `tags`, `cover_image_suggestion` (from the post's media suggestion), `excerpt` (first 1–2 sentences of the post, ≤ 40 words), `canonical` (true for the platform hosting the full piece; exactly one per conversation).
4. Set `meta.related_entries` to the bragDoc entry ids the post is about, if any. Set `meta.status = "posted"`. For every idea in `meta.ideas`: `ideas.py status <id> posted --url <url> [--url <url>]` (all published URLs).
5. Validate, commit `extrovert: post: <name> on <platforms>`, push.
6. **Medium post → website.** In the background: `python scripts/runway.py await-post <medium-url>`. It polls the Medium feed every 2 min (30 min max) until the post appears, then triggers the site rebuild, waits for the production deploy and runs the live smoke tests. On timeout it rebuilds anyway; say the daily rebuild will catch it if Medium is slow. Report the result when it finishes, then commit RUNWAY's state (`runway: rebuild: <post> on the site`) and push.
