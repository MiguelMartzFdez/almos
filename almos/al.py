import pandas as pd
import time
import os , sys
from pathlib import Path
import shutil
import re
from collections import Counter
import ast

from utils import (
    load_variables
)
from al_utils import (
    generate_quartile_medians_df,
    get_size_counters,
    assign_values,
    load_options_from_csv,
    get_metrics_from_batches,
    EarlyStopping,
    plot_metrics_subplots
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

        # CHECK dependencies (module, al)

        # check inputs are valid and load
        self.check_inputs_active_learning()
        
        # run robert model updated and generate predictions
        self.run_robert_process()

        # run active learning process for select points for new batch
        self.active_learning_process()

        # Check for convergence in the batches
        # Get metrics from batches
        results_plot_no_PFI, results_plot_PFI = get_metrics_from_batches()

        # Initialize EarlyStopping
        early_stopping = EarlyStopping(
            logger=self.args.log,
            rmse_min_delta = self.args.levels_tolerance[self.args.tolerance],
            sd_min_delta = self.args.levels_tolerance[self.args.tolerance],
        )
        # Check for convergence using EarlyStopping
        results_plot_no_pfi_df, results_plot_pfi_df = early_stopping.check_convergence(
            results_plot_no_PFI, results_plot_PFI
        )
        # Generate plots
        self.generate_plots(results_plot_no_pfi_df, results_plot_pfi_df)

        # Log the total time and finalize
        self.finalize_process(start_time_overall)
    
    
    def finalize_process(self, start_time_overall):
        """Stop the timer and calculate the total time taken"""
        
        elapsed_time = round(time.time() - start_time_overall, 2)

        # Log the total time and finalize
        self.args.log.write("\n==========================================\n")
        self.args.log.write(f"Process Completed! Total time taken for the process: {elapsed_time:.2f} seconds")
        self.args.log.finalize()

        # Move the .dat file to the proper batch folder
        log_file = Path.cwd() / "AL_data.dat"  # Path to the log file in the current directory
        log_destination = os.path.join(self.data_path, "AL_data.dat")  # Define the destination path
        shutil.move(log_file, log_destination)  # Move the file



    def check_inputs_active_learning(self):
        """
        Initializes and validates input parameters for active learning.

        This method:
        - Loads default options and adds values for missing attributes (`target_column`, `name_column`, `ignore_list`).
        - Prompts for and locates the CSV file if not specified, loading it into a DataFrame.
        - Ensures that required columns for molecule names and target values exist, prompting for values if necessary.
        - Validates `factor_explore` and `number_of_new_points`, ensuring valid ranges.
        - Manages the `batch_column`, adding or updating it as needed for data completeness.
        - Updates `ignore_list` and saves final options to a file.

        Raises:
            SystemExit: If any required input is missing, invalid, or the file is not found.
        """
        # Load options if attributes are missing
        if not self.args.y or not self.args.name or not self.args.ignore:
            options = load_options_from_csv(self.args.options_file)
            if options is not None:
                print("\nOptions loaded from CSV file!")
                # Assign values from options if available
                self.args.y = options['y'] if not self.args.y else self.args.y
                self.args.name = options['name'] if not self.args.name else self.args.name
                if not self.args.ignore and options['ignore'] is not None:
                    self.args.ignore = ast.literal_eval(options['ignore'])

        # Load CSV file
        self.path_csv_name, self.args.csv_name = self.find_csv_file(self.args.csv_name)
        self.base_name_raw = os.path.splitext(self.args.csv_name)[0]
        self.df_raw = pd.read_csv(self.path_csv_name)

        # Validate column names and set base name
        match = re.search(r'_b(\d+)', self.base_name_raw)
        self.base_name = re.sub(r'_b\d+', '', self.base_name_raw) if match else self.base_name_raw
        if 'code_name' in self.df_raw.columns:
            self.args.name = 'code_name'

        if not self.args.name:
            self.args.name = input("\nWARNING! Specify the column containing molecule names: ")
            if self.args.name not in self.df_raw.columns:
                print(f"\nWARNING! The column '{self.args.name}' hasn't been found. Exiting.")
                sys.exit()

        # Validate target column
        if  not self.args.y:
            print("\nWARNING! The target column has not been specified.")
            self.args.y = input("\nSpecify the column containing target value: ")

        if self.args.y not in self.df_raw.columns:
            print(f"\nWARNING! The target column '{self.args.y}' hasn't been found. Exiting.")
            sys.exit()

        # Validate factor_explore
        if not isinstance(self.args.factor_exp, (int, float)) or not (0 <= self.args.factor_exp <= 1):
            self.args.factor_exp = input("\nWARNING! Enter a valid exploration factor (must be beetween 0 and 1): ")
            try:
                self.args.factor_exp = float(self.args.factor_exp)
                if not (0 <= self.args.factor_exp <= 1):
                    raise ValueError
            except ValueError:
                print("\nWARNING! The exploration factor must be between 0 and 1. Exiting.")
                sys.exit()

        # Validate number_of_new_points
        if self.args.n_points is None:
            self.args.n_points = input("\nWARNING! The number of points has not been specified. Introduce the number of new points: ")
            try:
                self.args.n_points = int(self.args.n_points)
                if self.args.n_points <= 0:
                    raise ValueError
            except ValueError:
                print(f"\nWARNING! The number of new points '{self.args.n_points}' is not valid. Exiting.")
                sys.exit()

        # Validate batch column and assign batch number
        if self.args.batch_column in self.df_raw.columns:
            max_batch_number = int(self.df_raw[self.args.batch_column].max())
            self.current_number_batch = max_batch_number + 1

            last_batch = self.df_raw[self.df_raw[self.args.batch_column] == max_batch_number]
            if not last_batch[self.args.y].notna().all():
                print(f"\nWARNING! The column '{self.args.y}' is missing values. Exiting.")
                sys.exit()

        else:
            if self.args.y in self.df_raw.columns and self.df_raw[self.args.y].notna().any():
                self.df_raw[self.args.batch_column] = self.df_raw[self.args.y].notna().astype(int)
                self.df_raw.to_csv(self.path_csv_name, index=False)
                self.current_number_batch = 1
            else:
                print(f"\nWARNING! '{self.args.batch_column}' column not found, and '{self.args.y}' has no valid data. Exiting.")
                sys.exit()

        # Add batch column to ignore list and save options
        self.args.ignore.append(self.args.batch_column)
        self.args.ignore = list(set(self.args.ignore))

        options_df = pd.DataFrame({
            'y': [self.args.y],
            'csv_name': [self.args.csv_name],
            'ignore': [str(self.args.ignore)],
            'name': [self.args.name],
        })
        options_df.to_csv('options.csv', index=False)
        print("\nOptions saved successfully.\n")

    def find_csv_file(self, csv_name):
        """
        Locates the specified CSV file in the current or batch directories.
        """
        if not csv_name:
            csv_name = input("\nWARNING! The name of the file was not introduced. Introduce name of the CSV file: ")
            if not csv_name:
                print("\nWARNING! The name of the file was not introduced. Exiting.")
                sys.exit()

        if os.path.exists(csv_name):
            print(f"\nFile '{csv_name}' found in the current directory.")
            return Path.cwd() / csv_name, csv_name

        print(f"\nFile '{csv_name}' was not found in the current directory. Searching in batch directories...")
        for batch_dir in Path.cwd().glob('batch_*'):
            if batch_dir.name != 'batch_plots':
                potential_path = batch_dir / csv_name
                if potential_path.exists():
                    print(f"\nFile '{csv_name}' found in '{batch_dir}' directory.")
                    return potential_path, csv_name

        print(f"\nWARNING! The file '{csv_name}' was not found. Exiting.")
        sys.exit()
        

        
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
        # Initialize the logger
        # self.args.log = Logger(filein="AL", append="data")
        self.args.log.write("====================================\n")
        self.args.log.write("  Starting Active Learning process\n")
        self.args.log.write("====================================\n")

        # Log parameters for the process
        self.args.log.write("Parameters:\n")
        self.args.log.write("-------------------------------\n")
        self.args.log.write(f"CSV test file       : {self.args.csv_name}\n")
        self.args.log.write(f"Name column         : {self.args.name}\n")
        self.args.log.write(f"Target column       : {self.args.y}\n")
        self.args.log.write(f"Number of new points: {self.args.n_points}\n")
        self.args.log.write(f"Ignore              : {self.args.ignore}\n")
        self.args.log.write(f"Exploration factor  : {self.args.factor_exp}\n")
        self.args.log.write("-------------------------------\n")

        # Filter rows where value in the batch_column is not NaN for updating the model
        robert_model_df = self.df_raw[self.df_raw[self.args.batch_column].notna()]

        # Create the CSV filename and save it for ROBERT
        filename_model_csv = f"{self.base_name}_ROBERT_b{self.current_number_batch}.csv"
        robert_model_df.to_csv(filename_model_csv, index=False)

        if os.path.exists(filename_model_csv):
            # Create directory for saving ROBERT model results
            self.robert_folder = f'ROBERT_b{self.current_number_batch}'
            robert_path = Path.cwd() / self.robert_folder
            robert_path.mkdir(parents=True, exist_ok=True)

            # Move the generated file into the new folder
            shutil.move(filename_model_csv, robert_path / filename_model_csv)

            # Change to ROBERT directory
            os.chdir(robert_path)
        else:
            print(f"WARNING! The file '{filename_model_csv}' has not been found. Please check that the file exists.")
            sys.exit()

        # Trying to avoid error in subprocess with tkinter
        # Use "Agg" backend to prevent matplotlib from using tkinter, avoiding "main thread" errors in headless or multi-threaded environments.
        os.environ["MPLBACKEND"] = "Agg"

        # Build and run the command for updating the ROBERT model
        command = f'python -m robert --csv_name {filename_model_csv} --name {self.args.name} --y {self.args.y} --ignore "{self.args.ignore}"'
        self.args.log.write("\n")
        self.args.log.write("=======================================\n")
        self.args.log.write("  Generating the ROBERT model updated\n")
        self.args.log.write("=======================================\n")

        # Run the command and check for errors
        exit_code = os.system(command)
        if exit_code != 0:
            self.args.log.write(f"Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Check if the ROBERT model report was generated
        if os.path.exists('ROBERT_report.pdf'):
            self.args.log.write("\nROBERT model updated and generated successfully!\n")
        else:
            self.args.log.write("\nWARNING! ROBERT model was not generated\n")
            sys.exit()

        # Define paths for the source file and destination directory
        source = os.path.join(self.path_csv_name)
        destination_dir = Path(Path.cwd().parent, self.robert_folder)  # Ensure destination is a directory
        destination_dir.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
        destination = destination_dir / Path(source).name  # Complete path for the destination file

        # Check if the source file exists before copying
        if os.path.isfile(source):
            # Copy the file from source to destination
            print(f"Copying file from {source} \nto {destination}")
            shutil.copy(source, destination)
        else:
            print(f" File '{self.args.csv_name}' was not found for generate predictions! Exiting.")

        # Build and run the command for generating predictions
        command = f'python -m robert --name {self.args.name} --csv_test {self.args.csv_name} --ignore "{self.args.ignore}" --predict'
        self.args.log.write("\n")
        self.args.log.write("==================================================\n")
        self.args.log.write("  Generating predictions with ROBERT model updated\n")
        self.args.log.write("==================================================\n")

        # Run the command and check for errors
        exit_code = os.system(command)
        if exit_code != 0:
            self.args.log.write(f"Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Check if predictions were created correctly
        self.path_predictions = robert_path / 'PREDICT' / 'csv_test' / f"{self.base_name_raw}_predicted_PFI.csv"
        if self.path_predictions.exists():
            # Clean up: remove the test CSV file if it exists in main directory
            os.remove(destination)
            self.args.log.write("New predictions generated successfully!")
        else:
            self.args.log.write(f"WARNING! Predictions were not generated in {self.path_predictions}")
            sys.exit()

    def active_learning_process(self):
        """
        Main function for the active learning process, including:
        - Reading and concatenating predictions with the raw data.
        - Splitting data into experimental and prediction sets.
        - Calculating quartiles and assigning points for exploration and exploitation.
        - Updating the dataset and saving results into organized batch folders.
        
        This process manages both exploration and exploitation of data for an active learning cycle.
        """
        
        # Read predictions from ROBERT and concatenate with the raw data
        df_predictions = pd.read_csv(self.path_predictions)
        
        # Move to the parent directory
        parent_directory = Path.cwd() / '..'
        os.chdir(parent_directory) 
        
        # Add predictions and prediction SD to the original dataframe
        predictions_column = f'{self.args.y}_pred'
        sd_column = f'{predictions_column}_sd'
        self.df_raw[[predictions_column, sd_column]] = df_predictions[[predictions_column, sd_column]]
        
        # Filter the DataFrame into experimental and predictions data
        df_raw_copy = self.df_raw.copy()
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
        self.args.log.write(f"             Results for Batch {self.current_number_batch}\n")
        self.args.log.write("================================================\n")

        size_counters = get_size_counters(quartile_df_exp)
        self.args.log.write(f"\nInitial sizes of dataset: {size_counters}\n")

        # Determine the number of points for each quartile in exploration vs. exploitation
        number_new_q1_q2_q3_values = int(self.args.n_points * self.args.factor_exp)
        # Ensure that at least one point is assigned to each quartile if the factor is not 0 or 1 in each case.
        if number_new_q1_q2_q3_values < 1 and self.args.factor_exp != 0:
            number_new_q1_q2_q3_values = 1
        number_new_q4_values = self.args.n_points - number_new_q1_q2_q3_values
        if number_new_q4_values < 1 and self.args.factor_exp != 1:
            number_new_q4_values = 1

        # Exploitation: Select top rows for q4 based on the predictions
        top_q4_df = predictions_copy_df.nlargest(number_new_q4_values, predictions_column)
        predictions_copy_df.loc[top_q4_df.index, self.args.batch_column] = self.current_number_batch

        # Exploration: Assign values to the first three quartiles based on proximity to quartile medians
        assigned_points, min_size_quartiles = assign_values(
            predictions_copy_df[predictions_copy_df[self.args.batch_column].isna()],
            number_new_q1_q2_q3_values,
            quartile_medians, 
            size_counters, 
            predictions_column
        )

        # Count occurrences in exploration assignments
        points_counter = Counter([value for _, points in assigned_points.items() for value in points])

        # Update the batch column for exploration assignments
        for value, times_value_appears in points_counter.items():
            idx_list = predictions_copy_df[predictions_copy_df[predictions_column] == value].index
            if not idx_list.empty:
                indices_to_update = idx_list[:times_value_appears]
                predictions_copy_df.loc[indices_to_update, self.args.batch_column] = self.current_number_batch

        # Log quartile information
        self.args.log.write(f"\nQuartile medians of dataset: {quartile_medians}\n")
        self.args.log.write(f"Boundaries range: Min = {min(boundaries)}, Max = {max(boundaries)}\n")
        self.args.log.write(f"\nOrdered assigned points for exploration: {min_size_quartiles}\n")
        self.args.log.write(f'\nNumber of points for exploitation: {number_new_q4_values}\n')
        self.args.log.write(f"Assigned points for exploitation: {top_q4_df[predictions_column].tolist()}\n")
        self.args.log.write(f'\nNumber of points for exploration: {number_new_q1_q2_q3_values}\n')
        for q in ['q1', 'q2', 'q3']:
            self.args.log.write(f"Assigned points for {q}: {assigned_points[q]}\n")

        # Update batch column after exploration and exploitation
        df_raw_copy[self.args.batch_column] = df_raw_copy[self.args.batch_column].combine_first(predictions_copy_df[self.args.batch_column])
        # Drop predictions columns and save updated results
        df_raw_copy.drop([predictions_column, sd_column], axis=1, inplace=True)

        # Build the filename for the updated dataset and save it
        output_file = f"{self.base_name}_b{self.current_number_batch}.csv"
        df_raw_copy.to_csv(output_file, index=False)

        # Create a batch directory and move relevant files
        self.data_path = Path.cwd() / f'batch_{self.current_number_batch}'
        self.data_path.mkdir(parents=True, exist_ok=True)

        shutil.move(self.robert_folder, self.data_path)
        shutil.move(output_file, self.data_path)

        self.args.log.write("\n")
        self.args.log.write(f"Results generated successfully in folder 'batch_{self.current_number_batch}'\n")

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
            plot_metrics_subplots(df, model_type, output_dir="batch_plots", batch_count = self.current_number_batch)

        # Log confirmation after generating both plots
        self.args.log.write("\n==========================================")
        self.args.log.write("   Graph Generation Confirmation Report     ")
        self.args.log.write("==========================================\n")
        self.args.log.write("Subplot figures have been generated and saved successfully!\n")