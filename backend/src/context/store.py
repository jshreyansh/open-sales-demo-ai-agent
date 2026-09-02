import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..persona import AGENT_NAME

# Spoken/shown the instant a visitor joins — before the LLM is ever called —
# so the very first thing they hear is one short self-intro, not silence or
# a feature dump. Deliberately just an intro + open question, not a
# discovery interview — if the prospect volunteers their name, role, or
# company at any point, the model picks up on it opportunistically (see
# runtime.py's "prospect_name" tool field) rather than this being scripted
# to ask for it. The voice pipeline speaks this deterministically (see
# AgentRuntimeProcessor._greet, triggered off the pipeline's own StartFrame)
# and the frontend shows the identical text as the first chat bubble;
# seeding it into history here means run_turn's very next call already sees
# it as the opening turn.
# Opens social, not transactional.
#
# Two people joining a call say hello and exchange a line before they get to
# business — that is how the ice actually breaks. Opening on "want a
# walkthrough, or something specific?" skips straight past it and makes the
# first thing she does a menu. The discovery sequence (runtime.py instruction
# 0) picks up from here.
OPENING_GREETING = (
    f"Hi, I'm {AGENT_NAME}, sales rep at SwishX. How's your day going so far?"
)

# Adaptive interaction policy thresholds (see SessionState's
# pace_evidence/action_bias_evidence and runtime.py's _interaction_note).
# Defined here rather than in runtime.py so start_session below can seed
# evidence straight to/above threshold from the pre-call calibration answer
# without runtime.py importing back into this module. A single short reply
# is weak evidence (bumps evidence by 1, well under threshold); an explicit
# demand match is strong evidence on its own (bumps by the full threshold).
PACE_EVIDENCE_THRESHOLD = 3
ACTION_BIAS_EVIDENCE_THRESHOLD = 3


def build_greeting(prospect_name: Optional[str] = None) -> str:
    """Personalized variant of OPENING_GREETING when a name is already known
    up front (Meeting Mode's pre-join screen — see start_session below) —
    falls back to the generic version otherwise (e.g. Product Mode's chat,
    which has no equivalent pre-join step)."""
    if not prospect_name:
        return OPENING_GREETING
    return (
        f"Hi {prospect_name}, I'm {AGENT_NAME}, sales rep at SwishX. How's your day going so far?"
    )


@dataclass
class HistoryEntry:
    role: str
    text: str


