"""Outbound transactional email, sent through Postmark's REST API.

Two things go out from here and nothing else: the 6-digit code that verifies
a visitor's work address at the gate (see server.py's /api/visitor/otp/*),
and the recap that follows a finished call (see send_summary_email, called
from the existing call-summary path in voice/bot.py).

Postmark is called over plain HTTP rather than through their SDK: this is two
POSTs to one endpoint with a token header, and a hand-rolled request keeps the
failure surface something we can actually see and log (see _postmark_send's
error handling, which the gate depends on to refuse a visitor rather than wave
them through on a send that never happened).

Both messages are built as multipart HTML + plain text. The HTML is
table-based with inline styles only — Outlook's Word rendering engine ignores
<style> blocks, flexbox, and most modern CSS, so anything that isn't an inline
style on a table cell is not a layout decision, it's a suggestion. Colours are
committed dark rather than assuming a white page: Gmail and Outlook dark modes
will happily invert a light background out from under light text, and a
surface that is already dark comes through both modes unchanged.
"""

import base64
import os
import re
from typing import List, Optional, Tuple

import requests
from loguru import logger

from . import gate_log

POSTMARK_ENDPOINT = "https://api.postmarkapp.com/email"
# Long enough to survive an ordinary slow round-trip, short enough that a
# hung Postmark can't hold a gate request (or a call-teardown task) open
# indefinitely.
_POSTMARK_TIMEOUT_SECS = 15

# --- OTP policy. Enforced in server.py; defined here so the values the email
# copy quotes ("expires in 10 minutes") and the values the code actually
# enforces can never drift apart. ---
OTP_TTL_SECS = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_SEND_WINDOW_SECS = 15 * 60
OTP_MAX_SENDS_PER_WINDOW = 3
OTP_RESEND_COOLDOWN_SECS = 30

SITE_URL = "https://www.swishx.com/"
CALENDAR_URL = "https://www.swishx.com/calendar"

# The showcase reel, served by the same nginx that serves the frontend (it
# lives in frontend/public, which ships to the site root — see
# .github/workflows/deploy.yml). A public URL, not a relative one: an email
# client has no origin to resolve a relative path against.
SHOWCASE_VIDEO_URL = "https://contentiq-demo.benplat.in/videos/tecentriq-reel.mp4"
SHOWCASE_VIDEO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "frontend",
    "public",
    "videos",
    "tecentriq-reel.mp4",
)

# Postmark caps a whole message at 10MB, and attachments travel base64-encoded
# — which costs ~33% on top of the file's real size. So the usable ceiling for
# the file itself is ~7.5MB, not 10; anything above that is linked instead of
# attached. Sizing this against the raw file size and forgetting the encoding
# overhead is the classic way to build something that passes locally and then
# gets rejected by the API on a 9MB video.
_MAX_ATTACHMENT_BYTES = 7 * 1024 * 1024

# The one palette, shared by both templates. Dark surface on purpose (see the
# module docstring); every text colour below is chosen to clear WCAG AA
# against _INK.
_INK = "#0e0e10"        # page behind the card
_SURFACE = "#17171a"    # the card itself
_RAISE = "#202024"      # inset panels (the code box, the summary block)
_LINE = "#2e2e34"
_TEXT = "#f2efec"
_MUTED = "#9a938c"
_ACCENT = "#ff4f00"

_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
_MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"


class EmailSendError(RuntimeError):
    """Raised for every reason a send can fail — unconfigured credentials, a
    network error, or a non-200 from Postmark. Callers are expected to catch
    this and surface something to the user; the gate in particular must fail
    closed on it rather than letting an unverified visitor through."""


