"""
Parameters
----------
    al : bool
        Indicates whether the active learning process is enabled and should be performed. Defaults to "False".
        This parameter is activated in command line (i.e. --al)
    csv_name : str
        Name of the CSV file containing the database. (i.e. 'FILE.csv'). 
    y : str
        Name of the column containing the response variable in the input CSV file (i.e. 'solubility'). 
    name : str
        Name of the column containing the molecule names in the input CSV file (i.e. 'names').
    ignore : list, default=[]
        List containing the columns of the input CSV file that will be ignored during the ROBERT process
        (i.e. --ignore "[name,SMILES]"). The descriptors will be included in the final CSV file. The y value, name column and batch column
        are automatically ignored by ROBERT.  
    n_exps : int,
        Number of experiments to be selected in the active learning process for the new batch. (i.e. '--n_exps 10')
        If not provided or invalid, the program will request the values in the proper format.
    tolerance : str, default='medium'
        Indicates the tolerance level for the convergence process, defining the percentage change threshold required for convergence. Options:
        1. 'tight': Strictest level, convergence occurs if the metric improves by ≤1% (threshold = 0.01).
        2. 'medium': Balanced level, convergence occurs if the metric improves by ≤5% (threshold = 0.05).
        3. 'wide': Least strict, convergence occurs if the metric improves by ≤10% (threshold = 0.10).
        (i.e. '--tolerance tight')
    robert_keywords : str, default=""
        Additional keywords to be passed to the ROBERT model generation (i.e. --robert_keywords "--model RF --train [70] --seed [0]")
    objective : str
        Optimization direction for hit selection. Always required and must be 'max' or 'min'. (i.e. '--objective max')
    mode : str, optional
        Optional manual override for the acquisition strategy. Use 'model' to rank by uncertainty or 'hit' to rank by
        prediction with uncertainty. If omitted, ALMOS selects the strategy automatically from the model score.
    alpha : float, optional
        Optional acquisition weight used in hit mode. It also overrides the automatic alpha when the strategy is auto
        and the selected score activates hit ranking. (i.e. '--alpha 0.5' or '--alfa 0.5')
"""

#####################################################
#           This file stores the AL class           #
#        used in the active learning process        #
#####################################################

import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

import matplotlib
import numpy as np
import pandas as pd
matplotlib.use('Agg')  # Use 'Agg' backend for non-interactive plotting
from almos.utils import (
    Logger,
    csv_safe_identifiers,
    persist_failed_al_log,
    write_run_manifest,
    load_variables,
    check_dependencies
)
from almos.al_utils import (
    get_metrics_from_batches,
    EarlyStopping,
    plot_metrics_subplots,
    get_scores_from_robert_report,
    resolve_active_learning_strategy,
    rank_active_learning_candidates,
    write_log_header,
    write_log_block,
    format_objective_label,
    format_strategy_label,
    format_strategy_reason,
    format_score_regime_label,
    format_score_interpretation,
    format_score_explanation,
    build_selected_candidates_preview,
    format_text_table,
)


