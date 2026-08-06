# Integrations

Split clearly between what's actually shipped today and what's roadmap/Enterprise-gated —
don't blur the two.

## Shipped today

- **WhatsApp Business API** — via managed provider partners (AiSensy, DoubleTick). SwishX
  configures this for the workspace; it's not self-serve. This is how campaign sends actually go
  out on WhatsApp.
- **Email** — bring-your-own SMTP, configured per workspace.
- **Google OAuth** — sign-in/sign-up.

## Roadmap (Enterprise tier only, not yet built)

Veeva Vault integration, Salesforce integration, SSO/SAML, and custom API & webhooks are all listed
as Enterprise-tier features but are not yet implemented — treat these as "on the roadmap for
Enterprise," not "available now."

## The Veeva Vault story (the real depth here — lead with this if asked about integrations)

Veeva Vault PromoMats is the de facto MLR workflow and digital-asset-management standard for
promotional pharma content (it generates the FDA Form 2253 package); Vault MedComms governs medical
and MSL content. ContentIQ's stated position is to **interoperate with Vault, not compete with it**
— this is a cross-cutting integration point across all 30 content formats, not a per-format feature.

**Import (from Vault into ContentIQ):**
- Approved claims libraries and their linked references, so generation is grounded in already-cleared evidence.
- Brand templates, ISI, and fair-balance modules maintained in Vault.
- Approval status and lineage for modular content fragments, so reused content inherits its cleared state.

**Export (from ContentIQ into Vault):**
- Form 2253-ready packages, every claim annotated to its supporting reference.
- Assets structured for Vault's own review workflow, already carrying the MLR inputs it expects.
- Modular components tagged for reuse, matching Vault's parent-child content model.

**Competitive framing:** Veeva has its own AI review agents (Quick Check, Content Agent) and,
per industry reporting, Veeva Falcon MLR. ContentIQ's position is to sit *upstream* of these — it
generates already-compliant assets rather than competing on the review step. The platform makes
content that enters clean; Vault's tools confirm it faster. Complementary, not competitive.

Note: there's no equivalent depth of interoperability spec for Salesforce today — it exists only as
an Enterprise-tier roadmap line item, without the detail Veeva has. Be straightforward about that
gap if it comes up rather than inventing Salesforce specifics.