def _postmark_send(
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    tag: str,
    attachments: Optional[List[dict]] = None,
) -> str:
    """POSTs one message and returns Postmark's MessageID. Credentials are
    read at call time, not at import: the voice process loads its .env
    partway down its own import chain (see voice/bot.py's load_dotenv
    comment), so a module-level read here would bake in whatever was set at
    whichever moment this module happened to get imported."""
    token = os.getenv("POSTMARK_API_KEY")
    sender = os.getenv("POSTMARK_EMAIL")
    if not token or not sender:
        raise EmailSendError("Postmark is not configured — POSTMARK_API_KEY and POSTMARK_EMAIL must both be set")

    payload = {
        "From": sender,
        "To": to,
        "Subject": subject,
        "HtmlBody": html_body,
        "TextBody": text_body,
        "MessageStream": "outbound",
        "Tag": tag,
    }
    if attachments:
        payload["Attachments"] = attachments

    try:
        response = requests.post(
            POSTMARK_ENDPOINT,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": token,
            },
            timeout=_POSTMARK_TIMEOUT_SECS,
        )
    except requests.RequestException as exc:
        # Loud on purpose. A silent failure here means a visitor sits at a
        # code entry screen waiting on an email that was never sent, and
        # nothing in the logs says why.
        logger.exception(f"Postmark request failed for tag={tag} to={to}")
        raise EmailSendError(f"Could not reach Postmark: {exc}") from exc

    # Postmark reports application errors (bad token, unconfirmed sender
    # signature, inactive recipient) as a non-200 with an ErrorCode in the
    # body, not as a transport error — so a bare status check is not enough
    # context to debug from. The token is never part of what gets logged.
    if response.status_code != 200:
        detail = response.text[:500]
        logger.error(f"Postmark rejected tag={tag} to={to} status={response.status_code} body={detail}")
        raise EmailSendError(f"Postmark returned {response.status_code}: {detail}")

    body = response.json()
    message_id = body.get("MessageID", "")
    logger.info(f"Postmark accepted tag={tag} to={to} MessageID={message_id}")
    return message_id


# --------------------------------------------------------------------------
# Shared chrome
# --------------------------------------------------------------------------

def _escape(value: str) -> str:
    """Minimal HTML escaping. Everything interpolated into a template below
    is untrusted to some degree — a visitor types their own name and company
    at the gate, and the call summary is LLM output — so all of it goes
    through here rather than relying on any of it being well behaved."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _document(title: str, inner: str) -> str:
    """Wraps a card's contents in the outer scaffolding both emails share:
    the 100%-width background table, then a fixed 600px card table inside it.

    The width is set as BOTH a width="600" attribute and a max-width style.
    Outlook honours the attribute and ignores the style; every other client
    does the reverse and stays fluid on a phone. Dropping either one breaks
    one half of the audience."""
    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<!-- Tells Apple Mail and Outlook this message has already handled both
     schemes, which stops them applying their own colour inversion on top. -->
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
<title>{_escape(title)}</title>
</head>
<body style="margin:0;padding:0;background-color:{_INK};color:{_TEXT};-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_INK}" style="margin:0;padding:0;background-color:{_INK};">
<tr>
<td align="center" style="padding:32px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="{_SURFACE}" style="width:100%;max-width:600px;background-color:{_SURFACE};border:1px solid {_LINE};border-radius:14px;">
{inner}
</table>
</td>
</tr>
</table>
</body>
</html>"""


def _header_row() -> str:
    """Wordmark as live text, not an image — most clients block remote images
    by default, and a blocked logo means the message opens with a broken
    rectangle where the brand should be."""
    return f"""<tr>
<td style="padding:28px 32px 0 32px;font-family:{_FONT};font-size:17px;font-weight:700;letter-spacing:-0.01em;color:{_TEXT};">
SwishX<span style="color:{_ACCENT};">.</span>
</td>
</tr>"""


def _footer_row(note: str) -> str:
    return f"""<tr>
<td style="padding:8px 32px 28px 32px;border-top:1px solid {_LINE};font-family:{_FONT};font-size:12px;line-height:19px;color:{_MUTED};">
<div style="padding-top:16px;">{note}</div>
</td>
</tr>"""


