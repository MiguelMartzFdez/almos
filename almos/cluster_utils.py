######################################################.
# This file stores clustering helper functions and   #
# the clustering model-selection engine used by      #
# the CLUSTER module.                                #
######################################################.

from __future__ import annotations

from dataclasses import dataclass
import math
import warnings
from typing import Any, Callable

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from sklearn.mixture import GaussianMixture
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.decomposition import PCA
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler

try:
    from bayes_opt import BayesianOptimization, acquisition
except ImportError:  # pragma: no cover
    BayesianOptimization = None
    acquisition = None

try:
    import hdbscan
    from hdbscan.validity import validity_index as hdbscan_validity_index
except ImportError:  # pragma: no cover
    hdbscan = None
    hdbscan_validity_index = None

# Clustering metrics used in model selection:
#
# - silhouette_score:
#     Main geometric signal of separation and compactness.
#     Higher is better. Bounded in [-1, 1].
#
# - adjusted_rand_score (stability):
#     Measures consistency of clustering under perturbations
#     (e.g., subsampling or repeated fits).
#     Higher is better. In practical use it is typically in [0, 1],
#     although it can be slightly negative.
#
# - davies_bouldin_score:
#     Measures cluster overlap and internal dispersion.
#     Lower is better. Unbounded, but values close to 0 indicate
#     better-separated and more compact clusters.
#
# - calinski_harabasz_score:
#     Ratio of between-cluster dispersion to within-cluster dispersion.
#     Higher is better, but it has no absolute scale and may grow with
#     dataset size or cluster count.
#     Therefore, it is only meaningful for comparing models fitted on
#     the same dataset, and it is not used in the final cross-algorithm ranking.
#
# - noise_fraction:
#     Fraction of samples labeled as noise, mainly for density-based methods.
#     Used as a penalty to avoid solutions that discard excessive data.
#
# - imbalance_penalty:
#     Penalizes highly skewed cluster size distributions
#     (e.g., one giant cluster plus tiny residual clusters).
#
# Design note:
# - The final global ranking prioritizes robustness and geometric separation
#   over algorithm-specific criteria or raw model fit.
# - Metrics without a stable or comparable scale (e.g., Calinski-Harabasz)
#   are used only for intra-family ranking, not for cross-algorithm comparison.
# - As a result, a candidate may still lose globally even if it is favored by
#   an internal criterion such as GMM BIC.

# Small tolerance to avoid floating point comparison issues
SCORE_TOLERANCE = 1e-9
SCORE_PRACTICAL_TIE_TOLERANCE = 0.02

# Conditional dimensionality reduction safeguard:
# - The standard path clusters directly in cleaned descriptor space.
# - If the descriptor count grows too much, PCA is enabled automatically to keep
#   the optimization tractable and avoid clustering directly in an overly wide space.
HIGH_DIMENSIONALITY_THRESHOLD = 50
PCA_EXPLAINED_VARIANCE_THRESHOLD = 0.95
PCA_MIN_ACCEPTABLE_EXPLAINED_VARIANCE = 0.85
PCA_MIN_COMPONENTS = 3
# The PCA safeguard should remain bounded, but not by an overly rigid small cap.
# For wide descriptor tables, allow PCA to keep more components when needed to
# recover enough explained variance, while still preventing a near-identity transform.
PCA_MAX_COMPONENTS_ABSOLUTE = 100
PCA_MAX_COMPONENTS_FRACTION = 0.75
ENABLE_PCA_SAFEGUARD = True

# Large-dataset efficiency safeguards:
# - approximate the most expensive metrics on a subsample
# - reduce the number of stability repetitions
# - use a smaller HDBSCAN search space
ENABLE_LARGE_DATASET_MODE = True
STANDARD_DATASET_THRESHOLD = 2000
VERY_LARGE_DATASET_THRESHOLD = 10000
ULTRA_LARGE_DATASET_THRESHOLD = 25000
LARGE_SILHOUETTE_SAMPLE_SIZE = 1500
VERY_LARGE_SILHOUETTE_SAMPLE_SIZE = 2000
ULTRA_LARGE_SILHOUETTE_SAMPLE_SIZE = 3000
LARGE_DATASET_STABILITY_REPEATS = 3
FAST_SCREENING_TOP_CANDIDATES = 3

# Very-large-dataset KMeans safeguard:
# - KMeans is relatively cheap, but evaluating every k up to a large k_max still becomes
#   expensive when the dataset is very large.
# - Above this threshold, KMeans switches to a discrete Bayesian search over k.
KMEANS_COARSE_GRID_SIZE = 10
KMEANS_TOP_REFINEMENT_CANDIDATES = 1
KMEANS_REFINE_RADIUS = 2
KMEANS_BO_FRACTION = 0.20
KMEANS_BO_MAX_EVALUATIONS = 30

# GMM adaptive search settings:
# - GMM remains part of the model comparison, but it is given an adaptive search
#   budget because each fit is much more expensive than KMeans.
# - Small datasets keep broader GMM coverage.
# - Large datasets use a tighter search budget to avoid letting GMM dominate runtime.
GMM_BO_FRACTION = 0.08
GMM_BO_MAX_EVALUATIONS = 16
GMM_BIC_SHORTLIST_SIZE = 3
FilterResult = tuple[bool, list[str]]


@dataclass
class ClusteringCandidate:
    """
    Store the evaluation result of one clustering candidate configuration.
    """

    algorithm: str
    params: dict[str, Any]
    labels: np.ndarray
    raw_metrics: dict[str, Any]
    filter_reasons: list[str]
    passed_filters: bool
    internal_score: float | None = None
    final_score: float | None = None
    rank_metrics: dict[str, float] | None = None


@dataclass
class ClusteringSelectionResult:
    """
    Store the global output of the clustering model-selection stage.
    """

    scaler_name: str
    scaled_data: np.ndarray
    model_input_data: np.ndarray
    best_candidate: ClusteringCandidate | None
    best_by_algorithm: dict[str, ClusteringCandidate]
    all_candidates: list[ClusteringCandidate]
    summary_df: pd.DataFrame
    quality_assessment: dict[str, Any]
    dimensionality_reduction_info: dict[str, Any]
    descriptor_columns: list[str]


def _format_descriptor_preview(columns, max_items=8):
    if not columns:
        return "none"

    preview = [str(column) for column in columns[:max_items]]
    if len(columns) > max_items:
        preview.append(f"... (+{len(columns) - max_items} more)")
    return str(preview)

def remove_low_information_descriptors(df, log=None, top_freq_threshold=0.98):
    '''
    Remove descriptors that provide little to no information:
    - Constant descriptors (only one unique value)
    - Near-constant descriptors (one value dominates the distribution)
    '''

    constant_cols, near_constant_cols = [], []

    for column in df.columns:
        non_null_series = df[column].dropna()

        # Constant
        if non_null_series.nunique() <= 1:
            constant_cols.append(column)
            continue

        # Near-constant
        if len(non_null_series) > 0:
            top_freq = non_null_series.value_counts(normalize=True, dropna=True).iloc[0]

            if top_freq >= top_freq_threshold:
                near_constant_cols.append(column)

    # --- Logging (structured) ---
    if log is not None:
        log.write("\no Low-information descriptors:")
        log.write(
            f"   - Constant descriptors removed: {len(constant_cols)} "
            f"({_format_descriptor_preview(constant_cols)})"
        )
        log.write(
            f"   - Near-constant descriptors removed: {len(near_constant_cols)} "
            f"(threshold: {top_freq_threshold}; {_format_descriptor_preview(near_constant_cols)})"
        )

    # Drop columns
    cols_to_drop = constant_cols + near_constant_cols
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    return df, constant_cols, near_constant_cols

def remove_duplicate_descriptors(df, log=None):
    '''
    Remove duplicated descriptor columns (columns with exactly identical values).
    Only the first occurrence is kept.
    '''

    # Transpose → columns become rows → detect identical columns
    duplicated_mask = df.T.duplicated(keep='first')
    duplicated_cols = df.columns[duplicated_mask].tolist()

    duplicate_pairs = []

    # Log which column each duplicate matches
    if log is not None and duplicated_cols:
        kept_columns = df.columns[~duplicated_mask].tolist()

        for duplicated_col in duplicated_cols:
            for kept_col in kept_columns:
                # Exact equality check
                if df[duplicated_col].equals(df[kept_col]):
                    duplicate_pairs.append(f"{duplicated_col} -> {kept_col}")
                    break

    # Drop duplicated columns
    if duplicated_cols:
        df = df.loc[:, ~duplicated_mask]

    if log is not None:
        log.write(
            f"o Duplicated descriptors removed: {len(duplicated_cols)} "
            f"({_format_descriptor_preview(duplicate_pairs)})"
        )

    return df, duplicated_cols

def get_descriptor_variability_stats(series):
    '''
    Compute variability statistics for a descriptor.

    - Binary descriptors:
        score = minority class ratio → measures class balance

    - Continuous descriptors:
        Two complementary measures are computed:
        1) iqr → absolute variability (robust to outliers)
        2) rel_score = iqr / (|median| + iqr) → relative variability (scale-invariant)

    The idea is:
    - IQR detects near-constant descriptors
    - rel_score detects whether variability is meaningful relative to the scale
    '''

    non_null_series = series.dropna()

    if len(non_null_series) == 0:
        return None

    unique_vals = non_null_series.nunique()

    # --- Binary / quasi-binary case ---
    if unique_vals <= 2:
        class_ratios = non_null_series.value_counts(normalize=True, dropna=True)

        major_class_ratio = float(class_ratios.iloc[0])
        minor_class_ratio = 1.0 - major_class_ratio

        return {
            'type': 'binary',
            'score': minor_class_ratio,
            'major_class_ratio': major_class_ratio,
            'minor_class_ratio': minor_class_ratio
        }

    # --- Continuous case ---
    x = non_null_series.astype(float)

    std_value = float(x.std(ddof=0))
    median_value = float(np.median(x))
    q1 = float(np.percentile(x, 25))
    q3 = float(np.percentile(x, 75))
    iqr = q3 - q1

    # Absolute variability (robust)
    iqr_score = iqr

    # Relative variability (scale-invariant, stable)
    # - If median is large -> penalizes small relative variation
    # - If median is near zero -> behaves like iqr / iqr -> ~1 when iqr > 0
    # - If both median and iqr are zero, treat the descriptor as having no relative
    #   variability instead of raising 0/0
    denominator = abs(median_value) + iqr
    if denominator <= SCORE_TOLERANCE:
        rel_score = 0.0
    else:
        rel_score = iqr / denominator

    return {
        'type': 'continuous',
        'score': rel_score,  # used for comparisons (e.g., correlation step)
        'iqr_score': iqr_score,
        'rel_score': rel_score,
        'std': std_value,
        'median': median_value,
        'iqr': iqr
    }

