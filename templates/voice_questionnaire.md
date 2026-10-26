# Voice re-calibration questionnaire

Used by `/extrovert voice calibrate`. The answers update `data/extrovert/voice/profile.json` as a new version; the old
version stays in its `history`. Answer in your own words; short answers are fine. Skip any question that hasn't changed.

## 1. A fresh sample
Write or dictate at least 300 words, fast and unedited, on something you have a strong opinion about. Don't polish it.
The sample is archived under `raw/extrovert/voice/` and used for style only, never as a source of facts.

## 2. Rhythm
- Do your sentences still mix long explanations with short blunt lines, or has that changed?
- Paste one recent sentence of yours that sounds exactly like you, and one that doesn't.

## 3. Moves you use
For each, answer keep, limit (how often) or drop:
- a question, then its answer ("Why? Because ...")
- an analogy, or a moment from history
- talking straight to the reader
- a firm opinion first, then a fair concession
- capitals for emphasis
- casual fillers (which ones?)
- anything else you do that the profile doesn't name

## 4. Humor
- What kind of humor do you use, and at whose expense?
- How much of it belongs in a public post?

## 5. Person
- When do you write "we", and when "I"? (For example: employer work vs personal work.)

## 6. Words
- Phrases you never want to see in your posts, beyond the current banned list.
- Self-descriptions you never want used (or "it depends on the situation").
- Slang or profanity that is fine in raw notes but never public.

## 7. Registers
- Which platforms are public for you, and what changes between your raw voice and the public one?
- What should happen to your connectors (dashes, spaced hyphens, ellipses) in public?

## 8. Limits
Current caps per public post (change any):
- capitals for emphasis, theatrical one-line paragraphs, question-and-answer pairs, exclamation marks, hashtags,
  groups of three, runs of same-length sentences.

## 9. The last posts
- Name a line in a recent post that sounded unlike you, and say what you would have written.

## How the answers are used
1. The new sample goes to `raw/extrovert/voice/<YYYYMMDD-HHMM>-<name>.md`; `python scripts/voice_lint.py --stats <file>`
   measures it (sentence lengths, questions, capitals, connectors). The numbers come from the script, never from a guess.
2. Each answer maps to a profile field: moves to `traits` (keep, limit or drop), humor to `humor`, person to `person`,
   words to `banned` and the register's `drop`, limits to `registers.<name>.limits`.
3. The proposed change is shown as a diff before anything is written. On approval, `version` goes up by one and
   `history` gets one line: the date, what changed and the source.
