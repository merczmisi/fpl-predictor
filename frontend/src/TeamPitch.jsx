import React from "react";

const POSITION_ORDER = [1, 2, 3, 4]; // 1 gk, 2 def, 3 mid, 4 fwd
const POSITION_LABELS = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };

function PlayerCard({ player }) {
  const diff = player.event_started
    ? player.event_points - player.expected_points
    : null;
  const isGoalkeeper = player.element_type === 1;
  const shirtSrc = player.team_code
    ? `/shirts/shirt_${player.team_code}${isGoalkeeper ? "_1" : ""}.webp`
    : null;

  return (
    <div className={`player-card position-${player.element_type}`}>
      {shirtSrc ? (
        <img
          className="player-shirt"
          src={shirtSrc}
          alt=""
          // Goalkeeper shirt missing: fall back to the outfield shirt, then the colored placeholder.
          onError={(e) => {
            if (isGoalkeeper && e.currentTarget.src.endsWith("_1.webp")) {
              e.currentTarget.src = `/shirts/shirt_${player.team_code}.webp`;
              return;
            }
            e.currentTarget.style.display = "none";
            e.currentTarget.nextElementSibling?.classList.remove("player-shirt-hidden");
          }}
        />
      ) : null}
      <div className={`player-shirt player-shirt-fallback ${player.team_code ? "player-shirt-hidden" : ""}`} aria-hidden="true" />
      <div className="player-name">{player.web_name}</div>
      <div className="player-points">
        xP: {player.expected_points.toFixed(1)}
        {diff !== null && (
          <span className={`points-diff ${diff >= 0 ? "points-diff-positive" : "points-diff-negative"}`}>
            {" "}({diff >= 0 ? "+" : ""}{diff.toFixed(1)})
          </span>
        )}
      </div>
      {player.event_started ? (
        <div className="player-points">{player.event_points}</div>
      ) : (
        <div className="player-opponent">{player.next_opponent || "-"}</div>
      )}
    </div>
  );
}

export default function TeamPitch({ starting = [], subs = [] }) {
  if (!starting || starting.length === 0) {
    return <div>No data — click Load my team to see your formation.</div>;
  }

  const rows = POSITION_ORDER
    .map((type) => starting.filter((p) => p.element_type === type))
    .filter((row) => row.length > 0);

  return (
    <div className="pitch">
      {rows.map((row, idx) => (
        <div className="pitch-row" key={idx}>
          {row.map((p) => (
            <PlayerCard key={p.id} player={p} />
          ))}
        </div>
      ))}

      {subs.length > 0 && (
        <div className="pitch-bench">
          <div className="bench-label">Substitutes</div>
          <div className="pitch-row">
            {subs.map((p) => (
              <PlayerCard key={p.id} player={p} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export { POSITION_LABELS };
