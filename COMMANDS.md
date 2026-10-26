# COCKPIT COMMANDS
/cockpit [domain]  this sheet (or one domain)

## CHASSIS: vehicle (example domain)
/chassis configure-manual       one-off: manual in inbox/ → maintenance table
/chassis configure-history      one-off: slip images in inbox/ → timeline + anomalies
/chassis odom <km>              log reading, show deadlines
/chassis deadlines              what's due, soonest first
/chassis service + image        log a service slip
/chassis history                all past services
/chassis manual                 maintenance jobs + intervals

## EXTROVERT: conversations → posts
/extrovert configure            one-off: news fields + voice notes
/extrovert suggest              icebreakers from ideas, ledger, posts, news
/extrovert ideas                list open ideas, newest first
/extrovert ideas <text/links>   capture an idea (also "idea: ...")
/extrovert ideas find <query>   search text, tags, links, dates
/extrovert ideas show <id>      full idea + version history
/extrovert ideas edit <id> <change>   new version, never overwrite
/extrovert ideas status <id> <s>      new/developing/posted/parked/dropped
/extrovert ideas merge <id> <id>...   combine into one new idea
/extrovert start <idea/links|ids>   clarify, settle a name, begin conversation
/extrovert rename [ref] <name>  rename latest (or a specific) conversation
/end                            end the conversation
/extrovert editorial [ref]      side-by-side transcript vs edited, iterate
/extrovert post [platforms]     Medium (canonical) + LinkedIn summary
/extrovert voice [calibrate]    voice profile brief; calibrate: questionnaire + fresh sample → new version
I posted <conv> on <platform>: <url>   record it; Medium: wait for the feed, rebuild the site, live tests
/extrovert profiles [platform|all]   LinkedIn headline/About/Experience, Medium + GitHub bios, versioned
/extrovert profiles applied <platform|all>   record what I pasted
/extrovert profiles status       latest vs applied, what's stale
/extrovert repos [repo]         repo metadata: GitHub description + topics, PyPI keywords + classifiers, release scheme
/extrovert repos applied <repo>  record what I set by hand

## bragDoc: achievements
/bragdoc dump <text/files>      add items to staging
/bragdoc stage                  show staging + status
/bragdoc probe [id/batch]       grill me on one item/batch
/bragdoc renovate               merge probed → recategorize, re-rank, render PDF
/bragdoc brag                   extensive ATS resume PDF
/bragdoc extractor              read-only prompt for an AI pair session; paste result back
/bragdoc extractor incident <date> <desc>      incident prompt: timeline, durations, root cause
/bragdoc extractor project                     project prompt: architecture, evaluation, metrics
/bragdoc extractor period <from> <to> <topic>  multi-month work prompt: phases, then vs now
make <entry> public|private    set site visibility (natural language)

## RUNWAY: website (your own site repo)
/runway publish                 site data + PDF → content branch → build, check, push → preview URL
/runway promote                 after I approve the preview: content → main (live), set published hashes, live tests
/runway ship "<summary>"        site code change → gates → code/<slug> branch → preview URL
/runway promote code/<slug>     after I approve that preview: → main (live), live tests
/runway prune                   delete site branches already merged into main; show me any that aren't
/runway showcase <ids>          homepage case studies (max 3; staging ids as intents)
/runway status                  live vs pending, launch blockers, hook, feed health, freshness
/runway rebuild                 deploy hook → wait for production → live smoke tests
/runway live-check              live tests against production now
/runway profile                 a profile README's cockpit block: preview, gates, current?
verify the daily rebuild        no click: wait for the scheduled run, check production redeployed
release current-employer entries   make held current-employer entries public + publish

## FOURTHWALL: the system itself
/fourthwall log <note>          journal a decision, lesson, milestone or bug
/fourthwall changelog           summarize new commits into the public changelog
/fourthwall readme              regenerate the public README
/fourthwall export              build the public copy into staging + leak report
/fourthwall publish             push an approved export (never automatic)
/fourthwall handoff             queue a bragdoc item, an idea and a case study
