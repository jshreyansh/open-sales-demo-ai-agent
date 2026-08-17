import { useEffect, useState } from "react";
import Icon from "../../components/Icon";
import StepBar from "../../components/studio/StepBar";
import TeamDock from "../../components/studio/TeamDock";
import SceneList from "../../components/studio/SceneList";
import GenerationScreen from "../../components/studio/GenerationScreen";
import AvatarResult from "../../components/studio/AvatarResult";
import { MUSIC_TRACKS, generateDummyScenes, type Scene } from "../../registry/studioData";

const STEPS = ["Brief", "Scenes", "Options", "Generate"];
type MusicTab = "none" | "library" | "upload";

interface MagicAvatarMasterWizardProps {
  step: number;
  onStepChange: (step: number) => void;
  scenes: Scene[];
  onScenesChange: (scenes: Scene[]) => void;
  tier: "hd" | "cinematic";
  onTierChange: (tier: "hd" | "cinematic") => void;
  generating: boolean;
  onGeneratingChange: (generating: boolean) => void;
  // Lifted to the parent (see MagicAvatarStudio.tsx) rather than kept as
  // local state here — this used to live in this component alone, which
  // meant none of the parent's 8 registered wizard actions ever reset it:
  // once generation finished, every one of them silently failed to
  // navigate away from the result screen at all, a real functional bug
  // found during the highlight-system audit, not just a missed pulse.
  showResult: boolean;
  onShowResultChange: (show: boolean) => void;
  registerSegmentAndDirect: (fn: (() => void) | null) => void;
  onBack: () => void;
  onBackToAssets: () => void;
  onSubmitForReview: () => void;
}

/**
 * The real MagicAvatar "digital twin" personalization (doctor's own voice +
 * photo) happens in a separate mobile rep-portal app outside Content Studio
 * entirely — this wizard mirrors the Master-video creation flow reached from
 * the Launchpad's step 1: a silent, reusable presenter video, personalized
 * per-doctor later, outside this flow.
 *
 * `step`/`scenes`/`tier`/`generating` are ALL controlled by the parent
 * (MagicAvatarStudio) rather than local state, and every agent-triggerable
 * action (step-jumps, tier selection, generate) is registered there too —
 * on the always-mounted parent, not here. A prior version moved the
 * wizard-internal actions into this component instead, reasoning they only
 * make sense once mounted anyway — but that meant a single combined
 * request ("start it and skip to generate") could ask for an action here
 * before this component ever mounted, which silently queued and never
 * fired, while the conversation kept talking as if it had worked. Keeping
 * one single, always-reliable registration point (matching how `step`/
 * `scenes` already worked) avoids that regardless of what order things get
 * asked for. `segmentAndDirect` is the one exception — it needs this
 * component's own local persona/name fields — so instead of lifting those
 * too, this component hands the parent a live reference to the function via
 * `registerSegmentAndDirect`, cleared on unmount.
 */
