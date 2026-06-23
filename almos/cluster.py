"""
CLUSTER workflow.

This module prepares descriptors, applies cleanup, and selects representative
molecules that cover the cleaned chemical descriptor space. Natural clustering
diagnostics are optional and are not used by the default point-selection method.

Main user-facing parameters
---------------------------
General:
    input : str
        Input CSV or SDF file used by the coverage-selection workflow.
    name : str
        Identifier column when descriptors are already present in the CSV.
    ignore : list
        Columns excluded from descriptor cleanup and coverage selection.
    aqme : bool
        Generate descriptors with AQME before coverage selection.
    y : str
        Optional response column to ignore during coverage selection.
    categorical : str
        Encoding mode for categorical descriptor columns.

Descriptor cleanup:
    missing_threshold : float
        Remove descriptor columns with too many missing values.
    near_constant_threshold : float
        Remove descriptors dominated by almost one single value.
    iqr_threshold : float
        Minimum absolute variability required for continuous descriptors.
    rel_threshold : float
        Minimum relative variability required for continuous descriptors.
    binary_threshold : float
        Minimum minority-class proportion required for binary descriptors.
    correlation_threshold : float
        If two descriptors are too correlated, one of them is removed.
    min_descriptors : int
        Minimum number of descriptors required after cleanup.

Coverage selection:
    n_points : int or None
        Number of representative molecules to select. If not provided, ALMOS
        estimates an automatic coverage budget.
    evaluate : bool
        If True, skip representative reselection and only evaluate the existing
        user-provided selection stored as batch = 0 in the input CSV.
    mode : str
        Selection strategy. "representative" selects one real molecule nearest
        to each prototype centroid; diversity-focused selection keeps extra
        distant candidates.
    cluster_auto_budget_candidates : list
        Candidate budgets used as anchors for the automatic coverage scan.
    cluster_auto_budget_marginal_gain_threshold : float
        Marginal coverage-improvement threshold used to stop the budget scan.
    cluster_auto_budget_min_umap_area : float
        Minimum UMAP area fraction required for automatic recommendation.
    cluster_auto_budget_lookahead : int
        Number of later tested budgets inspected for local-slowdown detection.
    cluster_auto_budget_max_points : int
        Maximum automatic budget.
    cluster_natural_report : bool
        Run optional KMeans/GMM/HDBSCAN natural clustering diagnostics.

PCA safeguard:
    enable_pca : bool
        Disable PCA with --no_pca.
    cluster_high_dimensionality_threshold : int
        Descriptor-count threshold above which PCA can be activated.
    cluster_pca_explained_variance_threshold : float
        Target explained variance retained by PCA.
    cluster_pca_min_acceptable_variance : float
        Minimum variance required to accept PCA instead of raw descriptor space.
    cluster_pca_min_components : int
    pca_max_components : int
    pca_max_components_fraction : float

Large dataset mode:
    large_dataset_mode : bool
        Disable with --no_large_dataset_mode.
    cluster_standard_dataset_threshold : int
        Upper limit of the standard regime.
    cluster_very_large_dataset_threshold : int
        Upper limit of the large regime.
    cluster_ultra_large_dataset_threshold : int
        Above this, the workflow enters ultra-large mode.
    cluster_large_silhouette_sample_size : int
    cluster_very_large_silhouette_sample_size : int
    cluster_ultra_large_silhouette_sample_size : int
    cluster_large_dataset_stability_repeats : int
    cluster_fast_screening_top_candidates : int

Algorithm-specific search space:
    cluster_kmeans_coarse_grid_size : int
    cluster_kmeans_top_refinement_candidates : int
    cluster_kmeans_refine_radius : int
    cluster_kmeans_bo_fraction : float
    cluster_kmeans_bo_max_evaluations : int
    cluster_gmm_dimensionality_threshold : int
    cluster_gmm_standard_coarse_grid_size : int
    cluster_gmm_standard_refine_radius : int
    cluster_gmm_large_coarse_grid_size : int
    cluster_gmm_large_refine_radius : int
    cluster_gmm_very_large_coarse_grid_size : int
    cluster_gmm_very_large_refine_radius : int
    cluster_gmm_bo_fraction : float
    cluster_gmm_bo_max_evaluations : int
    cluster_gmm_bic_shortlist_size : int
    cluster_hdbscan_standard_min_cluster_ratios : list
    cluster_hdbscan_large_min_cluster_ratios : list
    cluster_hdbscan_very_large_min_cluster_ratios : list
    cluster_hdbscan_standard_min_samples : list
    cluster_hdbscan_large_min_samples : list
    cluster_hdbscan_very_large_min_samples : list

Quality filters:
    cluster_filter_max_noise_fraction : float
        Reject candidates with too many noise points, mainly for HDBSCAN.
    cluster_filter_max_cluster_fraction : float
        Reject candidates dominated by one oversized cluster.
    cluster_filter_max_imbalance_penalty : float
        Reject candidates with extreme cluster-size imbalance.
    cluster_quality_warning_silhouette_threshold : float
    cluster_quality_warning_stability_threshold : float
    cluster_quality_warning_noise_threshold : float
    cluster_quality_warning_imbalance_threshold : float
    cluster_quality_warning_final_score_threshold : float
    cluster_quality_good_silhouette_threshold : float
    cluster_quality_good_stability_threshold : float
    cluster_quality_good_noise_threshold : float
    cluster_quality_good_imbalance_threshold : float
    cluster_quality_good_final_score_threshold : float
"""

import html
import json
import os
import shutil
import subprocess
import sys
import time
import warnings

import numpy as np
import pandas as pd
from rdkit import Chem
from sklearn.cluster import MiniBatchKMeans
from sklearn.decomposition import PCA
from sklearn.impute import KNNImputer
from sklearn.manifold import trustworthiness
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from almos.cluster_utils import (
    ClusteringSelectionEngine,
    compute_cluster_descriptor_importance,
    log_descriptor_cleanup_summary,
    remove_correlated_descriptors,
    remove_duplicate_descriptors,
    remove_low_information_descriptors,
    remove_low_variance_descriptors,
)
from almos.argument_parser import CLUSTER_ALGORITHM_CHOICES, var_dict
from almos.utils import check_dependencies, load_variables


CLUSTER_SELECTION_MODE_CHOICES = {"representative", "exploratory", "natural"}
NATURAL_SELECTION_SCORE_TOLERANCE = 0.05


