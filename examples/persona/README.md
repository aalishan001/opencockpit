# Example persona: Sam Rivera

Sam is fictional: a backend engineer at the made-up Example Corp who rides a made-up "Example 150" scooter and keeps a side project called Shelfie. Every record here is invented so you can try each command before adding your own data.

Try it:

```bash
cp -r examples/persona/data/. data/
python scripts/validate.py
python scripts/chassis.py deadlines
python scripts/bragdoc_public.py stale
python scripts/ideas.py list
python scripts/render.py public-resume
```

Then ask Claude for `/bragdoc stage`, `/bragdoc probe s-0002` or `/extrovert ideas`. When you're done, restore the empty skeleton with `git checkout -- data/` and start on your own records.