export default function MagicAvatarMasterWizard({
  step,
  onStepChange: setStep,
  scenes,
  onScenesChange: setScenes,
  tier,
  onTierChange: setTier,
  generating,
  onGeneratingChange: setGenerating,
  showResult,
  onShowResultChange: setShowResult,
  registerSegmentAndDirect,
  onBack,
  onBackToAssets,
  onSubmitForReview,
}: MagicAvatarMasterWizardProps) {
  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [persona, setPersona] = useState("");
  const [aesthetic, setAesthetic] = useState("");
  const [segmenting, setSegmenting] = useState(false);
  const [addIntro, setAddIntro] = useState(true);
  const [addOutro, setAddOutro] = useState(true);

  const [musicTab, setMusicTab] = useState<MusicTab>("none");
  const [musicId, setMusicId] = useState<string | null>(null);

  function segmentAndDirect() {
    setSegmenting(true);
    setTimeout(() => {
      setScenes(generateDummyScenes(persona || "your specialty", name || "the presenter"));
      setSegmenting(false);
      setStep(1);
    }, 1300);
  }

  // Hands the parent a live reference so its always-mounted "generate-
  // breakdown" action can trigger this component's own function — cleared
  // on unmount so the parent never calls a stale reference into an
  // unmounted component.
  useEffect(() => {
    registerSegmentAndDirect(segmentAndDirect);
    return () => registerSegmentAndDirect(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persona, name]);

  if (showResult) {
    return (
      <div className="page studio">
        <div className="studio__header">
          <button className="studio__back" data-hl="launchpad:open" data-hl-group="studio-header" onClick={onBack}>
            <Icon name="chevron-down" size={14} /> MagicAvatar
          </button>
          <h1 className="page__title">Digital Twin Master Video</h1>
        </div>
        <AvatarResult
          name={name || "Untitled master"}
          persona={persona || "your specialty"}
          sceneCount={scenes.length}
          tier={tier}
          cards={[addIntro && "Intro", addOutro && "Outro"].filter(Boolean).join(", ") || "None"}
          onBackToAssets={onBackToAssets}
          onSubmitForReview={onSubmitForReview}
        />
      </div>
    );
  }

  return (
    <div className="page studio">
      <div className="studio__header">
        <button className="studio__back" onClick={onBack}>
          <Icon name="chevron-down" size={14} /> MagicAvatar
        </button>
        <h1 className="page__title">Digital Twin Master Video</h1>
        <p className="page__subtitle">Author the avatar's script, direct the visuals, pick music, and generate a silent cinematic master.</p>
      </div>

      <StepBar
        steps={STEPS}
        currentIndex={step}
        onStepClick={setStep}
        locked={generating}
        hlGroupPrefix="step"
        dataHl={(i) => {
          if (i === 0) return "wizard:step-brief";
          if (i === 1) return "wizard:step-scenes";
          return undefined;
        }}
      />

      <div className="studio__body">
        {step === 0 && (
          <div className="studio-card">
            <div className="field-label">Your script or notes</div>
            <input
              className="approvals-search"
              style={{ maxWidth: "100%", marginBottom: 12 }}
              placeholder="Name — e.g. National Doctor's Day — v1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <textarea
              className="studio-textarea"
              rows={5}
              placeholder="Paste your script or rough notes…"
              value={script}
              onChange={(e) => setScript(e.target.value)}
            />
            <p className="stub-page__note" style={{ marginTop: 8 }}>
              A rough script or bullet points is fine. Hit Next — the team refines it into proper scenes and drafts the visual direction; you
              review and edit next.
            </p>

            <div className="field-label" style={{ marginTop: 18 }}>
              Creative direction (optional)
            </div>
            <div className="studio-field-row">
              <div>
                <label className="field-label">Persona / specialty</label>
                <input
                  className="approvals-search"
                  style={{ maxWidth: "100%" }}
                  placeholder="e.g. Psychiatrist, warm and reassuring"
                  value={persona}
                  onChange={(e) => setPersona(e.target.value)}
                />
              </div>
              <div>
                <label className="field-label">Aesthetic</label>
                <input
                  className="approvals-search"
                  style={{ maxWidth: "100%" }}
                  placeholder="e.g. clinic-documentary; light / nature / metaphor"
                  value={aesthetic}
                  onChange={(e) => setAesthetic(e.target.value)}
                />
              </div>
            </div>

            <div className="studio__footer">
              <button className="btn-primary" data-hl="wizard:generate-breakdown" onClick={segmentAndDirect} disabled={segmenting}>
                <Icon name="sparkles" size={14} /> {segmenting ? "Directing visuals…" : "Next →"}
              </button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="studio-card">
            <TeamDock activeRole="Creative Producer" message="I've broken your script into scenes and drafted the visual direction for each — narration is kept exactly as you wrote it." />
            <SceneList scenes={scenes} onChange={setScenes} />
            <div className="chip-row" style={{ marginTop: 14 }}>
              <label className="studio-toggle-row studio-toggle-row--inline">
                <input type="checkbox" checked={addIntro} onChange={(e) => setAddIntro(e.target.checked)} /> Add intro card
              </label>
              <label className="studio-toggle-row studio-toggle-row--inline">
                <input type="checkbox" checked={addOutro} onChange={(e) => setAddOutro(e.target.checked)} /> Add outro card
              </label>
              <button className="btn" onClick={() => setScenes(generateDummyScenes(persona || "your specialty", name || "the presenter"))}>
                <Icon name="sparkles" size={13} /> Regenerate visuals
              </button>
            </div>
            <div className="studio__footer">
              <button className="btn-primary" data-hl="wizard:step-options" onClick={() => setStep(2)}>
                Continue to options →
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="studio-card">
            <div className="field-label">Video mode</div>
            <div className="tier-grid">
              <button
                data-hl="wizard:select-tier-hd"
                className={`tier-card ${tier === "hd" ? "tier-card--active" : ""}`}
                onClick={() => setTier("hd")}
              >
                <div className="tier-card__title">HD</div>
                <div className="tier-card__desc">Lifelike motion — the standard master quality.</div>
                <div className="tier-card__meta">4,500 credits · ~2 min</div>
              </button>
              <button
                data-hl="wizard:select-tier-cinematic"
                className={`tier-card ${tier === "cinematic" ? "tier-card--active" : ""}`}
                onClick={() => setTier("cinematic")}
              >
                <div className="tier-card__title">Cinematic 4K</div>
                <div className="tier-card__desc">Ultra-realistic, fully generated scenes — for flagship masters.</div>
                <div className="tier-card__meta">14,000 credits · ~4 min</div>
              </button>
            </div>

            <div className="field-label" style={{ marginTop: 18 }}>
              Background music (optional)
            </div>
            <div className="lane-switch">
              {(["none", "library", "upload"] as MusicTab[]).map((t) => (
                <button key={t} className={`lane-switch__pill ${musicTab === t ? "lane-switch__pill--active" : ""}`} onClick={() => setMusicTab(t)}>
                  {t === "none" ? "No music" : t === "library" ? "Library" : "Upload"}
                </button>
              ))}
            </div>
            {musicTab === "library" && (
              <div className="music-list">
                {MUSIC_TRACKS.map((m) => (
                  <button key={m.id} className={`music-row ${musicId === m.id ? "music-row--active" : ""}`} onClick={() => setMusicId(m.id)}>
                    <Icon name="play" size={14} />
                    <span className="music-row__title">{m.title}</span>
                    <span className="music-row__mood">{m.mood}</span>
                    <span className="music-row__duration">{m.duration}</span>
                  </button>
                ))}
              </div>
            )}
            {musicTab === "upload" && (
              <div className="upload-box">
                <Icon name="sparkles" size={18} />
                Upload an audio file (mp3, wav, m4a — up to 20MB)
              </div>
            )}
            <p className="stub-page__note" style={{ marginTop: 8 }}>
              One track over the whole master. The render stays silent per scene — voice is added later, per doctor, in the field.
            </p>

            <div className="studio__footer">
              <button className="btn-primary" data-hl="wizard:step-generate" onClick={() => setStep(3)}>
                Continue to generate →
              </button>
            </div>
          </div>
        )}

        {step === 3 &&
          (generating ? (
            <div className="studio-card">
              <GenerationScreen subjectLabel="master video" sourceLabel={name || "Untitled master"} onDone={() => setShowResult(true)} />
            </div>
          ) : (
            <div className="studio-card">
              <TeamDock activeRole="Creative Producer" message="I'll render the silent master with your cards and music, then it lands in your content library." />
              <dl className="review-list">
                <div>
                  <dt>Name</dt>
                  <dd>{name || "Untitled master"}</dd>
                </div>
                <div>
                  <dt>Scenes</dt>
                  <dd>{scenes.length}</dd>
                </div>
                <div>
                  <dt>Cards</dt>
                  <dd>{[addIntro && "Intro", addOutro && "Outro"].filter(Boolean).join(", ") || "None"}</dd>
                </div>
                <div>
                  <dt>Video mode</dt>
                  <dd>{tier === "hd" ? "HD" : "Cinematic 4K"}</dd>
                </div>
                <div>
                  <dt>Music</dt>
                  <dd>{musicTab === "none" ? "None" : musicTab === "library" ? MUSIC_TRACKS.find((m) => m.id === musicId)?.title ?? "Not selected" : "Uploaded track"}</dd>
                </div>
              </dl>
              <div className="studio__footer">
                <button className="btn-primary" data-hl="wizard:start-generation" onClick={() => setGenerating(true)}>
                  Generate master →
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
