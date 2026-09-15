import React, { useEffect, useMemo, useState } from "react";
import TeamPitch from "./TeamPitch";

// FDR 1 (easy) -> green, FDR 5 (difficult) -> red
const DIFFICULTY_COLORS = {
  1: "#2dc937",
  2: "#99c140",
  3: "#e7b416",
  4: "#db7b2b",
  5: "#cc3232",
};

function difficultyColor(difficulty) {
  return DIFFICULTY_COLORS[Number(difficulty)] || "transparent";
}

export default function App() {
  const [players, setPlayers] = useState([]);
  const [connection, setConnection] = useState("checking");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [eventId, setEventId] = useState(null);
  const [currentEventFinished, setCurrentEventFinished] = useState(null);

  useEffect(() => {
    async function checkConnection() {
      try {
        const res = await fetch("/auth/status");
        if (!res.ok) {
          throw new Error(`Request failed with status ${res.status}`);
        }

        const body = await res.json();
        setConnection(body.connected ? "connected" : "disconnected");
      } catch (err) {
        console.error(err);
        setConnection("error");
        setError(err.message || String(err));
      }
    }

    checkConnection();
  }, []);

  async function connectFpl() {
    setConnection("connecting");
    setError("");

    try {
      const res = await fetch("/auth/connect", { method: "POST" });
      const body = await res.json();
      if (!res.ok) {
        throw new Error(body.detail || `Request failed with status ${res.status}`);
      }
      setConnection("connected");
    } catch (err) {
      console.error(err);
      setConnection("disconnected");
      setError(err.message || String(err));
    }
  }

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const gameRes = await fetch("/game_state");
      if (!gameRes.ok) {
        throw new Error(`Request failed with status ${gameRes.status}`);
      }

      const gameBody = await gameRes.json();
      const resolvedEventId = gameBody.current_event_finished
        ? gameBody.next_event
        : gameBody.current_event;

      setCurrentEventFinished(gameBody.current_event_finished);
      setEventId(resolvedEventId);

      const res = await fetch(`/expected_points/my_team?event_id=${resolvedEventId}`);
      if (!res.ok) {
        throw new Error(`Request failed with status ${res.status}`);
      }

      const body = await res.json();
      setPlayers(body.data || []);
    } catch (err) {
      console.error(err);
      setError(err.message || String(err));
    } finally {
      setLoading(false);
    }
  }

  // Formation view preserves the original API order: first 11 are the
  // starting XI, the remaining players are substitutes.
  const { starting, subs } = useMemo(() => {
    const normalized = players.map((p) => ({
      id: p.id,
      web_name: p.web_name || `${p.first_name || ""} ${p.second_name || ""}`.trim(),
      element_type: Number(p.element_type) || 0,
      team_code: p.team_code || null,
      event_started: p.event_started ?? null,
      event_points: Number(p.event_points || 0),
      next_opponent: p.next_opponent || null,
      expected_points: Number(p.expected_points || 0),
    }));

    return { starting: normalized.slice(0, 11), subs: normalized.slice(11, 15) };
  }, [players]);

  // Derive a sorted, selected columns view similar to the pandas snippet
  const selected = useMemo(() => {
    if (!players || players.length === 0) return [];

    const copy = [...players];
    copy.sort((a, b) => (Number(b.expected_points || 0) - Number(a.expected_points || 0)));

    return copy.map((p) => ({
      id: p.id,
      web_name: p.web_name || `${p.first_name || ""} ${p.second_name || ""}`.trim(),
      expected_points: Number(p.expected_points || 0),
      team: p.team || p.team_name || "",
      element_type: p.element_type || p.position || "",
      next_match_difficulty: p.next_match_difficulty ?? null,
      chance_of_playing_next_round: p.chance_of_playing_next_round ?? 100,
      next_opponent: p.next_opponent ?? null,
      event_points: Number(p.event_points || 0),
    }));
  }, [players]);

  const totalXPFirst11 = useMemo(() => {
    return starting.reduce((sum, p) => sum + (Number(p.expected_points) || 0), 0);
  }, [starting]);

  const totalFirst11 = useMemo(() => {
    return starting.reduce((sum, p) => sum + (Number(p.event_points) || 0), 0);
  }, [starting]);

  const pointsDiff = totalFirst11 - totalXPFirst11;

  return (
    <div className="app">
      <header>
        <h1>FPL Draft — Expected Points</h1>
        <p className={`connection connection-${connection}`}>
          {connection === "connected" && "FPL account connected"}
          {connection === "disconnected" && "Connect your FPL account to load your team."}
          {connection === "connecting" && "Waiting for FPL login..."}
          {connection === "checking" && "Checking local connection..."}
          {connection === "error" && "The local API is unavailable."}
        </p>
      </header>

      <section className="controls" aria-label="FPL account controls">
        {connection !== "connected" && (
          <button type="button" onClick={connectFpl} disabled={connection === "connecting"}>
            {connection === "connecting" ? "Connect in progress..." : "Connect FPL account"}
          </button>
        )}
        {connection === "connected" && (
          <button type="button" onClick={loadData} disabled={loading}>
            {loading ? "Loading..." : "Load my team"}
          </button>
        )}
        {error && <p className="error">{error}</p>}
      </section>

      {players.length > 0 && (
        <>
          <div className="points-summary">
              Latest points
              <div className="total-points">
                {totalFirst11.toFixed(1)}
              </div>
              <div className="total-expected-points">
                xP: {totalXPFirst11.toFixed(1)}{" "}
                <span style={{ color: pointsDiff > 0 ? "green" : pointsDiff < 0 ? "red" : "inherit" }}>
                  ({pointsDiff > 0 ? "+" : ""}{pointsDiff.toFixed(1)})
                </span>
              </div>
          </div>


          <section className="pitch-section">
            <TeamPitch starting={starting} subs={subs} />
          </section>

          <section className="table">
            <h2>Players (sorted by expected_points)</h2>
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Expected Points</th>
                  <th>Next Opponent</th>
                </tr>
              </thead>
              <tbody>
                {selected.map((p) => (
                  <tr key={p.id}>
                    <td>{p.web_name}</td>
                    <td>{p.expected_points}</td>
                    <td>
                      <span
                        style={{
                          backgroundColor: difficultyColor(p.next_match_difficulty),
                          padding: "2px 6px",
                          borderRadius: "4px",
                        }}
                      >
                        {p.next_opponent}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