class cluster:
    """
    Class containing the CLUSTER module workflow.
    """

    def __init__(self, **kwargs):
        start_time_overall = time.time()

        self.args = load_variables(kwargs, "cluster")
        self.validate_cluster_threshold_options()

        if self.args.aqme:
            _ = check_dependencies(self, "cluster_aqme")

        self, df_csv_name, file_name = self.checking_cluster()
        self, descp_file, df_csv_name, csv = self.set_up_cluster(df_csv_name, file_name)

        if self.args.aqme:
            self, descp_file = self.run_aqme(csv, descp_file)

        self, descriptor_df, descp_file = self.clean_up_cluster(descp_file, csv, file_name)

        coverage_result = self.prepare_coverage_selection_input(descriptor_df)
        natural_selection_result = None
        if self.args.mode == "natural" or self.args.cluster_natural_report:
            natural_selection_result = self.run_natural_clustering_analysis(descriptor_df)
            coverage_result["natural_selection_result"] = natural_selection_result
        self.save_cluster_outputs(
            descp_file=descp_file,
            csv=csv,
            file_name=file_name,
            coverage_result=coverage_result,
        )

        if self.args.mode == "natural" or self.args.cluster_natural_report:
            if (
                natural_selection_result is not None
                and natural_selection_result.best_candidate is not None
            ):
                self.save_natural_clustering_report(
                    descp_file=descp_file,
                    selection_result=natural_selection_result,
                )
            else:
                self.args.log.write(
                    "\nx WARNING. Natural clustering report was requested, but no valid "
                    "clustering model survived filtering."
                )

        elapsed_time = round(time.time() - start_time_overall, 2)
        self.args.log.write(f"\nCoverage-based point selection time: {elapsed_time} seconds")
        self.args.log.finalize()

        shutil.move("CLUSTER_data.dat", "batch_0/CLUSTER_data.dat")

    def prepare_coverage_selection_input(self, descriptor_df):
        """
        Scale descriptors and apply the PCA safeguard used for coverage selection.
        """

        self.args.log.write("\no Coverage selection input preparation")
        self.args.log.write(f"   - Number of samples: {len(descriptor_df)}")
        self.args.log.write(f"   - Number of descriptors: {len(descriptor_df.columns)}")
        self.args.log.write("   - Feature scaling: StandardScaler")

        scaler = StandardScaler()
        scaled_data = scaler.fit_transform(descriptor_df.to_numpy(dtype=float))
        selection_data, dimensionality_reduction_info = self.prepare_coverage_selection_space(
            scaled_data,
            len(descriptor_df.columns),
        )
        return {
            "selection_data": selection_data,
            "descriptor_df": descriptor_df,
            "descriptor_columns": list(descriptor_df.columns),
            "dimensionality_reduction_info": dimensionality_reduction_info,
        }

    def run_natural_clustering_analysis(self, descriptor_df):
        """
        Run the optional natural clustering model selection once and reuse the result.
        """

        engine = ClusteringSelectionEngine(
            log=self.args.log,
            random_state=self.args.seed_clustered,
            stability_repeats=self.args.cluster_stability_repeats,
            subsample_fraction=self.args.cluster_subsample_fraction,
            hdbscan_enabled=self.args.hdbscan_enabled,
            config=self.build_clustering_engine_config(),
        )
        return engine.select_best_model(descriptor_df)

    def prepare_coverage_selection_space(self, scaled_data, descriptor_count):
        """
        Apply the high-dimensional PCA safeguard with selection-specific logging.
        """

        high_dimensionality_threshold = self.args.cluster_high_dimensionality_threshold
        if descriptor_count <= high_dimensionality_threshold:
            self.args.log.write(
                "   - Coverage selection is performed directly on the scaled descriptor space"
            )
            return scaled_data, {
                "applied": False,
                "method": None,
                "input_descriptor_count": descriptor_count,
                "output_dimension": scaled_data.shape[1],
            }

        if not self.args.enable_pca:
            self.args.log.write(
                f"\no PCA safeguard disabled by user "
                f"({descriptor_count} descriptors > {high_dimensionality_threshold})"
            )
            self.args.log.write(
                "   - Coverage selection will continue directly on the scaled descriptor space"
            )
            return scaled_data, {
                "applied": False,
                "method": None,
                "input_descriptor_count": descriptor_count,
                "output_dimension": scaled_data.shape[1],
                "disabled_by_user": True,
            }

        self.args.log.write(
            f"\nx WARNING. Descriptor count exceeds the direct selection threshold "
            f"({descriptor_count} > {high_dimensionality_threshold})."
        )
        self.args.log.write("o Activating PCA safeguard before coverage selection")

        pca_full = PCA(random_state=self.args.seed_clustered)
        pca_full.fit(scaled_data)
        cumulative_variance = np.cumsum(pca_full.explained_variance_ratio_)
        suggested_components = int(
            np.searchsorted(
                cumulative_variance,
                self.args.cluster_pca_explained_variance_threshold,
            )
            + 1
        )
        adaptive_component_cap = max(
            self.args.cluster_pca_min_components,
            int(np.floor(descriptor_count * self.args.pca_max_components_fraction)),
        )
        adaptive_component_cap = min(
            adaptive_component_cap,
            self.args.pca_max_components,
            scaled_data.shape[1],
            scaled_data.shape[0],
        )
        n_components = max(self.args.cluster_pca_min_components, suggested_components)
        n_components = min(n_components, adaptive_component_cap)

        pca = PCA(n_components=n_components, random_state=self.args.seed_clustered)
        selection_data = pca.fit_transform(scaled_data)
        retained_variance = float(np.sum(pca.explained_variance_ratio_))

        if retained_variance < self.args.cluster_pca_min_acceptable_variance:
            self.args.log.write(
                f"x WARNING. PCA fallback retained only {round(retained_variance, 6)} "
                "explained variance, below the minimum acceptable threshold."
            )
            self.args.log.write(
                "o PCA will be discarded and coverage selection will continue in the scaled descriptor space"
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
        self.args.log.write("   - PCA is used only as a high-dimensional fallback")
        self.args.log.write(f"   - Original descriptor count: {descriptor_count}")
        self.args.log.write(f"   - Adaptive PCA component cap: {adaptive_component_cap}")
        self.args.log.write(f"   - PCA components retained: {n_components}")
        self.args.log.write(
            f"   - Dimensionality reduction: {descriptor_count} -> {n_components} "
            f"({round(reduction_ratio * 100, 2)}% reduction)"
        )
        self.args.log.write(
            f"   - Cumulative explained variance retained: {round(retained_variance, 6)}"
        )
        return selection_data, {
            "applied": True,
            "method": "PCA",
            "input_descriptor_count": descriptor_count,
            "output_dimension": n_components,
            "explained_variance_ratio": retained_variance,
            "target_explained_variance": self.args.cluster_pca_explained_variance_threshold,
        }

    def _reset_cluster_option(self, option_name, reason):
        default_value = var_dict[option_name]
        setattr(self.args, option_name, default_value)
        self.args.log.write(
            f"\nx WARNING. Invalid value for --{option_name}: {reason}. "
            f"Using default value: {default_value}"
        )

    def _validate_numeric_option(
        self,
        option_name,
        expected_type,
        min_value=None,
        max_value=None,
        allow_none=False,
    ):
        value = getattr(self.args, option_name)

        if value is None:
            if allow_none:
                return
            self._reset_cluster_option(option_name, f"expected a {expected_type}, got None")
            return

        if expected_type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                self._reset_cluster_option(option_name, f"expected an integer, got {value}")
                return
        else:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                self._reset_cluster_option(option_name, f"expected a number, got {value}")
                return
            setattr(self.args, option_name, float(value))
            value = getattr(self.args, option_name)

        if min_value is not None and value < min_value:
            self._reset_cluster_option(
                option_name,
                f"value {value} is below the minimum allowed value of {min_value}",
            )
            return

        if max_value is not None and value > max_value:
            self._reset_cluster_option(
                option_name,
                f"value {value} is above the maximum allowed value of {max_value}",
            )

    def _validate_ratio_list_option(self, option_name):
        value = getattr(self.args, option_name)
        if not isinstance(value, list) or len(value) == 0:
            self._reset_cluster_option(option_name, "expected a non-empty list of ratios")
            return

        cleaned_values = []
        for element in value:
            if isinstance(element, bool) or not isinstance(element, (int, float)):
                self._reset_cluster_option(option_name, f"invalid ratio element {element}")
                return
            element = float(element)
            if not 0 < element < 1:
                self._reset_cluster_option(option_name, f"ratio {element} must be between 0 and 1")
                return
            cleaned_values.append(element)

        setattr(self.args, option_name, sorted(set(cleaned_values)))

    def _validate_optional_int_list_option(self, option_name):
        value = getattr(self.args, option_name)
        if not isinstance(value, list) or len(value) == 0:
            self._reset_cluster_option(option_name, "expected a non-empty list of integers")
            return

        cleaned_values = []
        for element in value:
            if element is None:
                cleaned_values.append(None)
                continue
            if isinstance(element, bool) or not isinstance(element, int) or element < 1:
                self._reset_cluster_option(option_name, f"invalid min_samples element {element}")
                return
            cleaned_values.append(element)

        unique_values = []
        for element in cleaned_values:
            if element not in unique_values:
                unique_values.append(element)
        setattr(self.args, option_name, unique_values)

    def _validate_choice_list_option(self, option_name, allowed_values):
        value = getattr(self.args, option_name)
        if not isinstance(value, list) or len(value) == 0:
            self._reset_cluster_option(option_name, "expected a non-empty list")
            return

        cleaned_values = []
        for element in value:
            if not isinstance(element, str):
                self._reset_cluster_option(option_name, f"invalid entry {element}")
                return
            normalized_value = element.strip().lower()
            if normalized_value not in allowed_values:
                self._reset_cluster_option(
                    option_name,
                    f"allowed values are {sorted(allowed_values)}",
                )
                return
            if normalized_value not in cleaned_values:
                cleaned_values.append(normalized_value)

        setattr(self.args, option_name, cleaned_values)

    def validate_cluster_threshold_options(self):
        for option_name in [
            "hdbscan_enabled",
            "enable_pca",
            "large_dataset_mode",
            "cluster_natural_report",
        ]:
            if not isinstance(getattr(self.args, option_name), bool):
                self._reset_cluster_option(option_name, "expected True or False")

        int_options = [
            ("n_clusters_max", 2, None),
            ("n_points", 1, None),
            ("min_descriptors", 1, None),
            ("cluster_stability_repeats", 1, None),
            ("cluster_high_dimensionality_threshold", 1, None),
            ("cluster_pca_min_components", 1, None),
            ("pca_max_components", 1, None),
            ("cluster_standard_dataset_threshold", 1, None),
            ("cluster_very_large_dataset_threshold", 1, None),
            ("cluster_ultra_large_dataset_threshold", 1, None),
            ("cluster_large_silhouette_sample_size", 2, None),
            ("cluster_very_large_silhouette_sample_size", 2, None),
            ("cluster_ultra_large_silhouette_sample_size", 2, None),
            ("cluster_large_dataset_stability_repeats", 1, None),
            ("cluster_fast_screening_top_candidates", 1, None),
            ("cluster_kmeans_coarse_grid_size", 2, None),
            ("cluster_kmeans_top_refinement_candidates", 1, None),
            ("cluster_kmeans_refine_radius", 1, None),
            ("cluster_kmeans_bo_max_evaluations", 1, None),
            ("cluster_gmm_dimensionality_threshold", 1, None),
            ("cluster_gmm_standard_coarse_grid_size", 2, None),
            ("cluster_gmm_standard_refine_radius", 1, None),
            ("cluster_gmm_large_coarse_grid_size", 2, None),
            ("cluster_gmm_large_refine_radius", 1, None),
            ("cluster_gmm_very_large_coarse_grid_size", 2, None),
            ("cluster_gmm_very_large_refine_radius", 1, None),
            ("cluster_gmm_bo_max_evaluations", 1, None),
            ("cluster_gmm_bic_shortlist_size", 1, None),
            ("cluster_auto_budget_min_points", 1, None),
            ("cluster_auto_budget_max_points", 1, None),
            ("cluster_auto_budget_lookahead", 1, None),
            ("cluster_auto_budget_coverage_sample_size", 100, None),
        ]
        float_options = [
            ("missing_threshold", 0.0, 1.0),
            ("near_constant_threshold", 0.0, 1.0),
            ("iqr_threshold", 0.0, None),
            ("rel_threshold", 0.0, 1.0),
            ("binary_threshold", 0.0, 1.0),
            ("correlation_threshold", 0.0, 1.0),
            ("cluster_subsample_fraction", 0.0, 1.0),
            ("cluster_pca_explained_variance_threshold", 0.0, 1.0),
            ("cluster_pca_min_acceptable_variance", 0.0, 1.0),
            ("pca_max_components_fraction", 0.0, 1.0),
            ("cluster_kmeans_bo_fraction", 0.0, 1.0),
            ("cluster_gmm_bo_fraction", 0.0, 1.0),
            ("cluster_filter_max_noise_fraction", 0.0, 1.0),
            ("cluster_filter_max_cluster_fraction", 0.0, 1.0),
            ("cluster_filter_max_imbalance_penalty", 0.0, 1.0),
            ("cluster_quality_warning_silhouette_threshold", -1.0, 1.0),
            ("cluster_quality_warning_stability_threshold", 0.0, 1.0),
            ("cluster_quality_warning_noise_threshold", 0.0, 1.0),
            ("cluster_quality_warning_imbalance_threshold", 0.0, 1.0),
            ("cluster_quality_warning_final_score_threshold", 0.0, 1.0),
            ("cluster_quality_good_silhouette_threshold", -1.0, 1.0),
            ("cluster_quality_good_stability_threshold", 0.0, 1.0),
            ("cluster_quality_good_noise_threshold", 0.0, 1.0),
            ("cluster_quality_good_imbalance_threshold", 0.0, 1.0),
            ("cluster_quality_good_final_score_threshold", 0.0, 1.0),
            ("cluster_auto_budget_sqrt_factor", 0.1, None),
            ("cluster_auto_budget_marginal_gain_threshold", 0.0, 1.0),
            ("cluster_auto_budget_min_umap_area", 0.0, 1.0),
        ]

        for option_name, min_value, max_value in int_options:
            self._validate_numeric_option(
                option_name,
                "int",
                min_value=min_value,
                max_value=max_value,
                allow_none=option_name in ["n_clusters_max", "n_points"],
            )
        for option_name, min_value, max_value in float_options:
            self._validate_numeric_option(option_name, "float", min_value=min_value, max_value=max_value)

        for option_name in [
            "cluster_hdbscan_standard_min_cluster_ratios",
            "cluster_hdbscan_large_min_cluster_ratios",
            "cluster_hdbscan_very_large_min_cluster_ratios",
        ]:
            self._validate_ratio_list_option(option_name)

        for option_name in [
            "cluster_hdbscan_standard_min_samples",
            "cluster_hdbscan_large_min_samples",
            "cluster_hdbscan_very_large_min_samples",
        ]:
            self._validate_optional_int_list_option(option_name)

        self._validate_choice_list_option("algorithms", CLUSTER_ALGORITHM_CHOICES)

        selection_mode = str(self.args.mode).lower()
        if selection_mode not in CLUSTER_SELECTION_MODE_CHOICES:
            self._reset_cluster_option(
                "mode",
                f"expected one of {sorted(CLUSTER_SELECTION_MODE_CHOICES)}",
            )
        else:
            self.args.mode = selection_mode

        if not (
            self.args.cluster_standard_dataset_threshold
            < self.args.cluster_very_large_dataset_threshold
            < self.args.cluster_ultra_large_dataset_threshold
        ):
            for option_name in [
                "cluster_standard_dataset_threshold",
                "cluster_very_large_dataset_threshold",
                "cluster_ultra_large_dataset_threshold",
            ]:
                setattr(self.args, option_name, var_dict[option_name])
            self.args.log.write(
                "\nx WARNING. Dataset size thresholds must satisfy "
                "standard < very_large < ultra_large. Default values will be used."
            )

        if self.args.cluster_pca_min_acceptable_variance > self.args.cluster_pca_explained_variance_threshold:
            self._reset_cluster_option(
                "cluster_pca_min_acceptable_variance",
                "the minimum acceptable variance cannot exceed the PCA target variance",
            )

    def build_clustering_engine_config(self):
        config = {
            option_name.replace("cluster_", "", 1): value
            for option_name, value in vars(self.args).items()
            if option_name.startswith("cluster_")
        }
        config["enable_pca_safeguard"] = self.args.enable_pca
        config["pca_max_components_absolute"] = self.args.pca_max_components
        config["enable_large_dataset_mode"] = self.args.large_dataset_mode
        config["algorithms"] = self.args.algorithms
        config["n_clusters_max"] = self.args.n_clusters_max
        return config

    def checking_cluster(self):
        """
        Detect errors and update variables before the CLUSTER run.
        """

        if self.args.input is None:
            self.args.log.write(
                "\nx WARNING. Please specify the input CSV file, "
                "for example --input example.csv"
            )
            self.args.log.finalize()
            sys.exit(9)

        file_name = os.path.basename(self.args.input)

        if not os.path.exists(self.args.input):
            self.args.log.write(
                f"\nx WARNING. The input file ({file_name}) does not exist. "
                "Please check the provided path."
            )
            self.args.log.finalize()
            sys.exit(10)

        if self.args.n_clusters is not None:
            self.args.log.write(
                f"\nx WARNING. The user-defined value --n_clusters {self.args.n_clusters} "
                "will be ignored. The new clustering pipeline determines the number of clusters automatically."
            )

        input_extension = file_name.split(".")[-1].lower()
        if input_extension not in ["csv", "sdf"]:
            self.args.log.write(
                f"\nx WARNING. Unsupported input format '.{input_extension}' for CLUSTER. "
                "Please provide a CSV file, or an SDF file with --aqme."
            )
            self.args.log.finalize()
            sys.exit(20)

        if input_extension == "sdf" and self.args.aqme is False:
            self.args.log.write(
                "\nx WARNING. SDF input is only supported when using AQME (--aqme)."
            )
            self.args.log.finalize()
            sys.exit(14)

        if input_extension == "sdf" and self.args.aqme:
            if self.args.ignore != []:
                self.args.log.write(
                    "\nx WARNING. The --ignore option can only be used when the input is a CSV file."
                )
                self.args.log.finalize()
                sys.exit(15)

            sdf_file = Chem.SDMolSupplier(self.args.input)
            column_name, column_smile = [], []
            name_column_sdf = None

            for mol in sdf_file:
                if mol is not None:
                    for prop in mol.GetPropNames():
                        if "name" in prop.lower():
                            name_column_sdf = prop
                            break
                if name_column_sdf:
                    break

            sdf_file = Chem.SDMolSupplier(self.args.input)
            for mol in sdf_file:
                if mol is not None:
                    if name_column_sdf is not None and mol.HasProp(name_column_sdf):
                        molecule_name = mol.GetProp(name_column_sdf)
                    elif mol.HasProp("_Name") and mol.GetProp("_Name").strip() != "":
                        molecule_name = mol.GetProp("_Name")
                    else:
                        molecule_name = f"mol_{len(column_name) + 1}"
                    column_name.append(molecule_name)
                    column_smile.append(Chem.MolToSmiles(mol))

            self.args.log.write("\no Analyzing SDF input")
            df_csv_name = pd.DataFrame(
                {
                    "code_name": column_name,
                    "SMILES": column_smile,
                }
            )

            file_name = file_name.replace("sdf", "csv")
            df_csv_name.to_csv(file_name, index=False)
            self.args.log.write(
                f"\no Converted SDF input into temporary CSV file: {file_name}"
            )

        if input_extension == "csv":
            df_csv_name = pd.read_csv(self.args.input)

            if self.args.name == "" and self.args.aqme is False:
                code_name_columns = [
                    column for column in df_csv_name.columns if column.lower() == "code_name"
                ]
                if code_name_columns:
                    self.args.name = code_name_columns[0]
                    self.args.log.write(
                        f"\no No --name column was specified; using '{self.args.name}' as the identifier column"
                    )
                else:
                    self.args.log.write(
                        "\nx WARNING. Please specify the name column of your CSV file, "
                        "for example --name molecules. If your CSV contains a 'code_name' "
                        "column, it will be used automatically."
                    )
                    self.args.log.finalize()
                    sys.exit(13)

            elements = []
            for element in self.args.ignore:
                if element not in df_csv_name.columns:
                    elements.append(element)
            if elements != []:
                string_ignore = "[" + ",".join(str(x) for x in self.args.ignore) + "]"
                self.args.log.write(
                    f"\nx WARNING. Some columns ({elements}), listed in --ignore {string_ignore}, "
                    f"do not exist in the input ({file_name}). Please review the ignore list."
                )
                self.args.log.finalize()
                sys.exit(5)

            batch_columns = [
                column for column in df_csv_name.columns if column.lower() == "batch"
            ]
            if batch_columns:
                batch_column = batch_columns[0]
                batch_values = pd.to_numeric(df_csv_name[batch_column], errors="coerce")
                has_assigned_batch_values = batch_values.notna().any()
                if self.args.evaluate:
                    if not has_assigned_batch_values:
                        self.args.log.write(
                            f"\nx WARNING. The input ({file_name}) contains a 'batch' column, "
                            "but no assigned batch values were found. The --evaluate mode requires "
                            "an existing selection marked with batch = 0."
                        )
                        self.args.log.finalize()
                        sys.exit(1)
                    if not (batch_values == 0).any():
                        self.args.log.write(
                            f"\nx WARNING. The input ({file_name}) does not contain any rows with "
                            "batch = 0. The --evaluate mode expects the current selection to be "
                            "marked with batch = 0."
                        )
                        self.args.log.finalize()
                        sys.exit(1)
                    df_csv_name[batch_column] = batch_values
                    self.args.log.write(
                        "\no Existing batch assignments detected. Running CLUSTER in evaluation-only mode."
                    )
                    self.args.log.write(
                        "   - Representative reselection will be skipped."
                    )
                    self.args.log.write(
                        "   - Rows with batch = 0 will be treated as the user-provided current selection."
                    )
                    if (batch_values > 0).any():
                        self.args.log.write(
                            "   - Non-zero batch values were also detected; only batch = 0 will be evaluated as the current clustering selection."
                        )
                elif has_assigned_batch_values:
                    self.args.log.write(
                        f"\nx WARNING. The input ({file_name}) already contains assigned batch values."
                    )
                    self.args.log.write(
                        "CLUSTER would overwrite the existing selection."
                    )
                    self.args.log.write(
                        "If you only want to evaluate and visualize the current selection, rerun with --evaluate."
                    )
                    self.args.log.finalize()
                    sys.exit(1)

            if self.args.y != "":
                if self.args.y not in df_csv_name.columns:
                    self.args.log.write(
                        f"\nx WARNING. The input ({file_name}) does not contain the target column "
                        f"specified with --y {self.args.y}"
                    )
                    self.args.log.finalize()
                    sys.exit(3)
                if self.args.y not in self.args.ignore:
                    self.args.ignore.append(self.args.y)

        if df_csv_name.duplicated().any():
            duplicate_rows = df_csv_name[df_csv_name.duplicated(keep=False)]
            self.args.log.write(
                f"\nx WARNING. The input ({file_name}) contains duplicate rows. "
                f"Only the first occurrence of each duplicated row will be kept.\n{duplicate_rows}"
            )
            df_csv_name = df_csv_name.drop_duplicates()

        if self.args.name != "":
            if self.args.name not in df_csv_name.columns:
                matching_name_columns = [
                    column
                    for column in df_csv_name.columns
                    if column.lower() == self.args.name.lower()
                ]
                if matching_name_columns:
                    self.args.name = matching_name_columns[0]
                else:
                    self.args.log.write(
                        f"\nx WARNING. The input ({file_name}) does not contain the name column "
                        f"specified with --name {self.args.name}"
                    )
                    self.args.log.finalize()
                    sys.exit(4)

            if self.args.name not in self.args.ignore:
                self.args.ignore.append(self.args.name)

            if df_csv_name[self.args.name].duplicated().any():
                duplicate_names = df_csv_name[
                    df_csv_name.duplicated(subset=[self.args.name], keep=False)
                ]
                self.args.log.write(
                    f"\nx WARNING. The input ({file_name}) contains duplicated identifiers in the "
                    f"name column ({self.args.name}) with inconsistent descriptor values.\n{duplicate_names}"
                )
                self.args.log.finalize()
                sys.exit(8)

        return self, df_csv_name, file_name

    def fix_cols_names(self, df):
        """
        Standardize code_name and SMILES column names.
        """

        for col in df.columns:
            if col.lower() == "smiles":
                df = df.rename(columns={col: "SMILES"})
            if col.lower() == "code_name":
                df = df.rename(columns={col: "code_name"})
        return df

    def auto_fill_knn(self, df):
        """
        Fill missing values using KNNImputer.
        """

        imputer = KNNImputer(n_neighbors=5, weights="uniform")
        return imputer.fit_transform(df)

    def categorical_transform(self, df):
        """
        Convert categorical columns into numeric descriptors.
        """

        txt_categor = "\no Analyzing categorical variables"
        categorical_vars, new_categor_desc = [], []

        for column in list(df.columns):
            if column not in self.args.ignore and column != self.args.y:
                if df[column].dtype == "object":
                    categorical_vars.append(column)

                    if self.args.categorical.lower() == "numbers":
                        df[column] = df[column].astype("category")
                        df[column] = df[column].cat.codes
                    else:
                        categor_descs = pd.get_dummies(df[column], prefix=column)
                        df = df.drop(column, axis=1)
                        df = pd.concat([df, categor_descs], axis=1)
                        new_categor_desc.extend(list(categor_descs.columns))

        if len(categorical_vars) == 0:
            txt_categor += "\n   - No categorical variables were found"
        else:
            txt_categor += (
                f"\n   - Converted {len(categorical_vars)} categorical variable(s) "
                f"using mode '{self.args.categorical}'"
            )
            txt_categor += "\n   - Original categorical columns:"
            txt_categor += "\n" + "\n".join(f"     - {var}" for var in categorical_vars)
            if new_categor_desc:
                txt_categor += "\n   - Generated encoded descriptors:"
                txt_categor += "\n" + "\n".join(f"     - {var}" for var in new_categor_desc)

        self.args.log.write(txt_categor)
        return df

    def set_up_cluster(self, df_csv_name, file_name):
        """
        Prepare the CSV file and working folders.
        """

        if self.args.evaluate and "batch" in df_csv_name.columns:
            df_csv_name["batch"] = pd.to_numeric(df_csv_name["batch"], errors="coerce")
        else:
            df_csv_name["batch"] = np.nan
        if "batch" not in self.args.ignore:
            self.args.ignore.append("batch")
        os.makedirs("batch_0", exist_ok=True)

        if self.args.aqme:
            fixed_df = self.fix_cols_names(df_csv_name)

            if self.args.name == "" and "code_name" in fixed_df.columns:
                self.args.name = "code_name"
                self.args.log.write(
                    "\no No --name column was specified; using 'code_name' as the identifier column"
                )

            if self.args.name.lower() == "code_name":
                self.args.name = "code_name"
                self.args.ignore = [
                    "code_name" if column.lower() == "code_name" else column
                    for column in self.args.ignore
                ]

            if self.args.name != "" and self.args.name in fixed_df.columns:
                if self.args.name != "code_name":
                    if "code_name" in fixed_df.columns:
                        self.args.log.write(
                            f"\nx WARNING. The input ({file_name}) contains both '{self.args.name}' "
                            "and 'code_name'. Please keep only one identifier column when using AQME."
                        )
                        self.args.log.finalize()
                        sys.exit(16)

                    self._aqme_output_name_column = self.args.name
                    fixed_df = fixed_df.rename(columns={self.args.name: "code_name"})
                    self.args.ignore = [
                        "code_name" if column == self.args.name else column
                        for column in self.args.ignore
                    ]
                    self.args.name = "code_name"
                    self.args.log.write(
                        "\no Renamed the user-defined identifier column to 'code_name' for AQME compatibility"
                    )

            if "code_name" not in fixed_df.columns or "SMILES" not in fixed_df.columns:
                self.args.log.write(
                    f"\nx WARNING. The input ({file_name}) must contain 'SMILES' and an identifier column "
                    "to generate descriptors with AQME. Use --name to specify the identifier column, "
                    "or provide a 'code_name' column."
                )
                self.args.log.finalize()
                sys.exit(2)

            original_input_columns = fixed_df.columns.tolist()
            for column in original_input_columns:
                if column not in self.args.ignore:
                    self.args.ignore.append(column)

            ignored_original_descriptors = [
                column
                for column in original_input_columns
                if column not in ["code_name", "SMILES", "batch", self.args.y]
            ]
            if ignored_original_descriptors:
                self.args.log.write(
                    "\no AQME mode enabled: original CSV descriptor columns will be ignored for coverage selection"
                )
                self.args.log.write(
                    f"   - Ignored original input columns: {ignored_original_descriptors}"
                )

            df_csv_name = fixed_df
            os.makedirs("aqme", exist_ok=True)

        for col in df_csv_name.columns:
            if col.lower() == "smiles":
                if col not in self.args.ignore:
                    self.args.ignore.append(col)

                invalid_smiles = []

                def canonicalize_smiles(value):
                    if pd.isna(value) or str(value).strip() == "":
                        invalid_smiles.append(value)
                        return None
                    molecule = Chem.MolFromSmiles(str(value))
                    if molecule is None:
                        invalid_smiles.append(value)
                        return None
                    return Chem.MolToSmiles(molecule)

                df_csv_name[col] = df_csv_name[col].apply(canonicalize_smiles)

                if invalid_smiles:
                    if self.args.aqme:
                        self.args.log.write(
                            f"\nx WARNING. Invalid SMILES were removed from ({file_name}): {invalid_smiles}"
                        )
                        df_csv_name = df_csv_name.dropna(subset=[col])
                    else:
                        self.args.log.write(
                            f"\nx WARNING. Invalid SMILES were detected in ({file_name}): {invalid_smiles}"
                        )

                if df_csv_name[col].duplicated().any():
                    duplicate_smiles = df_csv_name[
                        df_csv_name.duplicated(subset=[col], keep=False)
                    ]
                    if self.args.aqme:
                        self.args.log.write(
                            f"\nx WARNING. Duplicated canonical SMILES were found in ({file_name}). "
                            "Only the first occurrence of each duplicated structure will be kept.\n"
                            f"{duplicate_smiles}"
                        )
                        df_csv_name = df_csv_name.drop_duplicates(subset=[col])
                    else:
                        self.args.log.write(
                            f"\nx WARNING. Duplicated canonical SMILES were detected in ({file_name}).\n"
                            f"{duplicate_smiles}"
                        )

            if col == "code_name" and "code_name" not in self.args.ignore:
                self.args.ignore.append("code_name")

        csv = file_name.rsplit(".", 1)
        df_csv_name.to_csv(f"{csv[0]}_b0.csv", index=False, header=True)
        descp_file = f"{csv[0]}_b0.csv"

        self.args.log.write(f"\no Prepared initial coverage-selection CSV: {descp_file}")
        return self, descp_file, df_csv_name, csv

    def run_aqme(self, csv, descp_file):
        """
        Generate descriptors with AQME when requested.
        """

        cmd_qdescp = ["python", "-m", "aqme", "--qdescp", "--input", descp_file]

        if self.args.nprocs != 8:
            cmd_qdescp += ["--nprocs", f"{self.args.nprocs}"]

        if self.args.aqme_keywords != "":
            cmd_aqme = self.args.aqme_keywords.split()
            for word in cmd_aqme:
                word = word.replace('"', "").replace("'", "")
                cmd_qdescp.append(word)

        exit_error = subprocess.run(cmd_qdescp)

        string_cmd = " ".join(cmd_qdescp)
        self.args.log.write(f"\no Command line used in AQME: {string_cmd}")

        files_to_aqme = [
            f"AQME-ROBERT_denovo_{csv[0]}_b0.csv",
            f"AQME-ROBERT_interpret_{csv[0]}_b0.csv",
            f"AQME-ROBERT_full_{csv[0]}_b0.csv",
            "QDESCP_data.dat",
            "CSEARCH_data.dat",
            "CSEARCH",
            "QDESCP",
        ]
        folders = ["CSEARCH", "QDESCP"]

        if exit_error.returncode != 0 or not os.path.exists(
            f"AQME-ROBERT_denovo_{csv[0]}_b0.csv"
        ):
            self.args.log.write(
                "\nx WARNING. AQME descriptor generation failed. Check --aqme_keywords and the AQME input."
            )
            self.args.log.finalize()
            sys.exit(12)

        for file in files_to_aqme:
            destination = f"aqme/{file}"
            if os.path.exists(destination):
                if file in folders:
                    shutil.rmtree(destination)
                else:
                    os.remove(destination)

            if os.path.exists(file):
                shutil.move(file, destination)

        descp_file = f"aqme/AQME-ROBERT_{self.args.descp_level}_{csv[0]}_b0.csv"
        if not os.path.exists(descp_file):
            self.args.log.write(
                f"\nx WARNING. The selected AQME descriptor level '{self.args.descp_level}' "
                f"was not found ({descp_file})."
            )
            self.args.log.finalize()
            sys.exit(17)

        self.args.log.write(f"\no Using AQME descriptor file: {descp_file}")

        return self, descp_file

    def clean_up_cluster(self, descp_file, csv, file_name):
        """
        Prepare the descriptor matrix for clustering.
        """

        missing_data_cols = []

        original_batch_file = f"batch_0/{csv[0]}_b0.csv"
        shutil.move(f"{csv[0]}_b0.csv", original_batch_file)
        if self.args.aqme is False:
            descp_file = original_batch_file

        original_input_df = pd.read_csv(original_batch_file)
        descp_df = pd.read_csv(descp_file)
        descp_df_drop = descp_df.drop(self.args.ignore, axis=1, errors="ignore")
        initial_descriptor_columns = descp_df_drop.columns.tolist()

        self.args.log.write("\no Preparing descriptor matrix for coverage selection")
        self.args.log.write(f"   - Initial descriptor count: {len(initial_descriptor_columns)}")

        col_to_drop = []
        for col in descp_df_drop.columns:
            if descp_df_drop[col].isna().mean() > self.args.missing_threshold:
                self.args.log.write(
                    f"\nx WARNING. Descriptor ({col}) in ({file_name}) contains more than "
                    f"{self.args.missing_threshold * 100:.2f}% missing "
                    "values and will be removed."
                )
                col_to_drop.append(col)

        if col_to_drop != []:
            descp_df_drop = descp_df_drop.drop(col_to_drop, axis=1)
        missing_data_cols = col_to_drop.copy()

        descp_df_drop = self.categorical_transform(descp_df_drop)

        if descp_df_drop.isnull().any().any():
            if self.args.aqme is False:
                if self.args.auto_fill:
                    self.args.log.write(
                        f"\nx WARNING. Missing descriptor values were found in ({file_name}). "
                        "They will be imputed with KNNImputer because --auto_fill is enabled."
                    )
                else:
                    self.args.log.write(
                        f"\nx WARNING. Missing descriptor values were found in ({file_name}) "
                        "and --auto_fill is disabled."
                    )
                    self.args.log.finalize()
                    sys.exit(6)

            filled_array = self.auto_fill_knn(descp_df_drop)
            descp_df_drop = pd.DataFrame(
                filled_array,
                columns=descp_df_drop.columns,
                index=descp_df_drop.index,
            )
            descp_df.update(descp_df_drop)

        descp_df_drop, constant_cols, near_constant_cols = remove_low_information_descriptors(
            descp_df_drop,
            log=self.args.log,
            top_freq_threshold=self.args.near_constant_threshold,
        )
        descp_df_drop, duplicated_cols = remove_duplicate_descriptors(
            descp_df_drop,
            log=self.args.log,
        )
        descp_df_drop, low_variance_cols = remove_low_variance_descriptors(
            descp_df_drop,
            log=self.args.log,
            iqr_threshold=self.args.iqr_threshold,
            rel_threshold=self.args.rel_threshold,
            binary_threshold=self.args.binary_threshold,
        )
        descp_df_drop, correlated_cols = remove_correlated_descriptors(
            descp_df_drop,
            log=self.args.log,
            corr_threshold=self.args.correlation_threshold,
        )

        if len(descp_df_drop.columns) < self.args.min_descriptors:
            self.args.log.write(
                f"\nx WARNING. The input ({file_name}) must contain at least "
                f"{self.args.min_descriptors} descriptor columns "
                "after cleanup."
            )
            self.args.log.finalize()
            sys.exit(7)

        if self.args.aqme:
            if len(original_input_df) != len(descp_df_drop):
                self.args.log.write(
                    "\nx WARNING. The AQME descriptor file and the original input have different "
                    "numbers of rows after preprocessing, so the final CSV cannot be aligned safely."
                )
                self.args.log.finalize()
                sys.exit(18)

            descriptor_columns = descp_df_drop.columns.tolist()
            original_columns = original_input_df.columns.tolist()
            descp_df = pd.concat(
                [
                    original_input_df.reset_index(drop=True),
                    descp_df_drop.reset_index(drop=True),
                ],
                axis=1,
            )
            descp_df = descp_df.loc[
                :,
                original_columns
                + [column for column in descriptor_columns if column not in original_columns],
            ].copy()
        else:
            metadata_columns = [
                column for column in descp_df.columns if column in self.args.ignore
            ]
            metadata_df = descp_df.loc[:, metadata_columns].reset_index(drop=True)
            descp_df = pd.concat(
                [
                    metadata_df,
                    descp_df_drop.reset_index(drop=True),
                ],
                axis=1,
            )

        removed_summary = {
            "descriptors with more than 30% missing values": missing_data_cols,
            "constant descriptors": constant_cols,
            "near-constant descriptors": near_constant_cols,
            "duplicated descriptors": duplicated_cols,
            "low-variance descriptors": low_variance_cols,
            "highly correlated descriptors": correlated_cols,
        }
        log_descriptor_cleanup_summary(
            self.args.log,
            initial_descriptor_columns,
            descp_df_drop.columns.tolist(),
            removed_summary,
        )

        descp_df.to_csv(f"batch_0/{csv[0]}_b0.csv", index=False, header=True)
        descp_file = f"batch_0/{csv[0]}_b0.csv"

        self.args.log.write(
            f"\no Final descriptor count after cleanup: {len(descp_df_drop.columns)}"
        )
        return self, descp_df_drop, descp_file

    def select_representative_points(self, coverage_result):
        """
        Select representative rows by global descriptor-space coverage.
        """

        selection_data = coverage_result["selection_data"]
        selectable_indices = np.arange(len(selection_data))
        self._coverage_auto_budget_context = {}

        requested_points = self.args.n_points
        if requested_points is None:
            target_points = self.estimate_auto_coverage_budget(
                selection_data,
                selectable_indices,
            )
            automatic_points = True
        else:
            target_points = int(requested_points)
            automatic_points = False

        if target_points > len(selection_data):
            self.args.log.write(
                f"\nx WARNING. The requested number of points (--n_points {target_points}) "
                f"is larger than the number of rows in the CSV ({len(selection_data)})."
            )
            self.args.log.finalize()
            sys.exit(19)

        if self.args.mode == "natural":
            selected_indices = self.select_natural_cluster_representatives(
                coverage_result,
                selectable_indices,
                target_points,
            )
            if selected_indices is None:
                self.args.log.write(
                    "\nx WARNING. Natural selection mode could not use a valid natural "
                    "clustering partition. Falling back to representative mode."
                )
                selected_indices = self.select_coverage_representatives(
                    selection_data,
                    selectable_indices,
                    target_points,
                )
        else:
            selected_indices = self.select_coverage_representatives(
                selection_data,
                selectable_indices,
                target_points,
            )
        selected_indices = sorted(set(selected_indices))
        selected_ranks = {}
        for rank, index in enumerate(selected_indices, start=1):
            selected_ranks[index] = rank

        if not automatic_points:
            self.args.log.write("\no Coverage-based point selection")
            self.args.log.write(f"   - Requested points: {self.args.n_points}")
            self.args.log.write(f"   - Selected points: {len(selected_indices)}")
            self.args.log.write(
                f"   - Selection mode: {self.args.mode}"
            )
        coverage_result["selected_indices"] = selected_indices
        coverage_result["target_points"] = target_points
        coverage_result["automatic_points"] = automatic_points
        selected_points = selection_data[selected_indices]
        nearest_selected_model = NearestNeighbors(n_neighbors=1)
        nearest_selected_model.fit(selected_points)
        _, nearest_selected_positions = nearest_selected_model.kneighbors(selection_data)
        coverage_result["selection_region_labels"] = nearest_selected_positions[:, 0].astype(int)
        avg_gap_selected = self.compute_mean_nearest_selected_distance(
            selection_data,
            selected_points,
        )
        self.log_final_selection_quality(
            selection_data=selection_data,
            selected_indices=selected_indices,
            selected_points=selected_points,
            avg_gap_selected=avg_gap_selected,
        )

        return selected_indices, selected_ranks, {}

    def evaluate_existing_selection(self, coverage_result, descp_df):
        """
        Reuse an existing user-provided batch = 0 selection without recalculating representatives.
        """
        batch_values = pd.to_numeric(descp_df["batch"], errors="coerce")
        selected_indices = sorted(descp_df.index[batch_values == 0].tolist())

        if len(selected_indices) == 0:
            self.args.log.write(
                "\nx WARNING. No rows with batch = 0 were found, so --evaluate cannot assess an existing selection."
            )
            self.args.log.finalize()
            sys.exit(1)

        selection_data = coverage_result["selection_data"]
        selected_ranks = {index: rank for rank, index in enumerate(selected_indices, start=1)}
        coverage_result["selected_indices"] = selected_indices
        coverage_result["target_points"] = len(selected_indices)
        coverage_result["automatic_points"] = False

        selected_points = selection_data[selected_indices]
        nearest_selected_model = NearestNeighbors(n_neighbors=1)
        nearest_selected_model.fit(selected_points)
        _, nearest_selected_positions = nearest_selected_model.kneighbors(selection_data)
        coverage_result["selection_region_labels"] = nearest_selected_positions[:, 0].astype(int)

        avg_gap_selected = self.compute_mean_nearest_selected_distance(
            selection_data,
            selected_points,
        )
        self.args.log.write("\no Evaluating existing selection")
        self.args.log.write(f"   - Rows selected by the user (batch = 0): {len(selected_indices)}")
        self.args.log.write("   - Representative reselection: skipped (--evaluate)")
        self.log_final_selection_quality(
            selection_data=selection_data,
            selected_indices=selected_indices,
            selected_points=selected_points,
            avg_gap_selected=avg_gap_selected,
        )

        return selected_indices, selected_ranks, {}

    def get_auto_budget_candidates(self, n_selectable):
        """
        Build candidate exploration budgets for automatic coverage scanning.
        """

        if n_selectable < 200:
            max_points = min(
                int(self.args.cluster_auto_budget_max_points),
                int(self.args.cluster_auto_budget_sqrt_factor * np.sqrt(n_selectable)),
                n_selectable,
            )
            max_points = min(max_points, max(3, int(np.ceil(0.50 * n_selectable))))
        elif n_selectable < 10000:
            max_points = min(
                int(self.args.cluster_auto_budget_max_points),
                max(10, int(np.ceil(0.10 * n_selectable))),
                300,
                n_selectable,
            )
        elif n_selectable < 50000:
            max_points = min(
                int(self.args.cluster_auto_budget_max_points),
                max(500, int(np.ceil(0.05 * n_selectable))),
                500,
                n_selectable,
            )
        else:
            max_points = min(
                int(self.args.cluster_auto_budget_max_points),
                max(500, int(np.ceil(0.02 * n_selectable))),
                700,
                n_selectable,
            )

        adaptive_min_points = max(1, int(np.ceil(0.01 * n_selectable)))
        min_points = min(
            int(self.args.cluster_auto_budget_min_points),
            adaptive_min_points,
            n_selectable,
        )
        if max_points <= min_points:
            return [min_points]
        if n_selectable < 200:
            return list(range(min_points, max_points + 1))
        if n_selectable < 500:
            return list(range(min_points, max_points + 1))

        if n_selectable < 10000:
            budget_segments = [(100, 10), (200, 20), (max_points, 25)]
        elif n_selectable < 50000:
            budget_segments = [(100, 10), (300, 25), (max_points, 50)]
        else:
            budget_segments = [(100, 10), (300, 25), (max_points, 100)]

        candidates = {min_points}
        current_budget = min_points
        last_step = 10
        for segment_limit, step_size in budget_segments:
            segment_limit = min(segment_limit, max_points)
            if current_budget >= segment_limit:
                continue
            next_budget = current_budget + step_size
            while next_budget <= segment_limit:
                candidates.add(next_budget)
                current_budget = next_budget
                next_budget += step_size
            last_step = step_size
        last_regular = max(candidates)
        if max_points - last_regular >= max(1, int(np.ceil(0.5 * last_step))):
            candidates.add(max_points)
        return sorted(candidate for candidate in candidates if candidate > 0)

    def estimate_auto_coverage_budget(self, scaled_data, selectable_indices):
        """
        Estimate n_points by scanning coverage improvement over candidate budgets.
        """

        n_selectable = len(selectable_indices)
        candidates = self.get_auto_budget_candidates(n_selectable)
        coarse_budgets = list(candidates)
        sample_size = min(
            int(self.args.cluster_auto_budget_coverage_sample_size),
            n_selectable,
        )
        rng = np.random.default_rng(self.args.seed_clustered)
        if sample_size < n_selectable:
            sampled_local_indices = rng.choice(
                np.arange(n_selectable),
                size=sample_size,
                replace=False,
            )
            coverage_indices = selectable_indices[sampled_local_indices]
        else:
            coverage_indices = selectable_indices

        coverage_data = scaled_data[coverage_indices]
        umap_area_data = scaled_data[selectable_indices]
        umap_area_context = self.prepare_auto_budget_umap_area_context(umap_area_data)

        threshold = float(self.args.cluster_auto_budget_marginal_gain_threshold)
        min_umap_area = float(self.args.cluster_auto_budget_min_umap_area)
        lookahead_count = int(self.args.cluster_auto_budget_lookahead)
        evaluated_budgets = {}
        recommendation_mode = None

        self.args.log.write("\no Auto exploration budget scan")
        self.args.log.write(
            "   - avg_gap: how far, on average, each molecule is from its nearest selected "
            "molecule. Lower is better."
        )
        self.args.log.write(
            "   - marginal_gain: how much extra coverage is gained by adding more selected "
            "molecules. Small values mean extra experiments add little."
        )
        self.args.log.write(
            "   - umap_area: 2D map area covered by the selected molecules compared with "
            "the full dataset area, reported as 0-100%; this is a visual diagnostic."
        )
        if self.args.mode == "representative":
            self.args.log.write(
                "   - Selection mode: representative; ALMOS selects the real molecule "
                "nearest to each MiniBatchKMeans prototype centroid."
            )
        elif self.args.mode == "exploratory":
            self.args.log.write(
                "   - Selection mode: exploratory; ALMOS generates extra prototype "
                "candidates and keeps the most mutually distant representatives."
            )
        else:
            self.args.log.write(
                "   - Selection mode: natural; this scan estimates the number of points, "
                "then final molecules are allocated across natural clusters."
            )
        if n_selectable < 200:
            self.args.log.write(
                "   - Small-dataset rule: for fewer than 200 molecules, ALMOS evaluates "
                "all integer budgets and recommends the first visually broad local slowdown."
            )
        elif n_selectable < 500:
            self.args.log.write(
                "   - Medium-dataset rule: for 200-499 molecules, ALMOS uses proportional "
                "candidate budgets and avoids chasing the best avg_gap at the largest "
                "tested budget."
            )
        else:
            self.args.log.write(
                "   - Sweet-spot rule: recommend the first budget with broad UMAP area and "
                "no strong avg_gap improvement in the next evaluated budgets."
            )

        def format_umap_area(umap_area):
            return f"{100 * umap_area:.1f}%" if umap_area is not None else "NA"

        def log_scan_table_header():
            self.args.log.write("")
            self.args.log.write("   Exploration scan")
            self.args.log.write("   +----------+----------+---------------+-----------+")
            self.args.log.write("   | n_points | avg_gap  | marginal_gain | umap_area |")
            self.args.log.write("   +----------+----------+---------------+-----------+")

        def log_scan_table_row(budget, metrics, previous_distance):
            current_distance = metrics["avg_gap"]
            if previous_distance is None or previous_distance <= 0:
                marginal_gain = None
                marginal_text = "-"
            else:
                marginal_gain = (previous_distance - current_distance) / previous_distance
                marginal_text = f"{100 * marginal_gain:.1f}%"
            metrics["marginal_gain"] = marginal_gain
            self.args.log.write(
                f"   | {budget:<8} | {current_distance:<8.6f} | "
                f"{marginal_text:<13} | "
                f"{format_umap_area(metrics.get('umap_area_coverage')):<9} |"
            )
            return current_distance

        def evaluate_budget(budget):
            if budget in evaluated_budgets:
                return evaluated_budgets[budget]
            selected_indices = self.select_coverage_representatives(
                scaled_data,
                selectable_indices,
                budget,
                log_selection=False,
            )
            selected_points = scaled_data[selected_indices]
            nearest_distances = self.compute_nearest_selected_distances(
                coverage_data,
                selected_points,
            )
            mean_distance = float(np.mean(nearest_distances))
            umap_area_coverage = self.compute_umap_area_coverage(
                selected_points,
                umap_area_context,
            )
            budget_metrics = {
                "avg_gap": mean_distance,
                "umap_area_coverage": umap_area_coverage,
                "selected_indices": selected_indices,
            }
            evaluated_budgets[budget] = budget_metrics
            return budget_metrics

        def get_marginal_gain(previous_budget, current_budget):
            previous_distance = evaluated_budgets[previous_budget]["avg_gap"]
            current_distance = evaluated_budgets[current_budget]["avg_gap"]
            return (
                (previous_distance - current_distance) / previous_distance
                if previous_distance > 0
                else 0.0
            )

        def get_future_gains(budgets, budget):
            sorted_budgets = sorted(budgets)
            budget_position = sorted_budgets.index(budget)
            future_budgets = sorted_budgets[
                budget_position + 1 : budget_position + 1 + lookahead_count
            ]
            if not future_budgets:
                return 0.0, 0.0
            current_gap = evaluated_budgets[budget]["avg_gap"]
            first_gain = 0.0
            second_gain = 0.0
            if current_gap > 0:
                first_gap = evaluated_budgets[future_budgets[0]]["avg_gap"]
                first_gain = (current_gap - first_gap) / current_gap
                if len(future_budgets) > 1:
                    second_gap = evaluated_budgets[future_budgets[1]]["avg_gap"]
                    second_gain = (current_gap - second_gap) / current_gap
            return first_gain, second_gain

        def get_required_future_gain(current_budget, future_budget):
            if n_selectable < 100:
                extra_steps = max(1, future_budget - current_budget)
                return 0.05 * extra_steps
            extra_points = max(1, future_budget - current_budget)
            return 0.005 * extra_points

        def budget_satisfies_stop_rule(budget, sorted_available_budgets):
            if budget < min_recommendable_budget:
                return False
            metrics = evaluated_budgets[budget]
            umap_area = metrics.get("umap_area_coverage")
            umap_ok = umap_area is None or umap_area >= min_umap_area
            first_future_gain, second_future_gain = get_future_gains(
                sorted_available_budgets,
                budget,
            )
            budget_position = sorted_available_budgets.index(budget)
            future_budgets = sorted_available_budgets[
                budget_position + 1 : budget_position + 1 + lookahead_count
            ]
            first_required_gain = (
                get_required_future_gain(budget, future_budgets[0])
                if future_budgets
                else threshold
            )
            second_required_gain = (
                get_required_future_gain(budget, future_budgets[1])
                if len(future_budgets) > 1
                else 2.0 * threshold
            )
            future_gain_ok = (
                first_future_gain < first_required_gain
                and second_future_gain < second_required_gain
            )
            return umap_ok and future_gain_ok

        sorted_budgets = sorted(coarse_budgets)
        min_recommendable_budget = (
            max(3, int(np.ceil(0.05 * n_selectable)))
            if n_selectable < 100
            else sorted_budgets[0]
        )

        large_dataset_early_stop = n_selectable >= 10000
        recommended_budget = None
        if large_dataset_early_stop:
            log_scan_table_header()
            previous_coarse_distance = None
            for budget_index, budget in enumerate(sorted_budgets):
                metrics = evaluate_budget(budget)
                previous_coarse_distance = log_scan_table_row(
                    budget,
                    metrics,
                    previous_coarse_distance,
                )
                candidate_index = budget_index - lookahead_count
                if candidate_index >= 0:
                    candidate_budget = sorted_budgets[candidate_index]
                    available_budgets = sorted_budgets[: budget_index + 1]
                    if budget_satisfies_stop_rule(candidate_budget, available_budgets):
                        recommended_budget = candidate_budget
                        recommendation_mode = "local_slowdown"
                        evaluated_budgets[candidate_budget]["sweet_spot_valid"] = True
                        break
            self.args.log.write("   +----------+----------+---------------+-----------+")
            sorted_budgets = sorted(evaluated_budgets)
        else:
            log_scan_table_header()
            previous_coarse_distance = None
            for budget in sorted_budgets:
                metrics = evaluate_budget(budget)
                previous_coarse_distance = log_scan_table_row(
                    budget,
                    metrics,
                    previous_coarse_distance,
                )
            self.args.log.write("   +----------+----------+---------------+-----------+")
            for budget in sorted_budgets:
                if budget_satisfies_stop_rule(budget, sorted_budgets):
                    recommended_budget = budget
                    recommendation_mode = "local_slowdown"
                    evaluated_budgets[budget]["sweet_spot_valid"] = True
                    break

        if recommended_budget is None:
            umap_eligible_budgets = [
                budget
                for budget in sorted_budgets
                if evaluated_budgets[budget].get("umap_area_coverage") is None
                or evaluated_budgets[budget]["umap_area_coverage"] >= min_umap_area
            ]
            candidate_budgets = umap_eligible_budgets or sorted_budgets
            recommended_budget = min(
                candidate_budgets,
                key=lambda budget: evaluated_budgets[budget]["avg_gap"],
            )
            recommendation_mode = (
                "best_gap_with_umap" if umap_eligible_budgets else "best_gap"
            )

        plateau_plot_path = self.save_auto_budget_plateau_plot(
            evaluated_budgets,
            coarse_budgets,
            [],
            recommended_budget,
        )

        marginal_below_threshold_seen = any(
            get_marginal_gain(previous_budget, budget) < threshold
            for previous_budget, budget in zip(sorted_budgets, sorted_budgets[1:])
        )

        previous_budget_for_recommended = None
        for budget in sorted_budgets:
            if budget < recommended_budget:
                previous_budget_for_recommended = budget

        self._coverage_auto_budget_context = {
            "recommended_budget": recommended_budget,
            "previous_budget": previous_budget_for_recommended,
            "threshold": threshold,
            "marginal_below_threshold_seen": marginal_below_threshold_seen,
            "recommendation_scope": "coarse",
            "min_umap_area": min_umap_area,
            "lookahead_count": lookahead_count,
            "evaluated_budget_metrics": dict(evaluated_budgets),
            "umap_area_context": umap_area_context,
        }

        self.args.log.write("")
        self.args.log.write(
            f"   - Exploration scan range: {min(coarse_budgets)} to {max(coarse_budgets)} points"
        )
        self.args.log.write("   - Scan mode: single exploration scan")
        self.args.log.write(
            f"   - Recommendation rule: require umap_area >= {100 * min_umap_area:.0f}% "
            "when available, and keep scanning when the next evaluated budgets improve "
            "avg_gap by enough to justify the extra points."
        )
        if n_selectable < 100:
            self.args.log.write(
                "   - Small-dataset rule: each extra selected molecule must improve "
                "avg_gap by at least 5%; across two extra molecules the required "
                "cumulative improvement is 10%."
            )
        else:
            self.args.log.write(
                "   - Large-dataset rule: the required avg_gap improvement is 0.5% "
                "per added point."
            )
        self.args.log.write("")
        self.args.log.write(f"   - Recommended coverage budget: {recommended_budget} points")
        if plateau_plot_path is not None:
            self.args.log.write(
                f"   - Avg-gap plateau diagnostic plot: {plateau_plot_path}"
            )
        if recommendation_mode == "local_slowdown":
            reason = (
                "the scan found the first budget with broad UMAP area and no strong "
                "avg_gap improvement in the next evaluated budgets."
            )
        elif recommendation_mode == "best_gap_with_umap":
            reason = (
                "no local slowdown satisfied the stopping rule; using the evaluated "
                "budget with the lowest avg_gap among budgets with enough UMAP area."
            )
        else:
            reason = (
                "no local slowdown satisfied the stopping rule; using the evaluated "
                "budget with the lowest avg_gap."
            )
        self.args.log.write(f"   - Reason: {reason}")
        return recommended_budget

    def compute_nearest_selected_distances(self, coverage_data, selected_points):
        """
        Compute distances from each row to the nearest selected representative.
        """

        nearest_neighbors = NearestNeighbors(n_neighbors=1)
        nearest_neighbors.fit(selected_points)
        distances, _ = nearest_neighbors.kneighbors(coverage_data)
        return distances[:, 0]

    def compute_mean_nearest_selected_distance(self, coverage_data, selected_points):
        """
        Compute mean distance from coverage points to the nearest selected point.
        """

        distances = self.compute_nearest_selected_distances(coverage_data, selected_points)
        return float(np.mean(distances))

    def prepare_auto_budget_umap_area_context(self, coverage_data):
        """
        Build a lightweight UMAP map used only to report visual area coverage.
        """

        try:
            import umap
        except Exception:
            return {"available": False, "warning": "UMAP is not installed"}

        if len(coverage_data) < 4:
            return {"available": False, "warning": "UMAP requires at least four points"}

        n_neighbors = min(30, max(5, int(round(np.sqrt(len(coverage_data))))))
        n_neighbors = min(n_neighbors, len(coverage_data) - 1)
        if n_neighbors < 2:
            return {"available": False, "warning": "UMAP could not build a valid neighbor graph"}

        try:
            reducer = umap.UMAP(
                n_components=2,
                n_neighbors=n_neighbors,
                min_dist=0.1,
                metric="euclidean",
                random_state=self.args.seed_clustered,
            )
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="n_jobs value .* overridden to 1 by setting random_state.*",
                    category=UserWarning,
                )
                embedding = reducer.fit_transform(coverage_data)
        except Exception as exc:
            return {"available": False, "warning": f"UMAP failed: {exc}"}

        dataset_area = self.compute_convex_hull_area_2d(embedding)
        if dataset_area <= 0:
            return {"available": False, "warning": "UMAP map area could not be computed"}

        return {
            "available": True,
            "reducer": reducer,
            "embedding": embedding,
            "dataset_area": dataset_area,
            "source_count": len(coverage_data),
        }

    def compute_convex_hull_area_2d(self, points):
        """
        Compute the 2D convex-hull polygon area with a monotonic chain hull.
        """

        hull = self.compute_convex_hull_points_2d(points)
        if len(hull) < 3:
            return 0.0

        area = 0.0
        for index, point in enumerate(hull):
            next_point = hull[(index + 1) % len(hull)]
            area += point[0] * next_point[1] - next_point[0] * point[1]
        return float(abs(area) / 2.0)

    def compute_convex_hull_points_2d(self, points):
        """
        Return the 2D convex-hull vertices with a monotonic chain hull.
        """

        if len(points) < 3:
            return np.empty((0, 2), dtype=float)

        unique_points = sorted(set((float(x), float(y)) for x, y in points))
        if len(unique_points) < 3:
            return np.empty((0, 2), dtype=float)

        def cross(origin, point_a, point_b):
            return (
                (point_a[0] - origin[0]) * (point_b[1] - origin[1])
                - (point_a[1] - origin[1]) * (point_b[0] - origin[0])
            )

        lower = []
        for point in unique_points:
            while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
                lower.pop()
            lower.append(point)

        upper = []
        for point in reversed(unique_points):
            while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
                upper.pop()
            upper.append(point)

        hull = lower[:-1] + upper[:-1]
        if len(hull) < 3:
            return np.empty((0, 2), dtype=float)
        return np.asarray(hull, dtype=float)

    def point_inside_polygon_2d(self, point, polygon):
        """
        Ray-casting point-in-polygon test for 2D coverage diagnostics.
        """

        if len(polygon) < 3:
            return False

        x_coord, y_coord = float(point[0]), float(point[1])
        inside = False
        previous_x, previous_y = polygon[-1]
        tolerance = 1.0e-12
        for current_x, current_y in polygon:
            edge_cross = (
                (x_coord - previous_x) * (current_y - previous_y)
                - (y_coord - previous_y) * (current_x - previous_x)
            )
            on_segment = (
                abs(edge_cross) <= tolerance
                and min(previous_x, current_x) - tolerance
                <= x_coord
                <= max(previous_x, current_x) + tolerance
                and min(previous_y, current_y) - tolerance
                <= y_coord
                <= max(previous_y, current_y) + tolerance
            )
            if on_segment:
                return True

            intersects = (current_y > y_coord) != (previous_y > y_coord)
            if intersects:
                x_intersection = (
                    (previous_x - current_x)
                    * (y_coord - current_y)
                    / (previous_y - current_y + tolerance)
                    + current_x
                )
                if x_coord < x_intersection:
                    inside = not inside
            previous_x, previous_y = current_x, current_y
        return inside

    def compute_2d_map_coverage_metrics(self, dataset_embedding, selected_embedding):
        """
        Report 2D area coverage and grid filling for selected molecules.
        """

        if len(dataset_embedding) < 3 or len(selected_embedding) < 3:
            return {
                "area_coverage": None,
                "map_filling": None,
                "grid_coverage": None,
                "visual_score": None,
                "grid_size": None,
            }

        dataset_area = self.compute_convex_hull_area_2d(dataset_embedding)
        selected_area = self.compute_convex_hull_area_2d(selected_embedding)
        area_coverage = (
            float(np.clip(selected_area / dataset_area, 0.0, 1.0))
            if dataset_area > 0
            else None
        )

        selected_hull = self.compute_convex_hull_points_2d(selected_embedding)
        if len(selected_hull) < 3:
            return {
                "area_coverage": area_coverage,
                "map_filling": None,
                "grid_coverage": None,
                "visual_score": None,
                "grid_size": None,
            }

        grid_size = int(
            np.clip(
                round(
                    np.sqrt(len(selected_embedding))
                    + 0.15 * np.sqrt(len(dataset_embedding))
                ),
                6,
                30,
            )
        )
        x_min, y_min = np.min(dataset_embedding, axis=0)
        x_max, y_max = np.max(dataset_embedding, axis=0)
        x_span = x_max - x_min
        y_span = y_max - y_min
        if x_span <= 0 or y_span <= 0:
            return {
                "area_coverage": area_coverage,
                "map_filling": None,
                "grid_coverage": None,
                "visual_score": None,
                "grid_size": grid_size,
            }

        x_padding = 0.001 * x_span
        y_padding = 0.001 * y_span
        x_edges = np.linspace(x_min - x_padding, x_max + x_padding, grid_size + 1)
        y_edges = np.linspace(y_min - y_padding, y_max + y_padding, grid_size + 1)

        def occupied_cell(point):
            x_position = int(np.searchsorted(x_edges, point[0], side="right") - 1)
            y_position = int(np.searchsorted(y_edges, point[1], side="right") - 1)
            x_position = min(max(x_position, 0), len(x_edges) - 2)
            y_position = min(max(y_position, 0), len(y_edges) - 2)
            return x_position, y_position

        selected_cells = {occupied_cell(point) for point in selected_embedding}
        dataset_cells = {occupied_cell(point) for point in dataset_embedding}
        dataset_cells_inside_selected_area = {
            occupied_cell(point)
            for point in dataset_embedding
            if self.point_inside_polygon_2d(point, selected_hull)
        }
        if not dataset_cells_inside_selected_area:
            map_filling = None
        else:
            selected_populated_cells = selected_cells.intersection(
                dataset_cells_inside_selected_area
            )
            map_filling = (
                len(selected_populated_cells) / len(selected_embedding)
                if len(selected_embedding) > 0
                else None
            )
        if map_filling is not None:
            map_filling = float(np.clip(map_filling, 0.0, 1.0))
        grid_coverage = (
            len(selected_cells.intersection(dataset_cells)) / len(dataset_cells)
            if dataset_cells
            else None
        )
        if grid_coverage is not None:
            grid_coverage = float(np.clip(grid_coverage, 0.0, 1.0))
        if (
            area_coverage is not None
            and grid_coverage is not None
            and map_filling is not None
        ):
            visual_score = (
                0.50 * area_coverage
                + 0.30 * grid_coverage
                + 0.20 * map_filling
            )
            visual_score = float(np.clip(10.0 * visual_score, 0.0, 10.0))
        else:
            visual_score = None

        return {
            "area_coverage": area_coverage,
            "map_filling": map_filling,
            "grid_coverage": grid_coverage,
            "visual_score": visual_score,
            "grid_size": grid_size,
        }

    def get_2d_map_grid_details(self, dataset_embedding, selected_embedding):
        """
        Return area/filling details used to plot 2D selection diagnostics.
        """

        metrics = self.compute_2d_map_coverage_metrics(
            dataset_embedding,
            selected_embedding,
        )
        if len(dataset_embedding) < 3 or len(selected_embedding) < 3:
            return metrics

        selected_hull = self.compute_convex_hull_points_2d(selected_embedding)
        dataset_hull = self.compute_convex_hull_points_2d(dataset_embedding)
        if len(selected_hull) < 3:
            metrics.update(
                {
                    "dataset_hull": dataset_hull,
                    "selected_hull": selected_hull,
                    "dataset_cells_inside_selected_area": set(),
                    "selected_cells": set(),
                    "x_edges": None,
                    "y_edges": None,
                }
            )
            return metrics

        grid_size = metrics.get("grid_size")
        if grid_size is None:
            return metrics

        x_min, y_min = np.min(dataset_embedding, axis=0)
        x_max, y_max = np.max(dataset_embedding, axis=0)
        x_span = x_max - x_min
        y_span = y_max - y_min
        if x_span <= 0 or y_span <= 0:
            return metrics
        x_padding = 0.001 * x_span
        y_padding = 0.001 * y_span
        x_edges = np.linspace(x_min - x_padding, x_max + x_padding, grid_size + 1)
        y_edges = np.linspace(y_min - y_padding, y_max + y_padding, grid_size + 1)
        if len(x_edges) < 2 or len(y_edges) < 2:
            return metrics

        def occupied_cell(point):
            x_position = int(np.searchsorted(x_edges, point[0], side="right") - 1)
            y_position = int(np.searchsorted(y_edges, point[1], side="right") - 1)
            x_position = min(max(x_position, 0), len(x_edges) - 2)
            y_position = min(max(y_position, 0), len(y_edges) - 2)
            return x_position, y_position

        selected_cells = {occupied_cell(point) for point in selected_embedding}
        dataset_cells = {occupied_cell(point) for point in dataset_embedding}
        dataset_cells_inside_selected_area = {
            occupied_cell(point)
            for point in dataset_embedding
            if self.point_inside_polygon_2d(point, selected_hull)
        }
        metrics.update(
            {
                "dataset_hull": dataset_hull,
                "selected_hull": selected_hull,
                "dataset_cells": dataset_cells,
                "dataset_cells_inside_selected_area": dataset_cells_inside_selected_area,
                "selected_cells": selected_cells,
                "x_edges": x_edges,
                "y_edges": y_edges,
            }
        )
        return metrics

    def save_selection_2d_diagnostic_images(
        self,
        selection_data,
        selected_indices,
        selected_points,
        budget_context,
    ):
        """
        Save PCA/UMAP final-selection area and selected-dispersion diagnostic images.
        """

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.ticker import MaxNLocator
        except Exception as exc:
            self.args.log.write(
                f"\nx WARNING. 2D selection diagnostic images could not be created: {exc}"
            )
            return {}

        output_folder = "batch_0/selection_diagnostics"
        os.makedirs(output_folder, exist_ok=True)
        saved_paths = {}

        pca_embedding = self.compute_pca_2d_embedding(selection_data)
        pca_selected_embedding = pca_embedding[selected_indices]
        pca_output_folder = os.path.join(output_folder, "PCA")
        os.makedirs(pca_output_folder, exist_ok=True)
        pca_paths = self.save_single_2d_diagnostic_images(
            "PCA",
            pca_embedding,
            pca_selected_embedding,
            pca_output_folder,
            plt,
        )
        if pca_paths:
            saved_paths["PCA"] = pca_paths

        umap_context = self.prepare_final_umap_map_context(
            selection_data,
            budget_context,
            selected_indices,
        )
        if umap_context.get("available"):
            try:
                umap_selected_embedding = umap_context["embedding"][selected_indices]
                umap_output_folder = os.path.join(output_folder, "UMAP")
                os.makedirs(umap_output_folder, exist_ok=True)
                umap_paths = self.save_single_2d_diagnostic_images(
                    "UMAP",
                    umap_context["embedding"],
                    umap_selected_embedding,
                    umap_output_folder,
                    plt,
                )
                if umap_paths:
                    saved_paths["UMAP"] = umap_paths
            except Exception:
                pass

        return saved_paths

    def save_single_2d_diagnostic_images(
        self,
        embedding_name,
        dataset_embedding,
        selected_embedding,
        output_folder,
        plt,
    ):
        """
        Save separate PCA/UMAP area and selected-dispersion diagnostic images.
        """

        details = self.get_2d_map_grid_details(dataset_embedding, selected_embedding)
        area_text = self.format_fraction_percent(details.get("area_coverage"))
        filling_text = self.format_fraction_percent(details.get("map_filling"))
        grid_coverage_text = self.format_fraction_percent(details.get("grid_coverage"))
        selected_hull = details.get("selected_hull")
        dataset_hull = details.get("dataset_hull")
        x_edges = details.get("x_edges")
        y_edges = details.get("y_edges")
        dataset_cells = details.get("dataset_cells") or set()
        selected_cells = details.get("selected_cells") or set()
        saved_paths = {}

        fig, ax = plt.subplots(figsize=(7.2, 5.2), dpi=160)
        ax.scatter(
            dataset_embedding[:, 0],
            dataset_embedding[:, 1],
            s=8,
            c="#CBD5E1",
            edgecolors="none",
            alpha=0.75,
            label="Unselected molecules",
            zorder=2,
        )
        if dataset_hull is not None and len(dataset_hull) >= 3:
            closed_dataset_hull = np.vstack([dataset_hull, dataset_hull[0]])
            ax.plot(
                closed_dataset_hull[:, 0],
                closed_dataset_hull[:, 1],
                color="#64748B",
                linewidth=1.2,
                linestyle="--",
                label="Full map area",
                zorder=3,
            )
        if selected_hull is not None and len(selected_hull) >= 3:
            closed_selected_hull = np.vstack([selected_hull, selected_hull[0]])
            ax.fill(
                closed_selected_hull[:, 0],
                closed_selected_hull[:, 1],
                color="#16A34A",
                alpha=0.16,
                label="Selected area",
                zorder=4,
            )
            ax.plot(
                closed_selected_hull[:, 0],
                closed_selected_hull[:, 1],
                color="#15803D",
                linewidth=1.7,
                zorder=5,
            )
        ax.scatter(
            selected_embedding[:, 0],
            selected_embedding[:, 1],
            s=36,
            c="#16A34A",
            edgecolors="#111111",
            linewidths=0.45,
            label="Selected molecules",
            zorder=6,
        )
        ax.text(
            0.02,
            0.98,
            f"Area coverage: {area_text}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="#14532D",
            bbox={
                "boxstyle": "round,pad=0.28",
                "facecolor": "#DCFCE7",
                "edgecolor": "#16A34A",
                "alpha": 0.92,
            },
            zorder=7,
        )
        ax.set_title(f"{embedding_name} area coverage")
        ax.set_xlabel(f"{embedding_name} 1")
        ax.set_ylabel(f"{embedding_name} 2")
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#111111")
            spine.set_linewidth(0.9)
        ax.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()
        area_path = os.path.join(
            output_folder,
            f"{embedding_name.lower()}_area_coverage.png",
        )
        fig.savefig(area_path)
        plt.close(fig)
        saved_paths["area"] = area_path

        fig, ax = plt.subplots(figsize=(7.2, 5.2), dpi=160)
        if x_edges is not None and y_edges is not None:
            from matplotlib.patches import Rectangle

            selected_dataset_cells = selected_cells.intersection(dataset_cells)
            for x_index, y_index in sorted(dataset_cells):
                ax.add_patch(
                    Rectangle(
                        (x_edges[x_index], y_edges[y_index]),
                        x_edges[x_index + 1] - x_edges[x_index],
                        y_edges[y_index + 1] - y_edges[y_index],
                        facecolor="#DBEAFE",
                        edgecolor="#93C5FD",
                        linewidth=0.35,
                        alpha=0.30,
                        zorder=0,
                    )
                )
            for x_index, y_index in sorted(selected_dataset_cells):
                ax.add_patch(
                    Rectangle(
                        (x_edges[x_index], y_edges[y_index]),
                        x_edges[x_index + 1] - x_edges[x_index],
                        y_edges[y_index + 1] - y_edges[y_index],
                        facecolor="#22C55E",
                        edgecolor="#15803D",
                        linewidth=0.45,
                        alpha=0.32,
                        zorder=1,
                    )
                )
        ax.scatter(
            dataset_embedding[:, 0],
            dataset_embedding[:, 1],
            s=8,
            c="#CBD5E1",
            edgecolors="none",
            alpha=0.65,
            label="Unselected molecules",
            zorder=2,
        )
        ax.scatter(
            selected_embedding[:, 0],
            selected_embedding[:, 1],
            s=36,
            c="#16A34A",
            edgecolors="#111111",
            linewidths=0.45,
            label="Selected molecules",
            zorder=3,
        )
        ax.text(
            0.02,
            0.98,
            f"grid_coverage: {grid_coverage_text}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="#14532D",
            bbox={
                "boxstyle": "round,pad=0.28",
                "facecolor": "#DCFCE7",
                "edgecolor": "#16A34A",
                "alpha": 0.92,
            },
            zorder=4,
        )
        ax.set_title(f"{embedding_name} grid coverage")
        ax.set_xlabel(f"{embedding_name} 1")
        ax.set_ylabel(f"{embedding_name} 2")
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#111111")
            spine.set_linewidth(0.9)
        ax.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()
        grid_path = os.path.join(
            output_folder,
            f"{embedding_name.lower()}_grid_coverage.png",
        )
        fig.savefig(grid_path)
        plt.close(fig)
        saved_paths["grid"] = grid_path

        fig, ax = plt.subplots(figsize=(7.2, 5.2), dpi=160)
        if x_edges is not None and y_edges is not None:
            for x_value in x_edges[1:-1]:
                ax.axvline(
                    x_value,
                    color="#64748B",
                    linewidth=0.40,
                    alpha=0.24,
                    zorder=0,
                )
            for y_value in y_edges[1:-1]:
                ax.axhline(
                    y_value,
                    color="#64748B",
                    linewidth=0.40,
                    alpha=0.24,
                    zorder=0,
                )
        ax.scatter(
            dataset_embedding[:, 0],
            dataset_embedding[:, 1],
            s=8,
            c="#CBD5E1",
            edgecolors="none",
            alpha=0.70,
            label="Unselected molecules",
            zorder=1,
        )
        representative_mask = np.ones(len(selected_embedding), dtype=bool)
        repeated_cells = set()
        if x_edges is not None and y_edges is not None and len(selected_embedding) > 0:
            selected_point_cells = []
            for point in selected_embedding:
                x_position = int(np.searchsorted(x_edges, point[0], side="right") - 1)
                y_position = int(np.searchsorted(y_edges, point[1], side="right") - 1)
                x_position = min(max(x_position, 0), len(x_edges) - 2)
                y_position = min(max(y_position, 0), len(y_edges) - 2)
                selected_point_cells.append((x_position, y_position))
            representative_mask = np.zeros(len(selected_embedding), dtype=bool)
            first_position_by_cell = {}
            for position, cell in enumerate(selected_point_cells):
                if cell not in first_position_by_cell:
                    first_position_by_cell[cell] = position
                    representative_mask[position] = True
                else:
                    repeated_cells.add(cell)

        if x_edges is not None and y_edges is not None and repeated_cells:
            from matplotlib.patches import Rectangle

            for x_index, y_index in sorted(repeated_cells):
                ax.add_patch(
                    Rectangle(
                        (x_edges[x_index], y_edges[y_index]),
                        x_edges[x_index + 1] - x_edges[x_index],
                        y_edges[y_index + 1] - y_edges[y_index],
                        facecolor="#FDBA74",
                        edgecolor="#F97316",
                        linewidth=0.8,
                        alpha=0.18,
                        zorder=1,
                    )
                )

        if np.any(representative_mask):
            ax.scatter(
                selected_embedding[representative_mask, 0],
                selected_embedding[representative_mask, 1],
                s=38,
                c="#16A34A",
                edgecolors="#111111",
                linewidths=0.45,
                label="Grid region representative",
                zorder=3,
            )
        repeated_mask = ~representative_mask
        if np.any(repeated_mask):
            ax.scatter(
                selected_embedding[repeated_mask, 0],
                selected_embedding[repeated_mask, 1],
                s=46,
                c="#F59E0B",
                edgecolors="#111111",
                linewidths=0.45,
                label="Repeated in same grid region",
                zorder=4,
            )
        ax.text(
            0.02,
            0.98,
            f"dispersion_score: {filling_text}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="#14532D",
            bbox={
                "boxstyle": "round,pad=0.28",
                "facecolor": "#DCFCE7",
                "edgecolor": "#16A34A",
                "alpha": 0.92,
            },
            zorder=5,
        )
        ax.set_title(f"{embedding_name} dispersion score")
        ax.set_xlabel(f"{embedding_name} 1")
        ax.set_ylabel(f"{embedding_name} 2")
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#111111")
            spine.set_linewidth(0.9)
        ax.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()
        dispersion_path = os.path.join(
            output_folder,
            f"{embedding_name.lower()}_dispersion_score.png",
        )
        fig.savefig(dispersion_path)
        plt.close(fig)
        saved_paths["dispersion"] = dispersion_path

        return saved_paths

    def compute_umap_area_coverage(self, selected_points, umap_area_context):
        """
        Fraction of the dataset UMAP convex-hull area covered by selected molecules.
        """

        if not umap_area_context.get("available"):
            return None

        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="n_jobs value .* overridden to 1 by setting random_state.*",
                    category=UserWarning,
                )
                selected_embedding = umap_area_context["reducer"].transform(selected_points)
        except Exception:
            return None

        dataset_embedding = np.asarray(umap_area_context.get("embedding"), dtype=float)
        total_embedding = np.vstack([dataset_embedding, selected_embedding])
        dataset_area = self.compute_convex_hull_area_2d(total_embedding)
        if dataset_area <= 0:
            return None
        selected_area = self.compute_convex_hull_area_2d(selected_embedding)
        return float(np.clip(selected_area / dataset_area, 0.0, 1.0))

    def save_auto_budget_plateau_plot(
        self,
        evaluated_budgets,
        coarse_budgets,
        fine_window_budgets,
        recommended_budget,
    ):
        """
        Save an avg_gap plateau diagnostic plot for the automatic budget scan.
        """

        if not evaluated_budgets:
            return None

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.ticker import MaxNLocator
        except Exception as exc:
            self.args.log.write(
                f"\nx WARNING. Avg-gap plateau diagnostic plot could not be created: {exc}"
            )
            return None

        output_folder = "batch_0/selection_diagnostics"
        os.makedirs(output_folder, exist_ok=True)

        sorted_budgets = sorted(evaluated_budgets)
        avg_gaps = [
            evaluated_budgets[budget]["avg_gap"]
            for budget in sorted_budgets
        ]
        coarse_set = set(coarse_budgets)
        fine_set = set(fine_window_budgets)
        coarse_plot_budgets = [
            budget for budget in sorted_budgets if budget in coarse_set
        ]
        coarse_plot_gaps = [
            evaluated_budgets[budget]["avg_gap"]
            for budget in coarse_plot_budgets
        ]
        fine_plot_budgets = [
            budget for budget in sorted_budgets if budget in fine_set
        ]
        fine_plot_gaps = [
            evaluated_budgets[budget]["avg_gap"]
            for budget in fine_plot_budgets
        ]

        fig, ax_gap = plt.subplots(figsize=(8.2, 5.2), dpi=160)

        ax_gap.plot(
            sorted_budgets,
            avg_gaps,
            color="#2563EB",
            linewidth=2.0,
            marker="o",
            markersize=4,
            label="avg_gap",
        )
        if fine_plot_budgets:
            ax_gap.scatter(
                fine_plot_budgets,
                fine_plot_gaps,
                color="#F97316",
                edgecolors="#111111",
                linewidths=0.35,
                s=34,
                label="fine budgets",
                zorder=4,
            )
        if coarse_plot_budgets:
            ax_gap.scatter(
                coarse_plot_budgets,
                coarse_plot_gaps,
                color="#2563EB",
                edgecolors="#111111",
                linewidths=0.35,
                s=30,
                label="coarse budgets",
                zorder=3,
            )
        if recommended_budget in evaluated_budgets:
            ax_gap.axvline(
                recommended_budget,
                color="#111111",
                linewidth=1.3,
                linestyle="--",
                label="recommended budget",
            )

        ax_gap.set_title("Auto budget plateau diagnostic")
        ax_gap.set_xlabel("n_points")
        ax_gap.set_ylabel("avg_gap (lower is better)", color="#2563EB")
        ax_gap.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax_gap.grid(False)
        ax_gap.tick_params(axis="y", labelcolor="#2563EB")
        for spine in ax_gap.spines.values():
            spine.set_visible(True)
            spine.set_color("#111111")
            spine.set_linewidth(0.9)

        handles_gap, labels_gap = ax_gap.get_legend_handles_labels()
        ax_gap.legend(
            handles_gap,
            labels_gap,
            loc="best",
            frameon=False,
            fontsize=8,
        )
        fig.tight_layout()
        output_path = os.path.join(output_folder, "avg_gap_plateau.png")
        fig.savefig(output_path)
        plt.close(fig)
        return output_path

    def prepare_final_umap_map_context(
        self,
        selection_data,
        budget_context,
        selected_indices,
    ):
        """
        Build the final UMAP map on the full selection dataset.
        """

        return self.prepare_auto_budget_umap_area_context(selection_data)

    def compute_final_2d_coverage_metrics(
        self,
        selection_data,
        selected_indices,
        selected_points,
        budget_context,
    ):
        """
        Compute PCA/UMAP area and occupied-cell filling diagnostics for final reporting.
        """

        pca_embedding = self.compute_pca_2d_embedding(selection_data)
        pca_selected_embedding = pca_embedding[selected_indices]
        metrics = {
            "PCA": self.compute_2d_map_coverage_metrics(
                pca_embedding,
                pca_selected_embedding,
            )
        }

        umap_context = self.prepare_final_umap_map_context(
            selection_data,
            budget_context,
            selected_indices,
        )
        if umap_context.get("available"):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="n_jobs value .* overridden to 1 by setting random_state.*",
                        category=UserWarning,
                    )
                    umap_selected_embedding = umap_context["reducer"].transform(
                        selected_points
                    )
                metrics["UMAP"] = self.compute_2d_map_coverage_metrics(
                    umap_context["embedding"],
                    umap_selected_embedding,
                )
            except Exception:
                metrics["UMAP"] = {
                    "area_coverage": None,
                    "map_filling": None,
                    "grid_coverage": None,
                    "visual_score": None,
                    "grid_size": None,
                }
        else:
            metrics["UMAP"] = {
                "area_coverage": None,
                "map_filling": None,
                "grid_coverage": None,
                "visual_score": None,
                "grid_size": None,
            }
        return metrics

    def format_fraction_percent(self, value):
        """
        Format a fraction as a user-facing percentage.
        """

        return f"{100 * value:.1f}%" if value is not None else "NA"

    def format_visual_score(self, value):
        """
        Format the 2D visual exploration score on a 1-10 scale.
        """

        return f"{value:.1f}/10" if value is not None else "NA"

    def interpret_final_2d_coverage(self, map_metrics):
        """
        Provide a compact user-facing interpretation of the 2D coverage diagnostics.
        """

        area_values = [
            metrics.get("area_coverage")
            for metrics in map_metrics.values()
            if metrics.get("area_coverage") is not None
        ]
        filling_values = [
            metrics.get("map_filling")
            for metrics in map_metrics.values()
            if metrics.get("map_filling") is not None
        ]
        if not area_values or not filling_values:
            return "2D coverage diagnostics were not available for this dataset."

        mean_area = float(np.mean(area_values))
        mean_filling = float(np.mean(filling_values))
        if mean_area >= 0.85 and mean_filling >= 0.65:
            return (
                "the selected molecules cover most of the visible chemical map and "
                "are well distributed inside that area."
            )
        if mean_area >= 0.75 and mean_filling >= 0.45:
            return (
                "the selected molecules cover a broad part of the visible chemical map, "
                "with moderate dispersion inside that area."
            )
        if mean_area >= 0.75:
            return (
                "the selected molecules reach a broad visible area, but several selected "
                "molecules fall into similar populated map regions."
            )
        return (
            "the selected molecules cover a limited part of the visible 2D map; consider "
            "a larger coverage budget if broader visual coverage is needed."
        )

    def log_final_selection_quality(
        self,
        selection_data,
        selected_indices,
        selected_points,
        avg_gap_selected,
    ):
        """
        Report compact raw diagnostics for the selected coverage batch.
        """

        selected_budget = len(selected_indices)
        budget_context = getattr(self, "_coverage_auto_budget_context", {})
        evaluated_metrics = budget_context.get("evaluated_budget_metrics", {})
        final_metrics = evaluated_metrics.get(selected_budget, {})
        umap_area_coverage = final_metrics.get("umap_area_coverage")
        map_metrics = self.compute_final_2d_coverage_metrics(
            selection_data,
            selected_indices,
            selected_points,
            budget_context,
        )
        diagnostic_image_paths = self.save_selection_2d_diagnostic_images(
            selection_data,
            selected_indices,
            selected_points,
            budget_context,
        )
        if umap_area_coverage is None:
            umap_area_coverage = map_metrics.get("UMAP", {}).get("area_coverage")

        self.args.log.write("\no Final exploration summary")
        self.args.log.write(f"   - Selected molecules: {selected_budget}")
        self.args.log.write(f"   - avg_gap: {avg_gap_selected:.6f}")
        self.args.log.write("   - 2D area coverage: how much of the visible chemical map is reached.")
        self.args.log.write(
            "   - grid_coverage: occupied grid regions containing selected molecules / "
            "occupied grid regions containing any molecule."
        )
        self.args.log.write(
            "   - dispersion_score: the map is split into small occupied regions; "
            "this score measures whether selected molecules fall into different "
            "regions instead of repeating the same local region."
        )
        self.args.log.write(
            "   - Formula: occupied regions containing selected molecules / selected molecules."
        )
        self.args.log.write(
            "   - visual_score: 0.50*area_coverage + 0.30*grid_coverage + "
            "0.20*dispersion_score, reported from 0 to 10."
        )
        self.args.log.write("")
        self.args.log.write(
            "   +-----------+---------------+---------------+------------------+--------------+"
        )
        self.args.log.write(
            "   | embedding | area coverage | grid_coverage | dispersion_score | visual_score |"
        )
        self.args.log.write(
            "   +-----------+---------------+---------------+------------------+--------------+"
        )
        for embedding_name in ("PCA", "UMAP"):
            embedding_metrics = map_metrics.get(embedding_name, {})
            self.args.log.write(
                f"   | {embedding_name:<9} | "
                f"{self.format_fraction_percent(embedding_metrics.get('area_coverage')):<13} | "
                f"{self.format_fraction_percent(embedding_metrics.get('grid_coverage')):<13} | "
                f"{self.format_fraction_percent(embedding_metrics.get('map_filling')):<16} | "
                f"{self.format_visual_score(embedding_metrics.get('visual_score')):<12} |"
            )
        self.args.log.write(
            "   +-----------+---------------+---------------+------------------+--------------+"
        )
        self.args.log.write(
            f"   - Interpretation: {self.interpret_final_2d_coverage(map_metrics)}"
        )
        if diagnostic_image_paths:
            self.args.log.write("   - 2D selection diagnostic images:")
            for embedding_name in ("PCA", "UMAP"):
                image_paths = diagnostic_image_paths.get(embedding_name, {})
                area_path = image_paths.get("area")
                grid_path = image_paths.get("grid")
                dispersion_path = image_paths.get("dispersion")
                if area_path is not None:
                    self.args.log.write(f"     - {embedding_name} area: {area_path}")
                if grid_path is not None:
                    self.args.log.write(
                        f"     - {embedding_name} grid coverage: {grid_path}"
                    )
                if dispersion_path is not None:
                    self.args.log.write(
                        f"     - {embedding_name} dispersion score: {dispersion_path}"
                    )

        return {
            "avg_gap": avg_gap_selected,
            "umap_area_coverage": umap_area_coverage,
            "map_coverage_metrics": map_metrics,
            "diagnostic_image_paths": diagnostic_image_paths,
        }

    def allocate_points_by_group_population(self, labels, n_points):
        """
        Allocate selected points across natural groups proportionally to population.
        """

        labels = np.asarray(labels)
        unique_labels, counts = np.unique(labels, return_counts=True)
        groups = [
            {
                "label": int(label),
                "size": int(count),
                "raw_quota": float(n_points * count / len(labels)),
            }
            for label, count in zip(unique_labels, counts)
            if count > 0
        ]
        groups = sorted(
            groups,
            key=lambda group: (
                group["label"] == -1,
                -group["size"],
                group["label"],
            ),
        )
        if not groups:
            return {}

        if n_points < len(groups):
            return {group["label"]: 1 for group in groups[:n_points]}

        allocation = {
            group["label"]: max(1, int(np.floor(group["raw_quota"])))
            for group in groups
        }
        for group in groups:
            allocation[group["label"]] = min(allocation[group["label"]], group["size"])

        while sum(allocation.values()) > n_points:
            removable = [
                group
                for group in groups
                if allocation[group["label"]] > 1
            ]
            if not removable:
                break
            group_to_reduce = min(
                removable,
                key=lambda group: (
                    group["raw_quota"] - allocation[group["label"]],
                    group["size"],
                ),
            )
            allocation[group_to_reduce["label"]] -= 1

        while sum(allocation.values()) < n_points:
            expandable = [
                group
                for group in groups
                if allocation[group["label"]] < group["size"]
            ]
            if not expandable:
                break
            group_to_expand = max(
                expandable,
                key=lambda group: (
                    group["raw_quota"] - allocation[group["label"]],
                    group["size"],
                ),
            )
            allocation[group_to_expand["label"]] += 1

        return {
            label: count
            for label, count in allocation.items()
            if count > 0
        }

    def select_points_within_natural_group(self, selection_data, group_indices, n_points):
        """
        Pick one centroid representative, then farthest points within one natural group.
        """

        group_indices = [int(index) for index in group_indices]
        n_points = int(n_points)
        if n_points <= 0:
            return []
        if n_points >= len(group_indices):
            return group_indices

        group_points = selection_data[group_indices]
        centroid = np.mean(group_points, axis=0)
        first_position = int(np.argmin(np.linalg.norm(group_points - centroid, axis=1)))
        chosen_positions = [first_position]

        while len(chosen_positions) < n_points:
            chosen_points = group_points[chosen_positions]
            distances_to_chosen = np.linalg.norm(
                group_points[:, None, :] - chosen_points[None, :, :],
                axis=2,
            )
            min_distances = np.min(distances_to_chosen, axis=1)
            min_distances[chosen_positions] = -np.inf
            chosen_positions.append(int(np.argmax(min_distances)))

        return [int(group_indices[position]) for position in chosen_positions]

    def choose_natural_selection_candidate(self, natural_result):
        """
        Choose the simplest near-best natural clustering model for point allocation.
        """

        if natural_result is None:
            return None, "no natural clustering result was available"

        candidates = [
            candidate
            for candidate in natural_result.best_by_algorithm.values()
            if candidate.final_score is not None
            and candidate.passed_filters
            and candidate.raw_metrics.get("n_clusters", 0) >= 2
        ]
        if not candidates:
            return natural_result.best_candidate, "no filtered near-best candidates were available"

        best_score = max(float(candidate.final_score) for candidate in candidates)
        near_best_candidates = [
            candidate
            for candidate in candidates
            if float(candidate.final_score) >= best_score - NATURAL_SELECTION_SCORE_TOLERANCE
        ]
        selected_candidate = min(
            near_best_candidates,
            key=lambda candidate: (
                candidate.raw_metrics.get("n_clusters", np.inf),
                -float(candidate.final_score),
            ),
        )
        best_candidate = max(candidates, key=lambda candidate: float(candidate.final_score))
        if selected_candidate is best_candidate:
            reason = "it had the highest natural-clustering final_score."
        else:
            reason = (
                f"it was within {NATURAL_SELECTION_SCORE_TOLERANCE:.2f} final_score "
                "of the best natural model and produced fewer clusters for a more "
                "interpretable point allocation."
            )
        return selected_candidate, reason

    def select_natural_cluster_representatives(
        self,
        coverage_result,
        selectable_indices,
        n_points,
    ):
        """
        Select molecules from natural clusters using proportional allocation.
        """

        natural_result = coverage_result.get("natural_selection_result")
        natural_candidate, natural_candidate_reason = self.choose_natural_selection_candidate(
            natural_result
        )
        if natural_candidate is None:
            return None

        labels = np.asarray(natural_candidate.labels, dtype=int)
        selection_data = coverage_result["selection_data"]
        if len(labels) != len(selection_data):
            return None

        unique_non_noise = np.unique(labels[labels != -1])
        if len(unique_non_noise) < 2:
            return None

        allocation = self.allocate_points_by_group_population(labels, n_points)
        if not allocation:
            return None

        selected_indices = []
        for label, group_points_to_select in allocation.items():
            group_indices = [
                int(index)
                for index in selectable_indices
                if labels[int(index)] == label
            ]
            selected_indices.extend(
                self.select_points_within_natural_group(
                    selection_data,
                    group_indices,
                    group_points_to_select,
                )
            )

        selected_indices = list(dict.fromkeys(selected_indices))
        if len(selected_indices) < n_points:
            remaining_indices = [
                int(index)
                for index in selectable_indices
                if int(index) not in set(selected_indices)
            ]
            selected_indices.extend(
                self.select_coverage_representatives(
                    selection_data,
                    np.asarray(remaining_indices, dtype=int),
                    n_points - len(selected_indices),
                    log_selection=False,
                )
            )

        allocation_text = ", ".join(
            f"noise={count}" if label == -1 else f"cluster {label}={count}"
            for label, count in sorted(allocation.items(), key=lambda item: item[0])
        )
        self.args.log.write("\no Natural-cluster point selection")
        self.args.log.write(
            f"   - Natural clustering model used for selection: {natural_candidate.algorithm}"
        )
        self.args.log.write(
            f"   - Natural clustering parameters: {natural_candidate.params}"
        )
        self.args.log.write(
            f"   - Selection model reason: {natural_candidate_reason}"
        )
        self.args.log.write(
            f"   - Natural clusters used: {natural_candidate.raw_metrics.get('n_clusters')}"
        )
        self.args.log.write(f"   - Requested points: {n_points}")
        self.args.log.write(
            "   - Allocation strategy: proportional to natural cluster population"
        )
        self.args.log.write(f"   - Per-cluster allocation: {allocation_text}")
        self.args.log.write(
            "   - Within each natural cluster: first the centroid representative, "
            "then the farthest remaining molecules."
        )

        return selected_indices[:n_points]

    def select_coverage_representatives(
        self,
        scaled_data,
        selectable_indices,
        n_points,
        log_selection=True,
    ):
        """
        Select representatives with either centroid representatives or diversity pruning.
        """

        n_points = int(n_points)
        if n_points <= 0:
            return []
        if n_points > len(selectable_indices):
            self.args.log.write(
                f"\nx WARNING. The requested number of points ({n_points}) is larger than "
                f"the number of selectable points ({len(selectable_indices)})."
            )
            self.args.log.finalize()
            sys.exit(19)
        if n_points == len(selectable_indices):
            return [int(index) for index in selectable_indices]

        selection_data = scaled_data[selectable_indices]
        selection_mode = getattr(
            self.args,
            "mode",
            "representative",
        )
        selection_mode = str(selection_mode).lower()
        if selection_mode not in CLUSTER_SELECTION_MODE_CHOICES:
            selection_mode = "representative"
        if selection_mode == "exploratory":
            n_candidate_prototypes = min(2 * n_points, len(selectable_indices))
        else:
            n_candidate_prototypes = n_points
        prototype_model = MiniBatchKMeans(
            n_clusters=n_candidate_prototypes,
            random_state=self.args.seed_clustered,
            n_init=5,
            max_iter=150,
            batch_size=min(4096, max(256, len(selectable_indices))),
        )
        prototype_labels = prototype_model.fit_predict(selection_data)

        candidate_indices = []
        for prototype_label in range(n_candidate_prototypes):
            local_indices = np.where(prototype_labels == prototype_label)[0]
            if len(local_indices) == 0:
                continue
            prototype_points = selection_data[local_indices]
            centroid = prototype_model.cluster_centers_[prototype_label]
            centroid_distances = np.linalg.norm(prototype_points - centroid, axis=1)
            selected_local_index = local_indices[int(np.argmin(centroid_distances))]
            candidate_indices.append(int(selectable_indices[selected_local_index]))

        candidate_indices = list(dict.fromkeys(candidate_indices))
        if len(candidate_indices) < n_points:
            missing_indices = [
                int(index)
                for index in selectable_indices
                if int(index) not in set(candidate_indices)
            ]
            candidate_indices.extend(missing_indices[: n_points - len(candidate_indices)])

        if selection_mode == "representative":
            return candidate_indices[:n_points]

        candidate_points = scaled_data[candidate_indices]
        global_centroid = np.mean(selection_data, axis=0)
        first_candidate = int(
            np.argmin(np.linalg.norm(candidate_points - global_centroid, axis=1))
        )
        chosen_candidate_positions = [first_candidate]

        while len(chosen_candidate_positions) < n_points:
            chosen_points = candidate_points[chosen_candidate_positions]
            distances_to_chosen = np.linalg.norm(
                candidate_points[:, None, :] - chosen_points[None, :, :],
                axis=2,
            )
            min_distances = np.min(distances_to_chosen, axis=1)
            min_distances[chosen_candidate_positions] = -np.inf
            chosen_candidate_positions.append(int(np.argmax(min_distances)))

        selected_indices = [
            int(candidate_indices[position])
            for position in chosen_candidate_positions
        ]
        return selected_indices

    def molecule_svg_from_smiles(self, smiles):
        """
        Return an SVG molecule drawing for a SMILES string, if RDKit can parse it.
        """

        if pd.isna(smiles) or str(smiles).strip() == "":
            return ""
        molecule = Chem.MolFromSmiles(str(smiles))
        if molecule is None:
            return ""
        try:
            from rdkit.Chem.Draw import rdMolDraw2D

            drawer = rdMolDraw2D.MolDraw2DSVG(260, 200)
            drawer.DrawMolecule(molecule)
            drawer.FinishDrawing()
            return drawer.GetDrawingText()
        except Exception:
            return ""

    def compute_embedding_fidelity(self, original_data, embedding, selected_mask):
        """
        Compute user-facing fidelity metrics for a 2D visualization.
        """

        if len(original_data) < 3:
            return {"trustworthiness": None}
        n_neighbors = min(15, max(1, (len(original_data) - 1) // 2))
        try:
            trust_score = float(
                trustworthiness(
                    original_data,
                    embedding,
                    n_neighbors=n_neighbors,
                )
            )
        except Exception:
            trust_score = None

        return {"trustworthiness": trust_score}

    def compute_pca_2d_variance(self, selection_data):
        """
        Fraction of selection-space variance retained by the first two PCA axes.
        """

        if len(selection_data) < 2:
            return None
        if selection_data.shape[1] == 1:
            return 1.0
        try:
            pca = PCA(n_components=2, random_state=self.args.seed_clustered)
            pca.fit(selection_data)
            return float(np.sum(pca.explained_variance_ratio_))
        except Exception:
            return None

    def classify_visualization_local_quality(self, trustworthiness_score):
        """
        User-facing recommendation based on local-neighborhood preservation in 2D.
        """

        trust = trustworthiness_score if trustworthiness_score is not None else 0.0
        if trust >= 0.95:
            return "EXCELLENT"
        if trust >= 0.90:
            return "GOOD"
        if trust >= 0.80:
            return "ACCEPTABLE"
        return "LOW"

    def interpret_combined_2d_visualization_quality(
        self,
        pca_trustworthiness,
        pca_variance_retained,
        umap_trustworthiness,
    ):
        """
        Provide one compact interpretation for PCA/UMAP visualization quality.
        """

        pca_trust = pca_trustworthiness if pca_trustworthiness is not None else 0.0
        pca_variance = pca_variance_retained if pca_variance_retained is not None else 0.0
        umap_trust = umap_trustworthiness if umap_trustworthiness is not None else None
        pca_variance_high = pca_variance >= 0.70
        pca_trust_high = pca_trust >= 0.90
        umap_trust_high = umap_trust is not None and umap_trust >= 0.90

        if pca_variance_high and pca_trust_high and umap_trust_high:
            return (
                "PCA and UMAP both support chemically meaningful 2D inspection. PCA captures "
                "a large part of the global linear variability, and both maps preserve local "
                "neighborhoods well. Use them to inspect visual clusters, hotspots and selected "
                "molecules, while avoiding claims of perfect full-space distance preservation."
            )
        if (pca_trust_high or umap_trust_high) and not pca_variance_high:
            return (
                "The maps are useful for local chemical inspection because nearby molecules "
                "are generally reliable. PCA does not capture all global descriptor-space "
                "variability, so use PCA as a partial view and rely more on local neighborhoods "
                "for visual clusters and gradients."
            )
        if pca_trust_high or umap_trust_high:
            return (
                "At least one 2D map preserves local neighborhoods well, so it is useful for "
                "visual inspection of chemical clouds and gradients. Avoid treating far-apart "
                "2D distances as exact full-space chemical distances."
            )
        if pca_trust >= 0.80 or (umap_trust is not None and umap_trust >= 0.80):
            return (
                "The 2D maps are useful for qualitative inspection of local clouds and "
                "gradients, but avoid interpreting far-apart distances as exact chemical distances."
            )
        return (
            "The 2D maps should be treated as rough visual guides for this dataset."
        )

    def compute_pca_2d_embedding(self, selection_data):
        """
        Project the selection space to two dimensions with PCA.
        """

        if selection_data.shape[1] >= 2:
            return PCA(n_components=2, random_state=self.args.seed_clustered).fit_transform(
                selection_data
            )
        return np.column_stack([selection_data[:, 0], np.zeros(len(selection_data))])

    def compute_umap_2d_embedding(self, selection_data, selected_mask):
        """
        Compute a single adaptive UMAP visualization.
        """

        try:
            import umap
        except Exception:
            return None, None, "UMAP is not installed"

        if len(selection_data) < 4:
            return None, None, "UMAP requires at least four points"

        n_neighbors = min(30, max(5, int(round(np.sqrt(len(selection_data))))))
        n_neighbors = min(n_neighbors, len(selection_data) - 1)
        if n_neighbors < 2:
            return None, None, "UMAP could not build a valid neighbor graph"
        min_dist = 0.1

        self.args.log.write("\no Building UMAP visualization")
        self.args.log.write(
            "   - UMAP is used only for 2D visualization, not for point selection."
        )
        self.args.log.write(
            f"   - Parameters: n_neighbors={n_neighbors}, min_dist={min_dist}, metric=euclidean"
        )

        try:
            reducer = umap.UMAP(
                n_components=2,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric="euclidean",
                random_state=self.args.seed_clustered,
            )
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="n_jobs value .* overridden to 1 by setting random_state.*",
                    category=UserWarning,
                )
                embedding = reducer.fit_transform(selection_data)
            metrics = self.compute_embedding_fidelity(
                selection_data,
                embedding,
                selected_mask,
            )
        except Exception as exc:
            return None, None, f"UMAP failed: {exc}"

        metrics["params"] = {
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
            "metric": "euclidean",
        }
        self.args.log.write(
            "   - UMAP fidelity metrics will be reported together with PCA below."
        )
        return embedding, metrics, None

    def build_chemical_space_viewer(
        self,
        descp_df,
        selected_indices,
        coverage_result,
        file_name,
    ):
        """
        Build an interactive PCA/UMAP HTML viewer for the selected chemical space.
        """

        selection_data = coverage_result["selection_data"]
        self.args.log.write("\no Building 2D chemical space viewer")
        self.args.log.write("   - Computing PCA projection")
        selected_index_set = set(int(index) for index in selected_indices)
        selected_mask_full = np.array(
            [index in selected_index_set for index in range(len(selection_data))],
            dtype=bool,
        )

        all_indices = np.arange(len(selection_data))
        display_indices = all_indices

        display_data = selection_data[display_indices]
        selected_mask = selected_mask_full[display_indices]

        embeddings = {}
        pca_embedding = self.compute_pca_2d_embedding(display_data)
        pca_metrics = self.compute_embedding_fidelity(
            display_data,
            pca_embedding,
            selected_mask,
        )
        pca_metrics["variance_retained"] = self.compute_pca_2d_variance(display_data)
        embeddings["PCA"] = {
            "coords": pca_embedding,
            "metrics": pca_metrics,
        }

        umap_embedding, umap_metrics, umap_warning = self.compute_umap_2d_embedding(
            display_data,
            selected_mask,
        )
        if umap_embedding is not None:
            embeddings["UMAP"] = {
                "coords": umap_embedding,
                "metrics": umap_metrics,
            }

        smiles_column = next(
            (column for column in descp_df.columns if column.lower() == "smiles"),
            None,
        )
        has_smiles = smiles_column is not None
        name_column = self.args.name if self.args.name in descp_df.columns else None
        target_column = self.args.y if self.args.y in descp_df.columns else None
        target_values = None
        target_is_numeric = False
        target_categories = {}
        if target_column is not None:
            target_series = descp_df.loc[display_indices, target_column]
            numeric_target = pd.to_numeric(target_series, errors="coerce")
            valid_numeric_count = int(numeric_target.notna().sum())
            non_empty_target = target_series.dropna().astype(str).str.strip()
            non_empty_target = non_empty_target[non_empty_target != ""]
            if valid_numeric_count > 0:
                target_is_numeric = True
                target_values = [
                    None if pd.isna(value) else float(value)
                    for value in numeric_target
                ]
                missing_target_count = int(len(target_series) - valid_numeric_count)
                if missing_target_count > 0:
                    self.args.log.write(
                        "\nx WARNING. Some rows have no valid numeric value in the "
                        f"response column specified with --y ({target_column}); those "
                        "molecules will be shown without a target-gradient value."
                    )
            else:
                if len(non_empty_target) == 0:
                    self.args.log.write(
                        "\nx WARNING. The response column specified with --y "
                        f"({target_column}) has no valid values; the target gradient "
                        "will not be shown in the HTML viewer."
                    )
                    target_column = None
                else:
                    self.args.log.write(
                        "\nx WARNING. The response column specified with --y "
                        f"({target_column}) has no valid numeric values; the target "
                        "gradient will not be shown in the HTML viewer."
                    )

        descriptor_importance_df = compute_cluster_descriptor_importance(
            coverage_result["descriptor_df"],
            coverage_result["selection_region_labels"],
        )
        top_descriptor_columns = [
            descriptor
            for descriptor in descriptor_importance_df.head(5)["descriptor"].tolist()
            if descriptor in coverage_result["descriptor_df"].columns
        ]
        descriptor_color_payload = {}
        for descriptor in top_descriptor_columns:
            descriptor_color_payload[descriptor] = [
                float(value)
                for value in coverage_result["descriptor_df"]
                .loc[display_indices, descriptor]
                .astype(float)
                .tolist()
            ]
        records = []
        for index in display_indices:
            row = descp_df.loc[index]
            smiles = str(row[smiles_column]) if has_smiles else ""
            svg = self.molecule_svg_from_smiles(smiles) if has_smiles else ""
            records.append(
                {
                    "index": int(index),
                    "name": str(row[name_column]) if name_column is not None else str(index),
                    "smiles": smiles,
                    "selected": bool(index in selected_index_set),
                    "target": (
                        None
                        if target_column is None
                        else str(row[target_column])
                    ),
                    "svg": svg,
                }
            )

        embedding_payload = {}
        fidelity_rows = []
        for embedding_name, payload in embeddings.items():
            coords = payload["coords"]
            metrics = payload["metrics"]
            embedding_payload[embedding_name] = {
                "x": coords[:, 0].astype(float).tolist(),
                "y": coords[:, 1].astype(float).tolist(),
            }
            fidelity_rows.append(
                {
                    "embedding": embedding_name,
                    "trustworthiness": metrics.get("trustworthiness"),
                    "local_recommendation": self.classify_visualization_local_quality(
                        metrics.get("trustworthiness")
                    ),
                    "params": metrics.get("params"),
                }
            )

        color_payload = {}
        if target_values is not None:
            color_payload["target"] = target_values
        if descriptor_color_payload:
            color_payload["descriptors"] = descriptor_color_payload

        html_payload = {
            "embeddings": embedding_payload,
            "colors": color_payload,
            "records": records,
            "descriptorColorColumns": top_descriptor_columns,
            "targetColumn": target_column,
            "targetIsNumeric": target_is_numeric,
            "targetCategories": target_categories,
            "hasSmiles": has_smiles,
        }

        try:
            from plotly.offline import get_plotlyjs

            plotly_js = get_plotlyjs()
        except Exception:
            plotly_js = ""

        html_text = self.render_chemical_space_viewer_html(
            html_payload,
            plotly_js,
            file_name,
        )
        viewer_path = "batch_0/chemical_space_viewer.html"
        with open(viewer_path, "w", encoding="utf-8") as handle:
            handle.write(html_text)

        self.args.log.write("\no 2D chemical space visualization")
        self.args.log.write(f"   - Saved {viewer_path}")
        self.args.log.write("   - Embeddings: " + ", ".join(embeddings.keys()))
        self.args.log.write(
            f"   - Displayed molecules: {len(display_indices)} of {len(selection_data)} "
            "(all selected and non-selected molecules are included)."
        )
        if not has_smiles:
            self.args.log.write(
                "x WARNING. No SMILES column was found; molecule drawings are not available in the HTML viewer."
            )
        if umap_warning is not None:
            self.args.log.write(f"x WARNING. {umap_warning}; UMAP viewer was skipped.")

        self.args.log.write("\no 2D visualization quality")
        self.args.log.write(
            "   - Use these maps to inspect chemical-space clouds, selected molecules, "
            "and target/descriptor gradients."
        )
        self.args.log.write(
            "   - trustworthiness: 0-1 score; higher means nearby molecules in 2D are "
            "likely nearby in the full selection space."
        )
        pca_variance_retained = embeddings["PCA"]["metrics"].get("variance_retained")
        pca_trustworthiness = embeddings["PCA"]["metrics"].get("trustworthiness")
        umap_trustworthiness = (
            embeddings["UMAP"]["metrics"].get("trustworthiness")
            if "UMAP" in embeddings
            else None
        )
        pca_variance_text = (
            f"{100 * pca_variance_retained:.1f}%"
            if pca_variance_retained is not None
            else "NA"
        )
        if pca_variance_retained is not None and pca_variance_retained >= 0.70:
            self.args.log.write(
                f"   - PCA variance: PC1+PC2 show {pca_variance_text} of selection-space "
                "variance; PCA captures a large part of the global linear variability."
            )
        else:
            self.args.log.write(
                f"   - PCA variance: PC1+PC2 show {pca_variance_text} of selection-space "
                "variance; PCA does not represent all global variability, but it can still "
                "be useful for visual inspection when trustworthiness is acceptable."
            )
        if "UMAP" in embeddings:
            self.args.log.write(
                "   - UMAP has no explained-variance value; judge it mainly by trustworthiness."
            )
        else:
            self.args.log.write(
                "   - UMAP was not available, so only the PCA map is reported."
            )
        self.args.log.write("   +-----------+-----------------+----------------+")
        self.args.log.write("   | embedding | trustworthiness | recommendation |")
        self.args.log.write("   +-----------+-----------------+----------------+")
        for row in fidelity_rows:
            trust_text = (
                "NA"
                if row["trustworthiness"] is None
                else f"{row['trustworthiness']:.3f}"
            )
            self.args.log.write(
                f"   | {row['embedding']:<9} | {trust_text:<15} | "
                f"{row['local_recommendation']:<14} |"
            )
        self.args.log.write("   +-----------+-----------------+----------------+")
        self.args.log.write(
            f"   - Interpretation: "
            f"{self.interpret_combined_2d_visualization_quality(pca_trustworthiness, pca_variance_retained, umap_trustworthiness)}"
        )
        return viewer_path

    def render_chemical_space_viewer_html(self, payload, plotly_js, file_name):
        """
        Render the standalone chemical-space viewer HTML.
        """

        payload_json = json.dumps(
            payload,
            default=lambda value: value.item() if isinstance(value, np.generic) else str(value),
        ).replace("</", "<\\/")
        color_options = ["selected"]
        if payload["targetColumn"] is not None and payload["targetIsNumeric"]:
            color_options.insert(2, "target")
        color_options.extend(
            f"descriptor::{descriptor}"
            for descriptor in payload.get("descriptorColorColumns", [])
        )

        def format_color_option_label(option):
            if option == "target":
                return payload["targetColumn"]
            return option.replace("descriptor::", "descriptor: ")

        color_options_html = "\n".join(
            f'<option value="{html.escape(option)}">{html.escape(format_color_option_label(option))}</option>'
            for option in color_options
        )
        embedding_options_html = "\n".join(
            f'<option value="{embedding}">{embedding}</option>'
            for embedding in payload["embeddings"]
        )
        plotly_script = (
            f"<script>{plotly_js}</script>"
            if plotly_js
            else '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>'
        )
        base_file_name_json = json.dumps(os.path.splitext(file_name)[0])

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ALMOS chemical space viewer - {html.escape(file_name)}</title>
  {plotly_script}
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #1f2933; }}
    header {{ padding: 14px 18px; border-bottom: 1px solid #d9e2ec; }}
    main {{ min-height: calc(100vh - 86px); }}
    #plot {{ min-height: 720px; }}
    label {{ font-size: 13px; margin-right: 14px; }}
    select {{ margin-left: 6px; }}
    button {{
      border: 1px solid #9fb3c8;
      border-radius: 6px;
      background: #f0f4f8;
      color: #1f2933;
      cursor: pointer;
      font-size: 13px;
      padding: 5px 9px;
    }}
    button:hover {{ background: #d9e2ec; }}
    .meta {{ font-size: 13px; line-height: 1.45; }}
    .note {{ font-size: 12px; color: #52606d; margin-top: 8px; }}
    .mol svg {{ max-width: 100%; height: auto; }}
    .empty {{ color: #66788a; }}
    .hover-card {{
      position: fixed;
      display: none;
      z-index: 1000;
      width: 300px;
      max-height: 430px;
      overflow: auto;
      padding: 12px;
      border: 1px solid #bcccdc;
      border-radius: 8px;
      background: #f5f7fa;
      box-shadow: 0 10px 24px rgba(16, 24, 40, 0.18);
      font-size: 12px;
      line-height: 1.35;
      color: #1f2933;
      pointer-events: none;
    }}
    .hover-card h4, .meta h4 {{ margin: 10px 0 5px; font-size: 12px; }}
    .hover-card p, .meta p {{ margin: 5px 0; }}
    .hover-card ul, .meta ul {{ margin: 4px 0 0 17px; padding: 0; }}
    .hover-card .mol svg {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body>
  <header>
    <label>Embedding
      <select id="embeddingSelect">
        {embedding_options_html}
      </select>
    </label>
    <label>Color by
      <select id="colorSelect">
        {color_options_html}
      </select>
    </label>
    <button id="savePngButton" type="button">Save PNG</button>
    <div class="note">
      <div>Hover over a molecule to inspect its structure, response value when available, and selected-molecule status.</div>
    </div>
  </header>
  <main>
    <div id="plot"></div>
  </main>
  <div id="hoverCard" class="hover-card"></div>
  <script>
    const payload = {payload_json};
    const plot = document.getElementById("plot");
    const embeddingSelect = document.getElementById("embeddingSelect");
    const colorSelect = document.getElementById("colorSelect");
    const savePngButton = document.getElementById("savePngButton");
    const hoverCard = document.getElementById("hoverCard");
    const baseFileName = {base_file_name_json};
    function colorTitle(mode) {{
      if (mode === "target" && payload.targetColumn) return payload.targetColumn;
      if (mode.startsWith("descriptor::")) return mode.replace("descriptor::", "");
      return mode;
    }}

    function safeFilename(value) {{
      return String(value).replace(/[^a-z0-9._-]+/gi, "_").replace(/^_+|_+$/g, "");
    }}

    function currentPlotFileName() {{
      return safeFilename(`${{baseFileName}}_${{embeddingSelect.value}}_${{colorTitle(colorSelect.value)}}`);
    }}

    const plotConfig = {{
      responsive: true,
      displaylogo: false,
      displayModeBar: true,
      toImageButtonOptions: {{
        format: "png",
        filename: currentPlotFileName(),
        height: 900,
        width: 1400,
        scale: 2
      }}
    }};

    function draw() {{
      const embedding = embeddingSelect.value;
      const colorMode = colorSelect.value;
      const coords = payload.embeddings[embedding];
      const isTargetGradient = colorMode === "target";
      const isDescriptorGradient = colorMode.startsWith("descriptor::");
      const descriptorName = isDescriptorGradient ? colorMode.replace("descriptor::", "") : null;
      const traces = [];
      const xMin = Math.min(...coords.x);
      const xMax = Math.max(...coords.x);
      const yMin = Math.min(...coords.y);
      const yMax = Math.max(...coords.y);
      const xPad = Math.max((xMax - xMin) * 0.05, 1e-9);
      const yPad = Math.max((yMax - yMin) * 0.05, 1e-9);

      function makeTrace(name, indices, marker, showScale=false, colorValues=null) {{
        return {{
          type: "scattergl",
          mode: "markers",
          name,
          x: indices.map(i => coords.x[i]),
          y: indices.map(i => coords.y[i]),
          customdata: indices,
          hoverinfo: "none",
          marker: {{
            ...marker,
            color: colorValues ? indices.map(i => colorValues[i]) : marker.color,
            showscale: showScale,
            colorbar: showScale ? {{ title: colorTitle(colorMode) }} : undefined
          }}
        }};
      }}

      const allIndices = payload.records.map((_, i) => i);
      const selectedIndices = allIndices.filter(i => payload.records[i].selected);
      const backgroundIndices = allIndices.filter(i => !payload.records[i].selected);

      if (isTargetGradient || isDescriptorGradient) {{
        const gradientValues = isTargetGradient
          ? payload.colors.target
          : payload.colors.descriptors[descriptorName];
        const gradientIndices = isTargetGradient
          ? allIndices.filter(i => gradientValues[i] !== null && gradientValues[i] !== undefined)
          : allIndices;
        const missingTargetIndices = isTargetGradient
          ? allIndices.filter(i => gradientValues[i] === null || gradientValues[i] === undefined)
          : [];
        if (missingTargetIndices.length > 0) {{
          traces.push(makeTrace(`No ${{colorTitle(colorMode)}} value`, missingTargetIndices, {{
            color: "#d1d5db",
            size: 6,
            opacity: 0.55,
            symbol: "circle",
            line: {{ width: 0.2, color: "#9ca3af" }}
          }}));
        }}
        if (gradientIndices.length > 0) {{
          traces.push(makeTrace(colorTitle(colorMode), gradientIndices, {{
          colorscale: "Turbo",
          size: 7,
          opacity: 0.78,
          symbol: "circle",
          line: {{ width: 0.3, color: "#1f2933" }}
          }}, true, gradientValues));
        }}
        if (selectedIndices.length > 0) {{
          traces.push(makeTrace("Selected", selectedIndices, {{
            color: "#16a34a",
            size: 12,
            opacity: 1.0,
            symbol: "circle",
            line: {{ width: 1.2, color: "#064e3b" }}
          }}));
        }}
      }} else {{
        if (backgroundIndices.length > 0) {{
          traces.push(makeTrace("Not selected", backgroundIndices, {{
            color: "#b8c2cc",
            size: 6,
            opacity: 0.62,
            symbol: "circle",
            line: {{ width: 0.2, color: "#8a97a6" }}
          }}));
        }}
        if (selectedIndices.length > 0) {{
          traces.push(makeTrace("Selected", selectedIndices, {{
            color: "#16a34a",
            size: 11,
            opacity: 1.0,
            symbol: "circle",
            line: {{ width: 1.2, color: "#064e3b" }}
          }}));
        }}
      }}
      const layout = {{
        margin: {{ l: 50, r: 20, t: 25, b: 45 }},
        xaxis: {{
          title: embedding + " 1",
          zeroline: false,
          showgrid: false,
          showline: true,
          mirror: true,
          linecolor: "#000000",
          linewidth: 1.4,
          ticks: "outside",
          tickcolor: "#000000",
          tickfont: {{ color: "#000000" }},
          titlefont: {{ color: "#000000" }},
          autorange: false,
          range: [xMin - xPad, xMax + xPad]
        }},
        yaxis: {{
          title: embedding + " 2",
          zeroline: false,
          showgrid: false,
          showline: true,
          mirror: true,
          linecolor: "#000000",
          linewidth: 1.4,
          ticks: "outside",
          tickcolor: "#000000",
          tickfont: {{ color: "#000000" }},
          titlefont: {{ color: "#000000" }},
          autorange: false,
          range: [yMin - yPad, yMax + yPad]
        }},
        dragmode: "pan",
        legend: {{ orientation: "h", x: 0, y: 1.08 }}
      }};
      plotConfig.toImageButtonOptions.filename = currentPlotFileName();
      Plotly.react(plot, traces, layout, plotConfig);
    }}

    function downloadCurrentPlot() {{
      Plotly.downloadImage(plot, {{
        format: "png",
        filename: currentPlotFileName(),
        height: 900,
        width: 1400,
        scale: 2
      }});
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, ch => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }}[ch]));
    }}

    function moleculeBlock(record) {{
      return record.svg
        ? `<div class="mol">${{record.svg}}</div>`
        : `<p class="empty">${{payload.hasSmiles ? "No valid molecule drawing available." : "No SMILES column available."}}</p>`;
    }}

    function recordCard(record) {{
      return `
        ${{moleculeBlock(record)}}
        <p><strong>${{escapeHtml(record.name)}}</strong></p>
        <p>selected: ${{record.selected}}</p>
        <p>SMILES: ${{escapeHtml(record.smiles || "NA")}}</p>
        ${{payload.targetColumn ? `<p>${{escapeHtml(payload.targetColumn)}}: ${{escapeHtml(record.target)}}</p>` : ""}}
      `;
    }}

    draw();
    plot.on("plotly_hover", event => {{
      const pointIndex = event.points[0].customdata;
      const record = payload.records[pointIndex];
      hoverCard.innerHTML = recordCard(record);
      hoverCard.style.display = "block";
      const x = event.event.clientX + 16;
      const y = event.event.clientY + 16;
      const maxX = window.innerWidth - hoverCard.offsetWidth - 12;
      const maxY = window.innerHeight - hoverCard.offsetHeight - 12;
      hoverCard.style.left = `${{Math.max(12, Math.min(x, maxX))}}px`;
      hoverCard.style.top = `${{Math.max(12, Math.min(y, maxY))}}px`;
    }});

    plot.on("plotly_unhover", () => {{
      hoverCard.style.display = "none";
    }});

    embeddingSelect.addEventListener("change", draw);
    colorSelect.addEventListener("change", draw);
    savePngButton.addEventListener("click", downloadCurrentPlot);
  </script>
</body>
</html>
"""

    def save_natural_clustering_report(self, descp_file, selection_result):
        """
        Save optional natural clustering diagnostics.
        """

        best_candidate = selection_result.best_candidate
        if best_candidate is None:
            return

        descp_df = pd.read_csv(descp_file)
        summary_rows = []
        for algorithm, candidate in selection_result.best_by_algorithm.items():
            summary_rows.append(
                {
                    "algorithm": algorithm,
                    "params": str(candidate.params),
                    "n_clusters": candidate.raw_metrics["n_clusters"],
                    "cluster_sizes": str(candidate.raw_metrics["cluster_sizes"]),
                    "silhouette": candidate.raw_metrics["silhouette"],
                    "calinski_harabasz": candidate.raw_metrics["calinski_harabasz"],
                    "davies_bouldin": candidate.raw_metrics["davies_bouldin"],
                    "stability": candidate.raw_metrics["stability"],
                    "noise_fraction": candidate.raw_metrics.get("noise_fraction", 0.0),
                    "imbalance_penalty": candidate.raw_metrics["imbalance_penalty"],
                    "bic": candidate.raw_metrics.get("bic"),
                    "final_score": candidate.final_score,
                }
            )

        pd.DataFrame(summary_rows).to_csv(
            "batch_0/clustering_model_summary.csv",
            index=False,
        )

        descriptor_columns = [
            column for column in selection_result.descriptor_columns if column in descp_df.columns
        ]
        descriptor_importance_df = compute_cluster_descriptor_importance(
            descp_df.loc[:, descriptor_columns],
            best_candidate.labels,
        )
        descriptor_importance_df.to_csv(
            "batch_0/cluster_descriptor_importance.csv",
            index=False,
        )

        self.args.log.write("\no Optional natural clustering report")
        self.args.log.write(
            f"   - Best natural clustering model: {best_candidate.algorithm} "
            f"with parameters {best_candidate.params}"
        )
        self.args.log.write("   - Saved batch_0/clustering_model_summary.csv")
        self.args.log.write("   - Saved batch_0/cluster_descriptor_importance.csv")

        self.args.log.write("\no Descriptors most associated with the natural cluster separation:")
        if descriptor_importance_df.empty:
            self.args.log.write(
                "   - Not available: at least two non-noise clusters are required."
            )
        else:
            if selection_result.dimensionality_reduction_info.get("applied"):
                self.args.log.write(
                    "   - Clustering was performed in PCA space; this descriptor ranking is computed "
                    "post hoc on the final cluster labels using the cleaned original descriptors."
                )
            self.args.log.write(
                "   - F is an ANOVA-style between-cluster / within-cluster separation score "
                "for each descriptor; higher values indicate stronger separation."
            )
            self.args.log.write(
                "   - eta2 is the fraction of that descriptor's variance explained by the "
                "cluster labels, from 0 to 1; higher values indicate stronger association."
            )
            for _, row in descriptor_importance_df.head(10).iterrows():
                self.args.log.write(
                    f"   - #{int(row['rank'])} {row['descriptor']}: "
                    f"F={row['f_score']:.6g}, eta2={row['eta_squared']:.6g}"
                )

    def save_cluster_outputs(self, descp_file, csv, file_name, coverage_result):
        """
        Save the coverage-based selected point outputs.
        """

        descp_df = pd.read_csv(descp_file)
        aqme_output_name_column = getattr(self, "_aqme_output_name_column", None)
        if (
            self.args.aqme
            and aqme_output_name_column
            and "code_name" in descp_df.columns
            and aqme_output_name_column not in descp_df.columns
        ):
            descp_df = descp_df.rename(columns={"code_name": aqme_output_name_column})
            self.args.ignore = [
                aqme_output_name_column if column == "code_name" else column
                for column in self.args.ignore
            ]
            self.args.name = aqme_output_name_column

        if self.args.evaluate:
            selected_indices, _, _ = self.evaluate_existing_selection(
                coverage_result,
                descp_df,
            )
            descp_df["batch"] = pd.to_numeric(descp_df["batch"], errors="coerce")
        else:
            selected_indices, _, _ = self.select_representative_points(
                coverage_result
            )
            if "batch" not in descp_df.columns:
                descp_df["batch"] = pd.NA
            descp_df["batch"] = pd.NA
            for index in selected_indices:
                descp_df.loc[index, "batch"] = 0
        viewer_path = self.build_chemical_space_viewer(
            descp_df=descp_df,
            selected_indices=selected_indices,
            coverage_result=coverage_result,
            file_name=file_name,
        )
        descp_df = descp_df[
            [column for column in descp_df.columns if column != "batch"] + ["batch"]
        ]
        descp_df = descp_df.sort_values(
            by="batch",
            ascending=True,
            na_position="last",
            kind="stable",
        )
        descp_df.to_csv(f"batch_0/{csv[0]}_b0.csv", index=False, header=True)
        selected_points_file = "batch_0/cluster_selected_points.csv"
        if os.path.exists(selected_points_file):
            os.remove(selected_points_file)

        coverage_descriptor_importance_df = compute_cluster_descriptor_importance(
            coverage_result["descriptor_df"],
            coverage_result["selection_region_labels"],
        )
        coverage_descriptor_importance_df.to_csv(
            "batch_0/coverage_descriptor_importance.csv",
            index=False,
        )

        self.args.log.write("\no Descriptors most associated with selection regions:")
        self.args.log.write(
            "   - These descriptors explain the nearest-selected regions used to choose "
            "representative molecules."
        )
        self.args.log.write(
            "   - They do not imply natural clusters; they describe which descriptors "
            "drive coverage of the chemical space."
        )
        if coverage_descriptor_importance_df.empty:
            self.args.log.write(
                "   - Not available: at least two selection regions are required."
            )
        else:
            self.args.log.write(
                "   - F is an ANOVA-style between-region / within-region separation score."
            )
            self.args.log.write(
                "   - eta2 is the fraction of descriptor variance explained by the selection regions."
            )
            for _, row in coverage_descriptor_importance_df.head(10).iterrows():
                self.args.log.write(
                    f"   - #{int(row['rank'])} {row['descriptor']}: "
                    f"F={row['f_score']:.6g}, eta2={row['eta_squared']:.6g}"
                )

        self.args.log.write("\no Saved coverage selection outputs:")
        self.args.log.write(f"   - batch_0/{csv[0]}_b0.csv")
        self.args.log.write("   - batch_0/coverage_descriptor_importance.csv")
        self.args.log.write(f"   - {viewer_path}")
        self.args.log.write(f"\no Selected representative molecules for ({file_name})")
