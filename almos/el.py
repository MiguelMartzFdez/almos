"""
Parameters
----------
    el : bool
        Indicates whether exploratory learning process is enabled and should be performed. Defaults to "False".
        This parameter is activated in command line (i.e. --el)
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
    explore_rt : float, default= 1
        Specifies the exploration ratio for the exploratory learning process, determining how many points to explore in relation to the total number of experiments. (i.e. '--explore_rt 0.5')
        If not provided or invalid, the program will request the values in the proper format. 
    n_exps : int,
        Number of experiments to be selected in the exploratory learning process for the new batch. (i.e. '--n_exps 10')
        If not provided or invalid, the program will request the values in the proper format.
    tolerance : str, default='medium'
        Indicates the tolerance level for the convergence process, defining the percentage change threshold required for convergence. Options:
        1. 'tight': Strictest level, convergence occurs if the metric improves by ≤1% (threshold = 0.01).
        2. 'medium': Balanced level, convergence occurs if the metric improves by ≤5% (threshold = 0.05).
        3. 'wide': Least strict, convergence occurs if the metric improves by ≤10% (threshold = 0.10).
        (i.e. '--tolerance tight')
    robert_keywords : str, default=""
        Additional keywords to be passed to the ROBERT model generation (i.e. --robert_keywords "--model RF --train [70] --seed [0]")
    reverse : bool, default=False
        If set to True, the order of the points in the new batch is reversed, prioritizing in exploitation lower values (i.e. --reverse ).
    intelex : bool, default=False
        If set to True, the program will not need module scikit-learn-intelex to speed up the model update process.

"""

#####################################################
#           This file stores the EL class           #
#        used in the exploratory learning process        #
#####################################################

import pandas as pd
import time
import os , sys
from pathlib import Path
import re
import shutil
from collections import Counter

from almos.utils import (
    load_variables,
    check_dependencies
)
from almos.el_utils import (
    generate_quartile_medians_df,
    get_quartile,
    get_size_counters,
    assign_values,
    get_metrics_from_batches,
    EarlyStopping,
    plot_metrics_subplots,
    get_scores_from_robert_report
)


