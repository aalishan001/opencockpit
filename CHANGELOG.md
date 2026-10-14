# Changelog

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
