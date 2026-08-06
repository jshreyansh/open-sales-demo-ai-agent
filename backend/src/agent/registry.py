import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class RegistryAction:
    id: str
    description: str


@dataclass
class RegistryComponent:
    id: str
    label: str
    description: str
    actions: List[RegistryAction]


@dataclass
class RegistryPage:
    id: str
    label: str
    components: List[RegistryComponent]


@dataclass
class ContentFormatSpec:
    engine_tab: str
    title: str
    tool: str
    slug: str
    description: str
    audience: str
    stage: str
    promo: str
    lead: str
    soon: bool
    inputs: List[str] = field(default_factory=list)


# Mirrors frontend/src/registry/contentStudio.ts — no shared code between the
# two packages, so this is hand-kept in sync. `slug` must match formatSlug(tool)
# on the frontend exactly, since it's the uiRegistry component id the agent
# uses to open one specific format's modal (not just switch engine tabs).
CONTENT_STUDIO_FORMATS: List[ContentFormatSpec] = [
    # --- Magic Video ---
    ContentFormatSpec(
        engine_tab="Video", title="Short Video", tool="MagicReel™", slug="magicreel",
        description="A 30–180s customisable video built from the brand dossier. Used across HCP and patient channels: email, social, congress, web, rep follow-up.",
        audience="HCP + Patient", stage="Awareness, Consideration", promo="Promotional", lead="Creative Producer", soon=False,
        inputs=["Foundational dossier / brand KB", "Approved label / PI", "Reference library", "Brand identity kit", "Target channel & duration", "Voice / music / caption prefs"],
    ),
    ContentFormatSpec(
        engine_tab="Video", title="Digital Twin Master Video", tool="MagicAvatar™", slug="magicavatar",
        description="The doctor's own voice and photo generate a lip-synced presenter, so the asset feels as if the physician made it personally for the patient.",
        audience="Patient", stage="Awareness, Adherence / Loyalty", promo="Promotional", lead="Creative Producer", soon=False,
        inputs=["Doctor voice sample & consent", "Doctor photo", "Base video or approved script", "Consent & rights documentation", "Brand identity kit"],
    ),
    ContentFormatSpec(
        engine_tab="Video", title="Broadcast / DTC Video Ad", tool="MagicSpot", slug="magicspot",
        description="A 30–60s DTC television or streaming spot — the single largest DTC spend category in US pharma marketing.",
        audience="Patient", stage="Awareness", promo="Promotional", lead="Creative Producer", soon=True,
        inputs=["Creative brief & patient insight", "Approved label / PI", "Indication statement", "ISI + broadcast major statement (audio + on-screen)", "Adequate-provision fulfilment plan"],
    ),
    ContentFormatSpec(
        engine_tab="Video", title="MOA / Explainer Animation", tool="MagicMotion", slug="magicmotion",
        description="Mechanism-of-action animation visualising how the drug works at molecular and cellular level.",
        audience="HCP + Patient", stage="Consideration", promo="Promotional", lead="Creative Producer", soon=True,
        inputs=["Scientific source (pathway data, PK/PD, publications)", "Approved label", "Reference library", "Audience level (HCP vs patient)", "Brand identity kit"],
    ),
    ContentFormatSpec(
        engine_tab="Video", title="Webinar & Event Video", tool="MagicStage", slug="magicstage",
        description="Speaker-led webinar and congress event video — recorded, chaptered, and cut down into shareable clips.",
        audience="HCP", stage="Consideration", promo="Mixed", lead="Creative Producer", soon=True,
        inputs=["Speaker deck & notes", "Approved claims", "Event branding", "Disclosure requirements"],
    ),
    ContentFormatSpec(
        engine_tab="Video", title="Patient Story Video", tool="MagicStory", slug="magicstory",
        description="Patient testimonial and lived-experience storytelling for disease awareness and adherence, with the consent and typicality guardrails the format demands.",
        audience="Patient", stage="Awareness, Adherence / Loyalty", promo="Promotional", lead="Creative Producer", soon=True,
        inputs=["Patient consent & release", "Story outline", "Approved label boundaries", "ISI / fair balance where branded"],
    ),
    # --- Magic Aid ---
    ContentFormatSpec(
        engine_tab="Aid", title="Interactive Visual Aid (IVA / CLM)", tool="MagicCLM", slug="magicclm",
        description="The rep-facing interactive detail aid — clickable MOA tabs, safety callouts, chapter jumps, inline quiz points and talking prompts, delivered through CLM.",
        audience="HCP", stage="Consideration, Trial / Adoption", promo="Promotional", lead="Creative Producer", soon=True,
        inputs=["Brand dossier", "Approved claims & references", "ISI and fair balance", "Brand template", "CLM/Veeva packaging spec"],
    ),
    ContentFormatSpec(
        engine_tab="Aid", title="e-Detail / Remote Deck", tool="MagicDetail", slug="magicdetail",
        description="The remote-detailing deck a rep presents over video — a tighter, self-navigating cut of the visual aid built for a 10-minute virtual call.",
        audience="HCP", stage="Consideration, Trial / Adoption", promo="Promotional", lead="Content Strategist", soon=True,
        inputs=["Approved claims & references", "Call objective", "ISI and fair balance", "Brand template"],
    ),
    ContentFormatSpec(
        engine_tab="Aid", title="Leave-Behind", tool="MagicLeave", slug="magicleave",
        description="The printed or digital piece the rep leaves with the physician — the claims that must survive without the rep in the room.",
        audience="HCP", stage="Consideration", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Approved claims & references", "ISI", "Brand template", "Print/digital spec"],
    ),
    ContentFormatSpec(
        engine_tab="Aid", title="Reprint Carrier", tool="MagicCarrier", slug="magiccarrier",
        description="The branded wrapper around a published journal reprint — heavily scrutinised, because the framing must not overstate what the paper found.",
        audience="HCP", stage="Consideration", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["The reprint itself", "Approved claims", "Fair balance & ISI", "Journal permissions"],
    ),
    ContentFormatSpec(
        engine_tab="Aid", title="Dosing & Titration Guide", tool="MagicDose", slug="magicdose",
        description="The practical dosing, titration and administration reference — pure label derivation, where accuracy matters more than persuasion.",
        audience="HCP", stage="Trial / Adoption, Adherence / Loyalty", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Approved label / PI dosing section", "Renal/hepatic adjustments", "Special populations", "Brand template"],
    ),
    ContentFormatSpec(
        engine_tab="Aid", title="FAQ / Objection Handler", tool="MagicAnswer", slug="magicanswer",
        description="The rep-facing answer set for the questions and objections that actually come up in the room, each answer grounded on-label.",
        audience="HCP", stage="Consideration, Trial / Adoption", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Brand dossier FAQ section", "Competitive context", "Approved claims", "On-label boundaries"],
    ),
    # --- Magic Mail ---
    ContentFormatSpec(
        engine_tab="Mail", title="Approved Email", tool="MagicSend", slug="magicsend",
        description="The rep-triggered approved email — the highest-volume, cleanest-ROI proof of the platform, and the format the go-to-market leads with.",
        audience="HCP", stage="Consideration, Trial / Adoption, Adherence / Loyalty", promo="Promotional", lead="Content Strategist", soon=True,
        inputs=["Approved claims & references", "ISI", "Brand template", "CRM/Veeva approved-email spec"],
    ),
    ContentFormatSpec(
        engine_tab="Mail", title="Multi-touch Campaign", tool="MagicFlow", slug="magicflow",
        description="A sequenced journey across touches and channels, where the Content Strategist designs the arc and every touch inherits cleared modules.",
        audience="HCP + Patient", stage="Awareness, Consideration, Trial / Adoption, Adherence / Loyalty", promo="Promotional", lead="Content Strategist", soon=True,
        inputs=["Objective & journey stage", "Audience segments", "Approved module library", "Channel mix & cadence"],
    ),
    ContentFormatSpec(
        engine_tab="Mail", title="e-Newsletter", tool="MagicBrief", slug="magicbrief",
        description="The recurring scientific or brand newsletter — lowest MLR burden of the thirty, and the most punishing to produce by hand at cadence.",
        audience="HCP", stage="Adherence / Loyalty", promo="Mixed", lead="Medical Writer", soon=True,
        inputs=["Content calendar", "Source publications", "Approved claims where branded", "Template"],
    ),
    # --- Magic Canvas ---
    ContentFormatSpec(
        engine_tab="Canvas", title="Infographic", tool="MagicChart", slug="magicchart",
        description="Data and disease-state storytelling as a single designed visual, tuned to an HCP or a patient reading level.",
        audience="HCP + Patient", stage="Awareness, Consideration", promo="Promotional", lead="Creative Producer", soon=False,
        inputs=["Source data / trial results", "Reference library", "Audience level", "Brand identity kit"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Banner / Display Ad", tool="MagicBanner", slug="magicbanner",
        description="The programmatic display set — every IAB size, every variant, each carrying its own ISI treatment and PI link.",
        audience="HCP + Patient", stage="Awareness", promo="Promotional", lead="Creative Producer", soon=False,
        inputs=["Approved claim (short form)", "ISI / PI link", "Brand identity kit", "IAB size matrix"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Journal / Print Ad", tool="MagicPress", slug="magicpress",
        description="The peer-reviewed journal spread, where the brief summary / PI page is not an afterthought but half the deliverable.",
        audience="HCP", stage="Awareness, Consideration", promo="Promotional", lead="Creative Producer", soon=False,
        inputs=["Approved claims & references", "Full PI for the brief-summary page", "Fair balance", "Print spec"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Social Post / Campaign", tool="MagicPost", slug="magicpost",
        description="Organic and paid social, where the character limit collides with fair balance and the unbranded/branded decision is the whole game.",
        audience="Patient + HCP", stage="Awareness", promo="Promotional", lead="Content Strategist", soon=False,
        inputs=["Campaign angle", "Branded vs unbranded framing", "ISI / fair balance where branded", "Platform specs"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Savings / Co-pay Card", tool="MagicSave", slug="magicsave",
        description="The co-pay offer and its terms — the access instrument that converts a first prescription into a filled one.",
        audience="Patient", stage="Trial / Adoption", promo="Promotional", lead="Medical Writer", soon=False,
        inputs=["Offer terms & eligibility", "Legal restrictions (no federal beneficiaries)", "Brand identity kit", "Redemption mechanics"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Congress Poster / Booth", tool="MagicBooth", slug="magicbooth",
        description="Scientific poster and booth panel graphics, produced against congress deadlines that never move.",
        audience="HCP", stage="Consideration", promo="Promotional", lead="Creative Producer", soon=False,
        inputs=["Abstract / data", "Reference library", "Congress spec & dimensions", "Brand identity kit"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Point-of-Care Asset", tool="MagicPoint", slug="magicpoint",
        description="Waiting-room and exam-room media — posters, screens, and take-ones reaching the patient minutes before the conversation.",
        audience="Patient", stage="Awareness", promo="Promotional", lead="Creative Producer", soon=True,
        inputs=["Disease-state framing", "ISI / PI access", "Channel network spec", "Brand identity kit"],
    ),
    ContentFormatSpec(
        engine_tab="Canvas", title="Web Destination", tool="MagicSite", slug="magicsite",
        description="The branded HCP or patient site — an interactive build, which is why it sits in Canvas rather than Doc.",
        audience="HCP + Patient", stage="Awareness, Consideration, Adherence / Loyalty", promo="Promotional", lead="Content Strategist", soon=True,
        inputs=["Site architecture & objective", "Approved claims & references", "ISI, PI fulfilment, adequate provision", "Brand identity kit", "Audience gating rules"],
    ),
    # --- Magic Doc ---
    ContentFormatSpec(
        engine_tab="Doc", title="Product Monograph", tool="MagicMono", slug="magicmono",
        description="The comprehensive clinical reference on the brand — the longest promotional document a medical team will write.",
        audience="HCP", stage="Consideration", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Full clinical dataset", "Approved label / PI", "Reference library", "Fair balance & ISI"],
    ),
    ContentFormatSpec(
        engine_tab="Doc", title="HCP / Sales Brochure", tool="MagicFolio", slug="magicfolio",
        description="The core HCP brochure — the claims, the evidence, the safety, in the order a prescriber actually reads them.",
        audience="HCP", stage="Consideration", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Approved claims & references", "ISI", "Fair balance", "Brand template"],
    ),
    ContentFormatSpec(
        engine_tab="Doc", title="Patient Brochure / Leaflet", tool="MagicLeaflet", slug="magicleaflet",
        description="Plain-language patient education, held to a reading level and to the same fair-balance standard as any promotional piece.",
        audience="Patient", stage="Awareness, Adherence / Loyalty", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Approved label in plain language", "Reading-level target", "ISI / safety in patient language", "Brand identity kit"],
    ),
    ContentFormatSpec(
        engine_tab="Doc", title="AMCP / Formulary Dossier", tool="MagicDossier", slug="magicdossier",
        description="The AMCP-format payer dossier — the deepest source-grounding requirement of all thirty formats, which is why it builds last.",
        audience="Payer", stage="Trial / Adoption", promo="Promotional", lead="Medical Writer", soon=True,
        inputs=["Full clinical & economic evidence", "Health-economic models", "AMCP format specification", "Unapproved-use governance rules"],
    ),
    ContentFormatSpec(
        engine_tab="Doc", title="MSL / Medical Deck", tool="MagicMSL", slug="magicmsl",
        description="The scientific-exchange deck for Medical Science Liaisons — governed by medical affairs under Vault MedComms, not promotional MLR.",
        audience="HCP", stage="Consideration", promo="Non-promotional", lead="Medical Writer", soon=True,
        inputs=["Full scientific data & publications", "Reference library", "Medical-affairs governance rules", "Scientific-exchange boundaries"],
    ),
    ContentFormatSpec(
        engine_tab="Doc", title="KOL / Speaker Deck", tool="MagicSpeaker", slug="magicspeaker",
        description="The locked, on-label speaker deck a paid KOL presents to peers — content-lock enforcement is the whole compliance surface.",
        audience="HCP", stage="Consideration", promo="Mixed", lead="Content Strategist", soon=True,
        inputs=["Approved claims & references", "Indication, ISI, fair balance", "Speaker disclosure requirements", "Locked-content rules"],
    ),
    ContentFormatSpec(
        engine_tab="Doc", title="White Paper / Publication Summary", tool="MagicPaper", slug="magicpaper",
        description="Thought-leadership or a plain-language summary of published evidence — usually unbranded, and the framing decision is the control.",
        audience="HCP", stage="Consideration", promo="Non-promotional", lead="Medical Writer", soon=True,
        inputs=["Source publications & data", "Reference library", "Unbranded / disease framing", "Branded-claim boundaries"],
    ),
]


def _content_studio_components() -> List[RegistryComponent]:
    components = []
    for f in CONTENT_STUDIO_FORMATS:
        availability = (
            "available now"
            if not f.soon
            else "not yet built in this workspace — the agent can still open its spec to explain what it does and what it needs"
        )
        inputs_str = ", ".join(f.inputs)
        description = (
            f"{f.tool} ({f.engine_tab} engine). {f.description} Audience: {f.audience}. "
            f"Objective stage: {f.stage}. Promotional class: {f.promo}. Lead role: {f.lead}. "
            f"Required inputs: {inputs_str}. Status: {availability}."
        )
        components.append(
            RegistryComponent(
                id=f.slug,
                label=f.title,
                description=description,
                actions=[
                    RegistryAction(
                        id="open",
                        description=f"Open the {f.title} format's detail modal — shows its full spec, required inputs, the team that builds it, and MLR readiness.",
                    )
                ],
            )
        )
    return components


# General product knowledge, not tied to any one page/component — the
# agent's equivalent of "what the company actually does." Grounded in real
# copy already written for the product (the Content Studio hero banner,
# Brand Kit's subtitle, etc.) rather than invented, so the agent doesn't
# improvise claims that aren't backed by anything in the actual UI.
PRODUCT_OVERVIEW = """ContentIQ (by SwishX) is an AI content platform for pharma marketing teams. \
Its core differentiator: medical-grade, MLR-ready content in minutes, not weeks. MLR readiness — \
on-label claims, references, fair balance, ISI — is built in at generation time, not a downstream \
compliance check, so content enters review clean instead of bouncing back and forth with legal/medical \
review. It covers 30 content formats across 5 Magic Engines (Video, Aid, Mail, Canvas, Doc) — everything \
from short videos and AI digital-twin presenter avatars, to HCP detailing aids and approved emails, to \
banners/infographics and long-form documents like payer dossiers — all generated from a single Brand Kit \
so every asset stays on-brand automatically. It also has campaign analytics (WhatsApp/SMS/Email \
performance, HCP reach, engagement funnels) and an "Agentic IQ" layer tracking how many manhours \
autonomous agents have saved the team."""


# Describes what the agent can point at and do, in terms the LLM (or the
# keyword fallback) can reason over. `page` + component `id` must match the
# ids the frontend registers under (frontend/src/lib/uiRegistry.ts) — same
# convention, not shared code, since frontend/backend are separate packages.
#
# Extend this whenever a new page or actionable component is added on the
# frontend — that's the whole point of a registry: one place to update
# instead of teaching the agent new prompts by hand.
UI_REGISTRY: List[RegistryPage] = [
    RegistryPage(
        id="dashboard",
        label="Dashboard",
        components=[
            RegistryComponent(
                id="insights",
                label="Insights panel",
                description="The four insight cards: Campaign Insights, HCP Insights, Field Rep Insights, Agentic IQ.",
                actions=[RegistryAction(id="highlight", description="Draw attention to the insights panel")],
            ),
            RegistryComponent(
                id="active-campaigns",
                label="Active Campaigns",
                description="List of running campaigns with progress and status (Paused / Optimizing).",
                actions=[RegistryAction(id="highlight", description="Draw attention to the active campaigns list")],
            ),
        ],
    ),
    RegistryPage(
        id="mlr-review",
        label="MLR Review",
        components=[
            RegistryComponent(
                id="queue",
                label="Approvals queue",
                description=(
                    "The multi-stage MLR approval queue — every submission moves through Brand Review, "
                    "Medical Review, Legal Review, then Compliance Sign-off, with a full audit trail of who "
                    "approved/rejected each stage and when. This is what 'MLR-ready at generation' feeds "
                    "into: content still goes through this same review queue, it just arrives already "
                    "carrying its claims/references/fair-balance/ISI, so it moves through faster and with "
                    "fewer rejections than content built by hand."
                ),
                actions=[RegistryAction(id="highlight", description="Draw attention to the approvals queue")],
            ),
        ],
    ),
    RegistryPage(
        id="analytics",
        label="Analytics",
        components=[
            RegistryComponent(
                id="funnel",
                label="Engagement Funnel",
                description="Sent, Viewed, Played, Completed, Shared funnel for campaign engagement.",
                actions=[RegistryAction(id="highlight", description="Draw attention to the engagement funnel")],
            ),
        ],
    ),
    RegistryPage(
        id="content-studio",
        label="Content Studio",
        components=[
            RegistryComponent(
                id="video-tab",
                label="Magic Video",
                description=(
                    "Video content formats — short videos, digital twin avatars, broadcast ads. Like every "
                    "format in Content Studio, each is MLR-ready the moment it's generated (on-label claims, "
                    "references, fair balance, ISI already included), not something that gets checked and "
                    "bounced back afterward — this is usually the single biggest time-saver for teams whose "
                    "review/approval cycle is the bottleneck."
                ),
                actions=[RegistryAction(id="click", description="Switch Content Studio to the Video tab")],
            ),
            RegistryComponent(
                id="aid-tab",
                label="Magic Aid",
                description=(
                    "HCP detailing and field-rep enablement formats (interactive visual aids, e-detail decks, "
                    "leave-behinds). Same MLR-ready-at-generation guarantee as the rest of Content Studio."
                ),
                actions=[RegistryAction(id="click", description="Switch Content Studio to the Aid tab")],
            ),
            RegistryComponent(
                id="mail-tab",
                label="Magic Mail",
                description=(
                    "Email and CRM messaging formats — approved sends, multi-touch sequences, newsletters. "
                    "Same MLR-ready-at-generation guarantee as the rest of Content Studio."
                ),
                actions=[RegistryAction(id="click", description="Switch Content Studio to the Mail tab")],
            ),
            RegistryComponent(
                id="canvas-tab",
                label="Magic Canvas",
                description=(
                    "Static, display and web creative formats — infographics, banners, social posts, "
                    "co-pay cards. Same MLR-ready-at-generation guarantee as the rest of Content Studio."
                ),
                actions=[RegistryAction(id="click", description="Switch Content Studio to the Canvas tab")],
            ),
            RegistryComponent(
                id="doc-tab",
                label="Magic Doc",
                description=(
                    "Long-form documents — monographs, brochures, payer/AMCP dossiers, MSL and KOL decks. "
                    "Same MLR-ready-at-generation guarantee as the rest of Content Studio — this is usually "
                    "the format category with the longest normal review cycle, so the time saved is biggest here."
                ),
                actions=[RegistryAction(id="click", description="Switch Content Studio to the Doc tab")],
            ),
            # Every one of the 30 individual formats, so the agent can open a
            # specific format's modal directly (e.g. "do you have a co-pay
            # card format?" -> open MagicSave) instead of only being able to
            # gesture at a whole tab.
            *_content_studio_components(),
        ],
    ),
    # The two Content Studio formats with a real, walkable studio behind
    # them (BUILT_STUDIOS on the frontend) — everything else stops at the
    # format's detail modal. These pages let the agent actually enter the
    # studio and narrate its way through it step by step, rather than only
    # being able to describe it from the modal.
    RegistryPage(
        id="magicreel-studio",
        label="MagicReel Studio",
        components=[
            RegistryComponent(
                id="wizard",
                label="MagicReel wizard",
                description=(
                    "The MagicReel™ video-creation wizard — 5 steps in order: Source (brand dossier / news "
                    "article / custom brief), Brief (audience, topics, goal, voice, language, logo), Script "
                    "(structure + length, then generate/review the draft script), Scenes (review and edit each "
                    "scene's narration/visual direction), Generate (pick HD or Cinematic 4K and render). Jumping "
                    "ahead to Scenes or Generate before a script exists auto-drafts a placeholder script so the "
                    "screen isn't empty."
                ),
                actions=[
                    RegistryAction(id="step-source", description="Open MagicReel at the Source step (pick brand dossier / news / custom brief)"),
                    RegistryAction(id="step-brief", description="Jump to the Brief step (audience, topics, goal, voice, language, logo)"),
                    RegistryAction(id="step-script", description="Jump to the Script step (structure, length, generate the draft script)"),
                    RegistryAction(id="step-scenes", description="Jump to the Scenes step (review/edit each scene)"),
                    RegistryAction(id="step-generate", description="Jump to the Generate step (video quality tier, render)"),
                ],
            ),
        ],
    ),
    RegistryPage(
        id="magicavatar-studio",
        label="MagicAvatar Studio",
        components=[
            RegistryComponent(
                id="launchpad",
                label="MagicAvatar Launchpad",
                description=(
                    "The MagicAvatar front door — explains the 3-stage flow (1: create a silent Master video "
                    "here, 2: package it into a campaign, 3: reps generate a personalized per-doctor twin in "
                    "the field). Steps 2 and 3 are a separate mobile rep-portal app, out of scope for this "
                    "workspace, and stay visibly locked."
                ),
                actions=[
                    RegistryAction(id="open", description="Open the MagicAvatar Launchpad (the front door before the Master wizard)"),
                    RegistryAction(id="create-master", description="Start creating a Digital Twin Master Video (enters the Master wizard at Brief)"),
                ],
            ),
            RegistryComponent(
                id="wizard",
                label="MagicAvatar Master wizard",
                description=(
                    "The Digital Twin Master Video wizard — 4 steps in order: Brief (script/notes, persona, "
                    "aesthetic), Scenes (the team's scene breakdown + visual direction), Options (HD/Cinematic "
                    "4K, background music), Generate (render the silent master). Jumping ahead before scenes "
                    "exist auto-drafts a placeholder breakdown so the screen isn't empty."
                ),
                actions=[
                    RegistryAction(id="step-brief", description="Jump to the Brief step (script/notes, persona, aesthetic)"),
                    RegistryAction(id="step-scenes", description="Jump to the Scenes step (scene breakdown + visual direction)"),
                    RegistryAction(id="step-options", description="Jump to the Options step (video quality tier, music)"),
                    RegistryAction(id="step-generate", description="Jump to the Generate step (render the master)"),
                ],
            ),
        ],
    ),
    RegistryPage(
        id="brand-kit",
        label="Brand Kit",
        components=[
            RegistryComponent(
                id="logo",
                label="Logo",
                description="Where the workspace logo is uploaded and replaced.",
                actions=[RegistryAction(id="highlight", description="Draw attention to the logo upload control")],
            ),
            RegistryComponent(
                id="palette",
                label="Palette",
                description="The brand color fields: Primary, Accent, Callout Background, Text.",
                actions=[RegistryAction(id="highlight", description="Draw attention to the palette editor")],
            ),
        ],
    ),
]


@dataclass
class FlatAction:
    page: str
    page_label: str
    component: str
    component_label: str
    method: str
    keywords: List[str]


def flatten_registry(registry: List[RegistryPage]) -> List[FlatAction]:
    flat: List[FlatAction] = []
    for page in registry:
        for component in page.components:
            for action in component.actions:
                text = f"{page.label} {component.id} {component.label} {component.description} {action.id} {action.description}"
                keywords = sorted(set(t for t in re.split(r"[^a-z0-9]+", text.lower()) if t))
                flat.append(
                    FlatAction(
                        page=page.id,
                        page_label=page.label,
                        component=component.id,
                        component_label=component.label,
                        method=action.id,
                        keywords=keywords,
                    )
                )
    return flat
