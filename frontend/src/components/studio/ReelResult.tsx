import type { Ref } from "react";
import Icon from "../Icon";
import AssetVideoPlayer, { type AssetVideoPlayerHandle } from "./AssetVideoPlayer";
import { DEFAULT_REEL_VIDEO_URL } from "../../registry/studioData";

interface ReelResultProps {
  name: string;
  brand: string;
  audience: string;
  topic: string;
  language: string;
  onEditScenes: () => void;
  onBackToAssets: () => void;
  onSubmitForReview: () => void;
  playerRef?: Ref<AssetVideoPlayerHandle>;
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
  playerRef,
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
        <div className="reel-result__preview">
          <AssetVideoPlayer ref={playerRef} src={DEFAULT_REEL_VIDEO_URL} locked />
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
