# CRM Tool

A lightweight, document-based CRM that lives inside your project as plain markdown.
One row per relationship, one file per track. Built for a person or small team that
drives a handful of relationships in depth - not for sales volume. A contact earns a
row only when there is a real reason to engage.

There is **no tool to install**. The whole CRM is markdown files, and the whole
integration surface is that markdown: greppable, diffable, versioned next to your
project. The `crm` skill scaffolds it, keeps it updated, runs the weekly review, and
enforces the outreach rules.

## Getting started

Install the plugin, then ask Claude to set up a CRM:

> scaffold a new CRM in this project

The skill interviews you (which tracks you need, what "won" means per track, your
sender identity for outreach, where the files should live - default `context/crm/`)
and writes the files. From then on you talk to it in plain language:

> what's the status of Initech? · move Hooli to Proposed · run the weekly CRM review
> · draft an outreach campaign to fictional-widget makers

## File structure

    context/crm/
      README.md          # the CRM's own manual: tracks, status chain, conventions
      CLAUDE.md          # rules for any agent working in the folder
      customers.md       # one row per paying (or formerly paying) relationship
      prospects.md       # one row per relationship that isn't won yet
      outreach.md        # one row per outgoing CAMPAIGN (never per recipient)
      opt-out.md         # permanent do-not-contact list - rows are never removed
      people/            # one context file per relationship that earns one
      campaigns/         # one file per outreach campaign
    (tracks are configurable - a project may want investors.md or partners.md instead)

## Status chain

The pipeline has **two entry points** that meet after first contact - one for what
comes in, one for what you initiate:

    Prospect ─→ Contacted (outbound: we reached out)  ─┐
                                                        ├─→ Replied → Proposed → Meeting
    ────────→ Enquiry   (inbound: they reached out)  ──┘     → Agreement → Active → Delivered

Plus three exits available from anywhere: `Lost`, `Dormant`, `Unsubscribed`.

## Design rules (why this doesn't rot)

These are rules, not suggestions - they are what keeps the CRM alive:

1. **Status lives in exactly one place**: the row in the track file. Files in
   `people/` carry context (history, motivations, sensitive points) but never
   status, priority, or next action. Duplicated status drifts apart, and then you
   trust neither copy.
2. **No placeholder dates.** Every row in an active status has a real date in
   **Due**. If there is no next step, the row is not active - set it `Dormant`.
   Closed and parked rows get `-`. A previous CRM this design comes from filled up
   with `[[date]]` placeholders that were never filled in - that is how a CRM
   quietly stops being used.
3. **Weekly review**, three checks: rows whose Due has passed; rows whose Last
   contact is older than 60 days while the status claims something is in motion;
   rows without a next action. Without the routine, the placeholders win.
4. **Campaigns are one row, not many.** An outgoing mailing is one row in
   `outreach.md` plus a file in `campaigns/`. Only recipients who actually reply
   get their own row in `prospects.md` - otherwise the prospect list swells with
   names nobody has talked to.

## Outreach and opt-out

Every message must offer a working way to decline further contact, and every
recipient list must be checked against `opt-out.md` **before** a campaign goes out -
a contact who opted out receiving another mailing is the one CRM mistake that
cannot be corrected afterwards. The bundled rules
(`skills/crm/references/outreach-rules.md`) reflect Swedish marketing law and GDPR;
users in other jurisdictions must verify their own rules.
