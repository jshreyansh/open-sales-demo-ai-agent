import re
from dataclasses import dataclass
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
