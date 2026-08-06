import { useState } from "react";
import Icon from "../../components/Icon";
import StepBar from "../../components/studio/StepBar";
import TeamDock from "../../components/studio/TeamDock";
import SceneList from "../../components/studio/SceneList";
import GenerationScreen from "../../components/studio/GenerationScreen";
import { MUSIC_TRACKS, generateDummyScenes, type Scene } from "../../registry/studioData";

const STEPS = ["Brief", "Scenes", "Options", "Generate"];
type MusicTab = "none" | "library" | "upload";

interface MagicAvatarStudioProps {
  onExit: () => void;
}

/**
 * The real MagicAvatar "digital twin" personalization (doctor's own voice +
 * photo) happens in a separate mobile rep-portal app outside Content Studio
 * entirely — this wizard mirrors the Master-video creation flow that our
 * "Open Studio" button actually reaches: a silent, reusable presenter video,
 * personalized per-doctor later, outside this flow.
 */
export default function MagicAvatarStudio({ onExit }: MagicAvatarStudioProps) {
  const [step, setStep] = useState(0);

  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [persona, setPersona] = useState("");
  const [aesthetic, setAesthetic] = useState("");
  const [segmenting, setSegmenting] = useState(false);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [addIntro, setAddIntro] = useState(true);
  const [addOutro, setAddOutro] = useState(true);

  const [tier, setTier] = useState<"hd" | "cinematic">("hd");
  const [musicTab, setMusicTab] = useState<MusicTab>("none");
  const [musicId, setMusicId] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  function segmentAndDirect() {
    setSegmenting(true);
    setTimeout(() => {
      setScenes(generateDummyScenes(persona || "your specialty", name || "the presenter"));
      setSegmenting(false);
      setStep(1);
    }, 1300);
  }

  return (
    <div className="page studio">
      <div className="studio__header">
        <button className="studio__back" onClick={onExit}>
          <Icon name="chevron-down" size={14} /> Content Studio
        </button>
        <h1 className="page__title">Digital Twin Master Video</h1>
        <p className="page__subtitle">Author the avatar's script, direct the visuals, pick music, and generate a silent cinematic master.</p>
      </div>

      <StepBar steps={STEPS} currentIndex={step} onStepClick={setStep} locked={generating} />

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
              <button className="btn-primary" onClick={segmentAndDirect} disabled={segmenting}>
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
              <button className="btn-primary" onClick={() => setStep(2)}>
                Continue to options →
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="studio-card">
            <div className="field-label">Video mode</div>
            <div className="tier-grid">
              <button className={`tier-card ${tier === "hd" ? "tier-card--active" : ""}`} onClick={() => setTier("hd")}>
                <div className="tier-card__title">HD</div>
                <div className="tier-card__desc">Lifelike motion — the standard master quality.</div>
                <div className="tier-card__meta">4,500 credits · ~2 min</div>
              </button>
              <button className={`tier-card ${tier === "cinematic" ? "tier-card--active" : ""}`} onClick={() => setTier("cinematic")}>
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
              <button className="btn-primary" onClick={() => setStep(3)}>
                Continue to generate →
              </button>
            </div>
          </div>
        )}

        {step === 3 &&
          (generating ? (
            <div className="studio-card">
              <GenerationScreen subjectLabel="master video" sourceLabel={name || "Untitled master"} onDone={onExit} />
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
                <button className="btn-primary" onClick={() => setGenerating(true)}>
                  Generate master →
                </button>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
