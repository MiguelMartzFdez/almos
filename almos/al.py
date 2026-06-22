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

import pandas as pd
import time
import os , sys
from pathlib import Path
import re
import shutil
import matplotlib
matplotlib.use('Agg')  # Use 'Agg' backend for non-interactive plotting
from almos.utils import (
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

        # Check runtime dependencies required by AL
        _ = check_dependencies(self, "al")
        
        # run robert model updated and generate predictions
        self.run_robert_process()

        # run active learning process for selecting points for the new batch
        self.active_learning_process()

        # Check for convergence in the batches
        # Get metrics from batches
        results_plot_no_PFI, results_plot_PFI = get_metrics_from_batches()

        # Initialize EarlyStopping to check for convergence
        early_stopping = EarlyStopping(
            logger=self.args.log,
            rmse_min_delta = self.args.levels_tolerance[self.args.tolerance],
            sd_min_delta = self.args.levels_tolerance[self.args.tolerance],
        )
        
        results_plot_no_pfi_df, results_plot_pfi_df = early_stopping.check_convergence(
            results_plot_no_PFI, results_plot_PFI
        )
    
        # Generate plots
        self.generate_plots(results_plot_no_pfi_df, results_plot_pfi_df)

        # Log the total time and finalize
        self.finalize_process(start_time_overall)

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
        self.main_folder = os.getcwd()
        
        # Filter rows where value in the batch_column is not NaN for updating the model
        robert_model_df = self.args.df_raw[self.args.df_raw[self.args.batch_column].notna()]

        # Ensure the folder for ROBERT model results exists
        self.robert_folder = f'ROBERT_b{self.args.current_number_batch}'
        robert_path = Path(self.main_folder) / self.robert_folder
        robert_path.mkdir(parents=True, exist_ok=True)

        # Create and save the CSV file inside the folder
        filename_model_csv = robert_path / f"{self.args.base_name}_ROBERT_b{self.args.current_number_batch}.csv"
        try:
            robert_model_df.to_csv(filename_model_csv, index=False)
            print(f"o File successfully saved: {filename_model_csv}")

        except Exception as e:
            print(f"x WARNING! Could not save the file: {e}")
            sys.exit()

        # Change to the newly created ROBERT directory
        os.chdir(robert_path)

        robert_ignore_update = self._sanitize_ignore_columns(robert_model_df.columns)
        robert_ignore_update_cli = self._format_robert_ignore(robert_ignore_update)

        # Define paths for the source file and destination directory
        source = os.path.join(self.args.path_csv_name)
        destination_dir = Path(Path.cwd().parent, self.robert_folder)  # Ensure destination is a directory
        destination_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
        destination = destination_dir / Path(source).name  # Complete path for the destination file

        # Check if the source file exists before copying
        if os.path.isfile(source):
            # Copy the file from source to destination so ROBERT can train and predict in one run
            shutil.copy(source, destination)
        else:
            print(f"o File '{self.args.csv_name}' was not found for generate predictions! Exiting.")

        robert_ignore_predict = self._sanitize_ignore_columns(self.args.df_raw.columns)
        robert_ignore_predict_cli = self._format_robert_ignore(robert_ignore_predict)

        # Build and run the command for updating the ROBERT model
        command = (
            f'python -u -m robert --csv_name "{filename_model_csv}" '
            f'--csv_test "{destination}" '
            f'--name "{self.args.name}" '
            f'--y {self.args.y} '
            f'--ignore "{robert_ignore_predict_cli}" '
            f'{self.args.robert_keywords}'
        )

        write_log_header(self.args.log, "ROBERT Model Update")
        write_log_block(
            self.args.log,
            "Training data prepared",
            [
                ("Rows used for model update", len(robert_model_df)),
                ("Working folder", self.robert_folder),
                ("Training CSV", filename_model_csv.name),
                ("Prediction CSV", destination.name),
                ("ROBERT ignore list", robert_ignore_predict_cli),
            ],
        )

        # Run the command and check for errors
        exit_code = os.system(command)
        if exit_code != 0:
            self.args.log.write(f"x WARNING! Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Check if the ROBERT model report was generated
        if os.path.exists('ROBERT_report.pdf'):
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
            sys.exit()

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
            sys.exit()

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
        """
        Main function for the active learning process, including:
        - Reading and concatenating predictions with the raw data.
        - Splitting data into experimental and prediction sets.
        - Ranking candidates either by uncertainty or by hit acquisition.
        - Updating the dataset and saving results into organized batch folders.
        
        This process manages active learning cycles through one acquisition strategy per batch.
        """
        
        # Read predictions from ROBERT and concatenate with the raw data
        df_predictions = pd.read_csv(self.path_predictions)

        # Move to the parent directory
        parent_directory = Path.cwd() / '..'
        os.chdir(parent_directory) 
        
        # Add predictions and prediction SD to the original dataframe
        predictions_column = f'{self.args.y}_pred'
        sd_column = f'{predictions_column}_sd'
        self.args.df_raw[[predictions_column, sd_column]] = df_predictions[[predictions_column, sd_column]]

        # Check if all predictions are equal (firewall)
        if df_predictions[predictions_column].nunique() == 1:
            self.args.log.write(
                "\nx WARNING: All prediction values are identical. Active Learning process will stop.\n"
                f"Predicted value: {df_predictions[predictions_column].iloc[0]}\n"
                "This typically means that the machine learning model cannot find a pattern in the data.\n"
                "Possible reasons:\n"
                "- The molecular descriptors do not capture enough relevant information about the molecules.\n"
                "- The problem is too complex for the current model.\n"
                "- There are not enough data points to train a predictive model.\n"
                "Please review your data and descriptor selection, or try adding more experiments.\n"
            )
            print("\n[ALMOS] Process stopped: all prediction values are identical.")
            sys.exit(0)
        
        # Filter the DataFrame into experimental and predictions data
        df_raw_copy = self.args.df_raw.copy()
        predictions_df = df_raw_copy[df_raw_copy[self.args.batch_column].isna()]

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
        )
        selected_candidates = ranked_candidates.head(selected_count).copy()

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
            ("Candidates available", len(ranked_candidates)),
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

        predictions_copy_df = predictions_df.copy()
        predictions_copy_df.loc[selected_candidates.index, self.args.batch_column] = self.args.current_number_batch

        # Update batch column after exploration and exploitation
        df_raw_copy[self.args.batch_column] = df_raw_copy[self.args.batch_column].combine_first(predictions_copy_df[self.args.batch_column])
        # Drop predictions columns and save updated results
        df_raw_copy.drop([predictions_column, sd_column], axis=1, inplace=True)

        # Build the filename for the updated dataset and save it
        # Sort entire DataFrame by batch descending, keeping NaNs at the end
        df_raw_copy = df_raw_copy.sort_values(by=self.args.batch_column, ascending=False, na_position='last')
        output_file = f"{self.args.base_name}_b{self.args.current_number_batch}.csv"
        df_raw_copy.to_csv(output_file, index=False)

        # Create a batch directory and move relevant files
        self.data_path = Path.cwd() / f'batch_{self.args.current_number_batch}'
        self.data_path.mkdir(parents=True, exist_ok=True)

        # Move the files to the proper batch folder
        shutil.move(self.robert_folder, self.data_path)
        shutil.move(output_file, self.data_path)

        write_log_block(
            self.args.log,
            "Saved outputs",
            [
                ("Batch folder", f"batch_{self.args.current_number_batch}"),
                ("Updated dataset", output_file),
                ("ROBERT folder moved to", str(self.data_path / self.robert_folder)),
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
        """Stop the timer, calculate the total time taken and move the .dat file to the proper batch folder."""
        
        elapsed_time = round(time.time() - start_time_overall, 2)

        write_log_header(self.args.log, "Active Learning Process Completed")
        write_log_block(
            self.args.log,
            "Run summary",
            [
                ("Final batch number", self.args.current_number_batch),
                ("Output folder", f"batch_{self.args.current_number_batch}"),
                ("Total runtime (s)", f"{elapsed_time:.2f}"),
            ],
        )
        self.args.log.finalize()

        # Move the .dat file to the proper batch folder
        log_file = Path.cwd() / "AL_data.dat"  # Path to the log file in the current directory
        log_destination = os.path.join(self.data_path, "AL_data.dat")  # Define the destination path
        shutil.move(log_file, log_destination)  # Move the file