def _button(label: str, href: str) -> str:
    """A padded anchor, not a nested VML button. Outlook renders this as a
    plain padded link rather than a rounded pill — visually plainer, but it
    always works, which a VML shape only does until someone edits the markup
    around it."""
    return (
        f'<a href="{href}" style="display:inline-block;background-color:{_ACCENT};color:#ffffff;'
        f"font-family:{_FONT};font-size:15px;font-weight:600;text-decoration:none;"
        f'padding:13px 26px;border-radius:10px;mso-padding-alt:13px 26px;">{_escape(label)}</a>'
    )


# --------------------------------------------------------------------------
# 1. Gate verification code
# --------------------------------------------------------------------------

def send_otp_email(to_email: str, code: str) -> str:
    """Sends one verification code and returns Postmark's MessageID. Raises
    EmailSendError on any failure — server.py turns that into an error the
    gate form can show, and specifically does NOT let the visitor past."""
    minutes = OTP_TTL_SECS // 60
    subject = "Your SwishX demo code"

    inner = f"""{_header_row()}
<tr>
<td style="padding:24px 32px 0 32px;font-family:{_FONT};font-size:15px;line-height:24px;color:{_TEXT};">
Here is your verification code.
</td>
</tr>
<tr>
<td style="padding:20px 32px 0 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_RAISE}" style="background-color:{_RAISE};border:1px solid {_LINE};border-radius:12px;">
<tr>
<td align="center" style="padding:24px 16px;font-family:{_MONO};font-size:38px;line-height:44px;font-weight:700;letter-spacing:0.22em;color:{_TEXT};mso-line-height-rule:exactly;">
{_escape(code)}
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="padding:18px 32px 24px 32px;font-family:{_FONT};font-size:14px;line-height:22px;color:{_MUTED};">
It expires in {minutes} minutes. If you didn't ask for this, you can ignore this email.
</td>
</tr>
{_footer_row("SwishX — AI content for pharma marketing teams.")}"""

    text_body = (
        "Your SwishX demo code\n\n"
        f"    {code}\n\n"
        f"It expires in {minutes} minutes.\n"
        "If you didn't ask for this, you can ignore this email.\n\n"
        "-- \nSwishX - AI content for pharma marketing teams\n"
        f"{SITE_URL}\n"
    )

    return _postmark_send(
        to=to_email,
        subject=subject,
        html_body=_document(subject, inner),
        text_body=text_body,
        tag="visitor-otp",
    )


# --------------------------------------------------------------------------
# 2. Post-call recap
# --------------------------------------------------------------------------

# Two sentences, held to two deliberately. This is a reminder for someone who
# just spent half an hour being shown the product, not a re-pitch.
_NUTSHELL = (
    "SwishX is an AI content platform for pharma marketing teams — MLR-ready content in minutes "
    "rather than weeks, because on-label claims, references, fair balance and ISI are built in at "
    "generation time instead of caught in review. Thirty content formats across five Magic Engines, "
    "all generated from one Brand Kit so every asset stays on-brand automatically."
)

_NUTSHELL_TEXT = (
    "SwishX is an AI content platform for pharma marketing teams - MLR-ready content in\n"
    "minutes rather than weeks, because on-label claims, references, fair balance and ISI\n"
    "are built in at generation time instead of caught in review. Thirty content formats\n"
    "across five Magic Engines, all generated from one Brand Kit so every asset stays\n"
    "on-brand automatically."
)

# Phrases that mark a sentence in the generated summary as forward-looking.
# generate_call_summary (agent/runtime.py) is explicitly prompted to cover
# "any clear next step", so when the call produced one it is reliably phrased
# in one of these ways.
_NEXT_STEP_SIGNALS = (
    "next step",
    "next steps",
    "follow up",
    "follow-up",
    "wants to",
    "asked for",
    "asked to",
    "would like",
    "interested in seeing",
    "schedule",
    "scheduling",
    "pilot",
    "trial",
    "proposal",
    "pricing",
    "introduce",
    "loop in",
    "circle back",
    "reconnect",
)


