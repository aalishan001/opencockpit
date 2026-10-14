---
name: runway
description: Ships the bragDoc's public channel to the user's own website (a static site in its own git repo, next to cockpit). Commands - publish, promote, ship, showcase, status, rebuild, live-check, profile, release current-employer; also waits for a new post to reach the site. Use when the user talks about the website, the portfolio, publishing or previewing site content, case studies on the homepage, the site's resume PDF, or deploying.
---

# RUNWAY

**No command given** (bare `/runway`): read `COMMANDS.md` and print its `## RUNWAY` section verbatim (heading through the line before the next `## `) in a fenced code block. Nothing else, no commit.

RUNWAY moves the bragDoc's **public channel** into the site repo, one way only. `python scripts/runway.py` does all of it: building the data, every gate, git in the site repo, hashes. RUNWAY generates nothing: renovate already wrote every summary, card, slug and year (see the bragdoc skill). If anything is missing or out of date, publish blocks and names it; fix it through renovate, never at publish time.

- **Config:** `data/runway/config.json` (site path, remote, branches, build/check/test commands, preview-URL pattern, deploy hook, field map, impact bands, PDF name, the **standing visibility default**; every key is in `scripts/schemas.md`).
- **State:** `data/runway/state.json` (showcase, showcase intents, retired slugs, email confirmation, last publish/promote, shipped code branches).
- **The site:** any static site that reads one JSON file (the site data contract in `scripts/schemas.md`), in its own repo at `config.site_repo` (a sibling of cockpit, never inside it), hosted anywhere that deploys `main` to production and gives other branches a preview URL.
- **Its git:** branch `main` plus a `content` branch for previews, the same identity rules as cockpit. **Never force push.**
- **What publish writes:** only `config.data_path` and the public resume PDF. **Any other site file** (components, styles, tests, workflows) changes only on my explicit instruction: make the change in the site working tree on `main`, uncommitted, then **ship** it (below). Never commit site code straight to `main`.