class el:
    """
    Class containing all the functions from the active almos module

    """
    def __init__(self, **kwargs):

        # Initialize the timer
        start_time_overall = time.time()
        
        # load default and user-specified variables
        self.args = load_variables(kwargs, "el")

        # Check dependencies such as scikit-learn-intelex
        _ = check_dependencies(self, "el")
        
        # run robert model updated and generate predictions
        self.run_robert_process()

        # run exploratory learning process for select points for new batch
        self.exploratory_learning_process()

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
        - Runs the ROBERT model update command, logging all output and errors.
        - Checks for successful generation of the model report.
        - Runs the prediction command to generate new predictions with the updated model.
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
        self.args.log.write("\n")
        self.args.log.write("====================================\n")
        self.args.log.write("  Starting Exploratory learning process\n")
        self.args.log.write("====================================\n")

        # Log parameters for the process
        self.args.log.write("--- Parameters ---\n")
        self.args.log.write(f"CSV test file          : {self.args.csv_name}\n")
        self.args.log.write(f"Name column            : {self.args.name}\n")
        self.args.log.write(f"Y column               : {self.args.y}\n")
        self.args.log.write(f"Number of experiments  : {self.args.n_exps}\n")
        self.args.log.write(f"Exploration ratio      : {self.args.explore_rt} ({int(self.args.explore_rt * 100)}% of points for exploration)\n")
        self.args.log.write(f"Ignore columns         : {self.args.ignore}\n")
        self.args.log.write(f"Convergence tolerance  : {self.args.tolerance} ({self.args.levels_tolerance[self.args.tolerance] * 100:.2f}%)\n")
        # Add this line for clarity about REVERSE
        priority = "minimum (minimization)" if self.args.reverse else "maximum (maximization)"
        self.args.log.write(f"Optimization priority  : {priority}\n")
        self.args.log.write("-------------------------------\n")

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

        # Build and run the command for updating the ROBERT model
        command = (
            f'python -m robert --csv_name "{filename_model_csv}" '
            f'--name {self.args.name} '
            f'--y {self.args.y} '
            f'--ignore "{self.args.ignore}" '
            f'{self.args.robert_keywords}'
        )

        self.args.log.write("\n")
        self.args.log.write("=======================================\n")
        self.args.log.write("  Generating the ROBERT model updated\n")
        self.args.log.write("=======================================\n")

        # Run the command and check for errors
        exit_code = os.system(command)
        if exit_code != 0:
            self.args.log.write(f"x WARNING! Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Check if the ROBERT model report was generated
        if os.path.exists('ROBERT_report.pdf'):
            self.args.log.write("\no ROBERT model updated and generated successfully!\n")
        else:
            self.args.log.write("\nx WARNING! ROBERT model was not generated\n")
            sys.exit()

        # Define paths for the source file and destination directory
        source = os.path.join(self.args.path_csv_name)
        destination_dir = Path(Path.cwd().parent, self.robert_folder)  # Ensure destination is a directory
        destination_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
        destination = destination_dir / Path(source).name  # Complete path for the destination file

        # Check if the source file exists before copying
        if os.path.isfile(source):
            # Copy the file from source to destination
            shutil.copy(source, destination)
        else:
            print(f"o File '{self.args.csv_name}' was not found for generate predictions! Exiting.")

        # Build and run the command for generating predictions
        command = f'python -m robert --name "{self.args.name}" --csv_test "{self.args.csv_name}" --ignore "{self.args.ignore}" --predict'
        self.args.log.write("\n")
        self.args.log.write("==================================================\n")
        self.args.log.write("  Generating predictions with ROBERT model updated\n")
        self.args.log.write("==================================================\n")

        # Run the command and check for errors
        exit_code = os.system(command)
        if exit_code != 0:
            self.args.log.write(f"x WARNING! Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Get scores from PDF to decide which prediction to use
        pdf_path = robert_path / "ROBERT_report.pdf"
        score_no_PFI, score_PFI = get_scores_from_robert_report(pdf_path)
        use_pfi = False
        if score_PFI is not None and (score_no_PFI is None or score_PFI >= score_no_PFI):
            use_pfi = True
        self.args.log.write(f"Score No_PFI: {score_no_PFI}, Score PFI: {score_PFI}")

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
            self.args.log.write(f"o Using {'PFI' if use_pfi else 'No_PFI'} predictions: {self.path_predictions.name}")
        else:
            self.args.log.write(f"x WARNING! Predictions were not generated in {self.path_predictions}")
            sys.exit()

    def exploratory_learning_process(self):
        """
        Main function for the exploratory learning process, including:
        - Reading and concatenating predictions with the raw data.
        - Splitting data into experimental and prediction sets.
        - Calculating quartiles and assigning points for exploration and exploitation.
        - Updating the dataset and saving results into organized batch folders.
        
        This process manages both exploration and exploitation of data for an exploratory learning cycle.
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
        experimental_df = df_raw_copy[df_raw_copy[self.args.batch_column].notna()]
        predictions_df = df_raw_copy[df_raw_copy[self.args.batch_column].isna()]
        
        # Generate lists of target values for experimental and prediction datasets
        list_experimental = experimental_df[self.args.y].tolist()
        list_predictions = predictions_df[predictions_column].tolist()
        values = list_experimental + list_predictions

        # Create DataFrames with combined values and only experimental values
        total_value_df = pd.DataFrame({self.args.y: values})
        exp_value_df = pd.DataFrame({self.args.y: list_experimental})

        # Calculate quartiles and their medians for the experimental dataset
        quartile_df_exp, quartile_medians, boundaries = generate_quartile_medians_df(total_value_df, exp_value_df, self.args.y)
        
        # Copy predictions DataFrame to avoid modifications
        predictions_copy_df = predictions_df.copy()

        # Log results and initial data sizes
        self.args.log.write("\n")
        self.args.log.write("================================================\n")
        self.args.log.write(f"             Results for Batch {self.args.current_number_batch}\n")
        self.args.log.write("================================================\n")

        size_counters = get_size_counters(quartile_df_exp)
        # Dataset information
        self.args.log.write("--- Dataset Information ---\n")
        self.args.log.write(f"\nInitial sizes of dataset: {size_counters}\n")

        # Create variables for exploration vs exploitation using explore_rt
        if self.args.n_exps == 1:
            # One single point: decide based on ratio
            explore_points = 1 if self.args.explore_rt >= 0.5 else 0
            exploit_points = 1 - explore_points
        else:
            explore_points = round(self.args.n_exps * self.args.explore_rt)
            exploit_points = self.args.n_exps - explore_points
        
        # Exploitation: Select top rows for q4 or q1 based on the predictions and if the process is reverse or not
        if self.args.reverse:
            top_df = predictions_copy_df.nsmallest(exploit_points, predictions_column)
        else:
            top_df = predictions_copy_df.nlargest(exploit_points, predictions_column)

        predictions_copy_df.loc[top_df.index, self.args.batch_column] = self.args.current_number_batch

        # Assign quartiles to the predictions DataFrame
        predictions_copy_df['quartile'] = predictions_copy_df[predictions_column].apply(lambda x: get_quartile(x, boundaries))

        # Exploration: Assign values to the exploration quartiles based on proximity to quartile medians
        assigned_points, min_size_quartiles = assign_values(
            predictions_copy_df[predictions_copy_df[self.args.batch_column].isna()],
            exploit_points,
            explore_points,
            quartile_medians, 
            size_counters, 
            predictions_column,
            sd_column,
            self.args.reverse
        )

        # Count occurrences in exploration assignments
        points_counter = Counter([value for _, points in assigned_points.items() for value in points])

        # Update the batch column for exploration assignments
        for value, times_value_appears in points_counter.items():
            idx_list = predictions_copy_df[predictions_copy_df[predictions_column] == value].index
            if not idx_list.empty:
                indices_to_update = idx_list[:times_value_appears]
                predictions_copy_df.loc[indices_to_update, self.args.batch_column] = self.args.current_number_batch

        self.args.log.write(f"Quartile medians of dataset: {quartile_medians}\n")
        self.args.log.write(f"Boundaries range: Min = {min(boundaries)}, Max = {max(boundaries)}\n")

        # Exploration results
        self.args.log.write("\n--- Exploration ---\n")
        self.args.log.write(f"Ordered assigned points: {min_size_quartiles}\n\n")
        self.args.log.write(f"Number of points assigned for exploration: {explore_points}\n")

        # Dynamically select quartiles for logging
        if exploit_points == 0:
            quartiles = ['q1', 'q2', 'q3', 'q4']
        elif self.args.reverse:
            quartiles = ['q2', 'q3', 'q4']
        else:
            quartiles = ['q1', 'q2', 'q3']

        for q in quartiles:
            self.args.log.write(f"    Points assigned to {q}: {assigned_points[q]}\n")

        # Exploitation results
        if not exploit_points==0:
            self.args.log.write("\n--- Exploitation ---\n")
            self.args.log.write(f"Number of points assigned for exploitation: {exploit_points}\n")
            if self.args.reverse:
                self.args.log.write(f"    Points assigned to q1: {top_df[predictions_column].tolist()}\n")  
            else:
                self.args.log.write(f"    Points assigned to q4: {top_df[predictions_column].tolist()}\n")

        # Update batch column after exploration and exploitation
        df_raw_copy[self.args.batch_column] = df_raw_copy[self.args.batch_column].combine_first(predictions_copy_df[self.args.batch_column])
        # Drop predictions columns and save updated results
        df_raw_copy.drop([predictions_column, sd_column], axis=1, inplace=True)

        # Build the filename for the updated dataset and save it
        output_file = f"{self.args.base_name}_b{self.args.current_number_batch}.csv"
        df_raw_copy.to_csv(output_file, index=False)

        # Create a batch directory and move relevant files
        self.data_path = Path.cwd() / f'batch_{self.args.current_number_batch}'
        self.data_path.mkdir(parents=True, exist_ok=True)

        # Move the files to the proper batch folder
        shutil.move(self.robert_folder, self.data_path)
        shutil.move(output_file, self.data_path)

        # Log results
        self.args.log.write(f"\no Results generated successfully in folder 'batch_{self.args.current_number_batch}'\n")

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

        # Log confirmation after generating both plots
        self.args.log.write("\n==========================================")
        self.args.log.write("   Graph Generation Confirmation Report     ")
        self.args.log.write("==========================================\n")
        self.args.log.write("o Subplot figures have been generated and saved successfully!\n")
        
    def finalize_process(self, start_time_overall):
        """Stop the timer, calculate the total time taken and move the .dat file to the proper batch folder."""
        
        elapsed_time = round(time.time() - start_time_overall, 2)

        # Log the total time and finalize
        self.args.log.write("==========================================\n")
        self.args.log.write(f"Process Completed! Total time taken for the process: {elapsed_time:.2f} seconds")
        self.args.log.finalize()

        # Move the .dat file to the proper batch folder
        log_file = Path.cwd() / "AL_data.dat"  # Path to the log file in the current directory
        log_destination = os.path.join(self.data_path, "AL_data.dat")  # Define the destination path
        shutil.move(log_file, log_destination)  # Move the file