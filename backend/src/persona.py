"""The one place the agent's name lives on the backend. Change AGENT_NAME here
and every prompt, greeting, and log line that references the persona picks it
up — nothing else in backend/ should ever hardcode the name as a literal."""

AGENT_NAME = "Fiona"

# Fiona is based in New Jersey (see frontend/src/lib/personas.ts's "location"
# field) — this is what lets the agent answer real "what time/day is it"
# questions correctly. Kept on the persona, not as a single global constant,
# because it's a fact about Fiona specifically: the day a second persona from
# elsewhere (India, China, ...) goes live, that one gets its own timezone
# defined the same way, not a shared default.
AGENT_TIMEZONE = "America/New_York"

# Same reasoning as AGENT_TIMEZONE, for the same real bug: the timezone alone
# let the agent compute the right clock time, but never told it *where it
# is* — asked "where are you located," it had nothing to answer from and
# guessed wrong. Kept in sync with frontend/src/lib/personas.ts's "location"
# field by convention (not imported — that file isn't reachable from here).
AGENT_LOCATION = "New Jersey, United States"
