#######################################################
#        This file contains the argument parser       #
#######################################################


var_dict = {
    "varfile": None,
    "extra_cmd": '',
    "verbose": True,
    "command_line": False,
    "csv_name": None,
    "input": None,
    "n_clusters": None,
    "n_clusters_max": None,
    "n_points": None,
    "n_exps": 1,
    "batch_number": None,
    "seed_clustered": 0,
    "descp_level": "interpret",
    "ignore": [],
    "cluster": False,
    "evaluate": False,
    "aqme_keywords": '',
    "aqme": False,
    "name": '',
    "y": '',
    "auto_fill": True,
    "categorical": "onehot",
    "missing_threshold": 0.30,
    "near_constant_threshold": 0.98,
    "iqr_threshold": 1e-6,
    "rel_threshold": 0.02,
    "binary_threshold": 0.05,
    "correlation_threshold": 0.95,
    "min_descriptors": 2,
    "algorithms": ["kmeans", "gmm", "hdbscan"],
    "cluster_stability_repeats": 5,
    "cluster_subsample_fraction": 0.8,
    "hdbscan_enabled": True,
    "cluster_high_dimensionality_threshold": 80,
    "enable_pca": True,
    "cluster_pca_explained_variance_threshold": 0.95,
    "cluster_pca_min_acceptable_variance": 0.85,
    "cluster_pca_min_components": 2,
    "pca_max_components": 100,
    "pca_max_components_fraction": 0.75,
    "large_dataset_mode": True,
    "cluster_standard_dataset_threshold": 2000,
    "cluster_very_large_dataset_threshold": 10000,
    "cluster_ultra_large_dataset_threshold": 25000,
    "cluster_large_silhouette_sample_size": 1500,
    "cluster_very_large_silhouette_sample_size": 2000,
    "cluster_ultra_large_silhouette_sample_size": 3000,
    "cluster_large_dataset_stability_repeats": 3,
    "cluster_fast_screening_top_candidates": 3,
    "cluster_kmeans_coarse_grid_size": 10,
    "cluster_kmeans_top_refinement_candidates": 1,
    "cluster_kmeans_refine_radius": 2,
    "cluster_kmeans_bo_fraction": 0.20,
    "cluster_kmeans_bo_max_evaluations": 30,
    "cluster_gmm_dimensionality_threshold": 50,
    "cluster_gmm_standard_coarse_grid_size": 9,
    "cluster_gmm_standard_refine_radius": 3,
    "cluster_gmm_large_coarse_grid_size": 5,
    "cluster_gmm_large_refine_radius": 2,
    "cluster_gmm_very_large_coarse_grid_size": 5,
    "cluster_gmm_very_large_refine_radius": 1,
    "cluster_gmm_bo_fraction": 0.08,
    "cluster_gmm_bo_max_evaluations": 16,
    "cluster_gmm_bic_shortlist_size": 3,
    "cluster_auto_budget_candidates": [
        20, 30, 40, 50, 60, 70, 80, 90, 100,
        125, 150, 175, 200,
        250, 300, 350, 400, 450, 500,
    ],
    "cluster_auto_budget_min_points": 20,
    "cluster_auto_budget_max_points": 10000,
    "cluster_auto_budget_sqrt_factor": 5.0,
    "cluster_auto_budget_marginal_gain_threshold": 0.05,
    "cluster_auto_budget_min_umap_area": 0.85,
    "cluster_auto_budget_lookahead": 2,
    "cluster_auto_budget_coverage_sample_size": 10000,
    "mode": "representative",
    "cluster_natural_report": False,
    "cluster_filter_max_noise_fraction": 0.20,
    "cluster_filter_max_cluster_fraction": 0.85,
    "cluster_filter_max_imbalance_penalty": 0.90,
    "cluster_quality_warning_silhouette_threshold": 0.10,
    "cluster_quality_warning_stability_threshold": 0.40,
    "cluster_quality_warning_noise_threshold": 0.30,
    "cluster_quality_warning_imbalance_threshold": 0.40,
    "cluster_quality_warning_final_score_threshold": 0.35,
    "cluster_quality_good_silhouette_threshold": 0.25,
    "cluster_quality_good_stability_threshold": 0.80,
    "cluster_quality_good_noise_threshold": 0.10,
    "cluster_quality_good_imbalance_threshold": 0.30,
    "cluster_quality_good_final_score_threshold": 0.60,
    "cluster_hdbscan_standard_min_cluster_ratios": [0.005, 0.01, 0.02, 0.05],
    "cluster_hdbscan_large_min_cluster_ratios": [0.005, 0.01, 0.02, 0.05],
    "cluster_hdbscan_very_large_min_cluster_ratios": [0.01, 0.02, 0.05],
    "cluster_hdbscan_standard_min_samples": [1, 5, 10],
    "cluster_hdbscan_large_min_samples": [1, 5, 10],
    "cluster_hdbscan_very_large_min_samples": [1, 5],
    "al": False,
    'explore_rt': 1,
    'batch_column': 'batch',
    'tolerance': 'medium',
    'objective': None,
    'alpha': None,
    'al_mode': None,
    'levels_tolerance': {  
        'tight': 0.01,
        'medium': 0.05,
        'wide': 0.10,
    },
    'nprocs': 8,
    "robert_keywords" : '',
}

