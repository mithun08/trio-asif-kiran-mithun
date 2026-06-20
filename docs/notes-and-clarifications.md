# Demand Supply Matcher — Notes & Clarifications

> Companion to `problem-statement.md`. Summary of the kickoff discussion plus follow-up clarifications.

## Current manual process

- Weekly forum with HOEs, EMs, staffers, and leadership to review opportunities.
- Not simple skill matching — involves understanding client context, team dynamics, and stakeholder preferences.
- Example: an "AI architect" role actually needs a tech lead who understands AI in the SDLC.
- Considers relationship factors: some stakeholders micromanage, some prefer autonomy.
- Evaluates feedback: project performance, client feedback, beach performance.
- Sometimes matches adjacent skills (e.g. Python dev needed but only Java devs available — check willingness to learn).

## System goal

Build a democratic demand-supply marketplace that removes human bias while forming high-performing teams.

## Domain rules

- **Location constraint:** Hard requirement — no relocation assumptions. A co-location flag indicates the team must be in a specific city (e.g. MNS/BCG Chennai teams).
- **Start date flexibility:** A few days' buffer is acceptable for roll-offs or new joiners, but not months.
- **Priority framework:** Location is currently the highest priority in real staffing, but teams are free to implement different weighting if justified.
- **System scope:** Focus on the matching algorithm, not the UI — a CLI is sufficient as an interface.
- **Roll-off dates:** Dates in the sheet are final; the 30-day notice is already incorporated where applicable.
- **Multiple roles:** Start with single-role matching; multi-role team formation is an optional enhancement.
- **Evaluation approach:** 100% accuracy is not expected or desired — it would indicate insufficient test coverage. The system should handle uncertainty.

## Feedback notes

- New joiners have unverified skills in the EE context.
- Project feedback exists in two forms: client feedback (may be one-dimensional) and internal EE feedback (more comprehensive on team fit and hands-on ability).
- Beach feedback shows performance trajectory (improved / maintained / decreased).
- Teams must decide how to weight skill claims, project feedback, and beach performance.

## Skills matching

- Hard skills may have acceptable alternatives (e.g. a Kotlin requirement may accept Java developers willing to learn).
- Additional data is available — project feedback, client feedback — and teams decide if/how to use it.
- The system should explain gaps when it cannot match requirements.

## Development philosophy

- Embrace uncertainty — don't try to answer everything on day one.
- Build an extensible system where priorities/weights can change.
- Vertical slicing: start with beach-only matching, then add variables incrementally.
- POC approach: explore with the business, build a first version, iterate.
- Prioritize the top 10–20 backlog items, not a full thousand-item list.

## API keys & tech stack

- Use the OpenRouter API keys provided.
- Local model execution is also acceptable.
- A pre-configured tech stack is available on machines; teams can use alternative tools if justified.

## UX

- **Minimum:** a CLI accepting a single requirement (e.g. "backend engineer with database experience").
- **Optional enhancements:** web interface, file upload for multiple roles, team formation queries.
- Focus on system logic, not UX polish.
- Order of consumers: tests/evals first, then CLI, then web if time permits.

## Evals

- Include negative scenarios, not just positive cases.
- Find negative examples in the existing dataset or create synthetic data.
- An eval showing 100% success is considered a failure — it indicates insufficient exploration.
- Non-deterministic systems cannot achieve perfect accuracy.
- Balance thoroughness against practical constraints.

## Team structure & logistics

- Location-based grouping to enable Friday office collaboration and whiteboarding.
- Considered AI-tool exposure from engagements to distribute knowledge.
- Alphabetical ordering used when location didn't provide clear grouping.
- Trio format enables 9 demos instead of 27 individual or 14 pair demos.
- Allows team dynamics practice: problem division, coordination, decision-making.
- Pairing approach acknowledged as "fairly unscientific."
- Teams can request trio changes for any reason.

## Next steps

- Keep Slack channels active with questions and assumptions.
- Share assumptions publicly so others can learn.
- Cross-team collaboration encouraged — this is not a competition.
- Ask other groups if stuck; learn together.
- Next week's session is cancelled (many traveling).
- Async support available via channels.

## Open question (outstanding)

- Best way to create repos for each trio is still TBD — teams can self-organize and propose a simple approach.

## Clarifications (Q&A)

**Q1. Will the system give rolling-off / on-beach candidates preference over new joiners, due to the new joiners' lack of feedback? Assuming that's fine.**
Correct — though you are welcome to make a different, documented assumption.

**Q2. What is the impact of role priority? If a candidate is the best fit for two roles, should they be recommended for the higher-priority one?**
That interpretation is acceptable — and, as with Q1, teams may document a different approach if justified.

**Q3. What are the PII masking requirements?**
Standard. Personal data (e.g. email, phone number) should not be processed by LLMs.
