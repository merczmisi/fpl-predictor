from __future__ import annotations

from typing import Any

import pandas as pd

from fpl_draft import api
from fpl_draft.features import (
    compute_base_points,
    apply_fdr_multiplier,
    compute_expected_points_from_df,
)


def compute_expected_points_for_entry(
    client: Any, entry_id: int, event_id: int
) -> pd.DataFrame:
    """Orchestrate expected points computation for an entry/event.

    - Fetch player ids via the API wrappers (uses `client.get`).
    - Fetch `bootstrap-static` and select the players in the same order.
    - Compute base points, apply FDR multipliers, and final expected points.

    The function intentionally accepts a thin `client` object with a
    `.get(url, **kwargs)` method so it can be used with `requests.Session`,
    `FplHttpClient` wrappers, or simple test doubles.
    """

    player_ids = api.get_player_ids(client, entry_id, event_id)

    data = api.get_bootstrap_static(client)

    players = pd.json_normalize(data["elements"])

    selected = players.set_index("id").loc[player_ids].reset_index()

    # Ensure numeric columns
    selected["form"] = pd.to_numeric(selected["form"], errors="coerce")
    selected["points_per_game"] = pd.to_numeric(
        selected["points_per_game"], errors="coerce"
    )
    selected["chance_of_playing_next_round"] = pd.to_numeric(
        selected["chance_of_playing_next_round"], errors="coerce"
    )

    selected = compute_base_points(selected)

    # Retrieve next match difficulty using the API wrapper which will call
    # `client.get(...)` for element summaries. This keeps network calls
    # encapsulated and makes testing easier.
    selected["next_match_difficulty"] = selected["id"].apply(
        lambda pid: api.get_next_match_difficulty(client, int(pid))
    )

    selected = apply_fdr_multiplier(selected)

    selected = compute_expected_points_from_df(selected)

    return selected
