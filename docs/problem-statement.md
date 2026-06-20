# Demand Supply Matcher

## Context

A consultancy ("Parity Partners") continually moves consultants between client engagements.

On the **supply side**, people sit in 3 states:

- **On the beach** — free now.
- **Rolling off within ~90 days** — free on a date.
- **Joining in the next ~60 days** — new joiners.

On the **demand side** is a list of open roles that are quite dynamic. Each role has:

- Required skills
- A start date
- A location constraint
- A priority

The firm is growing fast — roughly 5% headcount a month — so the beach, the new joiners coming in, and the open roles are all in constant flux; today's snapshot is a fraction of what this has to handle.

Today, a staffing manager matches the two by hand in a spreadsheet — skills, availability, and a free-text column — on judgment. It's slow and inconsistent.

## Task

Given an open role, recommend a **ranked, explainable shortlist** of consultants to staff onto it, surfacing the trade-offs for a human to decide.

## Data

Refer to this [Drive link](https://drive.google.com/drive/folders/1ScFJyRc-vy4S23K7VrBzyAf3n0labZ8U?usp=sharing). It contains:

- `profiles/` — 50 consultant profiles. Some use the Parity Partners template; others are free-form.
- `project_feedback/` — project and client feedback for the existing consultants.
- `demand-supply.xlsx` — the live supply (beach, rolling off, new joiners) and the open roles, one tab each.

## Logistics

- The problem is to be solved by each trio.
- Initial questions and approaches to be discussed Friday.
- Repo sharing / repurposing approach is still TBD — suggestions welcome.
