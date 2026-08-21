# Seeded demo data for the landing Dashboard.
#
# Hard rule for this file: every metric has to point at something the visitor
# can actually reach in the nav (frontend/src/registry/pages.ts) — Content
# Studio, MLR Review, Brand Dossiers, Brand Kit, Content Library, Templates.
# The nav was narrowed to Dashboard / Create / Library, which left this file
# leading with "Active Campaigns: 5", "Total HCPs Reached", "MR Submissions"
# and an "Active Agents" count on a product with no Campaigns, Audience,
# Field Rep or Agents section anywhere. That's the same "claims something
# that isn't there" failure the voice agent is built to avoid, just rendered
# in HTML instead of spoken. The old numbers weren't wrong; the capabilities
# they described were gone.
#
# Anything added here must also stay clear of the "soon" badges in the nav:
# Magic Aid / Mail / Doc are marked coming-soon, so per-engine output figures
# are deliberately absent — an engine reporting 200 generated assets while
# the sidebar calls it "Soon" is the same contradiction one level down.
dashboard_data = {
    # Four cards, same four accent colours in the same order as before, so
    # the page reads identically — only the subject matter moved. Ordered the
    # way a pharma marketing lead scans it: what got made, will it clear
    # review, what was it built from, what did that buy back.
    "insights": [
        {
            "id": "content-output",
            "label": "Content Output",
            "description": "Assets generated in Content Studio.",
            "accent": "#FF4F00",
            "icon": "sparkles",
            "metrics": [
                {"label": "Assets Generated", "value": "1,284", "sub": "▲ 96 this week"},
                # Framed as coverage of the catalogue rather than a bare
                # count, because "30 formats across 5 Magic Engines" is the
                # product's own headline claim — this is the one number that
                # shows a team actually working through it.
                {"label": "Formats Used", "value": "22 / 30"},
                {"label": "Avg First Draft", "value": "4m 10s"},
            ],
            "sparkline": [742, 838, 905, 981, 1064, 1178, 1284],
        },
        {
            "id": "mlr",
            "label": "MLR Review",
            "description": "Review queue and pass rate.",
            "accent": "#3B82F6",
            "icon": "shield",
            # Pending Approval is the one metric that survived the cut intact
            # — it was stranded in "Campaign Insights" and now sits on the
            # card for the page it belongs to. The value tracks the pending
            # rows in data/approvals.py (3), which is also what the sidebar
            # badge renders; if those rows change, change this too, or the
            # dashboard and the sidebar will disagree in the same viewport.
            "metrics": [
                {"label": "Pending Approval", "value": "3", "sub": "1 awaiting you"},
                {"label": "First-Pass Approval", "value": "88%"},
                {"label": "Avg Time in Review", "value": "2.4 days"},
            ],
            # Trending down is the good direction here: the queue draining is
            # the story, not growth.
            "sparkline": [9, 8, 6, 7, 5, 4, 3],
        },
        {
            "id": "brand",
            "label": "Brand & Templates",
            "description": "Dossiers, brand kit and templates in play.",
            "accent": "#10B981",
            "icon": "palette",
            "metrics": [
                {"label": "Brand Dossiers Live", "value": "6", "sub": "▲ 2 this quarter"},
                {"label": "Templates", "value": "34"},
                {"label": "Library Assets", "value": "412"},
            ],
            "sparkline": [2, 3, 3, 4, 5, 5, 6],
        },
        {
            # Replaces "Agentic IQ". Manhours Saved was the only metric on
            # that card backed by anything the visitor can see — "Active
            # Agents: 7" and "Actions Executed: 493" described an agent
            # control plane with no page, no nav entry and no screen in the
            # walkthrough. Kept the number, dropped the fleet, and every
            # figure here is derived from generation + review, both of which
            # are real surfaces.
            "id": "time-saved",
            "label": "Time Saved",
            "description": "Turnaround and reuse versus the manual path.",
            "accent": "#8B5CF6",
            "icon": "clock",
            "metrics": [
                {"label": "Manhours Saved", "value": "412h", "sub": "▲ 58h this month"},
                {"label": "Brief to Approved", "value": "3.2 days"},
                {"label": "Library Reuse", "value": "61%"},
            ],
            "sparkline": [96, 148, 194, 246, 301, 354, 412],
        },
    ],
    # Took the slot the Active Campaigns list used to occupy, and the same
    # row shape (name / sub-line / progress / status pill) — dossiers are the
    # thing every generation is actually sourced from, so "which brands are
    # ready to generate against" is the closest honest equivalent of "what's
    # running right now".
    "brandDossiers": [
        {
            "name": "Oflox OZ — Foundational Dossier",
            "meta": "Cardiology · 34 sources",
            "percent": 100,
            "status": "Live",
        },
        {
            "name": "Nicotex — Foundational Dossier",
            "meta": "Smoking Cessation · 28 sources",
            "percent": 100,
            "status": "Live",
        },
        {
            "name": "Maxiflo — Foundational Dossier",
            "meta": "Diabetology & Metabolic Disorders · 21 sources",
            "percent": 76,
            "status": "In Build",
        },
        {
            "name": "Antiflu — Foundational Dossier",
            "meta": "Cardiology · 12 sources",
            "percent": 44,
            "status": "In Build",
        },
    ],
    # Replaces Campaign Performance by channel. Same three-stat row, but the
    # stages are the four real MLR stages from data/approvals.py — so the
    # section answers "where does content actually get stuck", which is the
    # question the MLR Review page exists to answer.
    "reviewStages": [
        {"stage": "Brand Review", "submissions": 46, "firstPass": 94, "avgDays": 0.4, "sentBack": 6},
        {"stage": "Medical Review", "submissions": 43, "firstPass": 88, "avgDays": 1.1, "sentBack": 12},
        {"stage": "Legal Review", "submissions": 38, "firstPass": 91, "avgDays": 0.6, "sentBack": 9},
        {"stage": "Compliance Sign-off", "submissions": 35, "firstPass": 97, "avgDays": 0.3, "sentBack": 3},
    ],
    # Same titles as the old "Top Content by Views" list, counted by reuse
    # instead of views: views are a distribution number and distribution left
    # with Campaigns, whereas reuse is native to the Content Library.
    "topAssets": [
        {"title": "Patient Counselling Tips for Physicians", "uses": 148},
        {"title": "Adverse Event Profile for Oncologists", "uses": 132},
        {"title": "Mechanism of Action for Physicians", "uses": 121},
        {"title": "Dosing Guide for Physicians", "uses": 104},
        {"title": "Adverse Event Profile for Physicians", "uses": 87},
    ],
}
