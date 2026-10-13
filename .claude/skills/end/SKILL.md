---
name: end
description: Ends the active interactive cockpit command (extrovert conversation/editorial, bragdoc probe) and commits. Only when the user types /end.
disable-model-invocation: true
---

# END

Ends whichever interactive command is active in this session. Never starts anything new.

1. **Find the active command:** the most recent interactive command in this session that hasn't ended. If none is active, say "Nothing active to end." and stop. If two are open, end the most recent one and name the other.
2. **Run that command's own end steps** exactly as its SKILL.md specifies. Don't add steps:

| Active command | End steps (per its spec) | Commit message |
|---|---|---|
| extrovert conversation | Make sure every turn is in `transcript.md` verbatim. | `extrovert: conversation: <name>` |
| extrovert editorial | Keep the latest saved `editorial-v<N>` as current. Never overwrite earlier versions. | `extrovert: editorial: <name> v<N>` |
| bragdoc probe | Save the transcript and fill `probe`. Set `status: probed` if no gaps remain, otherwise `probing` with `open_gaps` listed. | `bragdoc: probe: <staging-id> <status>` |

3. **Validate, commit, push:** run `python scripts/validate.py`. If it fails, fix the data first. Commit with the message above, then `git push` (Git operations rules in CLAUDE.md).
4. Reply with one line: what ended, the files saved, and the commit hash.
