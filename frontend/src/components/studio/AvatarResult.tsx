import type { Ref } from "react";
import Icon from "../Icon";
import AssetVideoPlayer, { type AssetVideoPlayerHandle } from "./AssetVideoPlayer";
import { DEFAULT_AVATAR_VIDEO_URL } from "../../registry/studioData";

interface AvatarResultProps {
  name: string;
  persona: string;
  sceneCount: number;
  tier: "hd" | "cinematic";
  cards: string;
  onBackToAssets: () => void;
  onSubmitForReview: () => void;
  playerRef?: Ref<AssetVideoPlayerHandle>;
}

export default function AvatarResult({
  name,
  persona,
  sceneCount,
  tier,
  cards,
  onBackToAssets,
  onSubmitForReview,
  playerRef,
}: AvatarResultProps) {
  return (
    <div className="studio-card reel-result">
      <div className="reel-result__banner">
        <Icon name="check-circle" size={18} />
        <div>
          <h2>Your Digital Twin master is ready!</h2>
          <p>Preview the silent master below, then share it or submit it for review.</p>
        </div>
      </div>

      <div className="reel-result__body">
        <div className="reel-result__preview">
          <AssetVideoPlayer ref={playerRef} src={DEFAULT_AVATAR_VIDEO_URL} locked />
        </div>

        <dl className="reel-details">
          <div className="reel-details__row">
            <dt>Name</dt>
            <dd>{name}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Persona</dt>
            <dd>{persona}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Scenes</dt>
            <dd>{sceneCount}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Tier</dt>
            <dd>{tier === "cinematic" ? "Cinematic 4K" : "HD"}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Cards</dt>
            <dd>{cards}</dd>
          </div>
          <div className="reel-details__row">
            <dt>Status</dt>
            <dd>Draft</dd>
          </div>
        </dl>
      </div>

      <div className="reel-result__actions">
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
