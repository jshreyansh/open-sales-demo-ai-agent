import Icon from "../Icon";

interface ReelResultProps {
  name: string;
  brand: string;
  audience: string;
  topic: string;
  language: string;
  onEditScenes: () => void;
  onBackToAssets: () => void;
  onSubmitForReview: () => void;
}

export default function ReelResult({
  name,
  brand,
  audience,
  topic,
  language,
  onEditScenes,
  onBackToAssets,
  onSubmitForReview,
}: ReelResultProps) {
  return (
    <div className="studio-card reel-result">
      <div className="reel-result__banner">
        <Icon name="check-circle" size={18} />
        <div>
          <h2>Your MagicReel is ready!</h2>
          <p>Preview your reel below, then edit scenes, share it, or submit it for review.</p>
        </div>
      </div>

      <div className="reel-result__body">
        <div className="scene-inspector__player reel-result__preview">
          <div className="scene-inspector__logo">{brand.slice(0, 1)}</div>
          <div className="scene-inspector__title">{brand}</div>
          <div className="scene-inspector__subtitle">{topic}</div>
          <div className="scene-inspector__playbar">
            <Icon name="play" size={13} />
            <span className="scene-inspector__time">0:00 / 0:50</span>
            <div className="scene-inspector__scrub" />
            <Icon name="chevron-down" size={13} />
          </div>
        </div>

        <dl className="reel-details">
          <div className="reel-details__row">
            <dt>Name</dt>
            <dd>{name}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Brand</dt>
            <dd>{brand}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Audience</dt>
            <dd>{audience}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Topic</dt>
            <dd>{topic}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Language</dt>
            <dd>{language}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Status</dt>
            <dd>Draft</dd>
          </div>
        </dl>
      </div>

      <div className="reel-result__actions">
        <button className="btn" onClick={onEditScenes}>
          <Icon name="sparkles" size={13} /> Edit scenes
        </button>
        <button className="btn" onClick={onBackToAssets}>
          ← Back to Assets
        </button>
        <button className="btn-dark" onClick={onSubmitForReview}>
          Submit for Review
        </button>
      </div>
    </div>
  );
}