# Phrases that mark a sentence as written for US, not for the prospect.
#
# This filter is not cosmetic and it is not optional. The stored summary is
# generated for a SALES REP — generate_call_summary's own system prompt (see
# agent/runtime.py) asks it to cover "how qualified they seem" — and this is
# the only place that rep-facing text gets forwarded to the prospect
# themselves. A verbatim recap cheerfully tells the person on the other end
# that they are "well qualified", who we think their budget owner is, and
# which of our competitors we believe they're talking to. That is a real
# incident, not an awkward sentence, and it is invisible until the day a
# summary happens to include one.
#
# Matched on substrings against a tight list rather than anything clever:
# a false positive costs one dropped sentence out of a recap, a false
# negative costs a customer relationship, so the trade is deliberately
# lopsided in favour of dropping too much.
_INTERNAL_ONLY_SIGNALS = (
    "qualified",
    "qualification",
    "budget owner",
    "budget holder",
    "economic buyer",
    "decision maker",
    "decision-maker",
    "champion",
    "competitor",
    "competing",
    "other vendors",
    "meddic",
    "deal size",
    "red flag",
)


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _prospect_safe_sentences(summary: str) -> List[str]:
    """The summary as it can safely be shown to the person it is about — see
    _INTERNAL_ONLY_SIGNALS. Every consumer of the summary in this module goes
    through here; nothing reads the raw text directly."""
    return [s for s in _sentences(summary) if not any(sig in s.lower() for sig in _INTERNAL_ONLY_SIGNALS)]


def _summary_paragraphs(summary: str) -> List[str]:
    """The stored summary is a single prose blob of up to ~150 words. Read
    end to end in an email that is a wall; regrouped two sentences at a time
    it is skimmable, which is the only thing anyone actually does with a
    recap. Beyond the redaction above, not a word is rewritten — the grouping
    is the only thing happening here."""
    sentences = _prospect_safe_sentences(summary)
    return [" ".join(sentences[i : i + 2]) for i in range(0, len(sentences), 2)]


def _next_steps(summary: str) -> List[str]:
    """Pulls forward-looking sentences out of the summary so the next steps
    are the ones this call actually produced, not boilerplate. Falls back to
    two generic-but-concrete asks when the call didn't produce any — better
    than an empty section, and honest, since nothing is being invented about
    what was discussed."""
    # Escaped here rather than at the call site, because unlike every other
    # interpolated value these list items are a MIX of untrusted text and
    # deliberate markup (the calendar link below) — so the call site can't
    # escape the lot without destroying the anchor.
    picked = [
        _escape(s) for s in _prospect_safe_sentences(summary) if any(sig in s.lower() for sig in _NEXT_STEP_SIGNALS)
    ]
    steps = picked[:3]
    steps.append(f'Book a follow-up with the team: <a href="{CALENDAR_URL}" style="color:{_ACCENT};">swishx.com/calendar</a>')
    if not picked:
        steps.insert(0, "Share this recap with anyone on your team who couldn't make the call.")
    return steps


def _next_steps_text(summary: str) -> List[str]:
    picked = [s for s in _prospect_safe_sentences(summary) if any(sig in s.lower() for sig in _NEXT_STEP_SIGNALS)]
    steps = picked[:3]
    steps.append(f"Book a follow-up with the team: {CALENDAR_URL}")
    if not picked:
        steps.insert(0, "Share this recap with anyone on your team who couldn't make the call.")
    return steps


