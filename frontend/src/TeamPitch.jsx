import React, { useRef, useState } from "react";

const POSITION_ORDER = [1, 2, 3, 4]; // 1 gk, 2 def, 3 mid, 4 fwd
const POSITION_LABELS = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };

function formatValue(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "-";
  return `${value}${suffix}`;
}

function formatDate(isoString) {
  if (!isoString) return null;
  const parsed = new Date(isoString);
  return Number.isNaN(parsed.getTime()) ? isoString : parsed.toLocaleDateString();
}

// Show a green/red arrow when the trade's outcome is decided, nothing when tied or unknown.
function tradeOutcomeIndicator(trade) {
  const mine = trade?.points_since_trade;
  const theirs = trade?.traded_with_points_since_trade;
  if (mine === null || mine === undefined || theirs === null || theirs === undefined) return null;
  if (mine === theirs) return null;

  const won = mine > theirs;
  return (
    <span
      className={`trade-outcome ${won ? "trade-outcome-positive" : "trade-outcome-negative"}`}
      title={won ? "Earned more than the traded-away player" : "Earned less than the traded-away player"}
    >
      {" "}
      {won ? "▲" : "▼"}
    </span>
  );
}

function PlayerInfoDialog({ player, onClose }) {
  const dialogRef = useRef(null);

  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (player) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  }, [player]);

  const raw = player?.raw || {};
  const fullName =
    [raw.first_name, raw.second_name].filter(Boolean).join(" ") || player?.web_name;
  const price = raw.now_cost !== undefined && raw.now_cost !== "" ? (Number(raw.now_cost) / 10).toFixed(1) : null;

  return (
    <dialog
      ref={dialogRef}
      className="player-dialog"
      onClose={onClose}
      onCancel={onClose}
    >
      {player && (
        <>
          <h3>{fullName}</h3>
          <dl className="player-dialog-details">
            <dt>Position</dt>
            <dd>{POSITION_LABELS[player.element_type] || "-"}</dd>

            <dt>Next opponent</dt>
            <dd>{formatValue(player.next_opponent)}</dd>

            <dt>Price</dt>
            <dd>{price !== null ? `£${price}m` : "-"}</dd>

            <dt>Selected by</dt>
            <dd>{formatValue(raw.selected_by_percent, "%")}</dd>

            <dt>Status</dt>
            <dd>{formatValue(raw.status)}</dd>

            {raw.news ? (
              <>
                <dt>News</dt>
                <dd>{raw.news}</dd>
              </>
            ) : null}

            <dt>Chance of playing</dt>
            <dd>{formatValue(raw.chance_of_playing_next_round, "%")}</dd>

            <dt>Form</dt>
            <dd>{formatValue(raw.form)}</dd>

            <dt>Points per game</dt>
            <dd>{formatValue(raw.points_per_game)}</dd>

            <dt>Total points</dt>
            <dd>{formatValue(raw.total_points)}</dd>

            <dt>Minutes</dt>
            <dd>{formatValue(raw.minutes)}</dd>

            <dt>Goals</dt>
            <dd>{formatValue(raw.goals_scored)}</dd>

            <dt>Assists</dt>
            <dd>{formatValue(raw.assists)}</dd>

            <dt>Clean sheets</dt>
            <dd>{formatValue(raw.clean_sheets)}</dd>

            <dt>Bonus</dt>
            <dd>{formatValue(raw.bonus)}</dd>

            <dt>Expected points</dt>
            <dd>{formatValue(player.expected_points?.toFixed?.(1))}</dd>

            {player.trade ? (
              <>
                <dt>Traded for</dt>
                <dd>{formatValue(player.trade.traded_with_name)}</dd>

                <dt>Traded on</dt>
                <dd>{formatValue(formatDate(player.trade.traded_at))}</dd>

                <dt>Points since trade</dt>
                <dd>
                  {formatValue(player.trade.points_since_trade)}
                  {tradeOutcomeIndicator(player.trade)}
                </dd>

                <dt>{formatValue(player.trade.traded_with_name)} points since trade</dt>
                <dd>{formatValue(player.trade.traded_with_points_since_trade)}</dd>
              </>
            ) : null}
          </dl>
          <button type="button" onClick={onClose} autoFocus>
            Close
          </button>
        </>
      )}
    </dialog>
  );
}

function PlayerCard({ player, onInfoClick }) {
  const diff = player.event_started
    ? player.event_points - player.expected_points
    : null;
  const isGoalkeeper = player.element_type === 1;
  const shirtSrc = player.team_code
    ? `/shirts/shirt_${player.team_code}${isGoalkeeper ? "_1" : ""}.webp`
    : null;

  return (
    <div className={`player-card position-${player.element_type}`}>
      <button
        type="button"
        className="player-info-btn"
        aria-label={`Show info for ${player.web_name}`}
        onClick={() => onInfoClick(player)}
      >
        i
      </button>
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
      <div className="player-details-container">
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
    </div>
  );
}

export default function TeamPitch({ starting = [], subs = [] }) {
  const [infoPlayer, setInfoPlayer] = useState(null);

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
            <PlayerCard key={p.id} player={p} onInfoClick={setInfoPlayer} />
          ))}
        </div>
      ))}

      {subs.length > 0 && (
        <div className="pitch-bench">
          <div className="bench-label">Substitutes</div>
          <div className="pitch-row">
            {subs.map((p) => (
              <PlayerCard key={p.id} player={p} onInfoClick={setInfoPlayer} />
            ))}
          </div>
        </div>
      )}

      <PlayerInfoDialog player={infoPlayer} onClose={() => setInfoPlayer(null)} />
    </div>
  );
}

export { POSITION_LABELS };
