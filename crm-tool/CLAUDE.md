# crm-tool - for anyone working ON this plugin

Read this before changing behavior. These are design decisions, not accidents.

## Design intent

This plugin generalizes a CRM that replaced an earlier one which quietly rotted.
Four deliberate corrections are the whole point - keep them encoded as **rules**
in the templates and the skill, never soften them into suggestions:

1. **Single-homed status.** Status, priority, and next action live only in the
   track-file row. `people/` files are context only. The earlier CRM duplicated
   status into detail files; the copies drifted, and neither was trusted.
2. **No placeholder dates.** Active rows carry a real Due date or the row is
   `Dormant`. The earlier CRM filled up with `[[date]]` placeholders that were
   never filled in - the visible symptom of a CRM going dead.
3. **Weekly review** (overdue Due / stale Last contact vs. active status / missing
   next action) is what keeps rule 2 true over time.
4. **Two-entry pipeline**: `Contacted` (outbound) and `Enquiry` (inbound) merge
   after first contact. Collapsing them loses the ball-in-whose-court signal.

Also non-negotiable: `opt-out.md` is permanent (rows never removed), and every
recipient list is checked against it before a send. That rule is intentionally
stated in three places - SKILL.md, `templates/CLAUDE.md`, `templates/opt-out.md` -
because it is the one error that can't be corrected afterwards.

## No install step - by design

Unlike backlog-tool there is no binary, no Python packaging, no installer, and no
version probing. The skill scaffolds by writing markdown straight from
`${CLAUDE_PLUGIN_DIR}/templates/`. If you feel the urge to add an install step:
don't. Markdown-only is the design.

## Gotchas

- **crm-tool's version lives in TWO places** - `crm-tool/.claude-plugin/plugin.json`
  and the `crm-tool` entry in `.claude-plugin/marketplace.json`. (Two, not
  backlog-tool's three: there is no Python package manifest here.)
- **This repo is public.** Template examples must be obviously fictional
  placeholders - no real companies, people, org numbers, or email addresses.
- Templates use `«…»` placeholders that the skill's init interview replaces
  (tracks, definition of "won" per track, sender identity, CRM location). If you
  add a placeholder, teach SKILL.md to fill it.
- The legal notes in `skills/crm/references/outreach-rules.md` are verified against
  Swedish marketing law and GDPR - they say so explicitly. Don't edit them into
  jurisdiction-neutral mush; add other jurisdictions as clearly-labeled additions.
