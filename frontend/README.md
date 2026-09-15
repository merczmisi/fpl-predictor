# Frontend Starter (React)

This file describes a minimal React development flow that calls the FastAPI backend at `http://localhost:8000`.

Create a new app with Vite (recommended) or Create React App:

```bash
# with npm + Vite + React
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm run dev
```

Example fetch snippet to call the backend (use in a component):

```js
// Fetch expected points for an entry
async function fetchExpectedPoints(eventId) {
  const res = await fetch(`http://localhost:8000/expected_points/my_team?event_id=${eventId}`);
  const body = await res.json();
  return body.data; // array of player records
}

// Example usage in React (pseudo-code)
// const [players, setPlayers] = useState([])
// useEffect(() => { fetchExpectedPoints(293299).then(setPlayers) }, [])
```

Frontends should query the `webapi` endpoints rather than calling external FPL APIs directly; this lets the server manage auth, caching, and rate limits.
