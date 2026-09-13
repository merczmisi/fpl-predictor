import React from "react";

const POSITION_ORDER = [1, 2, 3, 4]; // 1 gk, 2 def, 3 mid, 4 fwd
const POSITION_LABELS = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };

function PlayerCard({ player }) {
  return (
    <div className={`player-card position-${player.element_type}`}>
      <div className="player-shirt" aria-hidden="true" />
      <div className="player-name">{player.web_name}</div>
      <div className="player-opponent">{player.next_opponent || "-"}</div>
      <div className="player-points">{player.expected_points.toFixed(1)}</div>
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
