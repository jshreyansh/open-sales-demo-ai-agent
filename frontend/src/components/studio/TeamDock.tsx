import { TEAM_ROLES, type TeamRole } from "../../registry/contentStudio";

interface TeamDockProps {
  activeRole: TeamRole;
  message: string;
}

/**
 * Mirrors the real product's "Agent Team Dock" — a persona rail narrating
 * what "the team" is doing at each step. Their own code comments this as
 * presentation framing, not real orchestrated agents, so a static per-step
 * message here (no LLM call) is a faithful mockup, not a corner cut.
 */
export default function TeamDock({ activeRole, message }: TeamDockProps) {
  const lead = TEAM_ROLES.find((r) => r.role === activeRole) ?? TEAM_ROLES[0];
  return (
    <div className="team-dock">
      <div className="team-dock__avatars">
        {TEAM_ROLES.map((r) => {
          const active = r.role === activeRole;
          return (
            <div
              key={r.role}
              className={`team-dock__avatar ${active ? "team-dock__avatar--active" : ""}`}
              style={active ? { background: r.color } : undefined}
              title={r.role}
            >
              {r.initials}
            </div>
          );
        })}
      </div>
      <div className="team-dock__note">
        <b style={{ color: lead.color }}>{lead.role}</b>
        <p>{message}</p>
      </div>
    </div>
  );
}
