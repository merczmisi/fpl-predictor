import React from "react";
import Plot from "react-plotly.js";

export default function ExpectedPointsChart({ data = [] }) {
  if (!data || data.length === 0) {
    return <div>No data — click Fetch to load expected points.</div>;
  }

  // Map to chartable arrays
  const names = data.map((r) => r.web_name || `${r.first_name || ""} ${r.second_name || ""}`);
  const points = data.map((r) => Number(r.expected_points) || 0);

  return (
    <div>
      <Plot
        data={[
          {
            x: names,
            y: points,
            type: "bar",
            marker: { color: "#1f77b4" },
          },
        ]}
        layout={{ title: "Expected Points by Player", xaxis: { automargin: true }, yaxis: { title: "Expected Points" }, height: 500 }}
        config={{ responsive: true }}
      />
    </div>
  );
}
