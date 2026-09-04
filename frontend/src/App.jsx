import React, { useMemo, useState } from "react";
import ExpectedPointsChart from "./ExpectedPointsChart";

export default function App() {
  const [entryId, setEntryId] = useState(299995);
  const [loading, setLoading] = useState(false);
  const [players, setPlayers] = useState([]);

  async function fetchData() {
    setLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/expected_points?entry_id=${entryId}&use_my_team=true`);
      const body = await res.json();
      setPlayers(body.data || []);
    } catch (err) {
      console.error(err);
      alert("Error fetching expected points: " + (err.message || err));
    } finally {
      setLoading(false);
    }
  }

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
      next_match_difficulty: p.next_match_difficulty ?? p.fixture_adjusted_points ?? null,
      chance_of_playing_next_round: p.chance_of_playing_next_round ?? p.chance_of_playing ?? null,
    }));
  }, [players]);

  const totalFirst11 = useMemo(() => {
    return selected.slice(0, 11).reduce((sum, p) => sum + (Number(p.expected_points) || 0), 0);
  }, [selected]);

  return (
    <div className="app">
      <header>
        <h1>FPL Draft — Expected Points</h1>
      </header>

      <section className="controls">
        <label>
          Entry ID:
          <input type="number" value={entryId} onChange={(e) => setEntryId(Number(e.target.value))} />
        </label>
        <button onClick={fetchData} disabled={loading}>
          {loading ? "Loading…" : "Fetch"}
        </button>
      </section>

      <section className="chart">
        <ExpectedPointsChart data={selected} />
      </section>

      <section className="table">
        <h2>Players (sorted by expected_points)</h2>
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>web_name</th>
              <th>expected_points</th>
              <th>team</th>
              <th>element_type</th>
              <th>next_match_difficulty</th>
              <th>chance_of_playing_next_round</th>
            </tr>
          </thead>
          <tbody>
            {selected.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td>
                <td>{p.web_name}</td>
                <td>{p.expected_points}</td>
                <td>{p.team}</td>
                <td>{p.element_type}</td>
                <td>{p.next_match_difficulty}</td>
                <td>{p.chance_of_playing_next_round}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ marginTop: "1rem", fontWeight: "bold" }}>
          Total expected points (first 11): {totalFirst11}
        </div>
      </section>
    </div>
  );
}
