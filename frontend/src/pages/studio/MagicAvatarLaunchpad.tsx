import Icon from "../../components/Icon";

interface MagicAvatarLaunchpadProps {
  onBack: () => void;
  onCreateMaster: () => void;
}

/**
 * The real front door before the Master wizard — (1) create a silent Master
 * Video, (2) package it into a campaign, (3) reps generate per-doctor
 * Digital Twins in the field. Steps 2/3 are genuinely out of scope here (a
 * separate mobile rep-portal app, not part of Content Studio at all), so
 * they stay locked — that's accurate to the real product's own gating, not
 * a shortcut.
 */
export default function MagicAvatarLaunchpad({ onBack, onCreateMaster }: MagicAvatarLaunchpadProps) {
  return (
    <div className="page studio">
      <div className="avatar-launch__header">
        <div>
          <h1 className="page__title">MagicAvatar</h1>
          <p className="page__subtitle">Personalised AI-presenter detail aids — from one master video to a twin for every doctor.</p>
        </div>
      </div>
      <button className="studio__back" onClick={onBack}>
        <Icon name="chevron-down" size={14} /> Content Studio
      </button>

      <div className="chip-row" style={{ marginTop: 14 }}>
        <span className="avatar-launch__chip">
          <Icon name="play" size={13} /> Lifelike presenters
        </span>
        <span className="avatar-launch__chip">
          <Icon name="sparkles" size={13} /> Multilingual voice cloning
        </span>
        <span className="avatar-launch__chip">
          <Icon name="sparkles" size={13} /> Per-doctor personalisation
        </span>
      </div>

      <div className="field-label" style={{ marginTop: 26 }}>
        How it works — master to field
      </div>
      <div className="avatar-launch__steps">
        <div className="avatar-launch__step avatar-launch__step--active">
          <div className="avatar-launch__step-head">
            <span className="avatar-launch__step-num">1</span>
            <span className="avatar-launch__step-icon">
              <Icon name="play" size={14} />
            </span>
          </div>
          <div className="avatar-launch__step-title">Create the Master</div>
          <p className="avatar-launch__step-desc">
            Author the script, direct photoreal visuals, and generate a silent cinematic master video — your reusable presenter, once.
          </p>
          <p className="avatar-launch__step-team">Your Content Strategist, Creative Producer & MLR Reviewer draft it with you.</p>
          <button className="btn-primary avatar-launch__cta" onClick={onCreateMaster}>
            Create Digital Twin Master Video →
          </button>
        </div>

        <div className="avatar-launch__step avatar-launch__step--locked">
          <div className="avatar-launch__step-head">
            <span className="avatar-launch__step-num">2</span>
            <span className="avatar-launch__step-icon">
              <Icon name="megaphone" size={14} />
            </span>
          </div>
          <div className="avatar-launch__step-title">Build a campaign</div>
          <p className="avatar-launch__step-desc">Package the master into a MagicAvatar campaign and assign it to the reps who will take it into the field.</p>
          <div className="avatar-launch__locked-cta">
            <Icon name="shield" size={12} /> Create campaign
          </div>
        </div>

        <div className="avatar-launch__step avatar-launch__step--locked">
          <div className="avatar-launch__step-head">
            <span className="avatar-launch__step-num">3</span>
            <span className="avatar-launch__step-icon">
              <Icon name="users" size={14} />
            </span>
          </div>
          <div className="avatar-launch__step-title">Reps generate twins</div>
          <p className="avatar-launch__step-desc">On the field, MRs capture each doctor; the avatar is regenerated with their voice and likeness — a personalised twin per visit.</p>
          <div className="avatar-launch__locked-cta">
            <Icon name="shield" size={12} /> Open field portals
          </div>
        </div>
      </div>

      <div className="field-label" style={{ marginTop: 26 }}>
        Your MagicAvatar campaigns
      </div>
      <div className="avatar-launch__empty">
        <b>No MagicAvatar campaigns yet</b>
        <p>Create a Digital Twin Master Video first — a campaign packages that master for your reps.</p>
      </div>
    </div>
  );
}
