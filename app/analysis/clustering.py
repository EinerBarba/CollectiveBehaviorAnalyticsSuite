"""Grouping windows into behavioral states with a Gaussian mixture model.

Each window is a point in feature space (P, P_local, M and, with a stimulus,
S). Gaussian mixture models with 2 to 5 components are fitted, the number of
states is chosen by BIC, and every window is labeled with its most likely
state. See [Collective behavior](../pipeline/collective-behavior.md).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

K_RANGE = (2, 3, 4, 5)
"""Numbers of states tried."""

N_INIT = 10
"""Random restarts per fit. The best of them is kept."""

FEATURES = ["P", "P_local", "M", "S_normalized"]
"""Features used when there is a stimulus. `S_normalized` is S rescaled to 0 to 1."""

FEATURES_NO_STIMULUS = ["P", "P_local", "M"]
"""Features used when there is no stimulus."""


def _fit_gmm(X: np.ndarray, k: int) -> GaussianMixture:
    """Fit one mixture with `k` components, full covariance and a fixed random seed."""
    gmm = GaussianMixture(
        n_components=k,
        covariance_type="full",
        n_init=N_INIT,
        random_state=0,
    )
    gmm.fit(X)
    return gmm


def fit_gmm_models(
    windows: pd.DataFrame,
    features: list[str] | None = None,
) -> tuple[dict, pd.DataFrame]:
    """Fit a mixture for every number of states in `K_RANGE`.

    Only windows marked `included_in_clustering` are used. Missing feature
    values (such as S without a stimulus) are replaced with 0.5.

    Args:
        windows: Window features, with an `included_in_clustering` column.
        features: Feature columns to use. Defaults to `FEATURES`.

    Returns:
        The fitted models, keyed by number of states, each as
        (model, BIC, AIC); and a table of `k`, `bic` and `aic`.
    """
    if features is None:
        features = FEATURES
    sub = windows[windows["included_in_clustering"]].copy()
    X = sub[features].fillna(0.5).to_numpy(dtype=float)

    models: dict[int, tuple[GaussianMixture, float, float]] = {}
    for k in K_RANGE:
        gmm = _fit_gmm(X, k)
        models[k] = (gmm, float(gmm.bic(X)), float(gmm.aic(X)))

    bic_df = pd.DataFrame(
        [{"k": k, "bic": bic, "aic": aic} for k, (_, bic, aic) in models.items()]
    )
    return models, bic_df


def select_best_k(models: dict, bic_df: pd.DataFrame) -> int:
    """Pick the number of states with the lowest BIC.

    If the winner is not 4 but 4 states scores within 10 BIC units of it, a
    note is printed to the server log suggesting the fourth state be
    inspected. The choice itself is not changed.

    Args:
        models: The fitted models, as returned by `fit_gmm_models`.
        bic_df: The score table, as returned by `fit_gmm_models`.

    Returns:
        The chosen number of states.
    """
    best_k = int(bic_df.loc[bic_df["bic"].idxmin(), "k"])
    if best_k != 4:
        bic_k4 = bic_df.loc[bic_df["k"] == 4, "bic"].values[0]
        bic_best = bic_df.loc[bic_df["k"] == best_k, "bic"].values[0]
        if bic_k4 - bic_best <= 10.0:
            print(
                f"[clustering] k=4 is within 10 BIC units of best k={best_k} "
                f"(Δ={bic_k4 - bic_best:.2f}). Inspect fourth centroid."
            )
    return best_k


def assign_states(
    windows: pd.DataFrame,
    gmm: GaussianMixture,
    features: list[str] | None = None,
    sort_by: str = "S_normalized",
) -> pd.DataFrame:
    """Label every window with a state, numbered in a meaningful order.

    The model's components come out in arbitrary order, so they are
    renumbered by the mean of `sort_by` over the clustered windows, lowest
    first. State 0 therefore has the lowest mean of that column.

    Every window gets a label, including windows excluded from fitting.

    Args:
        windows: Window features.
        gmm: The chosen fitted model.
        features: Feature columns the model was fitted on.
        sort_by: Column used to order the states. Defaults to
            `S_normalized`; the experiment-level analysis uses `P`.

    Returns:
        A copy of `windows` with `state`, one `prob_<i>` column per state
        (the probability of belonging to it), and `assignment_entropy`
        (0 when the window clearly belongs to one state, higher when it is
        ambiguous).
    """
    if features is None:
        features = FEATURES
    windows = windows.copy()
    X_all = windows[features].fillna(0.5).to_numpy(dtype=float)
    raw_probs = gmm.predict_proba(X_all)
    raw_labels = gmm.predict(X_all)

    k = gmm.n_components

    sub_mask = windows["included_in_clustering"].to_numpy()
    raw_sub_labels = raw_labels[sub_mask]

    # Order states by mean of sort_by column (ascending)
    if sort_by in windows.columns:
        sort_vals = windows.loc[sub_mask, sort_by].fillna(0.5).to_numpy()
    else:
        sort_vals = np.zeros(int(sub_mask.sum()))
    mean_sort_per_component = np.array(
        [sort_vals[raw_sub_labels == c].mean() if (raw_sub_labels == c).any() else 0.0
         for c in range(k)]
    )
    order = np.argsort(mean_sort_per_component)
    raw_to_state = np.empty(k, dtype=int)
    for state_i, raw_c in enumerate(order):
        raw_to_state[raw_c] = state_i

    reordered_probs = raw_probs[:, order]

    windows["state"] = raw_to_state[raw_labels]
    for i in range(k):
        windows[f"prob_{i}"] = reordered_probs[:, i]

    eps = 1e-12
    ent = -np.sum(reordered_probs * np.log(reordered_probs + eps), axis=1)
    windows["assignment_entropy"] = ent

    return windows
