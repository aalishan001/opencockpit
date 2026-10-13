# opencockpit

A personal command system that runs inside [Claude Code](https://docs.claude.com/en/docs/claude-code/overview). You talk to it in plain language or slash commands, and it keeps structured, versioned records: a brag document of your engineering work, post ideas and posts, the website that shows your work, and an example maintenance log.

This is the public, generalized copy of a private cockpit used every day. It ships with empty data and a fictional example user, so you can try every command before adding your own records.

## The idea: harness first

A language model is good at judgment: interviewing you about a project, turning a messy transcript into a clean post. It is bad at exact work: adding kilometers, comparing dates, hashing, remembering a rule it read an hour ago.

So cockpit splits the work. The model makes the judgment calls; the harness around it does everything that must be exact or enforced:

- **Skills** (`.claude/skills/<domain>/SKILL.md`) spell out each command step by step, including how it ends and what it commits.
- **Scripts** (`scripts/`) do all arithmetic, dates, sorting, hashing, rendering and checks. The model runs them and reports their output.
- **Hooks** (`.claude/settings.json`) run the validator after every edit and pull the latest state when a session starts.
- **Rules** (`CLAUDE.md`) hold the contract: no invented facts, a source on every record, ask instead of guessing, show a change before writing it, one commit per command.
- **Lints** gate everything that leaves the repo: a disclosure lint per audience and a voice lint for prose.

Every command runs the same path:

```text
you: chat, files, phone photos
 -> CLAUDE.md      routes the request, applies the global rules
 -> a skill        the command's steps, from start to its end condition
 -> scripts/       every number, date, hash, render and check
 -> data/          structured records, validated after every edit
 -> git            one commit and push per command
```

## Domains

| Domain | What it does |
|---|---|
| **BRAGDOC** | A probed, metric-backed record of your work: brain dumps go to staging, a probe interviews you until each item has a problem, an action, a result and real numbers, and renovate ranks the entries and renders the BragDoc. |
| **EXTROVERT** | Interviews you about an idea and edits the transcript into posts in your own voice (Medium, plus a LinkedIn summary). Keeps an ideas backlog and versioned profile copy. |
| **RUNWAY** | Ships the BragDoc's public channel to your own site repo: a preview branch first, live only after you approve it, then live tests against production. |
| **FOURTHWALL** | Documents the system itself (journal, changelog, this README) and exports the public copy you are reading. |
| **CHASSIS** | An example domain: vehicle maintenance from the manual, service slips and odometer readings. |
| **HELP** | `/cockpit [domain]` prints the command sheet. `/end` closes whichever interactive command is running. |

`COMMANDS.md` is the source of truth for every command name.

## Folder layout

```text
CLAUDE.md                  router, folder contract, global and git rules
COMMANDS.md                every command name (the help sheet)
.claude/skills/<domain>/   one skill per domain
.claude/agents/            read-only subagents (the claim checker)
.claude/settings.json      hooks and permission rules
scripts/                   exact work: validate, lint, render, hash, publish
scripts/schemas.md         the format of every data file
data/                      your records (empty here)
examples/persona/          a fictional user's data
templates/                 render styles
tests/test_suite.py        synthetic tests
inbox/ raw/ out/           created on first use: drop zone, originals, renders
```

## Add your own domain

1. **Skill:** write `.claude/skills/<name>/SKILL.md`: a description with the phrases that should trigger it, and every command with its steps, how it ends and what it commits.
2. **Names:** add the commands to `COMMANDS.md` and a row to the domain table in `CLAUDE.md`.
3. **Script:** put the exact work in `scripts/<name>.py`, reading and writing only `data/<name>/`.
4. **Schema and validation:** describe each data file in `scripts/schemas.md` and check it in `scripts/validate.py`, so a bad write fails at the next edit.
5. **Tests:** add synthetic cases to `tests/test_suite.py` and example records to `examples/persona/`.
6. **Privacy:** if the domain is private, add its paths to the FOURTHWALL manifest rules and its terms to the deny list, so it can never reach a public copy.

## Safety rails

- **Provenance:** every record carries a `source`, and a claim only an AI summary made must be confirmed before it reaches an entry.
- **Claim checker:** a read-only subagent checks every resume bullet or post claim against the BragDoc.
- **Disclosure channels:** internal, resume and public outputs are each checked against a policy file; a failing render writes nothing.
- **Human gate:** nothing reaches your live site until you approve its preview.
- **Git rules:** permission rules deny force pushes, hard resets and global config changes.

## Setup

Create your own private repo from this template, then:

```bash
git clone <your private repo> cockpit
cd cockpit
pip install -r requirements.txt
python tests/test_suite.py
claude
```

To try it first, copy `examples/persona/data/` into `data/` and run `/cockpit`. RUNWAY needs a site repo of your own: fill in `data/runway/config.json` when you have one.

## How this repo is built

FOURTHWALL generates it from an allowlist manifest: each file is copied, rewritten in generalized form, or taken from a template. The build lands in a staging folder outside the private repo and must pass every leak check (structure, secrets, the public disclosure lint, a deny list of private names, no em dashes) before a reviewed release is pushed with its own history.

## License

MIT. See [LICENSE](LICENSE).

Built by Aalishan ([github.com/aalishan001](https://github.com/aalishan001)).
