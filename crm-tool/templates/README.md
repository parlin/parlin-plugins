# CRM - «project / company name»

Lightweight, document-based CRM. One row per relationship, one file per track.
Built for driving a handful of relationships in depth - not for sales volume. A
contact earns a row only when there is a real reason to engage.

## Tracks

| Track | File | Who | "Won" / `Delivered` means |
|---|---|---|---|
| **Customers** | `customers.md` | Organizations that pay or have paid «company» | «e.g. engagement delivered and invoiced» |
| **Prospects** | `prospects.md` | Individual relationships not yet won - inbound enquiries, brokers, own leads | - (row moves to `customers.md` when won) |
| **Outreach** | `outreach.md` | Outgoing campaigns: one row per *campaign*, not per recipient | - |

A contact lives in exactly **one** track. When a prospect becomes a customer the
row **moves** to `customers.md` - it is never duplicated.

`people/` holds one detail file per relationship that earns one. Those files carry
**context** - history, motivations, sensitive points - but never status, priority,
or next action. Those fields live in exactly one place: the row in the track file.
Duplicated status drifts apart, and then you trust neither copy.

## Status chain

Move left → right. The status in the track file is the only source of truth.

The chain has **two entry points** - one for what comes in, one for what we
initiate. After first contact both follow the same path.

| Status | Direction | Meaning |
|---|---|---|
| `Prospect` | - | Identified, no contact made. |
| `Contacted` | Outbound | We reached out. Awaiting reply. |
| `Enquiry` | Inbound | They reached out, unanswered - ball is with us. |
| `Replied` | | They replied - ball is with us. |
| `Proposed` | | Proposal/quote/reply sent, waiting on them. |
| `Meeting` | | Meeting or interview booked or held. |
| `Agreement` | | Agreement in negotiation or signing. |
| `Active` | | Engagement being delivered right now. |
| `Delivered` | | Engagement finished, relationship lives on. |
| `Lost` | | Declined or fell away after real engagement. |
| `Dormant` | | Parked, can be picked up again. |
| `Unsubscribed` | | Asked not to be contacted. See `opt-out.md`. Never contact again. |

## Fields

- **Priority** - High / Med / Low.
- **Next action** - the *single* next thing to do, verb first. Several things: pick the next one.
- **Due** - a date, so nothing rots silently.
- **Last contact** - date of most recent contact.
- **Detail** - link to a people file, client folder, enquiry, or agreement.

## Conventions

- Dates are absolute: `YYYY-MM-DD`.
- After doing something: update **Last contact** and rewrite **Next action**.
- New rows go at the **top** of the table.
- Nothing is deleted. Lost deals are useful history.
- **Due is always a real date** for rows in an active status (`Contacted` through
  `Active`). If there is no next step, the row is not active - set `Dormant`.
  Placeholders in that field are how a CRM quietly stops being used: the previous
  system this one replaced filled up with `[[date]]` placeholders that were never
  filled in.
- `Delivered`, `Lost`, `Dormant`, and `Unsubscribed` rows may carry `-` in
  **Next action** and **Due**. Those are closed or parked relationships, not
  forgotten rows.

## Outbound contact

Two forms, handled differently.

**Single contact** - you reach out to one named person. Add a row in
`prospects.md` with status `Contacted`. No campaign file needed.

**Mailing to several** - one row in `outreach.md` per *campaign*, plus a file in
`campaigns/<slug>.md` with audience, message, recipient list, and outcome.
Recipients who reply are broken out into their own `prospects.md` rows; those who
don't stay in the campaign file. Otherwise the prospect list swells with names
nobody has talked to.

### Email rules

Summary - the full rules ship with the `crm` skill (`references/outreach-rules.md`)
and reflect **Swedish/EU law**; verify locally if you operate elsewhere.

- Company addresses and named persons in their professional role: no prior
  consent required (opt-out applies for legal persons).
- Private individuals and private addresses: active consent **in advance**.
- Every message contains a working way to decline further contact - no exceptions.
- Content must be relevant to the recipient's professional role (this keeps the
  mailing within legitimate interest under the GDPR).
- Clear sender identity, no misleading subject line.

### `opt-out.md` - check before every send

Everyone who asked to be left alone is in `opt-out.md`. **Never run a mailing
without first checking the recipient list against that file.** An opted-out
contact receiving another mailing is the one mistake in this folder that cannot
be corrected afterwards. Rows are never removed - the list is permanent; that is
its entire function.

## Weekly review

Go through the track files once a week and look for three things:

1. Rows whose **Due** has passed - either do the action, or set `Dormant`.
2. Rows whose **Last contact** is older than 60 days while the status claims
   something is in motion.
3. Rows without a **Next action**.

That is the entire maintenance.

## Where the details live

The CRM is an index, not an archive. Content stays where it belongs:

| What | Where |
|---|---|
| «e.g. client background, engagement history» | «e.g. ../clients/<slug>/» |
| «e.g. incoming enquiries, RFPs» | «e.g. ../requests/» |
| «e.g. signed agreements» | «e.g. ../contracts/<slug>/» |
