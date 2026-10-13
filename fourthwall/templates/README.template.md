# {{project name}}

{{One paragraph: what this is and who it is for. Then: this is the public, generalized copy; empty data plus a fictional persona.}}

## The idea: harness first
{{Why the model makes judgment calls and the harness (skills, scripts, hooks, rules, lints) does the exact work and the enforcement. Then a plain-text diagram in a fenced code block (never mermaid or raw HTML: the README must also render in a sanitized Markdown popup): you -> CLAUDE.md -> a skill -> scripts/ -> data/ -> git.}}

## Domains
{{A table: one row per domain, one or two sentences each. Point at COMMANDS.md as the source of truth.}}

## Folder layout
{{A fenced code block: each top-level file and folder with one line on what it holds.}}

## Add your own domain
{{Numbered steps: skill, command names, script, schema + validation, tests + persona data, privacy (manifest rules + deny list).}}

## Safety rails
{{Short bullets: provenance, claim checker, disclosure channels, the human gate before anything goes live, git permission rules.}}

## Setup
{{Create a private repo from this template, clone, install requirements, run the tests, open in Claude Code. First run: the example persona.}}

## How this repo is built
{{FOURTHWALL: allowlist manifest (copy / generalize / template), staging outside the repo, leak checks, reviewed release with its own history.}}

## License
MIT. See [LICENSE](LICENSE).

{{Author line: "Built by <name> ([github.com/<handle>](https://github.com/<handle>))." (the only line where the author's name may appear)}}
