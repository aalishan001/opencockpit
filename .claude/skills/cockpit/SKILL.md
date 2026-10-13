---
name: cockpit
description: Help / cheat sheet for the cockpit command system. Prints COMMANDS.md, or one domain's section (chassis, extrovert, bragdoc, runway, fourthwall). Use when the user types /cockpit, asks for help, "what commands are there", "how do I ...", or forgets a command name.
---

# COCKPIT (help)

Read `COMMANDS.md` at the repo root and print it **verbatim** inside a single fenced code block. Do not reproduce it from memory, paraphrase, reorder, summarize, or add any text before or after.

- No argument → the whole file.
- Argument `chassis`, `extrovert`, `bragdoc`, `runway`, or `fourthwall` (case-insensitive) → only that domain's section: from its `## <DOMAIN>` heading up to, not including, the next `## ` heading.
- Any other argument → print the whole file.

One-off. Changes no files, so no commit.