NEGATED_BOOL_ALIASES = {
    "no_pca": "enable_pca",
    "no_large_dataset_mode": "large_dataset_mode",
}

BOOL_ARGS = [
    "cluster",
    "evaluate",
    "al",
    "aqme",
    "cluster_natural_report",
]

INT_ARGS = [
    "n_clusters",
    "n_clusters_max",
    "n_points",
    "seed_clustered",
    "nprocs",
    "n_exps",
    "batch_number",
    "min_descriptors",
    "cluster_stability_repeats",
    "cluster_high_dimensionality_threshold",
    "cluster_pca_min_components",
    "pca_max_components",
    "cluster_standard_dataset_threshold",
    "cluster_very_large_dataset_threshold",
    "cluster_ultra_large_dataset_threshold",
    "cluster_large_silhouette_sample_size",
    "cluster_very_large_silhouette_sample_size",
    "cluster_ultra_large_silhouette_sample_size",
    "cluster_large_dataset_stability_repeats",
    "cluster_fast_screening_top_candidates",
    "cluster_kmeans_coarse_grid_size",
    "cluster_kmeans_top_refinement_candidates",
    "cluster_kmeans_refine_radius",
    "cluster_kmeans_bo_max_evaluations",
    "cluster_gmm_dimensionality_threshold",
    "cluster_gmm_standard_coarse_grid_size",
    "cluster_gmm_standard_refine_radius",
    "cluster_gmm_large_coarse_grid_size",
    "cluster_gmm_large_refine_radius",
    "cluster_gmm_very_large_coarse_grid_size",
    "cluster_gmm_very_large_refine_radius",
    "cluster_gmm_bo_max_evaluations",
    "cluster_gmm_bic_shortlist_size",
    "cluster_auto_budget_min_points",
    "cluster_auto_budget_max_points",
    "cluster_auto_budget_lookahead",
    "cluster_auto_budget_coverage_sample_size",
]

LIST_ARGS = [
    "ignore",
    "algorithms",
    "cluster_hdbscan_standard_min_cluster_ratios",
    "cluster_hdbscan_large_min_cluster_ratios",
    "cluster_hdbscan_very_large_min_cluster_ratios",
    "cluster_hdbscan_standard_min_samples",
    "cluster_hdbscan_large_min_samples",
    "cluster_hdbscan_very_large_min_samples",
    "cluster_auto_budget_candidates",
]

FLOAT_ARGS = [
    "explore_rt",
    "missing_threshold",
    "near_constant_threshold",
    "iqr_threshold",
    "rel_threshold",
    "binary_threshold",
    "correlation_threshold",
    "cluster_subsample_fraction",
    "cluster_pca_explained_variance_threshold",
    "cluster_pca_min_acceptable_variance",
    "pca_max_components_fraction",
    "cluster_filter_max_noise_fraction",
    "cluster_filter_max_cluster_fraction",
    "cluster_filter_max_imbalance_penalty",
    "cluster_quality_warning_silhouette_threshold",
    "cluster_quality_warning_stability_threshold",
    "cluster_quality_warning_noise_threshold",
    "cluster_quality_warning_imbalance_threshold",
    "cluster_quality_warning_final_score_threshold",
    "cluster_quality_good_silhouette_threshold",
    "cluster_quality_good_stability_threshold",
    "cluster_quality_good_noise_threshold",
    "cluster_quality_good_imbalance_threshold",
    "cluster_quality_good_final_score_threshold",
    "cluster_auto_budget_sqrt_factor",
    "cluster_auto_budget_marginal_gain_threshold",
    "cluster_auto_budget_min_umap_area",
    "alpha",
]

CLUSTER_ALGORITHM_CHOICES = {"kmeans", "gmm", "hdbscan"}
AL_OPTION_ALIASES = {
    "alfa": "alpha",
}

# part for using the options in a script or jupyter notebook
class options_add:
    pass

def set_options(kwargs):
    """
    Combine default settings with user-provided arguments.

    This function merges the defaults from 'var_dict' with the values in 'kwargs'.
    User-provided arguments override defaults, and all options are returned as
    attributes of an object. Unrecognized arguments trigger a warning.

    Parameters:
    -----------
    kwargs : dict
        User-provided arguments to override default settings.
        From 'command_line_args()' function.

    Returns:
    --------
    options : options_add
        Object containing all configuration options as attributes.
    
    """
    # set default options and options provided
    options = options_add()
    
    # dictionary containing default values for options
    for key in var_dict:
        vars(options)[key] = var_dict[key]
    for key in kwargs:
        normalized_key = key if key in var_dict else key.lower()
        if normalized_key in var_dict:
            vars(options)[normalized_key] = kwargs[key]
        else:
            print("Warning! Option: [", key,":",kwargs[key],"] provided but no option exists, try the online documentation to see available options for each module.",)

    return options