def remove_low_variance_descriptors(df, log=None,
                                    iqr_threshold=1e-6,
                                    rel_threshold=0.02,
                                    binary_threshold=0.05):
    '''
    Remove descriptors with low variability.

    Continuous descriptors:
    -----------------------
    Two complementary criteria are used:

    1) Absolute variability (IQR):
       - Detects near-constant descriptors
       - Independent of scale

    2) Relative variability (rel_score):
       - rel_score = iqr / (|median| + iqr)
       - Detects whether variation is meaningful relative to magnitude
       - Prevents large-scale but flat descriptors from being kept

    A descriptor is removed if it fails ANY of these criteria.

    Binary descriptors:
    -------------------
    - Use minority class ratio (balance between classes)
    - Controlled via binary_threshold

    Design philosophy:
    ------------------
    Conservative filtering:
    - Prefer keeping borderline descriptors rather than removing useful ones
    - Thresholds can be tuned depending on aggressiveness
    '''

    if len(df.columns) == 0:
        return df, []

    low_variance_cols = []
    variability_stats = {}

    for column in df.columns:
        stats = get_descriptor_variability_stats(df[column])

        if stats is None:
            continue

        variability_stats[column] = stats

        if stats['type'] == 'binary':
            # --- Binary case ---
            # Remove if minority class is too small (highly imbalanced)
            if stats['score'] < binary_threshold:
                low_variance_cols.append(column)

        else:
            # --- Continuous case ---
            iqr = stats['iqr_score']
            rel_score = stats['rel_score']

            # Rule 1: Almost constant (absolute variability too small)
            if iqr < iqr_threshold:
                low_variance_cols.append(column)

            # Rule 2: Variability too small relative to scale
            elif rel_score < rel_threshold:
                low_variance_cols.append(column)

    removed_low_iqr = []
    removed_low_relative = []
    removed_binary = []
    for column in low_variance_cols:
        stats = variability_stats[column]
        if stats['type'] == 'binary':
            removed_binary.append(column)
        elif stats.get('iqr_score', 0.0) < iqr_threshold:
            removed_low_iqr.append(column)
        else:
            removed_low_relative.append(column)

    # --- Logging ---
    if log is not None:
        log.write("\no Low-variability analysis:")
        log.write(
            f"   - Removed {len(low_variance_cols)} descriptors "
            f"(iqr_threshold: {iqr_threshold}, rel_threshold: {rel_threshold}, binary_threshold: {binary_threshold})"
        )
        log.write(
            f"   - Removed by low IQR: {len(removed_low_iqr)} "
            f"({_format_descriptor_preview(removed_low_iqr)})"
        )
        log.write(
            f"   - Removed by low relative variability: {len(removed_low_relative)} "
            f"({_format_descriptor_preview(removed_low_relative)})"
        )
        log.write(
            f"   - Removed by binary imbalance: {len(removed_binary)} "
            f"({_format_descriptor_preview(removed_binary)})"
        )

    if low_variance_cols:
        df = df.drop(columns=low_variance_cols)

    return df, low_variance_cols

def remove_correlated_descriptors(df, log=None, corr_threshold=0.95):
    '''
    Remove highly correlated descriptors.

    When two descriptors are highly correlated:
    - Keep the one with higher variability score
    - Remove the less informative one
    '''

    if len(df.columns) <= 1:
        return df, []

    # Precompute variability scores for decision-making
    variability_stats = {}
    for column in df.columns:
        stats = get_descriptor_variability_stats(df[column])
        if stats is not None:
            variability_stats[column] = stats

    corr_matrix = df.corr().abs()
    upper_triangle_mask = np.triu(np.ones(corr_matrix.shape, dtype=bool), k=1)
    candidate_pairs = corr_matrix.where(upper_triangle_mask).stack()
    candidate_pairs = candidate_pairs[candidate_pairs >= corr_threshold]

    correlated_cols = set()
    correlation_decisions = []
    for (column_i, column_j), corr_value in candidate_pairs.items():
        if column_i in correlated_cols or column_j in correlated_cols:
            continue

        score_i = variability_stats.get(column_i, {}).get('score', -np.inf)
        score_j = variability_stats.get(column_j, {}).get('score', -np.inf)

        if score_i - score_j > SCORE_TOLERANCE:
            kept_column = column_i
            removed_column = column_j
            decision_reason = (
                f"kept '{kept_column}' because score {round(score_i, 6)} "
                f"> {round(score_j, 6)}"
            )
        elif score_j - score_i > SCORE_TOLERANCE:
            kept_column = column_j
            removed_column = column_i
            decision_reason = (
                f"kept '{kept_column}' because score {round(score_j, 6)} "
                f"> {round(score_i, 6)}"
            )
        else:
            kept_column = column_i
            removed_column = column_j
            decision_reason = (
                f"kept '{kept_column}' because both descriptors have the same "
                f"score {round(score_i, 6)}; tie resolved by column order"
            )

        correlated_cols.add(removed_column)

        correlation_decisions.append(
            f"{removed_column} -> {kept_column} (corr={round(float(corr_value), 4)})"
        )

    correlated_cols = list(correlated_cols)

    if correlated_cols:
        df = df.drop(columns=correlated_cols)

    if log is not None:
        log.write(
            f"o Highly correlated descriptors removed: {len(correlated_cols)} "
            f"(threshold: {corr_threshold}; {_format_descriptor_preview(correlation_decisions)})"
        )

    return df, correlated_cols


def log_descriptor_cleanup_summary(log, initial_columns, final_columns, removed_summary):
    '''
    Log a compact summary of the descriptor cleanup process:
    - What was removed at each step
    - Initial vs final dimensionality
    '''

    summary_lines = [
        '\no Descriptor cleanup summary:'
    ]

    for label, columns in removed_summary.items():
        summary_lines.append(f"   - Removed {len(columns)} {label}")

    summary_lines.append(f'   - Initial descriptor count: {len(initial_columns)}')
    summary_lines.append(f'   - Final descriptor count used for clustering: {len(final_columns)}')

    log.write('\n'.join(summary_lines))