class al:
    """
    Class containing all the functions from the active almos module

    """
    def __init__(self, **kwargs):

        # Initialize the timer
        start_time_overall = time.time()
        
        # load default and user-specified variables
        self.args = load_variables(kwargs, "al")

        try:
            check_dependencies(self, "al")
            self.run_robert_process()
            self.active_learning_process()
            self.finalize_process(start_time_overall)
        except (SystemExit, Exception) as error:
            persist_failed_al_log(self.args, error)
            raise

        self.update_convergence_monitoring()

    def update_convergence_monitoring(self):
        """Refresh campaign-wide diagnostics after publishing the selected batch."""
        try:
            self.args.log = Logger(self.data_path / "AL", "data", verbose=self.args.verbose, mode="a")
        except OSError as error:
            print(f"Warning: could not reopen the completed batch log: {error}")
            return
        try:
            no_pfi, pfi = get_metrics_from_batches(self.args.log)
            if no_pfi and pfi:
                tolerance = self.args.levels_tolerance[self.args.tolerance]
                early_stopping = EarlyStopping(
                    logger=self.args.log, rmse_min_delta=tolerance, sd_min_delta=tolerance,
                )
                self.generate_plots(*early_stopping.check_convergence(no_pfi, pfi))
            else:
                self.args.log.write("Convergence monitoring unavailable: no complete batch metrics were found.")
        except (OSError, ValueError) as error:
            self.args.log.write(f"Warning: could not update convergence monitoring: {error}")
        finally:
            self.args.log.finalize()

    def run_robert_process(self):
        """
        Executes the full ROBERT model update and prediction process.

        This method performs the following steps:
        - Initializes a logger to record process details and parameters.
        - Filters the input data to create a CSV file for updating the ROBERT model.
        - Creates necessary directories and moves files as required.
        - Runs the ROBERT model update command, including the prediction CSV via ``--csv_test``.
        - Checks for successful generation of the model report.
        - Verifies that predictions were successfully created and logs the result.

        Raises:
            SystemExit: Exits the program if any step fails or if required files are not found.
        """
        # Get the base name of the CSV file without the extension if the csv is introduced as path 
        self.args.csv_name = os.path.basename(self.args.csv_name)
        self.args.base_name_raw = os.path.splitext(self.args.csv_name)[0]

        # Handle cases of different batches (i.e test_b1, test_b2, etc), in order to extract the base name.
        base_name = os.path.splitext(self.args.csv_name)[0]
        match = re.match(r"^(.*)_b\d+$", base_name)
        if match:
            # If the name matches the pattern, extract the base name
            self.args.base_name = match.group(1)
        else:
            # Otherwise, use the entire base name
            self.args.base_name = self.args.base_name_raw

        # Initialize the logger
        write_log_header(self.args.log, "Starting Active Learning Process")
        write_log_block(
            self.args.log,
            "Input summary",
            [
                ("Data file", self.args.csv_name),
                ("Identifier column", self.args.name),
                ("Target column", self.args.y),
                ("Experiments requested", self.args.n_exps),
                (
                    "Optimization objective",
                    format_objective_label(self.args.objective)
                    if self.args.al_mode != "model"
                    else "not used in model mode",
                ),
                ("Selection mode request", self.args.al_mode or "auto"),
                (
                    "Alpha override",
                    "automatic" if self.args.alpha is None else self.args.alpha,
                ),
                ("Ignored columns", self.args.ignore),
                (
                    "Convergence tolerance",
                    f"{self.args.tolerance} ({self.args.levels_tolerance[self.args.tolerance] * 100:.2f}%)",
                ),
            ],
        )

        # Main directory for the process
        self.main_folder = Path.cwd()
        self.robert_folder = f'ROBERT_b{self.args.current_number_batch}'
        robert_path = Path(tempfile.mkdtemp(prefix=f".{self.robert_folder}-", dir=self.main_folder))
        self.robert_path = robert_path
        filename_model_csv = robert_path / f"{self.args.base_name}_ROBERT_b{self.args.current_number_batch}.csv"
        destination = robert_path / self.args.csv_name
        if " " in filename_model_csv.name:
            filename_model_csv = robert_path / "training.csv"
        if " " in destination.name:
            destination = robert_path / "prediction_input.csv"
        robert_data = self.args.df_raw.copy()
        identifiers = robert_data[self.args.name]
        self.robert_identifiers = csv_safe_identifiers(identifiers)
        robert_data[self.args.name] = self.robert_identifiers
        if not self.robert_identifiers.equals(identifiers):
            pd.DataFrame({"candidate_id": identifiers, "robert_id": self.robert_identifiers}).to_csv(
                robert_path / "candidate_id_mapping.csv", index=False,
            )
        robert_model_df = robert_data[robert_data[self.args.batch_column].notna()]
        robert_model_df.to_csv(filename_model_csv, index=False)
        robert_data.to_csv(destination, index=False)

        robert_ignore_predict = self._sanitize_ignore_columns(self.args.df_raw.columns)
        robert_ignore_predict_cli = self._format_robert_ignore(robert_ignore_predict)

        # Build and run the command for updating the ROBERT model
        keywords = shlex.shlex(self.args.robert_keywords, posix=True)
        keywords.whitespace_split = True
        keywords.commenters = ""
        if os.name == "nt":
            keywords.escape = ""
        command = [
            sys.executable, "-u", "-m", "robert", "--csv_name", filename_model_csv.name,
            "--csv_test", destination.name, "--names", self.args.name, "--y", self.args.y,
            "--ignore", robert_ignore_predict_cli, *keywords,
        ]

        write_log_header(self.args.log, "ROBERT Model Update")
        write_log_block(
            self.args.log,
            "Training data prepared",
            [
                ("Rows used for model update", len(robert_model_df)),
                ("Working folder", robert_path.name),
                ("Training CSV", filename_model_csv.name),
                ("Prediction CSV", destination.name),
                ("ROBERT ignore list", robert_ignore_predict_cli),
            ],
        )

        # Run the command and check for errors
        exit_code = subprocess.run(command, cwd=robert_path).returncode
        if exit_code != 0:
            self.args.log.write(f"x WARNING! Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Check if the ROBERT model report was generated
        if (robert_path / "ROBERT_report.pdf").is_file():
            write_log_block(
                self.args.log,
                "ROBERT update result",
                [
                    ("Status", "model generated successfully"),
                    ("Report file", "ROBERT_report.pdf"),
                ],
            )
        else:
            self.args.log.write("\nx WARNING! ROBERT model was not generated\n")
            sys.exit(1)

        # Predictions are generated in the same ROBERT run via --csv_test.
        write_log_header(self.args.log, "Prediction Generation")
        write_log_block(
            self.args.log,
            "Prediction request",
            [
                ("Prediction CSV", destination.name),
                ("ROBERT ignore list", robert_ignore_predict_cli),
                ("Execution mode", "generated during model update with --csv_test"),
            ],
        )

        # Get scores from PDF to decide which prediction to use
        pdf_path = robert_path / "ROBERT_report.pdf"
        score_no_PFI, score_PFI = get_scores_from_robert_report(pdf_path)
        use_pfi = False
        if score_PFI is not None and (score_no_PFI is None or score_PFI >= score_no_PFI):
            use_pfi = True
        self.selected_model_type = "PFI" if use_pfi else "No_PFI"
        self.selected_model_score = score_PFI if use_pfi else score_no_PFI
        write_log_block(
            self.args.log,
            "Prediction model comparison",
            [
                ("No_PFI score", score_no_PFI),
                ("PFI score", score_PFI),
                ("Selected prediction model", self.selected_model_type),
                ("Selected model score", self.selected_model_score),
            ],
        )

        # Define search path
        search_path = robert_path / "PREDICT" / "csv_test"

        # Find the correct prediction file
        if use_pfi:
            matching_files = [f for f in search_path.glob("*.csv") if f.name.endswith("_PFI.csv") and "No_PFI" not in f.name]
        else:
            matching_files = [f for f in search_path.glob("*.csv") if f.name.endswith("_No_PFI.csv")]

        self.path_predictions = matching_files[0] if matching_files else None

        if self.path_predictions and self.path_predictions.exists():
            if os.path.exists(destination):
                os.remove(destination)
            write_log_block(
                self.args.log,
                "Prediction output",
                [
                    ("Prediction CSV used", self.path_predictions.name),
                    ("Prediction source", f"{'PFI' if use_pfi else 'No_PFI'} predictions"),
                    ("ROBERT ignore list", robert_ignore_predict_cli),
                ],
            )
        else:
            self.args.log.write(f"x WARNING! Predictions were not generated in {self.path_predictions}")
            sys.exit(1)

    def _sanitize_ignore_columns(self, available_columns):
        """
        Keep only ignore columns that exist in the CSV passed to ROBERT.
        """
        available_column_set = set(available_columns)
        robert_ignore = []
        for column in self.args.ignore:
            if column in available_column_set and column not in robert_ignore:
                robert_ignore.append(column)
        return robert_ignore

    def _format_robert_ignore(self, ignore_columns):
        """
        Format ignore columns using ROBERT's CLI list style, e.g. [batch,SMILES].
        """
        return "[" + ",".join(map(str, ignore_columns)) + "]"

    def active_learning_process(self):
        """Align predictions by identifier, rank eligible candidates, and publish the batch."""
        identifier_column = self.args.name
        predictions_column = f'{self.args.y}_pred'
        sd_column = f'{predictions_column}_sd'
        df_raw_copy = self.args.df_raw.copy()
        pool_mask = df_raw_copy[self.args.batch_column].isna()
        pool_ids = self.robert_identifiers.loc[pool_mask]
        df_predictions = pd.read_csv(self.path_predictions, converters={identifier_column: str})
        required_columns = {identifier_column, predictions_column, sd_column}
        missing_columns = required_columns.difference(df_predictions.columns)
        if missing_columns:
            self.args.log.write(f"Prediction output is missing columns: {sorted(missing_columns)}.")
            raise SystemExit(1)
        prediction_ids = df_predictions[identifier_column]
        if prediction_ids.str.strip().eq("").any() or prediction_ids.duplicated().any():
            self.args.log.write("Prediction output must contain unique, non-empty identifiers.")
            raise SystemExit(1)
        predicted_index = pd.Index(prediction_ids)
        missing_ids = pd.Index(pool_ids).difference(predicted_index)
        unexpected_ids = predicted_index.difference(self.robert_identifiers)
        if len(missing_ids) or len(unexpected_ids):
            self.args.log.write(
                f"Prediction identifiers do not match the input. Missing ({len(missing_ids)}): "
                f"{missing_ids[:8].tolist()}; unexpected ({len(unexpected_ids)}): {unexpected_ids[:8].tolist()}."
            )
            raise SystemExit(1)

        predictions_df = df_raw_copy.loc[pool_mask, [identifier_column]].copy()
        aligned = df_predictions.set_index(identifier_column).loc[pool_ids, [predictions_column, sd_column]]
        aligned.index = predictions_df.index
        predictions_df[[predictions_column, sd_column]] = aligned.apply(pd.to_numeric, errors="coerce")
        eligible = (
            np.isfinite(predictions_df[predictions_column])
            & np.isfinite(predictions_df[sd_column])
            & predictions_df[sd_column].ge(0)
        )
        excluded_predictions = predictions_df.loc[~eligible]
        predictions_df = predictions_df.loc[eligible]
        if predictions_df.empty:
            self.args.log.write("No candidates have finite predictions and valid uncertainty values.")
            raise SystemExit(1)

        write_log_header(self.args.log, f"Batch {self.args.current_number_batch} Selection")

        strategy = resolve_active_learning_strategy(
            score=self.selected_model_score,
            objective=self.args.objective,
            mode=self.args.al_mode,
            alpha_override=self.args.alpha,
        )
        selected_count = min(self.args.n_exps, len(predictions_df))
        ranked_candidates = rank_active_learning_candidates(
            predictions_df,
            strategy,
            predictions_column,
            sd_column,
            selection_size=selected_count,
            identifier_column=identifier_column,
        )
        selected_candidates = ranked_candidates.head(selected_count).copy()
        last_score = selected_candidates["_ranking_metric"].iloc[-1]
        tied_at_cutoff = int(ranked_candidates["_ranking_metric"].eq(last_score).sum())
        self.selection_summary = {
            "batch": self.args.current_number_batch,
            "selected_count": selected_count,
            "eligible_count": len(ranked_candidates),
            "excluded_count": len(excluded_predictions),
            "strategy": strategy["strategy"],
            "model": self.selected_model_type,
            "model_score": self.selected_model_score,
            "objective": strategy["objective"],
            "alpha": strategy["alpha"],
        }

        acquisition_rows = [
            ("Prediction model used", self.selected_model_type),
            ("Model score used", self.selected_model_score),
            ("Model score interpretation", format_score_interpretation(self.selected_model_score)),
            ("What this means", format_score_explanation(strategy)),
            ("Resolved strategy", format_strategy_label(strategy["strategy"])),
            ("Why this strategy", format_strategy_reason(strategy)),
            (
                "Objective",
                "not used in model mode"
                if strategy["strategy"] == "model"
                else format_objective_label(strategy["objective"]),
            ),
            ("Score regime", format_score_regime_label(strategy)),
            (
                "Alpha used",
                "not used" if strategy["strategy"] == "model" else strategy["alpha"],
            ),
            (
                "Ranking rule",
                selected_candidates["_acquisition_label"].iloc[0] if selected_count else "n/a",
            ),
            ("Candidates available", int(pool_mask.sum())),
            ("Candidates excluded due to invalid predictions", len(excluded_predictions)),
            ("Candidates tied at the selection cutoff", tied_at_cutoff),
            ("Final tie-break", f"ascending identifier ({identifier_column})"),
            ("Experiments requested", self.args.n_exps),
            ("Points selected", selected_count),
        ]

        write_log_block(
            self.args.log,
            "Acquisition decision",
            acquisition_rows,
        )

        if selected_count:
            ranked_preview = build_selected_candidates_preview(
                selected_candidates,
                self.args.name,
                predictions_column,
                sd_column,
            )
            self.args.log.write("\nSelected candidates")
            self.args.log.write(
                format_text_table(
                    ranked_preview,
                    max_widths={"candidate": 72},
                )
            )

        df_raw_copy.loc[selected_candidates.index, self.args.batch_column] = self.args.current_number_batch

        # Build the filename for the updated dataset and save it
        # Sort entire DataFrame by batch descending, keeping NaNs at the end
        df_raw_copy = df_raw_copy.sort_values(by=self.args.batch_column, ascending=False, na_position="last", kind="stable")
        output_file = f"{self.args.base_name}_b{self.args.current_number_batch}.csv"
        self.data_path = Path.cwd() / f'batch_{self.args.current_number_batch}'
        ranking_file = "candidate_ranking.csv"
        ranking = pd.DataFrame({
            "rank": range(1, len(ranked_candidates) + 1),
            "candidate_id": ranked_candidates[identifier_column].to_numpy(),
            "prediction": ranked_candidates[predictions_column].to_numpy(),
            "uncertainty": ranked_candidates[sd_column].to_numpy(),
            "ranking_score": ranked_candidates["_ranking_metric"].to_numpy(),
            "selected": ranked_candidates.index.isin(selected_candidates.index),
        })
        self.staging_path = Path(tempfile.mkdtemp(prefix=f".{self.data_path.name}-", dir=self.data_path.parent))
        df_raw_copy.to_csv(self.staging_path / output_file, index=False)
        ranking.to_csv(self.staging_path / ranking_file, index=False)
        if not excluded_predictions.empty:
            excluded_predictions.to_csv(self.staging_path / "excluded_predictions.csv", index=False)
        shutil.move(self.robert_path, self.staging_path / self.robert_folder)

        write_log_block(
            self.args.log,
            "Saved outputs",
            [
                ("Batch folder", f"batch_{self.args.current_number_batch}"),
                ("Updated dataset", output_file),
                ("Complete candidate ranking", ranking_file),
                ("ROBERT results", self.robert_folder),
            ],
        )

    def generate_plots(self, results_plot_no_pfi_df, results_plot_pfi_df):
        """
        Generates and saves subplots for each model type (no_PFI and PFI) 
        and logs a confirmation message upon successful completion.
        
        Parameters
        ----------
        results_plot_no_pfi_df : pd.DataFrame
            DataFrame containing the results for the 'no_PFI' model.
        results_plot_pfi_df : pd.DataFrame
            DataFrame containing the results for the 'PFI' model.
        """
        for model_type, df in [('no_PFI', results_plot_no_pfi_df), ('PFI', results_plot_pfi_df)]:
            plot_metrics_subplots(df, model_type, output_dir="batch_plots", batch_count = self.args.current_number_batch)

        write_log_header(self.args.log, "Plot Generation Summary")
        write_log_block(
            self.args.log,
            "Generated monitoring plots",
            [
                ("No_PFI plot folder", "batch_plots/no_PFI_plots"),
                ("PFI plot folder", "batch_plots/PFI_plots"),
                ("Status", "subplot figures generated successfully"),
            ],
        )
        
    def finalize_process(self, start_time_overall):
        """Publish the completed batch only after all required artifacts exist."""
        
        elapsed_time = round(time.time() - start_time_overall, 2)
        log_file = self.args.log.path
        artifacts = sorted(path.name for path in self.staging_path.iterdir())
        if log_file is not None:
            artifacts.append("AL_data.dat")
        write_run_manifest(
            self.args, self.staging_path, module="al", input_path=self.args.path_csv_name,
            artifacts=artifacts, summary={**self.selection_summary, "duration_seconds": elapsed_time},
        )

        write_log_header(self.args.log, "Active Learning Process Completed")
        write_log_block(
            self.args.log,
            "Run summary",
            [
                ("Final batch number", self.args.current_number_batch),
                ("Status", "completed"),
                ("Output folder", f"batch_{self.args.current_number_batch}"),
                ("Total runtime (s)", f"{elapsed_time:.2f}"),
            ],
        )
        self.args.log.finalize()

        if log_file is not None:
            shutil.copyfile(log_file, self.staging_path / "AL_data.dat")
        if self.data_path.exists():
            raise FileExistsError(f"Output directory '{self.data_path}' already exists.")
        self.staging_path.rename(self.data_path)
        if log_file is not None:
            try:
                log_file.unlink(missing_ok=True)
            except OSError as error:
                print(f"Warning: could not remove the staged log: {error}")
