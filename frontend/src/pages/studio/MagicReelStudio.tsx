import { useState } from "react";
import Icon from "../../components/Icon";
import StepBar from "../../components/studio/StepBar";
import TeamDock from "../../components/studio/TeamDock";
import ScenesWorkspace from "../../components/studio/ScenesWorkspace";
import GenerationScreen from "../../components/studio/GenerationScreen";
import ReelResult from "../../components/studio/ReelResult";
import {
  AUDIENCES,
  DOSSIERS,
  GOALS,
  LANGUAGES,
  PRESET_VOICES,
  SCRIPT_STRUCTURES,
  TARGET_LENGTHS,
  TOPICS_BY_AUDIENCE,
  generateDummyScenes,
  type Scene,
} from "../../registry/studioData";

const STEPS = ["Source", "Brief", "Script", "Scenes", "Generate"];
const BRIEF_SUBSTEPS = ["Audience Configuration", "Voice & Language", "Brand & Product"];
type Lane = "dossier" | "news" | "custom";
const LOGO_POSITIONS = ["Top left", "Top right", "Bottom left", "Bottom right"];

interface MagicReelStudioProps {
  onNavigate: (pageId: string) => void;
}

export default function MagicReelStudio({ onNavigate }: MagicReelStudioProps) {
  const [view, setView] = useState<"wizard" | "result" | "edit-scenes">("wizard");
  const [step, setStep] = useState(0);
  const [briefSub, setBriefSub] = useState(0);

  const [lane, setLane] = useState<Lane>("dossier");
  const [dossierId, setDossierId] = useState(DOSSIERS[0].id);
  const [customTitle, setCustomTitle] = useState("");
  const [customText, setCustomText] = useState("");
  const [newsUrl, setNewsUrl] = useState("");

  const [audience, setAudience] = useState("doctor");
  const [topics, setTopics] = useState<string[]>(["Product Introduction"]);
  const [goal, setGoal] = useState("New Launch");
  const [includeQuiz, setIncludeQuiz] = useState(false);

  const [voiceId, setVoiceId] = useState(PRESET_VOICES[0].id);
  const [voiceRecorded, setVoiceRecorded] = useState(false);
  const [language, setLanguage] = useState("English");
  const [logoPosition, setLogoPosition] = useState(LOGO_POSITIONS[1]);

  const [structureId, setStructureId] = useState(SCRIPT_STRUCTURES[0].id);
  const [customScript, setCustomScript] = useState("");
  const [targetLength, setTargetLength] = useState(60);
  const [scriptGenerating, setScriptGenerating] = useState(false);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [addIntro, setAddIntro] = useState(true);
  const [addOutro, setAddOutro] = useState(true);

  const [tier, setTier] = useState<"hd" | "cinematic">("hd");
  const [showCitations, setShowCitations] = useState(true);
  const [showReferences, setShowReferences] = useState(true);
  const [generating, setGenerating] = useState(false);

  const dossier = DOSSIERS.find((d) => d.id === dossierId)!;
  const brandName = lane === "dossier" ? dossier.brand : lane === "custom" ? customTitle || "Your brand" : "This story";
  const grounded = lane === "dossier";
  const topicChoices = TOPICS_BY_AUDIENCE[audience] ?? [];

  function toggleTopic(t: string) {
    setTopics((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  }

  function generateScript() {
    setScriptGenerating(true);
    setTimeout(() => {
      setScenes(generateDummyScenes(topics[0] ?? "this product", brandName));
      setScriptGenerating(false);
    }, 1300);
  }

  function laneMessage() {
    if (lane === "news") return "I'll draft the script from the article and cite it. News reels aren't MLR claim-verified — review before publishing.";
    if (lane === "custom") return "I'll shape your own brief into scenes. A custom brief isn't MLR claim-verified — review before publishing.";
    return "I'll draft the script; the MLR Reviewer clears each scene as it lands.";
  }

  if (view === "result") {
    return (
      <div className="page studio">
        <div className="studio__header">
          <button className="studio__back" onClick={() => onNavigate("content-studio")}>
            <Icon name="chevron-down" size={14} /> Content Studio
          </button>
          <h1 className="page__title">MagicReel™ Studio</h1>
        </div>
        <ReelResult
          name={`${brandName} — ${topics[0] ?? "intro"}`}
          brand={brandName}
          audience={AUDIENCES.find((a) => a.id === audience)?.label ?? audience}
          topic={topics[0] ?? ""}
          language={language}
          onEditScenes={() => setView("edit-scenes")}
          onBackToAssets={() => onNavigate("content-studio")}
          onSubmitForReview={() => onNavigate("mlr-review")}
        />
      </div>
    );
  }

  if (view === "edit-scenes") {
    return (
      <div className="page studio">
        <button className="studio__back" onClick={() => setView("result")}>
          <Icon name="chevron-down" size={14} /> Back to result
        </button>
        <h1 className="page__title">
          {brandName} — {topics[0] ?? "intro"}
        </h1>
        <p className="page__subtitle">Edit narration, visual prompts, or images per scene. Save to regenerate only the changed scenes.</p>
        <div className="studio-card" style={{ maxWidth: 900 }}>
          <ScenesWorkspace scenes={scenes} onChange={setScenes} brandName={brandName} subtitle={topics[0] ?? ""} />
          <div className="studio__footer">
            <button className="btn-primary" onClick={() => setView("result")}>
              Save
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page studio">
      <div className="studio__header">
        <button className="studio__back" onClick={() => onNavigate("content-studio")}>
          <Icon name="chevron-down" size={14} /> Content Studio
        </button>
        <h1 className="page__title">MagicReel™ Studio</h1>
      </div>

      <StepBar steps={STEPS} currentIndex={step} onStepClick={setStep} locked={generating} />

      <div className="studio__body">
        {step === 0 && (
          <div className="studio-card">
            <TeamDock activeRole="Content Strategist" message="Pick a source — the team drafts only from what it can verify." />
            <div className="lane-switch">
              {(["dossier", "news", "custom"] as Lane[]).map((l) => (
                <button key={l} className={`lane-switch__pill ${lane === l ? "lane-switch__pill--active" : ""}`} onClick={() => setLane(l)}>
                  {l === "dossier" ? "Brand Dossier" : l === "news" ? "News Article" : "Custom"}
                </button>
              ))}
            </div>

            {lane === "dossier" && (
              <div className="dossier-grid">
                {DOSSIERS.map((d) => (
                  <button
                    key={d.id}
                    className={`dossier-card ${dossierId === d.id ? "dossier-card--active" : ""}`}
                    onClick={() => setDossierId(d.id)}
                  >
                    <div className="dossier-card__brand">{d.brand}</div>
                    <div className="dossier-card__therapy">{d.therapy}</div>
                  </button>
                ))}
              </div>
            )}
            {lane === "news" && (
              <div className="studio-field">
                <label className="field-label">Article URL</label>
                <input
                  className="approvals-search"
                  style={{ maxWidth: "100%" }}
                  placeholder="https://..."
                  value={newsUrl}
                  onChange={(e) => setNewsUrl(e.target.value)}
                />
              </div>
            )}
            {lane === "custom" && (
              <div className="studio-field">
                <label className="field-label">Title</label>
                <input
                  className="approvals-search"
                  style={{ maxWidth: "100%", marginBottom: 12 }}
                  placeholder="e.g. Oflox OZ — Field Update"
                  value={customTitle}
                  onChange={(e) => setCustomTitle(e.target.value)}
                />
                <label className="field-label">Brief (no brand, no MLR claim verification)</label>
                <textarea
                  className="studio-textarea"
                  rows={4}
                  placeholder="Paste your rough brief or notes…"
                  value={customText}
                  onChange={(e) => setCustomText(e.target.value)}
                />
              </div>
            )}

            <div className="studio__footer">
              <button className="btn-primary" onClick={() => setStep(1)}>
                Continue →
              </button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="studio-card">
            <div className="breadcrumb">
              {BRIEF_SUBSTEPS.map((label, i) => (
                <span key={label} className={`breadcrumb__item ${i === briefSub ? "breadcrumb__item--active" : i < briefSub ? "breadcrumb__item--done" : ""}`}>
                  {label}
                  {i < BRIEF_SUBSTEPS.length - 1 && <Icon name="chevron-down" size={11} />}
                </span>
              ))}
            </div>

            {briefSub === 0 && (
              <div>
                <div className="field-label" style={{ marginTop: 4 }}>
                  Audience
                </div>
                <div className="audience-grid">
                  {AUDIENCES.map((a) => (
                    <button
                      key={a.id}
                      className={`audience-card ${audience === a.id ? "audience-card--active" : ""}`}
                      onClick={() => {
                        setAudience(a.id);
                        setTopics([(TOPICS_BY_AUDIENCE[a.id] ?? [])[0]].filter(Boolean));
                      }}
                    >
                      <div className="audience-card__label">{a.label}</div>
                      <div className="audience-card__desc">{a.desc}</div>
                    </button>
                  ))}
                </div>

                <div className="field-label" style={{ marginTop: 18 }}>
                  Topics · pick one or more
                </div>
                <div className="chip-row">
                  {topicChoices.map((t) => (
                    <button key={t} className={`filter-pill ${topics.includes(t) ? "filter-pill--active" : ""}`} onClick={() => toggleTopic(t)}>
                      {t}
                    </button>
                  ))}
                </div>

                <div className="field-label" style={{ marginTop: 18 }}>
                  Goal
                </div>
                <div className="chip-row">
                  {GOALS.map((g) => (
                    <button key={g} className={`filter-pill ${goal === g ? "filter-pill--active" : ""}`} onClick={() => setGoal(g)}>
                      {g}
                    </button>
                  ))}
                </div>

                {audience === "rep" && (
                  <label className="studio-toggle-row">
                    <input type="checkbox" checked={includeQuiz} onChange={(e) => setIncludeQuiz(e.target.checked)} />
                    <div>
                      <b>Include quiz + gamification</b>
                      <div className="studio-toggle-row__sub">Adds quiz, XP scores, and leaderboard</div>
                    </div>
                  </label>
                )}
              </div>
            )}

            {briefSub === 1 && (
              <div>
                <div className="field-label">Your voices</div>
                <div className="voice-grid">
                  <button className={`voice-card voice-card--record ${voiceRecorded ? "voice-card--active" : ""}`} onClick={() => setVoiceRecorded(true)}>
                    <Icon name="sparkles" size={16} />
                    {voiceRecorded ? "Voice recorded ✓" : "Record your voice"}
                  </button>
                  {PRESET_VOICES.map((v) => (
                    <button
                      key={v.id}
                      className={`voice-card ${!voiceRecorded && voiceId === v.id ? "voice-card--active" : ""}`}
                      onClick={() => {
                        setVoiceRecorded(false);
                        setVoiceId(v.id);
                      }}
                    >
                      <span className="voice-card__name">{v.name}</span>
                      <span className="voice-card__gender">{v.gender}</span>
                    </button>
                  ))}
                </div>

                <div className="field-label" style={{ marginTop: 18 }}>
                  Language
                </div>
                <div className="chip-row">
                  {LANGUAGES.map((l) => (
                    <button key={l} className={`filter-pill ${language === l ? "filter-pill--active" : ""}`} onClick={() => setLanguage(l)}>
                      {l}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {briefSub === 2 && (
              <div>
                <div className="field-label">Logo position</div>
                <div className="logo-position-grid">
                  {LOGO_POSITIONS.map((p) => (
                    <button key={p} className={`logo-position ${logoPosition === p ? "logo-position--active" : ""}`} onClick={() => setLogoPosition(p)}>
                      {p}
                    </button>
                  ))}
                </div>
                <div className="field-label" style={{ marginTop: 18 }}>
                  Product packshot (optional)
                </div>
                <div className="upload-box">
                  <Icon name="image" size={18} />
                  Upload a product image
                </div>
              </div>
            )}

            <div className="studio__footer">
              {briefSub > 0 && (
                <button className="btn" onClick={() => setBriefSub(briefSub - 1)}>
                  ← Back
                </button>
              )}
              {briefSub < BRIEF_SUBSTEPS.length - 1 ? (
                <button className="btn-primary" onClick={() => setBriefSub(briefSub + 1)}>
                  Next: {BRIEF_SUBSTEPS[briefSub + 1]} →
                </button>
              ) : (
                <button className="btn-primary" onClick={() => setStep(2)}>
                  Continue to script →
                </button>
              )}
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="studio-card">
            <TeamDock activeRole="Content Strategist" message={laneMessage()} />

            <div className="field-label">Script structure</div>
            <div className="structure-grid">
              {SCRIPT_STRUCTURES.map((s) => (
                <button key={s.id} className={`structure-card ${structureId === s.id ? "structure-card--active" : ""}`} onClick={() => setStructureId(s.id)}>
                  <span className="structure-card__badge">{s.badge}</span>
                  <div className="structure-card__label">{s.label}</div>
                  <div className="structure-card__arc">{s.arc}</div>
                </button>
              ))}
            </div>
            {structureId === "custom" && (
              <textarea
                className="studio-textarea"
                style={{ marginTop: 12 }}
                rows={4}
                placeholder="Paste your own script…"
                value={customScript}
                onChange={(e) => setCustomScript(e.target.value)}
              />
            )}

            <div className="field-label" style={{ marginTop: 18 }}>
              Target length
            </div>
            <div className="chip-row">
              {TARGET_LENGTHS.map((len) => (
                <button key={len} className={`filter-pill ${targetLength === len ? "filter-pill--active" : ""}`} onClick={() => setTargetLength(len)}>
                  {len}s
                </button>
              ))}
            </div>

            <div className="studio__footer" style={{ justifyContent: "flex-start", gap: 12 }}>
              <button className="btn-primary" onClick={generateScript} disabled={scriptGenerating}>
                <Icon name="sparkles" size={14} /> {scenes.length > 0 ? "Regenerate script" : "Generate script"}
              </button>
              {scriptGenerating && <span className="stub-page__note">Drafting script…</span>}
            </div>

            {scenes.length > 0 && !scriptGenerating && (
              <>
                <div className="script-preview">
                  {scenes.map((s, i) => (
                    <div key={s.id} className="script-preview__row">
                      <span className="script-preview__num">{i + 1}</span>
                      <span>{s.narration}</span>
                    </div>
                  ))}
                </div>
                {grounded && (
                  <div className="mlr-kept-panel">
                    <Icon name="check-circle" size={14} /> 3 claims verified · 1 claim kept out (not on-label for this audience)
                  </div>
                )}
              </>
            )}

            <div className="studio__footer">
              <button className="btn-primary" disabled={scenes.length === 0} onClick={() => setStep(3)}>
                Review scenes →
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="studio-card" style={{ maxWidth: 900 }}>
            <TeamDock activeRole="Creative Producer" message="I've directed each scene to read photoreal and clinical, with a negative prompt that blocks cartoon/CGI looks." />
            <ScenesWorkspace scenes={scenes} onChange={setScenes} brandName={brandName} subtitle={topics[0] ?? ""} />
            <div className="chip-row" style={{ marginTop: 14 }}>
              <label className="studio-toggle-row studio-toggle-row--inline">
                <input type="checkbox" checked={addIntro} onChange={(e) => setAddIntro(e.target.checked)} /> Add intro card
              </label>
              <label className="studio-toggle-row studio-toggle-row--inline">
                <input type="checkbox" checked={addOutro} onChange={(e) => setAddOutro(e.target.checked)} /> Add outro card
              </label>
            </div>
            <div className="studio__footer">
              <button className="btn-primary" onClick={() => setStep(4)}>
                Continue to generate →
              </button>
            </div>
          </div>
        )}

        {step === 4 &&
          (generating ? (
            <div className="studio-card">
              <GenerationScreen subjectLabel="reel" sourceLabel={`${brandName} · ${topics[0] ?? ""}`} onDone={() => setView("result")} />
            </div>
          ) : (
            <div className="studio-card">
              <TeamDock activeRole="Project Manager" message="I'll render and assemble the reel, then ping the team when it's done." />

              <div className="field-label">Video mode</div>
              <div className="tier-grid">
                <button className={`tier-card ${tier === "hd" ? "tier-card--active" : ""}`} onClick={() => setTier("hd")}>
                  <div className="tier-card__title">HD</div>
                  <div className="tier-card__desc">Lifelike motion that stops the scroll — for launches & big moments.</div>
                  <div className="tier-card__meta">5,000 credits · ~2 min</div>
                </button>
                <button className={`tier-card ${tier === "cinematic" ? "tier-card--active" : ""}`} onClick={() => setTier("cinematic")}>
                  <div className="tier-card__title">Cinematic 4K</div>
                  <div className="tier-card__desc">Ultra-realistic, fully generated scenes — for flagship launches.</div>
                  <div className="tier-card__meta">15,000 credits · ~4 min</div>
                </button>
              </div>

              <div className="field-label" style={{ marginTop: 18 }}>
                MLR recommends
              </div>
              <label className={`studio-toggle-row ${!grounded ? "studio-toggle-row--disabled" : ""}`}>
                <input type="checkbox" checked={showCitations} disabled={!grounded} onChange={(e) => setShowCitations(e.target.checked)} />
                <div>
                  <b>On-screen source citations</b>
                  <div className="studio-toggle-row__sub">
                    {grounded ? "A lower-third source on each evidence scene." : "No cited sources in this reel — citations unavailable."}
                  </div>
                </div>
              </label>
              <label className={`studio-toggle-row ${!grounded ? "studio-toggle-row--disabled" : ""}`}>
                <input type="checkbox" checked={showReferences} disabled={!grounded} onChange={(e) => setShowReferences(e.target.checked)} />
                <div>
                  <b>References & disclaimer end-card</b>
                  <div className="studio-toggle-row__sub">A closing card listing every source + the HCP-only disclaimer.</div>
                </div>
              </label>

              <div className="studio__footer">
                <button className="btn-primary" onClick={() => setGenerating(true)}>
                  Generate reel →
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