def compute_cluster_descriptor_importance(
    descriptor_df: pd.DataFrame,
    labels: np.ndarray,
) -> pd.DataFrame:
    """
    Rank descriptors by how strongly their values separate the final clusters.

    This is an unsupervised interpretability summary, not a causal feature
    importance. Noise points from density-based clustering are ignored.
    """

    labels = np.asarray(labels)
    usable_mask = labels != -1
    usable_labels = labels[usable_mask]

    output_columns = [
        "rank",
        "descriptor",
        "f_score",
        "eta_squared",
        "n_samples_used",
        "n_clusters_used",
    ]
    if len(np.unique(usable_labels)) < 2:
        return pd.DataFrame(columns=output_columns)

    rows = []
    for descriptor in descriptor_df.columns:
        values = pd.to_numeric(descriptor_df[descriptor], errors="coerce").to_numpy(dtype=float)
        descriptor_mask = usable_mask & np.isfinite(values)
        descriptor_values = values[descriptor_mask]
        descriptor_labels = labels[descriptor_mask]
        unique_labels = np.unique(descriptor_labels)

        if len(unique_labels) < 2:
            continue

        overall_mean = float(np.mean(descriptor_values))
        ss_between = 0.0
        ss_within = 0.0

        for label in unique_labels:
            group_values = descriptor_values[descriptor_labels == label]
            group_mean = float(np.mean(group_values))
            ss_between += len(group_values) * (group_mean - overall_mean) ** 2
            ss_within += float(np.sum((group_values - group_mean) ** 2))

        df_between = len(unique_labels) - 1
        df_within = len(descriptor_values) - len(unique_labels)

        if df_within <= 0:
            f_score = np.nan
        elif ss_within <= SCORE_TOLERANCE:
            f_score = np.inf if ss_between > SCORE_TOLERANCE else 0.0
        else:
            f_score = (ss_between / df_between) / (ss_within / df_within)

        total_ss = ss_between + ss_within
        eta_squared = ss_between / total_ss if total_ss > SCORE_TOLERANCE else 0.0

        rows.append(
            {
                "descriptor": descriptor,
                "f_score": f_score,
                "eta_squared": eta_squared,
                "n_samples_used": int(len(descriptor_values)),
                "n_clusters_used": int(len(unique_labels)),
            }
        )

    importance_df = pd.DataFrame(rows)
    if importance_df.empty:
        return pd.DataFrame(columns=output_columns)

    importance_df = importance_df.sort_values(
        by=["f_score", "eta_squared", "descriptor"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    importance_df.insert(0, "rank", range(1, len(importance_df) + 1))
    return importance_df


class ClusteringSelectionEngine:
    """
    Search and compare clustering models using shared quality and stability metrics.

    Design notes:
    - The default workflow clusters directly in cleaned descriptor space after scaling.
    - If the descriptor count is too high for a direct clustering pass, a conditional PCA
      safeguard is applied before model selection. This is used only as a high-dimensional
      fallback, not as the default analysis path.
    - Different algorithms expose different native objectives, but final model comparison
      is always based on the same shared metrics to keep the ranking fair.
    - The pipeline does not assume that the best-ranked model is automatically "good";
      it also produces a qualitative assessment of the winning model and warns when the
      best available solution is still weak.
    """

    def __init__(
        self,
        log,
        random_state: int = 0,
        stability_repeats: int = 5,
        subsample_fraction: float = 0.8,
        hdbscan_enabled: bool = True,
        config: dict[str, Any] | None = None,
    ):
        self.log = log
        self.random_state = random_state
        self.stability_repeats = stability_repeats
        self.subsample_fraction = subsample_fraction
        self.hdbscan_enabled = hdbscan_enabled and hdbscan is not None
        self.config = config or {}
        self._rng = np.random.default_rng(random_state)
        self._is_large_dataset = False
        self._dataset_mode = "standard"
        self._effective_stability_repeats = stability_repeats

    def _config_value(self, key: str, default: Any) -> Any:
        return self.config.get(key, default)

    def _get_selected_algorithms(self) -> set[str]:
        return {
            str(algorithm).strip().lower()
            for algorithm in self._config_value("algorithms", ["kmeans", "gmm", "hdbscan"])
        }

    def _get_algorithm_skip_reason(
        self,
        algorithm: str,
        selected_algorithms: set[str],
    ) -> str | None:
        if algorithm not in selected_algorithms:
            return "skipped by user selection"

        if algorithm == "gmm" and self._dataset_mode == "ultra_large":
            return "skipped in ultra-large dataset mode"

        if algorithm == "hdbscan":
            if self._dataset_mode == "ultra_large":
                return "skipped in ultra-large dataset mode"
            if not self.hdbscan_enabled:
                return "unavailable (library not installed)"

        return None

    def _log_search_space_overview(
        self,
        n_samples: int,
        selected_algorithms: set[str],
    ) -> None:
        self.log.write("\no Search space overview:")

        kmeans_skip_reason = self._get_algorithm_skip_reason("kmeans", selected_algorithms)
        if kmeans_skip_reason is None:
            self.log.write(
                f"   - KMeans maximum cluster count: {self._compute_k_max(n_samples, 'KMeans')}"
            )
        else:
            self.log.write(f"   - KMeans: {kmeans_skip_reason}")

        gmm_skip_reason = self._get_algorithm_skip_reason("gmm", selected_algorithms)
        if gmm_skip_reason is None:
            self.log.write(
                f"   - GMM maximum cluster count: {self._compute_k_max(n_samples, 'GMM')}"
            )
        else:
            self.log.write(f"   - GMM: {gmm_skip_reason}")

        hdbscan_skip_reason = self._get_algorithm_skip_reason("hdbscan", selected_algorithms)
        if hdbscan_skip_reason is None:
            hdbscan_space = self._build_hdbscan_search_space(n_samples)
            self.log.write(
                f"   - HDBSCAN min_cluster_size candidates: {hdbscan_space['min_cluster_size']}"
            )
            self.log.write(
                f"   - HDBSCAN min_samples candidates: {hdbscan_space['min_samples']}"
            )
        else:
            self.log.write(f"   - HDBSCAN: {hdbscan_skip_reason}")

    @staticmethod
    def _format_dataset_mode_name(dataset_mode: str) -> str:
        return dataset_mode.replace("_", "-")

    def _get_dataset_mode_range_text(self) -> str:
        standard_threshold = self._config_value("standard_dataset_threshold", STANDARD_DATASET_THRESHOLD)
        very_large_threshold = self._config_value("very_large_dataset_threshold", VERY_LARGE_DATASET_THRESHOLD)
        ultra_large_threshold = self._config_value("ultra_large_dataset_threshold", ULTRA_LARGE_DATASET_THRESHOLD)

        if self._dataset_mode == "large":
            return f">{standard_threshold} and <= {very_large_threshold}"
        if self._dataset_mode == "very_large":
            return f">{very_large_threshold} and <= {ultra_large_threshold}"
        if self._dataset_mode == "ultra_large":
            return f">{ultra_large_threshold}"
        return f"<= {standard_threshold}"

    def _kmeans_n_init(self) -> int:
        if self._dataset_mode == "ultra_large":
            return 3
        if self._dataset_mode == "very_large":
            return 5
        if self._dataset_mode == "large":
            return 8
        return 20

    def _kmeans_max_iter(self) -> int:
        if self._dataset_mode == "ultra_large":
            return 120
        if self._dataset_mode == "very_large":
            return 160
        if self._dataset_mode == "large":
            return 220
        return 300

    def _gmm_n_init(self) -> int:
        if self._dataset_mode in {"large", "very_large", "ultra_large"}:
            return 2
        return 5

    def _gmm_max_iter(self) -> int:
        if self._dataset_mode in {"large", "very_large", "ultra_large"}:
            return 150
        return 300

    def select_best_model(self, descriptor_df: pd.DataFrame) -> ClusteringSelectionResult:
        """
        Fit and compare clustering candidates across the supported algorithms.
        """

        self.log.write("\no Clustering model selection")
        self.log.write(f"   - Number of samples: {len(descriptor_df)}")
        self.log.write(f"   - Number of descriptors: {len(descriptor_df.columns)}")
        self.log.write("   - Feature scaling: StandardScaler")
        self._configure_runtime_mode(len(descriptor_df))

        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(descriptor_df.to_numpy(dtype=float))
        model_input_data, dimensionality_reduction_info = self._prepare_model_input(
            scaled_data=scaled_data,
            descriptor_count=len(descriptor_df.columns),
        )

        selected_algorithms = self._get_selected_algorithms()
        self._log_search_space_overview(len(descriptor_df), selected_algorithms)

        all_candidates: list[ClusteringCandidate] = []
        best_by_algorithm: dict[str, ClusteringCandidate] = {}

        if self._get_algorithm_skip_reason("kmeans", selected_algorithms) is None:
            kmeans_candidates = self._evaluate_kmeans_candidates(model_input_data)
            all_candidates.extend(kmeans_candidates)
            best_kmeans = self._pick_best_candidate("KMeans", kmeans_candidates)
            if best_kmeans is not None:
                best_by_algorithm["KMeans"] = best_kmeans

        if self._get_algorithm_skip_reason("gmm", selected_algorithms) is None:
            gmm_candidates = self._evaluate_gmm_candidates(model_input_data)
            all_candidates.extend(gmm_candidates)
            best_gmm = self._pick_best_gmm_candidate(gmm_candidates)
            if best_gmm is not None:
                best_by_algorithm["GMM"] = best_gmm

        if self._get_algorithm_skip_reason("hdbscan", selected_algorithms) is None:
            hdbscan_candidates = self._evaluate_hdbscan_candidates(model_input_data)
            all_candidates.extend(hdbscan_candidates)
            best_hdbscan = self._pick_best_candidate("HDBSCAN", hdbscan_candidates)
            if best_hdbscan is not None:
                best_by_algorithm["HDBSCAN"] = best_hdbscan

        self._assign_final_scores(best_by_algorithm)

        best_candidate = None
        if best_by_algorithm:
            best_candidate = max(
                best_by_algorithm.values(),
                key=lambda candidate: candidate.final_score if candidate.final_score is not None else -np.inf,
            )

        summary_df = self._build_summary_dataframe(all_candidates)
        quality_assessment = self._assess_winner_quality(best_candidate)
        self._log_algorithm_summary(best_by_algorithm, best_candidate)
        self._log_quality_assessment(quality_assessment)

        return ClusteringSelectionResult(
            scaler_name="StandardScaler",
            scaled_data=scaled_data,
            model_input_data=model_input_data,
            best_candidate=best_candidate,
            best_by_algorithm=best_by_algorithm,
            all_candidates=all_candidates,
            summary_df=summary_df,
            quality_assessment=quality_assessment,
            dimensionality_reduction_info=dimensionality_reduction_info,
            descriptor_columns=list(descriptor_df.columns),
        )

    def _prepare_model_input(
        self,
        scaled_data: np.ndarray,
        descriptor_count: int,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """
        Prepare the matrix used by the clustering algorithms.

        Default path:
        - cluster directly on the scaled descriptor space

        High-dimensional safeguard:
        - if too many descriptors survive cleanup, apply PCA after scaling
        - retain enough components to explain most variance, while keeping the
          transformed space bounded and computationally manageable
        """

        high_dimensionality_threshold = self._config_value(
            "high_dimensionality_threshold",
            HIGH_DIMENSIONALITY_THRESHOLD,
        )
        enable_pca_safeguard = self._config_value(
            "enable_pca_safeguard",
            ENABLE_PCA_SAFEGUARD,
        )
        pca_explained_variance_threshold = self._config_value(
            "pca_explained_variance_threshold",
            PCA_EXPLAINED_VARIANCE_THRESHOLD,
        )
        pca_min_acceptable_variance = self._config_value(
            "pca_min_acceptable_variance",
            PCA_MIN_ACCEPTABLE_EXPLAINED_VARIANCE,
        )
        pca_min_components = self._config_value(
            "pca_min_components",
            PCA_MIN_COMPONENTS,
        )
        pca_max_components_fraction = self._config_value(
            "pca_max_components_fraction",
            PCA_MAX_COMPONENTS_FRACTION,
        )
        pca_max_components_absolute = self._config_value(
            "pca_max_components_absolute",
            PCA_MAX_COMPONENTS_ABSOLUTE,
        )

        if descriptor_count <= high_dimensionality_threshold:
            self.log.write("   - Clustering is performed directly on the cleaned descriptor space")
            return scaled_data, {
                "applied": False,
                "method": None,
                "input_descriptor_count": descriptor_count,
                "output_dimension": scaled_data.shape[1],
            }

        if not enable_pca_safeguard:
            self.log.write(
                f"\no PCA safeguard disabled by user "
                f"({descriptor_count} descriptors > {high_dimensionality_threshold})"
            )
            self.log.write("   - Clustering will continue directly on the scaled descriptor space")
            return scaled_data, {
                "applied": False,
                "method": None,
                "input_descriptor_count": descriptor_count,
                "output_dimension": scaled_data.shape[1],
                "disabled_by_user": True,
            }

        self.log.write(
            f"\nx WARNING. Descriptor count exceeds the direct clustering threshold "
            f"({descriptor_count} > {high_dimensionality_threshold})."
        )
        self.log.write("o Activating PCA safeguard before clustering")

        pca_full = PCA(random_state=self.random_state)
        pca_full.fit(scaled_data)
        cumulative_variance = np.cumsum(pca_full.explained_variance_ratio_)
        suggested_components = int(
            np.searchsorted(cumulative_variance, pca_explained_variance_threshold) + 1
        )
        n_components = max(pca_min_components, suggested_components)
        adaptive_component_cap = max(
            pca_min_components,
            int(math.floor(descriptor_count * pca_max_components_fraction)),
        )
        adaptive_component_cap = min(
            adaptive_component_cap,
            pca_max_components_absolute,
            scaled_data.shape[1],
            scaled_data.shape[0],
        )
        n_components = min(n_components, adaptive_component_cap)

        pca = PCA(n_components=n_components, random_state=self.random_state)
        model_input_data = pca.fit_transform(scaled_data)
        retained_variance = float(np.sum(pca.explained_variance_ratio_))

        if retained_variance < pca_min_acceptable_variance:
            self.log.write(
                f"x WARNING. PCA fallback retained only {round(retained_variance, 6)} explained variance, "
                f"below the minimum acceptable threshold of {pca_min_acceptable_variance}."
            )
            self.log.write(
                "o PCA will be discarded and clustering will continue in the scaled descriptor space"
            )
            return scaled_data, {
                "applied": False,
                "method": None,
                "input_descriptor_count": descriptor_count,
                "output_dimension": scaled_data.shape[1],
                "discarded_due_to_low_variance": True,
                "explained_variance_ratio": retained_variance,
            }

        reduction_ratio = 1.0 - (n_components / descriptor_count)

        self.log.write("   - PCA is used only as a high-dimensional fallback")
        self.log.write(f"   - Original descriptor count: {descriptor_count}")
        self.log.write(f"   - Adaptive PCA component cap: {adaptive_component_cap}")
        self.log.write(f"   - PCA components retained: {n_components}")
        self.log.write(
            f"   - Dimensionality reduction: {descriptor_count} -> {n_components} "
            f"({round(reduction_ratio * 100, 2)}% reduction)"
        )
        self.log.write(
            f"   - Cumulative explained variance retained: {round(retained_variance, 6)}"
        )
        if retained_variance < pca_explained_variance_threshold:
            self.log.write(
                f"x WARNING. PCA did not reach the target explained variance of "
                f"{pca_explained_variance_threshold}, but it is still above the minimum acceptable threshold."
            )
        if n_components > 80:
            self.log.write(
                "x WARNING. PCA was accepted, but the reduced space remains relatively high-dimensional for clustering."
            )

        return model_input_data, {
            "applied": True,
            "method": "PCA",
            "input_descriptor_count": descriptor_count,
            "output_dimension": n_components,
            "explained_variance_ratio": retained_variance,
        }

    def _configure_runtime_mode(self, n_samples: int) -> None:
        """
        Configure adaptive runtime safeguards for large datasets.
        """

        self._dataset_mode = self._determine_dataset_mode(n_samples)
        self._is_large_dataset = (
            self._config_value("enable_large_dataset_mode", ENABLE_LARGE_DATASET_MODE)
            and self._dataset_mode != "standard"
        )
        if self._is_large_dataset:
            self._effective_stability_repeats = min(
                self.stability_repeats,
                self._config_value(
                    "large_dataset_stability_repeats",
                    LARGE_DATASET_STABILITY_REPEATS,
                ),
            )
            self.log.write(
                f"\no {self._format_dataset_mode_name(self._dataset_mode).capitalize()} dataset mode activated "
                f"({n_samples} samples -> mode '{self._format_dataset_mode_name(self._dataset_mode)}', "
                f"range {self._get_dataset_mode_range_text()})"
            )
            self.log.write(
                f"   - Silhouette will be estimated on at most "
                f"{self._get_silhouette_sample_size()} samples"
            )
            self.log.write(
                f"   - Stability repetitions reduced from {self.stability_repeats} "
                f"to {self._effective_stability_repeats}"
            )
            if self._dataset_mode == "ultra_large":
                self.log.write("   - GMM will be skipped to keep model selection tractable")
                self.log.write("   - HDBSCAN will be skipped due to density-based runtime cost")
            else:
                self.log.write("   - HDBSCAN search space will be reduced for efficiency")
        else:
            self._effective_stability_repeats = self.stability_repeats
            if (
                n_samples > self._config_value("standard_dataset_threshold", STANDARD_DATASET_THRESHOLD)
                and not self._config_value("enable_large_dataset_mode", ENABLE_LARGE_DATASET_MODE)
            ):
                self.log.write(
                    f"\no Large dataset mode disabled by user "
                    f"({n_samples} samples would trigger '{self._format_dataset_mode_name(self._dataset_mode)}' mode, "
                    f"range {self._get_dataset_mode_range_text()})"
                )

    def _evaluate_kmeans_candidates(self, scaled_data: np.ndarray) -> list[ClusteringCandidate]:
        self.log.write("\no Evaluating KMeans candidates")
        n_samples = len(scaled_data)
        k_max = self._compute_k_max(n_samples, "KMeans")
        candidates: list[ClusteringCandidate] = []

        candidate_ks = list(range(2, k_max + 1))
        kmeans_coarse_grid_size = self._config_value(
            "kmeans_coarse_grid_size",
            KMEANS_COARSE_GRID_SIZE,
        )
        kmeans_top_refinement_candidates = self._config_value(
            "kmeans_top_refinement_candidates",
            KMEANS_TOP_REFINEMENT_CANDIDATES,
        )
        kmeans_refine_radius = self._config_value(
            "kmeans_refine_radius",
            KMEANS_REFINE_RADIUS,
        )

        if self._dataset_mode in {"large", "very_large", "ultra_large"} and len(candidate_ks) > kmeans_coarse_grid_size:
            self.log.write(
                f"   - {self._dataset_mode.replace('_', '-').capitalize()} KMeans Bayesian search activated"
            )
            self.log.write("   - Full KMeans grid search disabled for efficiency")
            total_budget = self._compute_bayesian_search_budget(
                candidate_space=candidate_ks,
                exploration_grid_size=kmeans_coarse_grid_size,
                refinement_radius=kmeans_refine_radius,
                refinement_centers=kmeans_top_refinement_candidates,
                search_fraction=self._config_value("kmeans_bo_fraction", KMEANS_BO_FRACTION),
                max_evaluations=self._config_value("kmeans_bo_max_evaluations", KMEANS_BO_MAX_EVALUATIONS),
            )
            exploration_budget, exploitation_budget = self._split_bayesian_search_budget(total_budget)
            self.log.write(f"   - Candidate k range: 2-{k_max}")
            self.log.write(f"   - Bayesian optimization budget: {total_budget} KMeans candidates")
            self.log.write(
                f"   - Budget calculation: candidate_space={len(candidate_ks)}, "
                f"baseline={kmeans_coarse_grid_size} exploration-grid points + "
                f"{kmeans_top_refinement_candidates} refinement center(s) * "
                f"(2 * radius {kmeans_refine_radius} + 1), "
                f"fractional=ceil({self._config_value('kmeans_bo_fraction', KMEANS_BO_FRACTION):.0%} "
                f"* {len(candidate_ks)}), cap={self._config_value('kmeans_bo_max_evaluations', KMEANS_BO_MAX_EVALUATIONS)}"
            )
            self.log.write(f"   - Exploration evaluations: {exploration_budget}")
            self.log.write(f"   - Exploitation evaluations: {exploitation_budget}")
            candidates = self._bayesian_optimize_kmeans_candidates(
                scaled_data=scaled_data,
                candidate_space=candidate_ks,
                exploration_budget=exploration_budget,
                exploitation_budget=exploitation_budget,
            )
        else:
            for n_clusters in candidate_ks:
                params = {"n_clusters": n_clusters}
                candidate = self._evaluate_candidate(
                    algorithm="KMeans",
                    params=params,
                    estimator_builder=lambda p=params: KMeans(
                        n_clusters=p["n_clusters"],
                        random_state=self.random_state,
                        n_init=self._kmeans_n_init(),
                        init="k-means++",
                        max_iter=self._kmeans_max_iter(),
                        tol=1e-4,
                        algorithm="lloyd",
                    ),
                    fit_predict=lambda model, x: model.fit_predict(x),
                    scaled_data=scaled_data,
                    compute_stability=not self._is_large_dataset,
                )
                candidates.append(candidate)

            self._assign_internal_scores(candidates, algorithm="KMeans")

        self._refine_top_candidates(
            algorithm="KMeans",
            candidates=candidates,
            scaled_data=scaled_data,
            estimator_builder_factory=lambda params: KMeans(
                n_clusters=params["n_clusters"],
                random_state=self.random_state,
                n_init=self._kmeans_n_init(),
                init="k-means++",
                max_iter=self._kmeans_max_iter(),
                tol=1e-4,
                algorithm="lloyd",
            ),
            fit_predict=lambda model, x: model.fit_predict(x),
        )
        return candidates

    def _bayesian_optimize_kmeans_candidates(
        self,
        scaled_data: np.ndarray,
        candidate_space: list[int],
        exploration_budget: int,
        exploitation_budget: int,
    ) -> list[ClusteringCandidate]:
        """
        Evaluate KMeans k values with a discrete Bayesian optimization schedule.
        """

        candidates: list[ClusteringCandidate] = []
        evaluated_ks: set[int] = set()

        def objective(n_clusters: int) -> float:
            candidate = self._evaluate_single_kmeans_candidate(scaled_data, n_clusters)
            candidates.append(candidate)
            evaluated_ks.add(n_clusters)
            return self._candidate_bayesian_objective_score(candidate)

        self._run_integer_bayesian_search(
            candidate_space=candidate_space,
            parameter_name="n_clusters",
            exploration_budget=exploration_budget,
            exploitation_budget=exploitation_budget,
            objective=objective,
            log_label="KMeans",
        )

        self._assign_internal_scores(candidates, algorithm="KMeans")
        return candidates

    def _evaluate_single_kmeans_candidate(
        self,
        scaled_data: np.ndarray,
        n_clusters: int,
    ) -> ClusteringCandidate:
        params = {"n_clusters": n_clusters}
        return self._evaluate_candidate(
            algorithm="KMeans",
            params=params,
            estimator_builder=lambda p=params: KMeans(
                n_clusters=p["n_clusters"],
                random_state=self.random_state,
                n_init=self._kmeans_n_init(),
                init="k-means++",
                max_iter=self._kmeans_max_iter(),
                tol=1e-4,
                algorithm="lloyd",
            ),
            fit_predict=lambda model, x: model.fit_predict(x),
            scaled_data=scaled_data,
            compute_stability=not self._is_large_dataset,
        )

    def _compute_bayesian_search_budget(
        self,
        candidate_space: list[int],
        exploration_grid_size: int,
        refinement_radius: int,
        refinement_centers: int = 1,
        search_fraction: float | None = None,
        max_evaluations: int | None = None,
    ) -> int:
        """
        Scale the BO budget with the discrete search-space size.
        """

        minimum_budget = exploration_grid_size + refinement_centers * (2 * refinement_radius + 1)
        if search_fraction is None:
            proportional_budget = minimum_budget
        else:
            proportional_budget = int(math.ceil(len(candidate_space) * search_fraction))

        budget = max(minimum_budget, proportional_budget)
        if max_evaluations is not None:
            budget = min(budget, max_evaluations)

        return max(1, min(len(candidate_space), budget))

    @staticmethod
    def _split_bayesian_search_budget(total_budget: int) -> tuple[int, int]:
        """
        Split the search budget into explicit exploration and exploitation halves.
        """

        if total_budget <= 1:
            return total_budget, 0

        exploration_budget = max(1, total_budget // 2)
        exploitation_budget = total_budget - exploration_budget
        return exploration_budget, exploitation_budget

    def _run_integer_bayesian_search(
        self,
        candidate_space: list[int],
        parameter_name: str,
        exploration_budget: int,
        exploitation_budget: int,
        objective: Callable[[int], float],
        log_label: str,
    ) -> dict[int, float]:
        """
        Run BayesianOptimization over a bounded integer clustering parameter.

        Exploration is deterministic: an evenly spaced coarse grid is evaluated
        first and registered as the BO history. Exploitation then uses the
        acquisition function to suggest additional integer candidates.
        """

        evaluated_values: dict[int, float] = {}
        candidate_set = set(candidate_space)
        total_budget = exploration_budget + exploitation_budget

        if total_budget <= 0 or not candidate_space:
            return evaluated_values

        def evaluate_candidate(candidate: int) -> float:
            candidate = int(candidate)
            if candidate not in candidate_set:
                candidate = min(candidate_space, key=lambda value: abs(value - candidate))
            if candidate in evaluated_values:
                return evaluated_values[candidate]

            value = float(objective(candidate))
            evaluated_values[candidate] = value
            return value

        if BayesianOptimization is None or acquisition is None:
            self.log.write(
                "   - bayesian-optimization is not installed; falling back to the local "
                f"discrete Bayesian search for {log_label}"
            )
            return self._run_local_integer_bayesian_search(
                candidate_space=candidate_space,
                exploration_budget=exploration_budget,
                exploitation_budget=exploitation_budget,
                objective=evaluate_candidate,
                log_label=log_label,
                evaluated_values=evaluated_values,
            )

        exploration_values = self._build_evenly_spaced_grid(candidate_space, exploration_budget)
        self.log.write(f"   - Coarse exploration grid for {log_label}: {exploration_values}")
        self.log.write(
            f"   - Using bayesian-optimization with pre-registered coarse points="
            f"{len(exploration_values)} and n_iter={exploitation_budget}"
        )
        self.log.write(
            f"   - Target unique evaluations: {min(total_budget, len(candidate_space))}; "
            "duplicate integer suggestions are skipped and replaced"
        )

        def wrapped_objective(**params: float) -> float:
            return evaluate_candidate(int(params[parameter_name]))

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Non-float parameters are experimental.*",
                category=UserWarning,
            )
            optimizer = BayesianOptimization(
                f=wrapped_objective,
                pbounds={parameter_name: (min(candidate_space), max(candidate_space), int)},
                acquisition_function=acquisition.ExpectedImprovement(
                    xi=0.01,
                    random_state=self.random_state,
                ),
                random_state=self.random_state,
                verbose=0,
                allow_duplicate_points=False,
            )

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Non-float parameters are experimental.*",
                    category=UserWarning,
                )
                warnings.filterwarnings(
                    "ignore",
                    message="Data point .* is not unique.*",
                    category=UserWarning,
                )
                for candidate in exploration_values:
                    value = evaluate_candidate(candidate)
                    optimizer.register(
                        params={parameter_name: candidate},
                        target=value,
                    )
                optimizer.maximize(
                    init_points=0,
                    n_iter=exploitation_budget,
                )
        except Exception as exc:
            duplicate_suggestion = "not unique" in str(exc).lower()
            if duplicate_suggestion:
                self.log.write(
                    f"   - bayesian-optimization suggested a duplicate integer for {log_label}; "
                    "completing the remaining evaluations with the local EI fallback"
                )
            else:
                self.log.write(
                    f"   - bayesian-optimization failed for {log_label} ({exc}); "
                    "continuing with the local discrete fallback"
                )
            self._run_local_integer_bayesian_search(
                candidate_space=candidate_space,
                exploration_budget=0,
                exploitation_budget=max(0, total_budget - len(evaluated_values)),
                objective=evaluate_candidate,
                log_label=log_label,
                evaluated_values=evaluated_values,
            )

        target_unique_evaluations = min(total_budget, len(candidate_space))
        while len(evaluated_values) < target_unique_evaluations:
            next_candidate = self._suggest_bayesian_discrete_candidate(
                candidate_space=candidate_space,
                evaluated_values=evaluated_values,
            )
            if next_candidate is None:
                break

            self.log.write(
                f"   - Replacing duplicate/skipped BO suggestion for {log_label}: "
                f"{parameter_name}={next_candidate}"
            )
            evaluate_candidate(next_candidate)

        self.log.write(
            f"   - Unique BO evaluations completed: {len(evaluated_values)}/"
            f"{target_unique_evaluations}"
        )
        return evaluated_values

    def _run_local_integer_bayesian_search(
        self,
        candidate_space: list[int],
        exploration_budget: int,
        exploitation_budget: int,
        objective: Callable[[int], float],
        log_label: str,
        evaluated_values: dict[int, float] | None = None,
    ) -> dict[int, float]:
        """
        Local fallback for integer BO when bayesian-optimization is unavailable.
        """

        if evaluated_values is None:
            evaluated_values = {}

        exploration_values = [
            value
            for value in self._build_evenly_spaced_grid(candidate_space, exploration_budget)
            if value not in evaluated_values
        ]
        self.log.write(f"   - Local fallback exploration {log_label} grid: {exploration_values}")

        for candidate in exploration_values:
            evaluated_values[candidate] = objective(candidate)

        for step in range(exploitation_budget):
            next_candidate = self._suggest_bayesian_discrete_candidate(
                candidate_space=candidate_space,
                evaluated_values=evaluated_values,
            )
            if next_candidate is None or next_candidate in evaluated_values:
                break

            self.log.write(
                f"   - Local fallback BO exploitation {log_label} candidate "
                f"{step + 1}/{exploitation_budget}: {next_candidate}"
            )
            evaluated_values[next_candidate] = objective(next_candidate)

        return evaluated_values

    @staticmethod
    def _candidate_bayesian_objective_score(candidate: ClusteringCandidate) -> float:
        """
        Convert one clustering candidate into a stable higher-is-better BO target.
        """

        if not candidate.passed_filters:
            return -1.0

        silhouette = (float(candidate.raw_metrics.get("silhouette", -1.0)) + 1.0) / 2.0
        stability = float(candidate.raw_metrics.get("stability", 0.0))
        davies_bouldin = float(candidate.raw_metrics.get("davies_bouldin", np.inf))
        davies_score = 0.0 if not np.isfinite(davies_bouldin) else 1.0 / (1.0 + max(0.0, davies_bouldin))
        imbalance_penalty = float(candidate.raw_metrics.get("imbalance_penalty", 0.0))

        return (
            0.45 * silhouette
            + 0.25 * stability
            + 0.25 * davies_score
            - 0.05 * imbalance_penalty
        )

    @staticmethod
    def _build_evenly_spaced_grid(candidate_space: list[int], grid_size: int) -> list[int]:
        """
        Build a deterministic exploration grid over a discrete integer space.
        """

        if grid_size <= 0:
            return []
        if len(candidate_space) <= grid_size:
            return candidate_space

        raw_positions = np.linspace(0, len(candidate_space) - 1, num=grid_size)
        indices = sorted(set(int(round(position)) for position in raw_positions))
        return [candidate_space[index] for index in indices]

    def _suggest_bayesian_discrete_candidate(
        self,
        candidate_space: list[int],
        evaluated_values: dict[int, float],
    ) -> int | None:
        """
        Suggest the next unevaluated integer candidate with expected improvement.

        The objective is always treated as "higher is better"; minimization tasks
        should pass a negated objective, e.g. -BIC.
        """

        remaining_candidates = [
            candidate for candidate in candidate_space if candidate not in evaluated_values
        ]
        if not remaining_candidates:
            return None

        valid_observations = {
            candidate: value
            for candidate, value in evaluated_values.items()
            if np.isfinite(value)
        }
        if len(valid_observations) < 2:
            middle_index = len(remaining_candidates) // 2
            return remaining_candidates[middle_index]

        x_min = min(candidate_space)
        x_range = max(candidate_space) - x_min
        if x_range == 0:
            return remaining_candidates[0]

        x_observed = np.array(
            [[(candidate - x_min) / x_range] for candidate in valid_observations],
            dtype=float,
        )
        y_observed = np.array(list(valid_observations.values()), dtype=float)
        x_remaining = np.array(
            [[(candidate - x_min) / x_range] for candidate in remaining_candidates],
            dtype=float,
        )

        kernel = (
            ConstantKernel(1.0, constant_value_bounds="fixed")
            * Matern(length_scale=0.35, length_scale_bounds=(0.05, 2.0), nu=2.5)
            + WhiteKernel(noise_level=1e-6, noise_level_bounds=(1e-9, 1e-3))
        )
        model = GaussianProcessRegressor(
            kernel=kernel,
            alpha=1e-8,
            normalize_y=True,
            random_state=self.random_state,
            n_restarts_optimizer=0,
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ConvergenceWarning)
                model.fit(x_observed, y_observed)
            means, stds = model.predict(x_remaining, return_std=True)
        except Exception:
            best_candidate = max(valid_observations, key=valid_observations.get)
            return min(remaining_candidates, key=lambda candidate: abs(candidate - best_candidate))

        best_observed = float(np.max(y_observed))
        improvement_margin = 0.01
        expected_improvement = []
        for mean, std in zip(means, stds):
            std = max(float(std), 1e-12)
            improvement = float(mean) - best_observed - improvement_margin
            z_score = improvement / std
            normal_cdf = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
            normal_pdf = math.exp(-0.5 * z_score ** 2) / math.sqrt(2.0 * math.pi)
            expected_improvement.append(improvement * normal_cdf + std * normal_pdf)

        best_index = int(np.argmax(expected_improvement))
        return remaining_candidates[best_index]

    def _evaluate_gmm_candidates(self, scaled_data: np.ndarray) -> list[ClusteringCandidate]:
        self.log.write("\no Evaluating Gaussian Mixture Model candidates")
        self.log.write("   - Optimization strategy: Bayesian search over n_components using BIC")
        k_max = self._compute_k_max(len(scaled_data), "GMM")
        gmm_search_config = self._build_gmm_search_config(
            n_samples=len(scaled_data),
            n_features_used=scaled_data.shape[1],
        )
        covariance_types = gmm_search_config["covariance_types"]
        self.log.write(f"   - Adaptive GMM search regime: {gmm_search_config['regime']}")
        self.log.write(f"   - Effective clustering dimensions: {scaled_data.shape[1]}")
        self.log.write(f"   - Covariance types: {covariance_types}")
        self.log.write(f"   - Initial exploration grid size: {gmm_search_config['coarse_grid_size']}")
        self.log.write(
            f"   - BO exploitation budget radius setting: {gmm_search_config['refine_radius']}"
        )
        if gmm_search_config.get("dimensionally_capped"):
            self.log.write(
                f"   - GMM covariance types reduced due to high dimensionality "
                f"({scaled_data.shape[1]} > {gmm_search_config['dimensionality_threshold']})"
            )
        elif gmm_search_config.get("regime_capped"):
            self.log.write(
                "   - GMM covariance types restricted to ['diag'] in large-dataset modes "
                "to avoid expensive full-covariance fits"
            )
        candidates: list[ClusteringCandidate] = []

        shortlisted_params = self._bayesian_optimize_gmm_params(
            scaled_data,
            k_max,
            covariance_types,
            gmm_search_config,
        )
        for params in shortlisted_params:
            candidate = self._evaluate_candidate(
                algorithm="GMM",
                params=params,
                estimator_builder=lambda p=params: GaussianMixture(
                    n_components=p["n_components"],
                    covariance_type=p["covariance_type"],
                    random_state=self.random_state,
                    reg_covar=1e-6,
                    n_init=self._gmm_n_init(),
                    max_iter=self._gmm_max_iter(),
                    tol=1e-3,
                    init_params="kmeans",
                ),
                fit_predict=lambda model, x: model.fit_predict(x),
                scaled_data=scaled_data,
                extra_metrics_builder=lambda model, x: {"bic": float(model.bic(x))},
                compute_stability=not self._is_large_dataset,
            )
            candidates.append(candidate)

        self._assign_internal_scores(candidates, algorithm="GMM")
        self._refine_top_candidates(
            algorithm="GMM",
            candidates=candidates,
            scaled_data=scaled_data,
            estimator_builder_factory=lambda params: GaussianMixture(
                n_components=params["n_components"],
                covariance_type=params["covariance_type"],
                random_state=self.random_state,
                reg_covar=1e-6,
                n_init=self._gmm_n_init(),
                max_iter=self._gmm_max_iter(),
                tol=1e-3,
                init_params="kmeans",
            ),
            fit_predict=lambda model, x: model.fit_predict(x),
            extra_metrics_builder=lambda model, x: {"bic": float(model.bic(x))},
        )
        return candidates

    def _bayesian_optimize_gmm_params(
        self,
        scaled_data: np.ndarray,
        k_max: int,
        covariance_types: list[str],
        gmm_search_config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Optimize GMM n_components separately for each covariance type using a
        discrete Bayesian search on BIC.
        """

        all_shortlisted_params: list[dict[str, Any]] = []
        candidate_space = list(range(2, k_max + 1))

        if len(candidate_space) == 0:
            return all_shortlisted_params

        for covariance_type in covariance_types:
            self.log.write(f"\no Bayesian optimization for GMM covariance_type='{covariance_type}'")
            evaluated_bics: dict[int, float] = {}
            total_budget = self._compute_bayesian_search_budget(
                candidate_space=candidate_space,
                exploration_grid_size=gmm_search_config["coarse_grid_size"],
                refinement_radius=gmm_search_config["refine_radius"],
                search_fraction=self._config_value("gmm_bo_fraction", GMM_BO_FRACTION),
                max_evaluations=self._config_value("gmm_bo_max_evaluations", GMM_BO_MAX_EVALUATIONS),
            )
            exploration_budget, exploitation_budget = self._split_bayesian_search_budget(total_budget)
            self.log.write(f"   - Candidate n_components range: 2-{k_max}")
            self.log.write(f"   - Bayesian optimization budget: {total_budget} BIC evaluations")
            self.log.write(
                f"   - Budget calculation: candidate_space={len(candidate_space)}, "
                f"baseline={gmm_search_config['coarse_grid_size']} exploration-grid points + "
                f"1 refinement center * (2 * radius {gmm_search_config['refine_radius']} + 1), "
                f"fractional=ceil({self._config_value('gmm_bo_fraction', GMM_BO_FRACTION):.0%} "
                f"* {len(candidate_space)}), cap={self._config_value('gmm_bo_max_evaluations', GMM_BO_MAX_EVALUATIONS)}"
            )
            self.log.write("   - BO objective: minimize BIC by maximizing -BIC")
            self.log.write(
                "   - BIC is only used for GMM screening; shortlisted candidates still "
                "must pass clustering-quality filters"
            )
            self.log.write(f"   - Exploration evaluations: {exploration_budget}")
            self.log.write(f"   - Exploitation evaluations: {exploitation_budget}")

            def objective(n_components: int) -> float:
                bic = self._evaluate_gmm_bic(
                    scaled_data=scaled_data,
                    n_components=n_components,
                    covariance_type=covariance_type,
                )
                evaluated_bics[n_components] = bic
                return -bic

            self._run_integer_bayesian_search(
                candidate_space=candidate_space,
                parameter_name="n_components",
                exploration_budget=exploration_budget,
                exploitation_budget=exploitation_budget,
                objective=objective,
                log_label=f"GMM covariance_type='{covariance_type}'",
            )

            ranked_bics = sorted(evaluated_bics.items(), key=lambda item: item[1])
            best_n_components, best_bic = ranked_bics[0]
            self.log.write(
                f"   - Best BIC for covariance_type='{covariance_type}': "
                f"n_components={best_n_components}, bic={round(best_bic, 6)}"
            )
            shortlist_size = min(
                self._config_value("gmm_bic_shortlist_size", GMM_BIC_SHORTLIST_SIZE),
                len(ranked_bics),
            )
            self.log.write(
                f"   - Shortlisting top {shortlist_size} BIC candidate(s) "
                "for clustering-quality evaluation"
            )
            for n_components, bic_value in ranked_bics[:shortlist_size]:
                self.log.write(
                    f"     - n_components={n_components}, bic={round(bic_value, 6)}"
                )
                all_shortlisted_params.append(
                    {
                        "n_components": n_components,
                        "covariance_type": covariance_type,
                    }
                )

        return all_shortlisted_params

    def _evaluate_gmm_bic(
        self,
        scaled_data: np.ndarray,
        n_components: int,
        covariance_type: str,
    ) -> float:
        """
        Fit one GMM configuration and return its BIC.
        """

        model = GaussianMixture(
            n_components=n_components,
            covariance_type=covariance_type,
            random_state=self.random_state,
            reg_covar=1e-6,
            n_init=self._gmm_n_init(),
            max_iter=self._gmm_max_iter(),
            tol=1e-3,
            init_params="kmeans",
        )
        model.fit(scaled_data)
        bic_value = float(model.bic(scaled_data))
        self.log.write(
            f"   - Evaluated BIC: covariance_type='{covariance_type}', "
            f"n_components={n_components}, bic={round(bic_value, 6)}"
        )
        return bic_value

    def _build_gmm_search_config(self, n_samples: int, n_features_used: int) -> dict[str, Any]:
        """
        Define an adaptive GMM search budget based on the shared dataset mode.

        GMM is kept in the model comparison because it can be useful on some datasets,
        but its search space is tightened as sample count grows so it does not dominate
        runtime disproportionately.
        """

        if self._dataset_mode == "standard":
            config = {
                "regime": "standard",
                "covariance_types": ["full", "diag", "tied"],
                "coarse_grid_size": self._config_value(
                    "gmm_standard_coarse_grid_size",
                    9,
                ),
                "refine_radius": self._config_value(
                    "gmm_standard_refine_radius",
                    3,
                ),
            }
        elif self._dataset_mode == "large":
            config = {
                "regime": "large",
                "covariance_types": ["diag", "full"],
                "coarse_grid_size": self._config_value(
                    "gmm_large_coarse_grid_size",
                    5,
                ),
                "refine_radius": self._config_value(
                    "gmm_large_refine_radius",
                    2,
                ),
            }
        else:
            config = {
                "regime": "very_large",
                "covariance_types": ["diag"],
                "coarse_grid_size": self._config_value(
                    "gmm_very_large_coarse_grid_size",
                    5,
                ),
                "refine_radius": self._config_value(
                    "gmm_very_large_refine_radius",
                    1,
                ),
            }

        config["dimensionally_capped"] = False
        config["regime_capped"] = self._dataset_mode in {"large", "very_large", "ultra_large"}
        config["dimensionality_threshold"] = self._config_value(
            "gmm_dimensionality_threshold",
            50,
        )
        if self._dataset_mode == "very_large" and n_features_used <= 25:
            config["covariance_types"] = ["diag", "full"]
            config["regime_capped"] = False
        if n_features_used > config["dimensionality_threshold"]:
            config["covariance_types"] = ["diag"]
            config["dimensionally_capped"] = True

        return config

    def _evaluate_hdbscan_candidates(self, scaled_data: np.ndarray) -> list[ClusteringCandidate]:
        self.log.write("\no Evaluating HDBSCAN candidates")
        search_space = self._build_hdbscan_search_space(len(scaled_data))
        candidates: list[ClusteringCandidate] = []

        for min_cluster_size in search_space["min_cluster_size"]:
            for min_samples in search_space["min_samples"]:
                if min_samples is not None and min_samples >= min_cluster_size:
                    continue

                params = {
                    "min_cluster_size": min_cluster_size,
                    "min_samples": min_samples,
                }
                candidate = self._evaluate_candidate(
                    algorithm="HDBSCAN",
                    params=params,
                    estimator_builder=lambda p=params: hdbscan.HDBSCAN(
                        min_cluster_size=p["min_cluster_size"],
                        min_samples=p["min_samples"],
                        metric="euclidean",
                        alpha=1.0,
                        cluster_selection_method="eom",
                        allow_single_cluster=False,
                        prediction_data=False,
                    ),
                    fit_predict=lambda model, x: model.fit_predict(x),
                    scaled_data=scaled_data,
                    extra_metrics_builder=self._build_hdbscan_extra_metrics,
                    compute_stability=not self._is_large_dataset,
                )
                candidates.append(candidate)

        self._assign_internal_scores(candidates, algorithm="HDBSCAN")
        self._refine_top_candidates(
            algorithm="HDBSCAN",
            candidates=candidates,
            scaled_data=scaled_data,
            estimator_builder_factory=lambda params: hdbscan.HDBSCAN(
                min_cluster_size=params["min_cluster_size"],
                min_samples=params["min_samples"],
                metric="euclidean",
                alpha=1.0,
                cluster_selection_method="eom",
                allow_single_cluster=False,
                prediction_data=False,
            ),
            fit_predict=lambda model, x: model.fit_predict(x),
            extra_metrics_builder=self._build_hdbscan_extra_metrics,
        )
        return candidates

    def _evaluate_candidate(
        self,
        algorithm: str,
        params: dict[str, Any],
        estimator_builder: Callable[[], Any],
        fit_predict: Callable[[Any, np.ndarray], np.ndarray],
        scaled_data: np.ndarray,
        extra_metrics_builder: Callable[[Any, np.ndarray], dict[str, Any]] | None = None,
        compute_stability: bool = True,
    ) -> ClusteringCandidate:
        self.log.write(f"\no Evaluating {algorithm} candidate: {params}")

        try:
            estimator = estimator_builder()
            labels = np.asarray(fit_predict(estimator, scaled_data), dtype=int)
            raw_metrics = self._compute_common_metrics(scaled_data, labels)

            if extra_metrics_builder is not None:
                raw_metrics.update(extra_metrics_builder(estimator, scaled_data))

            raw_metrics["stability"] = 0.0
            raw_metrics["stability_mode"] = "skipped"
            if compute_stability:
                raw_metrics["stability"] = self._estimate_stability(
                    scaled_data=scaled_data,
                    reference_labels=labels,
                    estimator_builder=estimator_builder,
                    fit_predict=fit_predict,
                )
                raw_metrics["stability_mode"] = "full"
        except Exception as exc:  # pragma: no cover
            self.log.write(f"x Candidate failed during evaluation: {exc}")
            return ClusteringCandidate(
                algorithm=algorithm,
                params=params,
                labels=np.full(len(scaled_data), -1, dtype=int),
                raw_metrics={"error": str(exc)},
                filter_reasons=[f"evaluation_error: {exc}"],
                passed_filters=False,
            )

        passed_filters, filter_reasons = self._apply_filters(raw_metrics)
        self._log_candidate_metrics(raw_metrics, passed_filters, filter_reasons)

        return ClusteringCandidate(
            algorithm=algorithm,
            params=params,
            labels=labels,
            raw_metrics=raw_metrics,
            filter_reasons=filter_reasons,
            passed_filters=passed_filters,
        )

    def _refine_top_candidates(
        self,
        algorithm: str,
        candidates: list[ClusteringCandidate],
        scaled_data: np.ndarray,
        estimator_builder_factory: Callable[[dict[str, Any]], Any],
        fit_predict: Callable[[Any, np.ndarray], np.ndarray],
        extra_metrics_builder: Callable[[Any, np.ndarray], dict[str, Any]] | None = None,
    ) -> None:
        """
        Run the expensive stability pass only for the top screened candidates.
        """

        if not self._is_large_dataset:
            return

        if algorithm == "GMM":
            self.log.write(
                "\no Skipping full stability refinement for GMM in large-dataset mode"
            )
            self.log.write(
                "   - GMM candidates are kept with screening metrics and BIC because repeated "
                "GMM refits are too expensive at this scale"
            )
            return

        valid_candidates = [candidate for candidate in candidates if candidate.passed_filters]
        if not valid_candidates:
            return

        ranked_candidates = sorted(
            valid_candidates,
            key=lambda candidate: candidate.internal_score if candidate.internal_score is not None else -np.inf,
            reverse=True,
        )
        top_candidate_count = self._config_value(
            "fast_screening_top_candidates",
            FAST_SCREENING_TOP_CANDIDATES,
        )
        if self._dataset_mode == "very_large":
            top_candidate_count = min(top_candidate_count, 2)
        elif self._dataset_mode == "ultra_large":
            top_candidate_count = min(top_candidate_count, 1)
        top_candidates = ranked_candidates[:top_candidate_count]

        self.log.write(
            f"\no Refining the top {len(top_candidates)} {algorithm} candidate(s) with full stability evaluation"
        )

        for candidate in top_candidates:
            estimator_builder = lambda params=candidate.params: estimator_builder_factory(params)
            estimator = estimator_builder()
            labels = np.asarray(fit_predict(estimator, scaled_data), dtype=int)
            raw_metrics = self._compute_common_metrics(scaled_data, labels)

            if extra_metrics_builder is not None:
                raw_metrics.update(extra_metrics_builder(estimator, scaled_data))

            raw_metrics["stability"] = self._estimate_stability(
                scaled_data=scaled_data,
                reference_labels=labels,
                estimator_builder=estimator_builder,
                fit_predict=fit_predict,
            )
            raw_metrics["stability_mode"] = "full"

            passed_filters, filter_reasons = self._apply_filters(raw_metrics)
            candidate.labels = labels
            candidate.raw_metrics = raw_metrics
            candidate.passed_filters = passed_filters
            candidate.filter_reasons = filter_reasons
            self._log_candidate_metrics(raw_metrics, passed_filters, filter_reasons)

        self._assign_internal_scores(candidates, algorithm=algorithm)

    def _compute_common_metrics(self, scaled_data: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
        """
        Compute the common metrics used to compare clustering models across algorithms.

        Metric rationale:
        - silhouette:
            Measures how well separated and compact the clusters are overall.
            Higher is better. It is a strong general-purpose metric, but it can penalize
            elongated or non-convex structures.
        - calinski_harabasz:
            Ratio of between-cluster dispersion to within-cluster dispersion.
            Higher is better. It rewards compact and separated clusters, but can dominate
            numerically if not normalized before combination.
        - davies_bouldin:
            Measures relative overlap between clusters.
            Lower is better. We later invert/normalize it before ranking.
        - noise_fraction:
            Relevant mainly for HDBSCAN. A high value means too many points were left
            unclustered, which usually indicates an impractical solution.
        - imbalance_penalty:
            Penalizes highly uneven cluster size distributions. This prevents degenerate
            solutions with one dominant cluster and several tiny residual ones.
        """

        metrics: dict[str, Any] = {}
        non_noise_mask = labels != -1
        clustered_labels = labels[non_noise_mask]
        clustered_data = scaled_data[non_noise_mask]
        unique_clusters = np.unique(clustered_labels)
        cluster_sizes = [int(np.sum(clustered_labels == label)) for label in unique_clusters]

        metrics["n_clusters"] = int(len(unique_clusters))
        metrics["cluster_sizes"] = cluster_sizes
        metrics["noise_fraction"] = float(1.0 - np.mean(non_noise_mask))
        metrics["max_cluster_fraction"] = (
            float(max(cluster_sizes) / len(clustered_labels)) if len(clustered_labels) > 0 else 1.0
        )
        metrics["imbalance_penalty"] = self._compute_imbalance_penalty(cluster_sizes)

        if len(unique_clusters) < 2 or len(clustered_data) <= len(unique_clusters):
            metrics["silhouette"] = -1.0
            metrics["calinski_harabasz"] = 0.0
            metrics["davies_bouldin"] = math.inf
            return metrics

        if min(cluster_sizes) < 2:
            metrics["silhouette"] = -1.0
            metrics["calinski_harabasz"] = 0.0
            metrics["davies_bouldin"] = math.inf
            return metrics

        metrics["silhouette"] = float(self._compute_silhouette(clustered_data, clustered_labels))
        metrics["calinski_harabasz"] = float(calinski_harabasz_score(clustered_data, clustered_labels))
        metrics["davies_bouldin"] = float(davies_bouldin_score(clustered_data, clustered_labels))
        return metrics

    def _compute_silhouette(self, clustered_data: np.ndarray, clustered_labels: np.ndarray) -> float:
        """
        Compute silhouette exactly for small datasets and approximately for large ones.
        """

        sample_cap = self._get_silhouette_sample_size()

        if len(clustered_data) <= sample_cap or not self._is_large_dataset:
            return silhouette_score(clustered_data, clustered_labels)

        sample_size = min(sample_cap, len(clustered_data))
        sample_idx = np.sort(self._rng.choice(len(clustered_data), size=sample_size, replace=False))
        return silhouette_score(clustered_data[sample_idx], clustered_labels[sample_idx])

    def _build_hdbscan_extra_metrics(self, model, scaled_data: np.ndarray) -> dict[str, Any]:
        metrics: dict[str, Any] = {"density_score": None}
        if hdbscan_validity_index is None:
            return metrics

        labels = np.asarray(model.labels_, dtype=int)
        non_noise_mask = labels != -1
        clustered_labels = labels[non_noise_mask]
        clustered_data = scaled_data[non_noise_mask]

        if len(np.unique(clustered_labels)) < 2:
            return metrics

        try:
            metrics["density_score"] = float(hdbscan_validity_index(clustered_data, clustered_labels))
        except Exception:
            metrics["density_score"] = None

        return metrics

    def _apply_filters(self, metrics: dict[str, Any]) -> FilterResult:
        reasons: list[str] = []
        max_noise_fraction = self._config_value("filter_max_noise_fraction", 0.2)
        max_cluster_fraction = self._config_value("filter_max_cluster_fraction", 0.85)
        max_imbalance_penalty = self._config_value("filter_max_imbalance_penalty", 0.90)

        if metrics.get("n_clusters", 0) < 2:
            reasons.append("fewer than two clusters")
        if metrics.get("silhouette", -1.0) < 0:
            reasons.append("negative silhouette score")
        if metrics.get("noise_fraction", 0.0) > max_noise_fraction:
            reasons.append(f"noise fraction above {max_noise_fraction:.2f}")
        if metrics.get("max_cluster_fraction", 1.0) > max_cluster_fraction:
            reasons.append(f"maximum cluster fraction above {max_cluster_fraction:.2f}")
        if metrics.get("imbalance_penalty", 1.0) > max_imbalance_penalty:
            reasons.append("extreme cluster imbalance")

        return len(reasons) == 0, reasons

    def _estimate_stability(
        self,
        scaled_data: np.ndarray,
        reference_labels: np.ndarray,
        estimator_builder: Callable[[], Any],
        fit_predict: Callable[[Any, np.ndarray], np.ndarray],
    ) -> float:
        """
        Estimate clustering stability with repeated subsampling and ARI.

        Rationale:
        - A clustering solution can look strong on one fit and still be unstable under
          small perturbations of the data.
        - We repeatedly subsample the dataset, refit the same configuration, and compare
          the new partition against the reference labels on the overlapping samples.
        - The Adjusted Rand Index (ARI) is used because it compares partitions without
          assuming label identities are aligned across runs.
        """

        n_samples = len(scaled_data)
        subsample_size = max(4, int(math.ceil(n_samples * self.subsample_fraction)))
        ari_scores: list[float] = []

        for _ in range(self._effective_stability_repeats):
            sample_idx = np.sort(self._rng.choice(n_samples, size=subsample_size, replace=False))

            try:
                estimator = estimator_builder()
                subsample_labels = np.asarray(fit_predict(estimator, scaled_data[sample_idx]), dtype=int)
                reference_subset = reference_labels[sample_idx]
                if len(np.unique(subsample_labels[subsample_labels != -1])) < 2:
                    ari_scores.append(0.0)
                else:
                    ari_scores.append(float(adjusted_rand_score(reference_subset, subsample_labels)))
            except Exception:
                ari_scores.append(0.0)

        return float(np.mean(ari_scores)) if ari_scores else 0.0

    def _assign_internal_scores(self, candidates: list[ClusteringCandidate], algorithm: str) -> None:
        """
        Rank candidates within the same algorithm family.

        Notes:
        - Scores are normalized only against candidates from the same algorithm family.
        - This score is used to keep the best candidate inside each family.
        - Final cross-algorithm comparison is handled later with the shared global score.
        """

        valid_candidates = [candidate for candidate in candidates if candidate.passed_filters]

        if not valid_candidates:
            if algorithm == "HDBSCAN":
                self.log.write(
                    "x HDBSCAN did not yield a valid density-based partition under the current settings"
                )
                self.log.write(
                    "   - all evaluated HDBSCAN candidates were discarded by the clustering quality filters"
                )
            else:
                self.log.write(f"x No valid {algorithm} candidates survived filtering")
            return

        silhouettes = self._normalize_metric([c.raw_metrics["silhouette"] for c in valid_candidates])
        calinski = self._normalize_metric([c.raw_metrics["calinski_harabasz"] for c in valid_candidates])
        davies = self._normalize_metric(
            [c.raw_metrics["davies_bouldin"] for c in valid_candidates],
            lower_is_better=True,
        )
        stability = self._normalize_metric([c.raw_metrics["stability"] for c in valid_candidates])

        if algorithm == "HDBSCAN":
            density_values = []
            for candidate in valid_candidates:
                density_value = candidate.raw_metrics.get("density_score")
                density_values.append(-1.0 if density_value is None else density_value)
            density = self._normalize_metric(density_values)
        else:
            density = [0.0] * len(valid_candidates)

        for idx, candidate in enumerate(valid_candidates):
            noise_penalty = candidate.raw_metrics.get("noise_fraction", 0.0)
            imbalance_penalty = candidate.raw_metrics.get("imbalance_penalty", 0.0)
            if algorithm == "HDBSCAN":
                candidate.internal_score = (
                    0.35 * silhouettes[idx]
                    + 0.20 * density[idx]
                    + 0.25 * stability[idx]
                    + 0.10 * davies[idx]
                    + 0.10 * calinski[idx]
                    - 0.10 * noise_penalty
                    - 0.05 * imbalance_penalty
                )
            else:
                candidate.internal_score = (
                    0.35 * silhouettes[idx]
                    + 0.25 * calinski[idx]
                    + 0.20 * davies[idx]
                    + 0.20 * stability[idx]
                    - 0.05 * imbalance_penalty
                )

    def _pick_best_candidate(
        self,
        algorithm: str,
        candidates: list[ClusteringCandidate],
    ) -> ClusteringCandidate | None:
        valid_candidates = [candidate for candidate in candidates if candidate.passed_filters]
        if not valid_candidates:
            self.log.write(f"x {algorithm} produced no valid model")
            return None

        best_candidate = self._pick_best_with_simplicity_tie_break(valid_candidates)
        self.log.write(
            f"\no Best {algorithm} candidate selected within the {algorithm} family "
            f"with internal_score "
            f"{round(best_candidate.internal_score, 4)}"
        )
        return best_candidate

    def _pick_best_gmm_candidate(
        self,
        candidates: list[ClusteringCandidate],
    ) -> ClusteringCandidate | None:
        valid_candidates = [candidate for candidate in candidates if candidate.passed_filters]
        if not valid_candidates:
            self.log.write("x GMM produced no valid model")
            return None

        # GMM candidates have already been screened internally with BIC during the
        # Bayesian search. At this stage, the family representative should be the
        # valid GMM candidate with the strongest shared clustering metrics, not
        # necessarily the one with the absolute minimum BIC.
        best_candidate = self._pick_best_with_simplicity_tie_break(valid_candidates)
        self.log.write(
            f"\no Best GMM candidate selected within the GMM family after BIC screening "
            f"with internal_score "
            f"{round(best_candidate.internal_score, 4) if best_candidate.internal_score is not None else 'NA'}"
        )
        return best_candidate

    def _pick_best_with_simplicity_tie_break(
        self,
        candidates: list[ClusteringCandidate],
    ) -> ClusteringCandidate:
        """
        Prefer fewer clusters when scores are within a practical noise tolerance.
        """

        best_score = max(
            candidate.internal_score if candidate.internal_score is not None else -np.inf
            for candidate in candidates
        )
        near_best_candidates = [
            candidate
            for candidate in candidates
            if candidate.internal_score is not None
            and best_score - candidate.internal_score <= SCORE_PRACTICAL_TIE_TOLERANCE
        ]
        selected_candidate = min(
            near_best_candidates,
            key=lambda candidate: (
                candidate.raw_metrics.get("n_clusters", np.inf),
                -candidate.internal_score,
            ),
        )
        if len(near_best_candidates) > 1:
            self.log.write(
                f"   - Practical score tie detected within {SCORE_PRACTICAL_TIE_TOLERANCE}; "
                "preferring the candidate with fewer clusters"
            )
        return selected_candidate

    def _assign_final_scores(self, best_by_algorithm: dict[str, ClusteringCandidate]) -> None:
        """
        Compute the final shared score used to compare the best model from each algorithm.

        The ranking intentionally focuses on the metrics that are easiest to defend
        conceptually for this workflow:
        - stability: robustness under subsampling
        - silhouette: global separation/compactness signal
        - davies_bouldin: overlap penalty transformed into a "higher is better" score

        Practical penalties are still applied for:
        - noise_fraction: too many unclustered points
        - imbalance_penalty: highly uneven cluster sizes

        Calinski-Harabasz is still computed and reported, but it is not used in the final
        score because it is less intuitive and can distort the ranking despite normalization.
        """

        if not best_by_algorithm:
            return

        candidates = list(best_by_algorithm.values())
        silhouettes = self._normalize_metric([c.raw_metrics["silhouette"] for c in candidates])
        davies = self._normalize_metric(
            [c.raw_metrics["davies_bouldin"] for c in candidates],
            lower_is_better=True,
        )
        stability = self._normalize_metric([c.raw_metrics["stability"] for c in candidates])

        for idx, candidate in enumerate(candidates):
            noise_penalty = candidate.raw_metrics.get("noise_fraction", 0.0)
            imbalance_penalty = candidate.raw_metrics.get("imbalance_penalty", 0.0)
            candidate.rank_metrics = {
                "silhouette_norm": silhouettes[idx],
                "davies_norm": davies[idx],
                "stability_norm": stability[idx],
            }
            candidate.final_score = (
                0.30 * stability[idx]
                + 0.32 * silhouettes[idx]
                + 0.22 * davies[idx]
                - 0.12 * noise_penalty
                - 0.04 * imbalance_penalty
            )

    def _build_summary_dataframe(self, candidates: list[ClusteringCandidate]) -> pd.DataFrame:
        rows = []
        for candidate in candidates:
            metrics = candidate.raw_metrics
            rows.append(
                {
                    "algorithm": candidate.algorithm,
                    "params": str(candidate.params),
                    "passed_filters": candidate.passed_filters,
                    "filter_reasons": "; ".join(candidate.filter_reasons),
                    "n_clusters": metrics.get("n_clusters"),
                    "cluster_sizes": str(metrics.get("cluster_sizes")),
                    "silhouette": metrics.get("silhouette"),
                    "calinski_harabasz": metrics.get("calinski_harabasz"),
                    "davies_bouldin": metrics.get("davies_bouldin"),
                    "stability": metrics.get("stability"),
                    "noise_fraction": metrics.get("noise_fraction", 0.0),
                    "imbalance_penalty": metrics.get("imbalance_penalty"),
                    "density_score": metrics.get("density_score"),
                    "bic": metrics.get("bic"),
                    "internal_score": candidate.internal_score,
                    "final_score": candidate.final_score,
                }
            )
        return pd.DataFrame(rows)

    def _log_candidate_metrics(
        self,
        metrics: dict[str, Any],
        passed_filters: bool,
        filter_reasons: list[str],
    ) -> None:
        self.log.write(f"   - n_clusters: {metrics.get('n_clusters')}")
        self.log.write(f"   - cluster_sizes: {metrics.get('cluster_sizes')}")
        self.log.write(f"   - silhouette: {round(metrics.get('silhouette', -1.0), 6)}")
        self.log.write(
            f"   - calinski_harabasz: {round(metrics.get('calinski_harabasz', 0.0), 6)}"
        )
        self.log.write(f"   - davies_bouldin: {metrics.get('davies_bouldin')}")
        self.log.write(f"   - stability: {round(metrics.get('stability', 0.0), 6)}")
        self.log.write(f"   - imbalance_penalty: {round(metrics.get('imbalance_penalty', 0.0), 6)}")
        if "noise_fraction" in metrics:
            self.log.write(f"   - noise_fraction: {round(metrics.get('noise_fraction', 0.0), 6)}")
        if metrics.get("density_score") is not None:
            self.log.write(f"   - density_score: {round(metrics['density_score'], 6)}")
        if metrics.get("bic") is not None:
            self.log.write(f"   - bic: {round(metrics['bic'], 6)}")

        if passed_filters:
            self.log.write("   - status: accepted")
        else:
            self.log.write("   - status: discarded")
            self.log.write(f"   - discard_reasons: {filter_reasons}")

    def _log_algorithm_summary(
        self,
        best_by_algorithm: dict[str, ClusteringCandidate],
        best_candidate: ClusteringCandidate | None,
    ) -> None:
        self.log.write("\no Best candidate per algorithm before cross-algorithm ranking:")
        if not best_by_algorithm:
            self.log.write("   - No valid clustering model was found")
            return

        for algorithm, candidate in best_by_algorithm.items():
            self.log.write(
                f"   - {algorithm}: params={candidate.params}, "
                f"n_clusters={candidate.raw_metrics['n_clusters']}, "
                f"final_score={round(candidate.final_score, 6) if candidate.final_score is not None else 'NA'}"
            )

        if best_candidate is not None:
            self.log.write("\no Global best clustering model selected by cross-algorithm final_score:")
            self.log.write(f"   - algorithm: {best_candidate.algorithm}")
            self.log.write(f"   - parameters: {best_candidate.params}")
            self.log.write(f"   - n_clusters: {best_candidate.raw_metrics['n_clusters']}")
            self.log.write(f"   - cluster_sizes: {best_candidate.raw_metrics['cluster_sizes']}")
            self.log.write(f"   - silhouette: {round(best_candidate.raw_metrics['silhouette'], 6)}")
            self.log.write(
                f"   - calinski_harabasz: {round(best_candidate.raw_metrics['calinski_harabasz'], 6)}"
            )
            self.log.write(
                f"   - davies_bouldin: {round(best_candidate.raw_metrics['davies_bouldin'], 6)}"
            )
            self.log.write(f"   - stability: {round(best_candidate.raw_metrics['stability'], 6)}")
            self.log.write(
                f"   - noise_fraction: {round(best_candidate.raw_metrics.get('noise_fraction', 0.0), 6)}"
            )
            self.log.write(
                f"   - imbalance_penalty: {round(best_candidate.raw_metrics['imbalance_penalty'], 6)}"
            )
            self.log.write(f"   - final_score: {round(best_candidate.final_score, 6)}")

    def _assess_winner_quality(
        self,
        best_candidate: ClusteringCandidate | None,
    ) -> dict[str, Any]:
        """
        Assess whether the winning model is genuinely reliable or just the least bad option.

        This is intentionally separate from the ranking step:
        - ranking answers "which evaluated model is best?"
        - quality assessment answers "is that winner actually good enough to trust?"
        """

        if best_candidate is None:
            return {
                "label": "UNAVAILABLE",
                "warning": True,
                "reasons": ["no valid clustering model was found"],
            }

        reasons = []
        metrics = best_candidate.raw_metrics

        silhouette = metrics.get("silhouette", -1.0)
        stability = metrics.get("stability", 0.0)
        noise_fraction = metrics.get("noise_fraction", 0.0)
        imbalance_penalty = metrics.get("imbalance_penalty", 1.0)
        final_score = best_candidate.final_score if best_candidate.final_score is not None else 0.0
        quality_warning_silhouette_threshold = self._config_value(
            "quality_warning_silhouette_threshold",
            0.10,
        )
        quality_warning_stability_threshold = self._config_value(
            "quality_warning_stability_threshold",
            0.40,
        )
        quality_warning_noise_threshold = self._config_value(
            "quality_warning_noise_threshold",
            0.30,
        )
        quality_warning_imbalance_threshold = self._config_value(
            "quality_warning_imbalance_threshold",
            0.40,
        )
        quality_warning_final_score_threshold = self._config_value(
            "quality_warning_final_score_threshold",
            0.35,
        )
        quality_good_silhouette_threshold = self._config_value(
            "quality_good_silhouette_threshold",
            0.25,
        )
        quality_good_stability_threshold = self._config_value(
            "quality_good_stability_threshold",
            0.80,
        )
        quality_good_noise_threshold = self._config_value(
            "quality_good_noise_threshold",
            0.10,
        )
        quality_good_imbalance_threshold = self._config_value(
            "quality_good_imbalance_threshold",
            0.30,
        )
        quality_good_final_score_threshold = self._config_value(
            "quality_good_final_score_threshold",
            0.60,
        )

        # Quality assessment is intentionally stricter than ranking:
        # - The ranking step selects the best model among the evaluated candidates.
        # - The quality label answers whether that winner is genuinely strong enough
        #   to be trusted without caveats.
        # A model can therefore win the ranking and still be only ACCEPTABLE.
        #
        # In practice:
        # - These thresholds below define weak-signal warnings.
        # - GOOD also requires clearing a stricter set of gates, so high stability
        #   alone is not enough when cluster separation remains modest.
        if silhouette < quality_warning_silhouette_threshold:
            reasons.append(
                f"low silhouette score ({round(silhouette, 4)}), indicating weak cluster separation"
            )
        if stability < quality_warning_stability_threshold:
            reasons.append(
                f"low stability ({round(stability, 4)}), indicating the partition is not robust under subsampling"
            )
        if noise_fraction > quality_warning_noise_threshold:
            reasons.append(
                f"high noise fraction ({round(noise_fraction, 4)}), indicating many samples remain unclustered"
            )
        if imbalance_penalty > quality_warning_imbalance_threshold:
            reasons.append(
                f"high cluster imbalance penalty ({round(imbalance_penalty, 4)}), indicating uneven cluster sizes"
            )
        if final_score < quality_warning_final_score_threshold:
            reasons.append(
                f"low final score ({round(final_score, 4)}), indicating weak overall clustering quality"
            )

        # GOOD is reserved for winners that are not only free of weak-signal warnings,
        # but also show genuinely solid separation, robustness, and overall score.
        good_quality = (
            silhouette >= quality_good_silhouette_threshold
            and stability >= quality_good_stability_threshold
            and noise_fraction <= quality_good_noise_threshold
            and imbalance_penalty <= quality_good_imbalance_threshold
            and final_score >= quality_good_final_score_threshold
        )

        if len(reasons) == 0 and good_quality:
            label = "GOOD"
            warning = False
        elif len(reasons) <= 1:
            label = "ACCEPTABLE"
            warning = False
        elif len(reasons) == 2:
            label = "POOR"
            warning = True
        else:
            label = "UNRELIABLE"
            warning = True

        return {
            "label": label,
            "warning": warning,
            "reasons": reasons,
        }

    def _log_quality_assessment(self, quality_assessment: dict[str, Any]) -> None:
        """
        Log a human-readable quality verdict for the selected clustering model.
        """

        label = quality_assessment["label"]
        reasons = quality_assessment["reasons"]

        self.log.write("\no Quality assessment of the selected clustering model:")
        self.log.write(f"   - verdict: {label}")

        if quality_assessment["warning"]:
            self.log.write(
                "x WARNING. This is the best model among the evaluated candidates, "
                "but its clustering quality is weak and should be interpreted with caution."
            )

        if reasons:
            self.log.write("   - diagnostic notes:")
            for reason in reasons:
                self.log.write(f"     - {reason}")
        else:
            self.log.write("   - diagnostic notes: no major quality concerns were detected")

    def _build_hdbscan_search_space(self, n_samples: int) -> dict[str, list[int | None]]:
        if self._dataset_mode == "very_large":
            ratios = self._config_value(
                "hdbscan_very_large_min_cluster_ratios",
                [0.01, 0.02, 0.05],
            )
            min_samples_candidates = self._config_value(
                "hdbscan_very_large_min_samples",
                [1, 5],
            )
        elif self._dataset_mode == "large":
            ratios = self._config_value(
                "hdbscan_large_min_cluster_ratios",
                [0.005, 0.01, 0.02, 0.05],
            )
            min_samples_candidates = self._config_value(
                "hdbscan_large_min_samples",
                [1, 5, 10],
            )
        else:
            ratios = self._config_value(
                "hdbscan_standard_min_cluster_ratios",
                [0.005, 0.01, 0.02, 0.05],
            )
            min_samples_candidates = self._config_value(
                "hdbscan_standard_min_samples",
                [1, 5, 10],
            )

        min_cluster_candidates = {
            max(2, int(math.floor(n_samples * ratio)))
            for ratio in ratios
        }
        min_cluster_candidates = sorted(
            value for value in min_cluster_candidates if value < n_samples
        )

        min_samples_candidates = [
            value for value in min_samples_candidates if value is None or value < n_samples
        ]

        return {
            "min_cluster_size": min_cluster_candidates,
            "min_samples": min_samples_candidates,
        }

    def _determine_dataset_mode(self, n_samples: int) -> str:
        """
        Map sample count to one shared runtime mode for all clustering algorithms.
        """

        if n_samples <= self._config_value("standard_dataset_threshold", STANDARD_DATASET_THRESHOLD):
            return "standard"
        if n_samples <= self._config_value("very_large_dataset_threshold", VERY_LARGE_DATASET_THRESHOLD):
            return "large"
        if n_samples <= self._config_value("ultra_large_dataset_threshold", ULTRA_LARGE_DATASET_THRESHOLD):
            return "very_large"
        return "ultra_large"

    def _get_silhouette_sample_size(self) -> int:
        """
        Return the silhouette subsample cap associated with the current dataset mode.
        """

        if self._dataset_mode == "large":
            return self._config_value("large_silhouette_sample_size", LARGE_SILHOUETTE_SAMPLE_SIZE)
        if self._dataset_mode == "very_large":
            return self._config_value("very_large_silhouette_sample_size", VERY_LARGE_SILHOUETTE_SAMPLE_SIZE)
        if self._dataset_mode == "ultra_large":
            return self._config_value("ultra_large_silhouette_sample_size", ULTRA_LARGE_SILHOUETTE_SAMPLE_SIZE)
        return self._config_value("large_silhouette_sample_size", LARGE_SILHOUETTE_SAMPLE_SIZE)

    def _compute_k_max(self, n_samples: int, algorithm: str) -> int:
        """
        Compute a data-driven upper bound for the explored cluster count.

        Design rationale:
        - The bound depends only on the number of samples, since the cluster count is
          ultimately a partition of the observations.
        - Small datasets are cheap to evaluate, so they should be allowed to explore
          a broader range of cluster counts.
        - Large datasets need explicit caps because each KMeans/GMM fit scales with
          sample count even when Bayesian screening avoids an exhaustive grid.
        - The average-cluster-size bound prevents extremely fragmented solutions.
        """

        if n_samples <= 100:
            automatic_k_max = max(2, min(10, n_samples // 3))
        elif n_samples <= 1000:
            automatic_k_max = max(2, int(math.floor(math.sqrt(n_samples))))
        else:
            sqrt_bound = int(math.floor(math.sqrt(n_samples)))
            average_cluster_bound = int(math.floor(n_samples / 15))
            automatic_k_max = max(2, min(sqrt_bound, average_cluster_bound))

        runtime_caps = {
            "large": 60,
            "very_large": 80,
            "ultra_large": 100,
        }
        runtime_cap = runtime_caps.get(self._dataset_mode)
        if runtime_cap is not None:
            automatic_k_max = min(automatic_k_max, runtime_cap)

        user_k_max = self._config_value("n_clusters_max", None)
        if user_k_max is None:
            return automatic_k_max

        return min(automatic_k_max, user_k_max)

    @staticmethod
    def _compute_imbalance_penalty(cluster_sizes: list[int]) -> float:
        """
        Quantify cluster imbalance with normalized entropy.
        """

        if len(cluster_sizes) < 2:
            return 1.0

        proportions = np.asarray(cluster_sizes, dtype=float) / np.sum(cluster_sizes)
        entropy = -np.sum(proportions * np.log(proportions + 1e-12))
        normalized_entropy = entropy / math.log(len(cluster_sizes))
        return float(1.0 - normalized_entropy)

    @staticmethod
    def _normalize_metric(values: list[float], lower_is_better: bool = False) -> list[float]:
        """
        Normalize a metric list to [0, 1] before combining it with other metrics.
        """

        arr = np.asarray(values, dtype=float)

        if lower_is_better:
            finite_mask = np.isfinite(arr)
            if not finite_mask.any():
                return [0.0] * len(arr)
            max_finite = np.max(arr[finite_mask])
            arr = np.where(finite_mask, arr, max_finite)
            arr = -arr
        else:
            finite_mask = np.isfinite(arr)
            if not finite_mask.any():
                return [0.0] * len(arr)
            min_finite = np.min(arr[finite_mask])
            arr = np.where(finite_mask, arr, min_finite)

        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        if math.isclose(min_val, max_val):
            return [1.0] * len(arr)

        return ((arr - min_val) / (max_val - min_val)).tolist()