def _video_attachment() -> Tuple[Optional[dict], str]:
    """Returns (attachment_or_None, reason). Size is checked against the real
    file every time rather than assumed once: the reel gets re-cut, and the
    difference between a 6MB and a 12MB version is the difference between an
    email that sends and one Postmark rejects outright (see
    _MAX_ATTACHMENT_BYTES for why the ceiling is 7MB, not 10)."""
    try:
        size = os.path.getsize(SHOWCASE_VIDEO_PATH)
    except OSError as exc:
        logger.warning(f"Showcase video not readable at {SHOWCASE_VIDEO_PATH} ({exc}) — linking instead")
        return None, "unreadable"
    if size > _MAX_ATTACHMENT_BYTES:
        logger.info(
            f"Showcase video is {size / 1024 / 1024:.1f}MB, over the "
            f"{_MAX_ATTACHMENT_BYTES / 1024 / 1024:.1f}MB attach ceiling — linking instead"
        )
        return None, "too_large"
    with open(SHOWCASE_VIDEO_PATH, "rb") as fh:
        content = base64.b64encode(fh.read()).decode("ascii")
    return (
        {
            "Name": "swishx-showcase.mp4",
            "Content": content,
            "ContentType": "video/mp4",
        },
        "attached",
    )


def build_summary_email(
    name: Optional[str],
    company: Optional[str],
    summary: str,
    video_attached: bool,
) -> Tuple[str, str, str]:
    """Returns (subject, html, text). Split out from the send so the whole
    template can be rendered and eyeballed without putting a message through
    Postmark.

    `video_attached` is passed in rather than re-derived here so the file is
    read and base64-encoded exactly once per send — the copy has to agree
    with what the message actually carries, and the cheapest way to guarantee
    that is for one decision to feed both."""
    first_name = (name or "").strip().split(" ")[0] if name else ""
    if first_name and company:
        greeting = f"Hi {first_name} — great speaking with the team at {company} today."
    elif first_name:
        greeting = f"Hi {first_name} — great speaking with you today."
    else:
        greeting = "Great speaking with you today."

    subject = f"Your SwishX demo recap{f' — {company}' if company else ''}"

    if video_attached:
        video_line = "The showcase reel from the call is attached to this email."
        video_line_text = "The showcase reel from the call is attached to this email."
    else:
        video_line = (
            f'The showcase reel is too large to attach, so here it is instead: '
            f'<a href="{SHOWCASE_VIDEO_URL}" style="color:{_ACCENT};">watch the SwishX reel</a>.'
        )
        video_line_text = f"The showcase reel is too large to attach, so here it is instead:\n{SHOWCASE_VIDEO_URL}"

    paragraphs = "".join(
        f'<p style="margin:0 0 14px 0;font-family:{_FONT};font-size:15px;line-height:24px;color:{_TEXT};">{_escape(p)}</p>'
        for p in _summary_paragraphs(summary)
    )
    steps = "".join(
        f'<li style="margin:0 0 10px 0;font-family:{_FONT};font-size:15px;line-height:23px;color:{_TEXT};">{step}</li>'
        for step in _next_steps(summary)
    )

    inner = f"""{_header_row()}
<tr>
<td style="padding:24px 32px 0 32px;font-family:{_FONT};font-size:17px;line-height:26px;font-weight:600;color:{_TEXT};">
{_escape(greeting)}
</td>
</tr>
<tr>
<td style="padding:14px 32px 0 32px;font-family:{_FONT};font-size:15px;line-height:24px;color:{_MUTED};">
{_NUTSHELL}
</td>
</tr>

<tr>
<td style="padding:28px 32px 0 32px;font-family:{_FONT};font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:{_MUTED};">
What we covered
</td>
</tr>
<tr>
<td style="padding:12px 32px 0 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_RAISE}" style="background-color:{_RAISE};border:1px solid {_LINE};border-radius:12px;">
<tr><td style="padding:20px 22px 6px 22px;">{paragraphs}</td></tr>
</table>
</td>
</tr>

<tr>
<td style="padding:28px 32px 0 32px;font-family:{_FONT};font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:{_MUTED};">
Suggested next steps
</td>
</tr>
<tr>
<td style="padding:12px 32px 0 32px;">
<ul style="margin:0;padding:0 0 0 20px;">{steps}</ul>
</td>
</tr>

<tr>
<td style="padding:26px 32px 0 32px;">{_button("Book time with us", CALENDAR_URL)}</td>
</tr>
<tr>
<td style="padding:16px 32px 26px 32px;font-family:{_FONT};font-size:14px;line-height:22px;color:{_MUTED};">
{video_line}<br />
More at <a href="{SITE_URL}" style="color:{_ACCENT};">swishx.com</a>.
</td>
</tr>
{_footer_row("You're receiving this because you joined a SwishX demo. Reply to this email and a human will answer.")}"""

    text_body = "\n".join(
        [
            greeting,
            "",
            _NUTSHELL_TEXT,
            "",
            "WHAT WE COVERED",
            "",
            "\n\n".join(_summary_paragraphs(summary)),
            "",
            "SUGGESTED NEXT STEPS",
            "",
            "\n".join(f"  - {s}" for s in _next_steps_text(summary)),
            "",
            "LINKS",
            f"  SwishX: {SITE_URL}",
            f"  Book time: {CALENDAR_URL}",
            "",
            video_line_text,
            "",
            "-- ",
            "You're receiving this because you joined a SwishX demo.",
            "Reply to this email and a human will answer.",
        ]
    )

    return subject, _document(subject, inner), text_body


