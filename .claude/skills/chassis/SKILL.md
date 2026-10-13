---
name: chassis
description: Example maintenance tracker for a vehicle (bike, scooter, car): owner's manual setup, service slip images, odometer readings, what's due, service history, maintenance intervals. Commands - configure-manual, configure-history, odom, deadlines, service, history, manual. Trigger even on bare inputs like "odo 15230" or a photo of a service slip.
---

# CHASSIS

**No command given** (bare `/chassis`): read `COMMANDS.md` and print its `## CHASSIS` section verbatim (heading through the line before the next `## `) in a fenced code block. Nothing else, no commit.

A worked example of a domain: maintenance tracking on **kilometres** (months-or-km "whichever earlier" → keep the km only, by design). Exception: a job the manual gives *no* km interval for (and none is found on the web) goes in a separate time-based category with `interval_months`.
All deadline math is done by `python scripts/chassis.py`. Never compute due km yourself.

Data: `data/chassis/manual.json`, `services.jsonl`, `odometer.jsonl`, `anomalies.jsonl` (schemas in `scripts/schemas.md`).

## One-off setup

### configure-manual
Input: owner's manual (PDF/images) in `inbox/` (or the optional second inbox set in `COCKPIT_DRIVE_INBOX`). Manual page images go through `python scripts/ingest_images.py chassis <paths>` first; PDFs are moved as-is.
1. Extract every maintenance job: id, name, action, interval_km, and a source page reference.
2. If a job has no km interval in the manual, find it on the web for this exact model and record `source: web:<url>`. If the web has nothing model-specific, store it with `interval_months` from the manual (time-based category), never a guessed km.
   Fully itemized: one row per item per distinct action/interval (e.g. `brake_fluid` replace 21000 and `brake_fluid_check` check 3000). Keep the manual's code (I, R, I & T, …) in `notes`.
3. Show the full table, write `manual.json`, move originals to `raw/chassis/`, commit.

### configure-history
Input: bulk service slip images in `inbox/` or the second inbox.
0. `python scripts/ingest_images.py chassis <paths>` (or `--pending` to find them). Work from the printed `raw/chassis/` copies; each row's `source` is that file name.
1. Read every slip into a candidate row: date, odo, jobs (mapped to manual ids), workshop, source file. Keep unmapped job lines in `notes`.
2. Unreadable or ambiguous fields go to a question list, not into data.
3. Sort by date and run `python scripts/chassis.py check-candidates <tmpfile>` to detect anomalies: decreasing odo, implausible jumps, date/odo order conflicts.
4. Present the timeline plus each anomaly with a proposed resolution. I decide. Log decisions to `anomalies.jsonl`.
5. Ask for the current odometer reading, append it, write `services.jsonl`, commit, then run `deadlines`.

## Commands

| Command | Trigger | Does | End |
|---|---|---|---|
| `odom <km>` | command + reading | `python scripts/chassis.py odom <km>` (appends, rejects decreases, flags jumps), then shows deadlines | one-off |
| `deadlines` | command | `python scripts/chassis.py deadlines`: every job with last done (odo + date) and km remaining, sorted soonest first; overdue at top | one-off |
| `service` | command + image | Ingest the image (`ingest_images.py chassis <path>`; `source` = the raw/ copy) → extract slip → show parsed row → ask only about unclear items → `python scripts/chassis.py add-service <json>` → show deadlines → commit | one-off (asks if needed) |
| `history` | command | `python scripts/chassis.py history` | one-off |
| `manual` | command | `python scripts/chassis.py manual` | one-off |

## Extraction rules for slips
- Workshop shorthand varies. Map to manual ids by meaning (e.g. "EO chg" → engine_oil). If unsure, ask.
- "Checked" vs "replaced" matters: only count a job as done if the slip shows it was actually performed.
- Never infer an odometer value from neighbouring slips. Missing odo → question.