@dataclass
class SessionState:
    history: List[HistoryEntry] = field(default_factory=list)
    current_page: str = "home"
    # Set by the voice pipeline when the visitor started talking while the
    # agent was actually still speaking (tracked via pipecat's own
    # BotStartedSpeakingFrame/BotStoppedSpeakingFrame) — read once by the
    # next run_turn call so the agent knows its last explanation may have
    # landed only partially, then cleared.
    was_interrupted: bool = False
    # Set by the voice pipeline when the current turn was released with low
    # confidence it was truly the prospect's whole point AND arrived shortly
    # after the agent's own last reply (see CONTINUATION_WINDOW_SECS in
    # agent_processor.py) — read once by _build_system so the agent ties the
    # new input back to what it just said instead of restarting, then
    # cleared. Independent of was_interrupted: this fires even when there
    # was no literal audio overlap (session afe71838, turn 4 -> 5).
    low_confidence_continuation: bool = False
    # Captured once the prospect introduces themselves in response to
    # OPENING_GREETING (see runtime.py's "prospect_name" tool field) — kept
    # for the rest of the session so the agent can use it naturally later
    # (e.g. a tag-question close like "Sound good, {name}?"), not just in
    # the opening acknowledgment.
    prospect_name: Optional[str] = None
    # Captured from Meeting Mode's pre-join screen (see server.py's
    # /api/session/start) — the company name and work email the visitor gave
    # before the call even started. Real MEDDIC data points from minute one,
    # not something the agent has to go ask for.
    company: Optional[str] = None
    work_email: Optional[str] = None
    # MEDDIC qualification, captured opportunistically over the course of the
    # call (see runtime.py's tool fields of the same names) — each one set
    # once, the first time it genuinely comes up, then left alone so the
    # agent never re-asks something it already knows. Mirrors the
    # prospect_name pattern above, just for six fields instead of one.
    meddic_metrics: Optional[str] = None
    meddic_economic_buyer: Optional[str] = None
    meddic_decision_criteria: Optional[str] = None
    meddic_decision_process: Optional[str] = None
    meddic_pain: Optional[str] = None
    meddic_champion: Optional[str] = None
    # The 5-question qualification KPI (see runtime.py's
    # _qualification_note) — question 1 ("what problem brought them here")
    # deliberately has no field of its own here; it's satisfied by
    # meddic_pain above, since asking both would be two near-identical
    # questions back to back. Same "set once, on the turn it's learned"
    # pattern as the MEDDIC fields.
    qual_current_solution: Optional[str] = None
    qual_daily_users: Optional[str] = None
    qual_past_attempts: Optional[str] = None
    qual_next_step_response: Optional[str] = None
    # Asked in the opening sequence (see runtime.py instruction 0). Kept
    # separate from the MEDDIC fields because these two are asked deliberately
    # and early, by name, rather than inferred from whatever the prospect
    # happens to volunteer later.
    qual_urgency: Optional[str] = None
    qual_budget: Optional[str] = None
    # Turn number (see runtime.py's _qualification_note — len(history)//2)
    # the last qualification/MEDDIC field was captured on, 0 if none yet.
    # Drives turn-count-based escalating pressure instead of a wall-clock
    # gate — a fast-paced short call and a slow long call both get
    # proportional nudging based on actual missed opportunities, not
    # elapsed minutes, which don't distinguish the two.
    last_qual_capture_turn: int = 0
    # Wall-clock start of this session (monotonic, not calendar time) — lets
    # the prompt tell the agent how long the call has actually been running,
    # so it can pace itself toward the ~10 minute target instead of pacing
    # blind.
    started_at: float = field(default_factory=time.monotonic)
    # Position (1-10) in the scripted platform walkthrough (see
    # agent/walkthrough.py + runtime.py's _walkthrough_note) — None means no
    # tour is currently active. A plain overwrite every turn the model moves
    # position, unlike the MEDDIC/qual fields above which are set once and
    # never touched again.
    walkthrough_step: Optional[int] = None
    # True from the turn the model answers a REAL interruption mid-tour
    # (a genuine question, or asking the prospect to repeat something
    # unclear) onward — tells the voice pipeline's auto-continue scheduler
    # (agent_processor.py) to pause and stay paused, no matter how many
    # follow-up turns the prospect spends on the tangent, instead of
    # auto-advancing the moment any one reply doesn't happen to end with a
    # check-in question. STICKY, not reset every turn — only cleared by the
    # model setting "resume_walkthrough" true (a real "let's continue"),
    # or by start_walkthrough/end_walkthrough (see runtime.py's
    # _finalize_turn). This also gets set directly by agent_processor.py's
    # own "still catching up" recovery message (see AgentRuntimeProcessor's
    # _interruption_replay_depth), which never goes through the model at all.
    walkthrough_awaiting_answer: bool = False
    # An EXPLICIT stop from the prospect ("stop", "hold on", "pause",
    # "let me discuss with my colleague"), as distinct from
    # walkthrough_awaiting_answer above.
    #
    # These were one flag until a real test showed why they can't be. The
    # latch escape added for awaiting_answer (a hard ceiling, so a tour that
    # froze on a garbled transcript could recover on its own) also expired a
    # deliberate human stop: the prospect said "stop for a moment, I'll tell
    # you to continue", the flag was set correctly, and 45 seconds later the
    # ceiling released it and the tour resumed talking over him. He had to
    # say "I told you to stop, why are you continuing?".
    #
    # The two states need opposite escape rules:
    #   awaiting_answer      model got confused  -> MUST time out
    #   walkthrough_user_stopped  a human said stop -> MUST NOT, ever
    #
    # Only the prospect clears this: a real go-ahead ("continue", "carry on"),
    # or starting/ending a walkthrough outright. No timer touches it.
    walkthrough_user_stopped: bool = False
    # Transient, single-turn: the prospect's own words on THIS turn matched
    # an unambiguous request for a guided tour (see runtime.py's
    # _explicit_walkthrough_request). "full", "magicreel", "magicavatar", or
    # None. Set by _begin_turn, consumed and cleared by _finalize_turn as a
    # backstop for the model failing to set start_walkthrough itself. Never
    # persisted — it describes one turn, not the session.
    pending_walkthrough_request: Optional[str] = None
    # A DIFFERENT gap than pending_walkthrough_request above: that one only
    # covers the turn the request phrase is actually heard. Instruction 0c's
    # own documented pattern has the model ask a clarifying/confirming
    # question first ("Want to walk through it?") rather than deciding
    # outright — pending_walkthrough_request is gone by the time the
    # prospect answers "yeah" (it's re-derived fresh from THAT turn's raw
    # text every turn, via _begin_turn, and "yeah" matches no module name).
    # Set by _finalize_turn when it sees the model defer this way; consumed,
    # unconditionally, by the very next turn's _finalize_turn — confirmed
    # live (call 631341bd, 2026-08-25): the model asked to walk through
    # MagicAvatar, the prospect said "yeah," and the model narrated straight
    # into the Brief step without ever setting start_module_walkthrough —
    # so the walkthrough state machine never activated, nothing scheduled
    # the next beat, and the tour went silent until the prospect hung up.
    walkthrough_module_awaiting_confirmation: Optional[str] = None
    # Same "backstop, cleared every turn" shape as pending_walkthrough_request
    # above, for a different gap: a prospect's own words plainly asking about
    # pricing/cost/commercials/subscription/money don't reliably get the
    # Plans page opened (see runtime.py's _PRICING_INTENT / _begin_turn /
    # _pricing_backstop_action) — confirmed live (call 535e606c) with the
    # SAME wording pattern getting navigation on one ask and not the next.
    # Set by _begin_turn from the raw message, consumed in _stream_with_claude
    # / _select_with_claude only if the model chose no action itself.
    pending_pricing_request: bool = False
    # None means the active walkthrough (if any) runs the full 10-step
    # platform tour, ending naturally at step 10 — today's original
    # behavior, unchanged. A concrete step number means this is a
    # module-scoped walkthrough (see runtime.py's "start_module_walkthrough"
    # field and _walkthrough_note): auto-continue should stop once THIS
    # step is fully delivered, instead of advancing into the rest of the
    # platform tour, so "just show me MagicReel end-to-end" doesn't
    # silently roll on into MagicAvatar/MLR/home. Cleared
    # back to None by a fresh "start_walkthrough" (a genuine full-tour
    # request always means "no scoping"), set to the entry step by
    # "start_module_walkthrough" (see _finalize_turn's precedence chain).
    walkthrough_scope_end: Optional[int] = None
    # True once the model has asked a closing/qualifying question in
    # response to the prospect indicating they're leaving the call — set
    # once and never reset (same "set once" pattern as the MEDDIC/qual
    # fields above), so if they indicate leaving AGAIN later in the same
    # call, the model has a real signal to just say goodbye instead of
    # asking yet another question. Without this, each "I have to go" is
    # independently treated as a fresh opening for one more question,
    # which reads as not listening when the prospect says it twice in a row.
    farewell_question_asked: bool = False
    # True once "start-generation" has fired for the CURRENT run through
    # step 6 or 7's internal wizard (see walkthrough.py's step 6/7 guidance
    # and runtime.py's _walkthrough_note/_finalize_turn) — surfaced as
    # ground truth so the model isn't relying on rereading its own history
    # to notice it already kicked off the render, which real testing showed
    # it doesn't reliably do under auto-continue's rapid, unattended pacing:
    # confirmed live, "start-generation" fired 3 times in a row across 3
    # separate auto-continue beats, each narrated as if for the first time,
    # before the tour ever wrapped up. Cleared the instant walkthrough_step
    # actually changes value (advancing past this step, ending the tour, or
    # a fresh module/full walkthrough starting) — see _finalize_turn.
    walkthrough_generate_fired: bool = False
    # Every registry action method already fired while on the CURRENT run
    # through step 6 or 7's internal wizard (see walkthrough.py's step 6/7
    # guidance) — e.g. {"step-brief", "brief-audience"}. Same reasoning as
    # walkthrough_generate_fired above, generalized: step 6/7 stay on one
    # walkthrough_step value for 10+ turns while the model is expected to
    # track its own sub-navigation (step-source, select-source-*, step-brief,
    # brief-*, step-script, ...) purely by rereading its own conversation
    # history, and real testing showed that isn't reliable under
    # auto-continue's rapid, unattended pacing: confirmed live, "step-brief"
    # fired 3 separate times across 3 auto-continue beats, each re-narrating
    # the Brief step's intro (and re-covering sub-parts already delivered) as
    # if for the first time. Cleared the instant walkthrough_step actually
    # changes value, same as walkthrough_generate_fired.
    walkthrough_fired_actions: set = field(default_factory=set)
    # Adaptive interaction policy (see runtime.py's _interaction_note) — two
    # small, decaying evidence counters, NOT a stored "state" value. The
    # actual pace/action_bias state is always derived fresh from these on
    # read (see _pace_state/_action_bias_state), same "one source of truth"
    # reasoning as agent_processor.py's _fragmentation_protection() deriving
    # from _fragmentation_events rather than caching a separate flag.
    # Bumped by runtime.py's _begin_turn on a short reply or a match on
    # _ACTION_DEMAND_RE, decayed by turns without new evidence — a single
    # short reply is weak evidence, several in a row (or an explicit "let's
    # do the demo") is strong evidence, and it takes several quiet turns to
    # decay back down, not one. Seeded above zero at session creation by the
    # optional pre-call calibration answer (see start_session's pace_prior)
    # rather than tracked as a separate "prior" — one running number per
    # dimension, not two things to reconcile.
    pace_evidence: int = 0
    turns_since_pace_evidence: int = 0
    action_bias_evidence: int = 0
    turns_since_action_bias_evidence: int = 0
    # Single-turn backstop, same shape as pending_pricing_request/
    # pending_walkthrough_request above: set by _begin_turn when this turn's
    # raw message matches _ACTION_DEMAND_RE, consumed and cleared by
    # _finalize_turn. Confirmed live (the Jai call) that the model can
    # recognize an explicit "let's do the demo" and still not reliably act
    # on it — this turns that recognition into a directive note instead of
    # hoping the model's own read of the conversation catches it.
    pending_action_demand: bool = False
    # The same id this session is keyed by in _sessions below — kept on the
    # object itself (not just as the dict key) so run_turn() can persist each
    # turn to the durable transcript log (see data/gate_log.py) without
    # needing it threaded through as a separate parameter everywhere.
    visitor_id: Optional[str] = None


