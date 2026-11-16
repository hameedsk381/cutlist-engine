# Launch checklist

What the code now does is listed in `PRODUCTION.md`. This is what only you can do.
Tick each line before you open sign-ups.

## Must do

- [ ] **Fill in the legal pages.** `frontend/public/terms.html` and `privacy.html` have
      `[bracketed]` values (operator name, address, contact email, jurisdiction, dates).
      Have a lawyer read them. They describe what the software does today; change them if it changes.
- [ ] **Set the server's `.env`:** `CUTLIST_JWT_SECRET`, `POSTGRES_PASSWORD`, `CUTLIST_APP_URL`
      (your https address), all `CUTLIST_SMTP_*`, and `GROQ_API_KEY` for the AI features.
- [ ] **Prove email works.** Sign up with a real address: you must receive the verification email.
      Then use "Forgot password?" and finish a reset from the emailed link.
- [ ] **Put HTTPS in front** and make the proxy send `X-Forwarded-For` and `X-Forwarded-Proto`
      (see `PRODUCTION.md`). Without it sign-in limits count every user as one.
- [ ] **Back up and test a restore.** Daily `pg_dump` and a copy of the storage volume, kept off the
      server. Restore into an empty database once to be sure it works.
- [ ] **Redeploy, then re-run your projects** so they get the cutting order and model checks.
- [ ] **Rotate the API key** that was pasted into a chat during development.

## Should do

- [ ] Read the Hindi text with a native speaker. All of it is machine-written and unreviewed.
- [ ] Run the SketchUp extension in real SketchUp and follow `docs/SKETCHUP_GUIDE.md`. It has never
      been run there. Also try a real SketchUp DAE export.
- [ ] Check what the AI says about a messy model on the live site (`artch` is a good one).
- [ ] Decide on pricing or limits beyond the free plan (50 plans a month, 200 AI calls a day) and
      add them to the terms if you charge.
- [ ] Watch the logs for a day: `docker compose logs -f`.
- [ ] Add a status or error alert (an uptime check on `/healthz`).

## Known gaps

- The Content-Security-Policy was checked on the plan, share, legal and upload pages without violations, but not
  against Google Fonts loading from the live site or the voice and sketch buttons. After deploying, open the browser
  console on each main screen; set `CUTLIST_CSP=report-only` if anything is blocked.
- Sign-in tokens last 7 days and stay valid after a password reset.
- Rate-limit counts are per process and reset on restart.
- Grain and edge banding are not read from SketchUp; shaped boards are planned as full rectangles.
- The downloadable `sheet_layout.html` and the share page still use the older sheet drawing.
- STEP import is unverified.
- Test projects #12, #13 and #16–#19 on the live account can now be deleted from the project list.
- The Git history of this public repository still contains files removed in the launch cleanup,
  including a client floor plan (`WhatsApp Image … plan2cad.dxf`). Removing it from history means
  rewriting and force-pushing the repository; decide whether that is worth it.