def send_summary_email(visitor_id: str, summary: Optional[str] = None) -> Optional[str]:
    """Emails the post-call recap for one session and returns the MessageID,
    or None when there is nothing to send.

    Deliberately takes a visitor_id and nothing else required: the existing
    call-summary path (voice/bot.py's _save_call_summary) has exactly that
    and the summary text, so wiring this in is a single call with no new
    plumbing. Everything else — who to email, their name and company — is
    looked up here.

    Never raises. This runs inside call teardown, where an unhandled
    exception would land in a fire-and-forget task and take other teardown
    work with it; a recap that failed to send is worth a loud log line, not a
    broken hangup."""
    try:
        if summary is None:
            summary = gate_log.get_call_summary(visitor_id)
        if not summary:
            logger.info(f"No call summary for visitor {visitor_id} — skipping recap email")
            return None

        # A summary made entirely of internal assessment leaves nothing to
        # recap. Sending the shell anyway — greeting, pitch, links, no
        # content — reads worse than not writing at all, and quietly falling
        # back to the unredacted text would defeat the whole filter.
        if not _prospect_safe_sentences(summary):
            logger.warning(
                f"Call summary for visitor {visitor_id} is entirely rep-facing after redaction "
                "— skipping recap email rather than sending an empty one"
            )
            return None

        identity = gate_log.get_visitor_identity(visitor_id)
        if not identity or not identity["email"]:
            logger.warning(f"No gated identity for visitor {visitor_id} — cannot send recap email")
            return None

        # Checked here rather than by the caller so every entry point gets the
        # guard for free — see gate_log.summary_emails for why the same
        # session can legitimately reach this more than once.
        if gate_log.summary_email_sent(visitor_id):
            logger.info(f"Recap email already sent for visitor {visitor_id} — not sending again")
            return None

        attachment, attach_reason = _video_attachment()
        logger.info(f"Recap email for visitor {visitor_id} — showcase video: {attach_reason}")
        subject, html_body, text_body = build_summary_email(
            identity["name"], identity["company"], summary, video_attached=attachment is not None
        )
        message_id = _postmark_send(
            to=identity["email"],
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tag="call-recap",
            attachments=[attachment] if attachment else None,
        )
        gate_log.record_summary_email(visitor_id, identity["email"], message_id)
        return message_id
    except Exception:
        logger.exception(f"Failed to send recap email for visitor {visitor_id}")
        return None