_sessions: Dict[str, SessionState] = {}


def get_session(visitor_id: str) -> SessionState:
    session = _sessions.get(visitor_id)
    if session is None:
        session = SessionState(history=[HistoryEntry(role="agent", text=OPENING_GREETING)], visitor_id=visitor_id)
        _sessions[visitor_id] = session
    return session


def start_session(
    visitor_id: str,
    prospect_name: Optional[str] = None,
    company: Optional[str] = None,
    work_email: Optional[str] = None,
    pace_prior: Optional[str] = None,
) -> SessionState:
    """Explicitly (re)starts a session for visitor_id — called once, right
    when the visitor picks a name on Meeting Mode's pre-join screen, before
    the voice connection is made. Unlike get_session, this always creates a
    fresh session (overwriting any existing one) rather than only creating
    on first-ever contact: visitor_id persists in the browser's sessionStorage
    across visits, so without this a repeat visitor (or a dev re-testing the
    same browser tab) would silently resume a stale conversation instead of
    starting the new call they just asked for.

    pace_prior is the pre-call calibration screen's answer (see
    PreCallCalibrationScreen.tsx) — "fast", "self_directed", or None (either
    "walk me through everything" or skipped). Seeds the adaptive-interaction
    evidence counters straight to/above threshold rather than starting cold,
    so turn one is already calibrated instead of learned the hard way several
    turns in — but it's still just a starting value on the same counter
    mid-call evidence keeps updating, not a locked-in mode (see runtime.py's
    _interaction_note)."""
    session = SessionState(
        history=[HistoryEntry(role="agent", text=build_greeting(prospect_name))],
        prospect_name=prospect_name,
        company=company,
        work_email=work_email,
        visitor_id=visitor_id,
    )
    if pace_prior == "fast":
        session.pace_evidence = PACE_EVIDENCE_THRESHOLD
        session.action_bias_evidence = ACTION_BIAS_EVIDENCE_THRESHOLD
    elif pace_prior == "self_directed":
        session.action_bias_evidence = ACTION_BIAS_EVIDENCE_THRESHOLD
    _sessions[visitor_id] = session
    return session