## What reaches the site
| Site field | From |
|---|---|
| entries | entries with `visibility: "public"` only |
| `id` | `site_slug`: cut once from the public headline, never changed (deep links `/bragdoc#<id>` must never break); a retired slug is never reused |
| `field` | `category` → `config.category_to_field` |
| `impact` | `rank_score` → `config.impact_bands` (e.g. 8–10 → 3, 5–7 → 2, 1–4 → 1) |
| `year` | entry `year` (period, else `data/bragdoc/project_years.json`, else a single-year tenure) |
| `title` / `summary` / `stack` | `public_summary` headline / summary / stack |
| `metric` / `context` / `did` / `result` / `where` | `site_card` |
| `highlight` | `state.showcase` (max 3; public; never the current employer's), with showcase intents applied |
| `pdf` | the full public bragDoc (`render.py public-resume`, header `names.public_full`), served at `/<pdf.file>` |

## Gates (every publish; any failure writes nothing)
- **Contract check:** field ids exist, impact 1–3, ≤ 3 highlights, unique slug ids, every required string present.
- **Disclosure:** `disclosure_lint --channel public` on every string, per entry (with the entry's employer: relative cost figures only from past employers, clients or personal work; never the current employer; absolute amounts never), and again as one document.
- **The PDF:** its HTML, its extracted text **and metadata** pass the public channel, plus the local-path and username patterns (fourthwall deny list `regex` + `local_identity`, any `file://`).
- **The site's build** (`config.build_cmd`): files it rewrites (`config.synced_files`, e.g. a hosting config whose CSP hashes follow the pages) are committed with the data.
- **The site's copy:** `voice_lint.py --site <dist>` on the fresh build (the voice rules' em-dash limit on titles, meta and link-preview text, visible text, alt and aria-label; text marked `data-source`, from another platform, only warns).
- **The site's check and tests:** `config.check_cmd`, then `config.test_cmd` against the fresh build served on `test_port` (for example smoke and accessibility tests).

## Commands
| Command | Does |
|---|---|
| `/runway publish` | `runway.py publish`: gates → `content` branch (merged up from `main`) → write data + PDF → build + check + tests → commit → push → print the preview URL. Nothing is live. Show me the URL and wait |
| `/runway promote` | Only after I approve the preview: `runway.py promote` merges `content` → `main`, pushes, and sets `published_hash` (from `bragdoc_public.py payload-hash`) for every published entry; entries made private since get `published_hash: null`. Refuses if the bragDoc changed after the publish. Then it waits for the production deploy and runs the live tests (see "After every promote and rebuild") |
| `/runway ship "<summary>"` | `runway.py ship "<summary>" [--slug <slug>]`: for site code changes I asked for, sitting uncommitted on `main`. Refuses content files (they go through publish). Runs the gates on main + the changes first (nothing is created if one fails), then creates `code/<slug>` (≤ `config.code_slug_max` characters, so the preview hostname works), commits (with `config.commit_trailer`), pushes, returns the site repo to clean `main`, records `state.ships`, and prints the preview URL. Show me the URL and wait |
| `/runway promote code/<slug>` | Only after I approve that preview: `runway.py promote code/<slug>`: if `main` moved since the ship, merges it into the branch and runs the gates again; then fast-forwards `main`, pushes, waits for the production deploy and runs the live tests |
| `/runway showcase <ids>` | `runway.py showcase <entry_ids>` (max 3; public; never current-employer). `runway.py showcase intent <staging_id> --replaces <entry_id>`: once that staging item is probed, renovated and public, its entry takes the slot at the next publish |
| `/runway status` | `runway.py status`: live vs pending (`bragdoc_public.py pending`), gate problems, showcase intents, and launch blockers (the site email not set or not yet confirmed, the PDF not on `main`, no preview URL). Then **Rebuilds and production**: the local deploy hook (present / valid / missing, never shown), whether a scheduled rebuild is verified, when production was last built, the posts feed's health, and the last live check |
| `/runway rebuild` | `runway.py rebuild`: POSTs the deploy hook from `config.deploy_hook_file` (gitignored; validate.py fails if it's ever tracked), then waits for the production deploy and runs the live tests. If the file doesn't exist (e.g. a cloud session), tell me to trigger the site repo's scheduled-rebuild workflow by hand |
| Post confirmed (EXTROVERT) | `runway.py await-post <post-url>`, run in the background: polls the posts feed (`config.medium.feed`) until that post is in it, then rebuilds. On timeout it rebuilds anyway and says the scheduled rebuild will catch a slow feed. Report the result when it finishes |
| "verify the daily rebuild" | `runway.py verify-action` in the background, then tell me to run the site repo's rebuild workflow by hand: a production redeploy proves its secret works. Records `rebuild_action_verified` |
| `/runway profile` | `runway.py profile`: print the cockpit block with its gates and whether the profile README is current; `runway.py profile --write` updates it (normally done by promote) |
| `/runway live-check` | `runway.py live-check`: the live tests against production now, no waiting |
| "release current-employer entries" | My one instruction: `runway.py release current-employer` makes every private current-employer entry public, then publishes (content branch + preview only) |
| "the test email arrived" | `runway.py confirm email` (the email launch blocker clears only on my word) |

After every command that changes files: validate, commit `runway: <command>: <summary>` in cockpit, push.

## A profile README (optional, `config.profile`)
If you keep a profile README (for example a GitHub profile repo), cockpit can own one block of it: the text between `<!-- COCKPIT:START -->` and `<!-- COCKPIT:END -->`. Everything else stays yours, byte for byte (line endings too), and any other generated block (such as a latest-posts list written by that repo's own workflow) is never touched. Never edit outside the markers without my explicit instruction.
- **The block** (`runway.py profile` prints it): the two-line intro from `config.profile.intro`; **Selected work**: the top `config.profile.top` (5) public entries, each its public headline linked to `<site_url>/bragdoc#<slug>`, plus the metric only when the headline lacks its numbers; then links (website, Medium, LinkedIn) from `profile.json` contacts on the public channel.
- **Selection:** highlighted entries first; then impact; then recency (year); then `rank_score`; a metric without a number only breaks the remaining ties; at most `config.profile.per_project` (2) per project (the first part of the card's `where`). Impact comes from `rank_score` (my 1–10 assessment at renovate, never re-rated without asking) through `config.impact_bands`.
- **Gates:** each entry's title and metric pass `disclosure_lint --channel public` with that entry as context, the rest as one document; the visible text passes the EXTROVERT voice lint. Any failure writes nothing.
- **Publishing:** every promote (content or code) runs `runway.py profile --write`: `git pull --rebase`, replace the block, commit, push; nothing happens when the block is unchanged; a failure is reported and never undoes the site promote.

## After every promote and rebuild
`runway.py` reads production's `Last-Modified` before the trigger, waits (`config.deploy_wait_s`, 15 min by default) until production serves a newer deployment, warms the cache (`config.warm_paths`), then runs `config.live_test_cmd` against production and records the result in `state.last_live_check`. Report: when it deployed, passed/failed, and any failing test. If production doesn't redeploy in time, say so: a failed build usually keeps the previous version live, so check the deployment on the host. These waits are long: run promote, rebuild and await-post in the background and report when they finish. `--no-wait` skips the wait and the tests.

## The deploy hook is a secret
Never print, log, echo or paste the hook URL (not even part of it), and never put it in a commit, a message or an error. `runway.py` validates it against `config.deploy_hook_pattern` and reports only present / valid / missing; request failures report only the HTTP status or the error type. A copy for a scheduled rebuild lives only in the site repo's CI secrets; that workflow should run with no extra permissions, fail with a clear error if the secret is missing, and never print it.

## Standing visibility default
New entries get `config.visibility_default` (the template: private; for example "public unless they belong to the current employer"). It is the user's own rule, applied once, by `bragdoc_public.py add-entry` at renovate. The current employer is always the open role in `employment.json`: a job change re-tiers the cost and highlight rules automatically but never flips an existing entry's visibility.

## After renovate (automatic)
Renovate ends with `runway.py publish --if-pending`: when any public payload (or the site data) changed, it publishes to the `content` branch and prints the preview URL; otherwise it does nothing. **Promote is never automatic**: it is the one human gate before anything goes live.

## Launch (first run)
1. `runway.py preview` writes the data + PDF into the site working tree (uncommitted), builds and checks. Show me `runway.py table` and the PDF; wait for my OK.
2. `runway.py publish --initial`: the very first commit, straight onto the empty repo's `main`, push. Stop.
3. After I approve: `runway.py promote --initial` (marks main as published). I connect the repo to a host and point the domain at it; set `config.preview_url` once the host builds branches.
