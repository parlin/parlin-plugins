---
name: crm
description: >
  Use when the user mentions their CRM, customers, clients, prospects, leads,
  pipeline, follow-ups, outreach, cold contact, mailings, email campaigns, or
  opt-outs; asks "who should I reach out to", "what's the status of X", "any
  overdue follow-ups", or wants a weekly pipeline review; or asks to scaffold /
  set up a new CRM for a project. Also use when adding a new contact, logging a
  reply or meeting, moving a deal forward, or preparing a campaign send.
allowed-tools: Read, Grep, Glob, Edit, Write, Bash
---

# CRM - Claude Code Skill

You are managing a **document-based CRM**: plain markdown files, by default in
`context/crm/` at the project root. There is no binary and nothing to install -
you read and edit the files directly.

## Architecture

- **Track files** (`customers.md`, `prospects.md`, `outreach.md`, …) - one table
  row per relationship (or per campaign in `outreach.md`). The row is the **single
  source of truth** for status, priority, next action, Due, and last contact.
- **`people/<slug>.md`** - context per relationship: history, motivations,
  sensitive points. **Never** status, priority, or next action. If you find those
  fields in a people file, that's a bug - remove them and point to the track row.
- **`campaigns/<slug>.md`** - one file per outreach campaign: audience, message,
  recipient list, outcome.
- **`opt-out.md`** - permanent do-not-contact list. Rows are **never removed**.
- **`README.md`** in the CRM folder - the user's manual for their instance: the
  status chain, field conventions, and what "won" means per track. Read it first
  when working in an existing CRM.

## Status chain

Two entry points that merge after first contact:

`Prospect` → `Contacted` (outbound - we reached out) **or** `Enquiry` (inbound -
they reached out) → `Replied` → `Proposed` → `Meeting` → `Agreement` → `Active` →
`Delivered`. Exits from anywhere: `Lost`, `Dormant`, `Unsubscribed`.

`Unsubscribed` always comes with a row appended to `opt-out.md`.

## Hard rules

1. **Status lives on the track row only.** Update the row; keep people files pure
   context.
2. **No placeholder dates.** A row in an active status (`Contacted` through
   `Active`) must have a real `YYYY-MM-DD` in Due. No next step → set `Dormant`.
   `Delivered`, `Lost`, `Dormant`, `Unsubscribed` may carry `-`.
3. **After any action**: update **Last contact** and rewrite **Next action** (one
   thing, verb first). New rows go at the top of the table.
4. **Nothing is deleted.** Lost deals are useful history.
5. **Never send - or help prepare a send as final - without the opt-out check.**
   Before any campaign goes out, diff the recipient list against `opt-out.md` and
   record the check date in the campaign file. If the user asks to skip it,
   refuse and explain: it is the one CRM mistake that cannot be corrected
   afterwards. Email legal rules: read `references/outreach-rules.md` (bundled
   next to this skill) before drafting or reviewing any outreach.

## Operations

### Initialize a CRM (scaffold)

Templates live in `${CLAUDE_PLUGIN_DIR}/templates/`. Scaffold by reading them and
writing adapted copies with Write/Bash - **there is no install step**.

Interview the user first (briefly - offer the defaults):

1. **Which tracks?** Default `customers` + `prospects` + `outreach`. Another
   project may want e.g. `investors` or `partners` - clone the prospects template
   shape for extra tracks.
2. **What does "won" mean per track?** (e.g. "engagement delivered and invoiced",
   "round closed"). Goes into the track table in the scaffolded README.
3. **Sender identity for outreach** - legal/company name, registration number if
   any, contact address. Filled into `campaigns/_TEMPLATE.md` and the pre-send
   checklist in `outreach.md`.
4. **Where?** Default `context/crm/` at the project root.

Then: create the directory, copy every template (`README.md`, `CLAUDE.md`, track
files, `opt-out.md`, `people/_TEMPLATE.md`, `campaigns/_TEMPLATE.md`), and replace
every `«…»` placeholder with the interview answers. Drop track files the user
declined; add ones they requested. Templates are in English - offer to scaffold
in another language if the user prefers.

### Query / update

Read the track file(s); answer from the rows. To update: edit the row (status,
Next action, Due, Last contact). Add substance to `people/<slug>.md` when there is
real context worth keeping - create it from `people/_TEMPLATE.md`.

### Move a row between tracks

When a prospect is won, **move** the row to `customers.md` (top of table) - never
duplicate it. A contact lives in exactly one track.

### Weekly review

Scan every track file for three things and report them as a short actionable list:

1. Rows whose **Due** has passed → do the action or set `Dormant`.
2. Rows whose **Last contact** is older than 60 days while the status claims
   something is in motion (`Contacted` through `Active`).
3. Active rows with no **Next action**.

Then help the user fix each finding. This review is the entire maintenance burden
of the CRM - encourage running it weekly.

### Create a campaign

1. Copy `campaigns/_TEMPLATE.md` to `campaigns/<slug>.md`; fill audience, purpose,
   message, recipient table.
2. Add **one row** to `outreach.md` (one row per campaign, never per recipient).
   Campaign statuses: `Draft` → `Listed` (recipient list finalized **and checked
   against opt-out.md**) → `Sent` → `Followed up` → `Closed`.
3. Before `Listed`: run the opt-out check (rule 5) and verify every address is a
   company address or a named person in their professional role - see
   `references/outreach-rules.md`.
4. After replies: break out **only the responders** into `prospects.md` rows
   (status `Replied`); non-responders stay in the campaign file.

A one-off message to a single named person is not a campaign - it is a
`prospects.md` row with status `Contacted`.
