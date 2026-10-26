# Changelog

## v0.2.6 (2026-10-26)

- EXTROVERT repo metadata: /extrovert repos suggests a paste-ready GitHub description and topics for each of your public repos (the site topic included when a repo belongs on your site), PyPI keywords and classifiers for packages, a release tag and version scheme, and a one-line note for the package's own session. scripts/repos.py gathers the inputs from the public GitHub and PyPI APIs, checks GitHub's topic rules and PyPI's official classifier list, versions every suggestion and flags a repo again after a new tag, release, PyPI version or a published post that names it.
- RUNWAY previews exist only while something waits for approval: every promote deletes the branch it promoted, the next publish recreates the content branch from main, and runway.py prune deletes any other branch already merged into main while listing the rest with their commits.
- Git rules: deleting a site branch fully merged into main is the one exception to never deleting branches.

## v0.2.5 (2026-10-26)

- EXTROVERT voice profile: a versioned record of how you write (traits to keep, limit or drop, a raw and a public register, your banned phrases and patterns), stored next to the config and validated. /extrovert voice prints it as a drafting brief before every draft; /extrovert voice calibrate updates it from a questionnaire (templates/voice_questionnaire.md) and a fresh writing sample, measured by script. The persona example ships one.
- Voice lint: on top of the ban list, the public register now caps capitals for emphasis, theatrical one-line paragraphs, question-and-answer pairs, exclamation marks, hashtags and habitual groups of three, and flags runs of same-length sentences, spaced-hyphen connectors and anything in the register's drop list (slang, shorthand, typography). --stats measures a text's rhythm for calibration.
- Editorials and the new Medium paste file (render.py post) render only when the draft passes the voice lint and the public disclosure lint; a failure writes nothing. A paste sheet can sit above an 'article starts here' line, and the lints and word counts skip it.

## v0.2.4 (2026-10-15)

- RUNWAY: verify-action --scheduled now prints the scheduled and deploy times instead of a function name.

## v0.2.3 (2026-10-15)

- RUNWAY: verify-action --scheduled proves the scheduled rebuild's deploy-hook secret with no click: it waits for the next scheduled run, then checks that production was redeployed after it (90-minute grace) and runs the live tests.

## v0.2.2 (2026-10-15)

- The brag document is now written bragDoc everywhere in the docs, skills and rendered titles; commands, paths and file names keep their lowercase form (/bragdoc, data/bragdoc).
- EXTROVERT profiles: the Medium About page is a piece of its own next to the short bio, with its own character cap (Medium publishes none) and the same staleness triggers.

## v0.2.1 (2026-10-15)

- bragDoc: a probed item can record the parts its owner answered they have no data for (probe.waived: scale, impact, stack or problem, with the owner as source and a reason). Validation exempts exactly those parts, so an honest "don't know" renovates without anyone filling the gap with a guessed number.

## v0.2.0 (2026-10-14)

- RUNWAY, a new domain: ships the bragDoc's public channel to a site repo of your own as one JSON file (a documented data contract) plus a public resume PDF. Every publish is gated by a contract check, the public disclosure lint per entry and as one document, and the site's own build, check and tests.
- RUNWAY previews: content goes to a preview branch and reaches main only through promote, after you approve the preview. Site code changes get their own preview branch through the same gates.
- RUNWAY production checks: after a promote or a rebuild it waits until production serves the new build, warms the cache and runs the site's live tests. The deploy hook is validated against a pattern and never printed.
- RUNWAY posts: a new post's URL is polled in the posts feed, then the site rebuilds, so the homepage lists it without a manual deploy.
- RUNWAY profile README: cockpit can own one marked block of a profile README with your top public entries (highlighted first, then impact and recency, at most two per project), linted, with everything outside the markers kept byte for byte.
- bragDoc site fields: site cards, stable slugs that are never reused, years from a period or a project map, and a standing visibility default applied once when renovate creates an entry.
- bragDoc public rules: relative cost changes and usage numbers are allowed only for past roles, clients and personal work; never for the current role; absolute amounts never.
- bragDoc employment: a public one-line summary per role, kept apart from the internal context notes.
- bragDoc extractor: read-only prompts that pull a session, an incident, a project or a multi-month period out of an AI pair session, with evidence tags on every number, an overlap check against existing items and incident durations computed by script.
- EXTROVERT profiles: versioned profile copy (headline, about, one entry per role, short bios) checked against platform limits, the public lint and the voice lint, with a staleness policy that reminds at most every two weeks.
- Voice lint for websites: it reads a built site's titles, meta, link-preview text, visible text and alt text, so the em-dash rule holds on the site too; text pulled from other platforms only warns.
- FOURTHWALL: the README now renders whole in a sanitized Markdown popup (no raw HTML, no mermaid), and every export fails on an em dash anywhere in the public copy.

## v0.1.0 (2026-10-08)

- Scaffolded the command system: a router in CLAUDE.md, one skill per domain, a folder contract (inbox, raw, data, templates, out) and global rules such as no invented facts, a source on every record, and scripts for all exact work.
- Made every script run on Windows: commands call `python`, and console output is forced to UTF-8.
- Handed git to the assistant: main only, a pull when a session starts, a commit and push after every command, and permission rules that block force pushes, hard resets and global config changes.
- Added a help system: COMMANDS.md is the single source of command names, `/cockpit` prints it, and a bare domain command prints that domain's section.
- Added `/end`, which closes whichever interactive command is running and commits what it produced.
- Added image ingestion: EXIF rotation, a 1600 px long edge, JPEG quality 80, location metadata stripped, plus an optional second inbox for phone uploads.
- CHASSIS: owner's manual setup into an itemized maintenance table, with time-based jobs kept apart from kilometer-based ones and every deadline computed by script.
- bragDoc: a dump, probe and renovate pipeline with source trust tiers, tracked conflicts between sources, a question queue, and a completeness standard the validator enforces.
- bragDoc public layer: entry kinds, links, visibility, public constraints and generated summaries stamped with source hashes, so outdated summaries are found automatically.
- Disclosure channels: internal, resume and public outputs, each checked against a policy file; a render that fails its check writes nothing.
- EXTROVERT: voice settings with a ban list and a voice linter (zero em dashes), Medium as the canonical home and a LinkedIn summary.
- EXTROVERT ideas backlog: an append-only event log with fast capture, search by text, tag and date, versioned edits, status changes and merges.
- FOURTHWALL: a private build journal, this changelog, and an allowlist export that generates this public copy and runs five leak checks before anything ships.
