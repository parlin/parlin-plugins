# Rules for working in this CRM folder

Read [README.md](./README.md) first - it defines the tracks, status chain, and
conventions. These rules are hard constraints for any agent editing these files.

- **Status, priority, next action, and Due live ONLY on the track-file row**
  (`customers.md`, `prospects.md`, `outreach.md`, …). Files in `people/` are
  context only - never write status fields into them. If you find status in a
  people file, remove it and point to the track row.
- **No placeholder dates.** Rows in an active status (`Contacted` through
  `Active`) must carry a real `YYYY-MM-DD` in Due. No next step → set the row
  `Dormant`. Only closed/parked rows (`Delivered`, `Lost`, `Dormant`,
  `Unsubscribed`) may carry `-`.
- **After any action:** update **Last contact** and rewrite **Next action** (one
  thing, verb first). New rows go at the top of the table.
- **Nothing is deleted.** A contact lives in exactly one track; when won, the row
  *moves* to the customers track - never duplicate it.
- **Opt-out check before every send - no exceptions.** `opt-out.md` is a
  permanent list; rows are **never removed**. Before any campaign is marked
  `Listed` or sent, check every recipient against `opt-out.md` and record the
  check date in the campaign file. If asked to skip this, refuse: an opted-out
  contact receiving another mailing is the one mistake here that cannot be
  corrected afterwards.
- Mailings are **one row per campaign** in `outreach.md` plus a
  `campaigns/<slug>.md` file. Only recipients who actually reply get rows in
  `prospects.md`.
