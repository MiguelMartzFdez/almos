"""
Parameters
----------
    al : bool
        Indicates whether active learning process is enabled and should be performed. Defaults to "False".
        This parameter is activated in command line (i.e. --al)
    csv_name : str
        Name of the CSV file containing the database. (i.e. 'FILE.csv'). 
    y : str
        Name of the column containing the response variable in the input CSV file (i.e. 'solubility'). 
    name : str
        Name of the column containing the molecule names in the input CSV file (i.e. 'names').
    ignore : list, default=[]
        List containing the columns of the input CSV file that will be ignored during the ROBERT process
        (i.e. --ignore "['name','SMILES']"). The descriptors will be included in the final CSV file. The y value, name column and batch column
        are automatically ignored by ROBERT.  
    options_file : str
        Name of the CSV file containing parameter settings, such as "y", "csv_name", "ignore", and "name".
        Defaults to "option.csv".
    batch_column : str
        Name of the column in the CSV file that represents batches or groups for processing.
    n_points : tuple of two int 
        Specifies the number of new points for exploration and exploitation in the next batch. 
        The first value is for exploration, and the second is for exploitation. (i.e. '5:10')
        If not provided or invalid, the program will request the values in the format 'explore:exploit'.
    tolerance : str, default='medium'
        Indicates the tolerance level for the convergence process, defining the percentage change threshold required for convergence. Options:
        1. 'tight': Strictest level, convergence occurs if the metric improves by ≤1% (threshold = 0.01).
        2. 'medium': Balanced level, convergence occurs if the metric improves by ≤5% (threshold = 0.05).
        3. 'wide': Least strict, convergence occurs if the metric improves by ≤10% (threshold = 0.10).

"""

#####################################################
#           This file stores the AL class           #
#        used in the active learning process        #
#####################################################

import pandas as pd
import time
import os , sys
from pathlib import Path
import shutil
import re
from collections import Counter
import ast

from almos.utils import (
    load_variables
)
from almos.al_utils import (
    generate_quartile_medians_df,
    get_size_counters,
    assign_values,
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

        # # check inputs are valid and load
        # self.check_inputs_active_learning()
        
        # run robert model updated and generate predictions
        self.run_robert_process()

        # run active learning process for select points for new batch
        self.active_learning_process()

        # Check for convergence in the batches
        # Get metrics from batches
        results_plot_no_PFI, results_plot_PFI = get_metrics_from_batches()
        print(results_plot_no_PFI)
        print(results_plot_PFI)

        # Initialize EarlyStopping and checking for convergence using EarlyStopping
        early_stopping = EarlyStopping(
            logger=self.args.log,
            rmse_min_delta = self.args.levels_tolerance[self.args.tolerance],
            sd_min_delta = self.args.levels_tolerance[self.args.tolerance],
        )
        
        results_plot_no_pfi_df, results_plot_pfi_df = early_stopping.check_convergence(
            results_plot_no_PFI, results_plot_PFI
        )
        print(results_plot_no_pfi_df)
        print(results_plot_pfi_df)
        
        # Generate plots
        self.generate_plots(results_plot_no_pfi_df, results_plot_pfi_df)

        # Log the total time and finalize
        self.finalize_process(start_time_overall)
    
    # def check_inputs_active_learning(self):
    #     """
    #     Initializes and validates input parameters for active learning.

    #     This method:
    #     - Loads default options and adds values for missing attributes ('target_column', 'name_column', 'ignore_list').
    #     - Prompts for and locates the CSV file if not specified, loading it into a DataFrame.
    #     - Ensures that required columns for molecule names and target values exist, prompting for values if necessary.
    #     - Validates 'n_points' and 'tolerance' ensuring valid ranges.
    #     - Manages the 'batch_column', adding or updating it as needed for data completeness.
    #     - Updates 'ignore_list' and saves final options to a file.

    #     Raises:
    #         SystemExit: If any required input is missing, invalid, or the file is not found.
    #     """
    #     # Load options if attributes are missing
    #     if not self.args.y or not self.args.name or not self.args.ignore:
    #         options = load_options_from_csv(self.args.options_file)
    #         if options is not None:
    #             self.args.log.write("\no Options were loaded from the CSV file because some required attributes are missing in the input!")
    #             # Assign values from options if available
    #             self.args.y = options['y'] if not self.args.y else self.args.y
    #             self.args.name = options['name'] if not self.args.name else self.args.name
    #             if not self.args.ignore and options['ignore'] is not None:
    #                 self.args.ignore = ast.literal_eval(options['ignore'])

    #     # Load CSV file
    #     self.path_csv_name, self.args.csv_name = self.find_csv_file(self.args.csv_name)
    #     self.base_name_raw = os.path.splitext(self.args.csv_name)[0]
    #     self.df_raw = pd.read_csv(self.path_csv_name)

    #     # Validate column names and set base name
    #     match = re.search(r'_b(\d+)', self.base_name_raw)
    #     self.base_name = re.sub(r'_b\d+', '', self.base_name_raw) if match else self.base_name_raw
    #     if 'code_name' in self.df_raw.columns:
    #         self.args.name = 'code_name'

    #     if not self.args.name:
    #         self.args.name = input("\nx WARNING! Specify the column containing molecule names: ")
    #         if self.args.name not in self.df_raw.columns:
    #             print(f"\nx WARNING! The column '{self.args.name}' hasn't been found. Exiting.")
    #             sys.exit()

    #     # Validate target column
    #     if  not self.args.y:
    #         self.args.y = input("\nx WARNING! The target column has not been specified. Specify the column: ")

    #     if self.args.y not in self.df_raw.columns:
    #         print(f"\nx WARNING! The target column '{self.args.y}' hasn't been found. Exiting.")
    #         sys.exit()

    #     # Validate factor_explore
    #     if not isinstance(self.args.factor_exp, (int, float)) or not (0 <= self.args.factor_exp <= 1):
    #         self.args.factor_exp = input("\nx WARNING! Enter a valid exploration factor (must be beetween 0 and 1): ")
    #         try:
    #             self.args.factor_exp = float(self.args.factor_exp)
    #             if not (0 <= self.args.factor_exp <= 1):
    #                 raise ValueError
    #         except ValueError:
    #             print("\nx WARNING! The exploration factor must be between 0 and 1. Exiting.")
    #             sys.exit()

    #     # Validate number_of_new_points
    #     if self.args.n_points is None:
    #         self.args.n_points = input("\nx WARNING! The number of points has not been specified. Introduce the number of new points: ")
    #         try:
    #             self.args.n_points = int(self.args.n_points)
    #             if self.args.n_points <= 0:
    #                 raise ValueError
    #         except ValueError:
    #             print(f"x WARNING! The number of new points '{self.args.n_points}' is not valid. Exiting.")
    #             sys.exit()

    #     # Validate n_points
    #     if self.args.n_points is None or len(self.args.n_points) != 2: #or not isinstance(self.args.n_points, tuple)
    #         self.args.n_points = input(f"\nx WARNING! The number of points '{self.args.n_points}' to explore and exploit has not been specified correctly. Introduce the values as 'explore:exploit': ")
    #         try:
    #             # Ensure the input is in the correct format and contains two positive integers
    #             parts = self.args.n_points.split(":")
    #             n_points = tuple(map(int, parts))  # Convert parts to integers
    #             if len(parts) != 2 or n_points[0] <= 0 or n_points[1] <= 0:
    #                 raise ValueError
    #             self.args.n_points = n_points
    #         except ValueError:
    #             print(f"\nx WARNING! Invalid input '{self.args.n_points}'. Expected format: 'explore:exploit' with two positive integers. Exiting.")
    #             sys.exit()

    #     # Validate tolerance level
    #     if self.args.tolerance not in self.args.levels_tolerance:
    #         self.args.tolerance = input("\nx WARNING! Enter a valid tolerance level ('tight':1%, 'medium':5%, 'wide':10%): ")
    #         if self.args.tolerance not in self.args.levels_tolerance:
    #             print(f"\nx WARNING! The tolerance level '{self.args.tolerance}' is not valid. Exiting.")
    #             sys.exit()

    #     # Validate batch column and assign batch number
    #     if self.args.batch_column in self.df_raw.columns:
    #         max_batch_number = int(self.df_raw[self.args.batch_column].max())
    #         self.current_number_batch = max_batch_number + 1

    #         # Check if there are missing values in y column
    #         last_batch = self.df_raw[self.df_raw[self.args.batch_column] == max_batch_number]
    #         if not last_batch[self.args.y].notna().all():
    #             print(f"\nx WARNING! The column '{self.args.y}' contains missing values. Please check the data before proceeding! Exiting.")
    #             sys.exit()
    #         # Check if there are values in y but no values in batch column
    #         if not self.df_raw[self.df_raw[self.args.y].notna() & self.df_raw[self.args.batch_column].isna()].empty:
    #             print(f"\nx WARNING! The column '{self.args.y}' contains values, but there are missing entries in the column '{self.args.batch_column}'. Please fix the data before proceeding. Exiting.")
    #             sys.exit()

    #     else:
    #         # Create batch column if it doesn't exist when y has valid data
    #         if self.args.y in self.df_raw.columns and self.df_raw[self.args.y].notna().any():
    #             self.df_raw[self.args.batch_column] = 0
    #             self.df_raw.loc[~self.df_raw[self.args.y].notna(), self.args.batch_column] = None
    #             self.df_raw.to_csv(self.path_csv_name, index=False)
    #             self.current_number_batch = 1
    #             print(f"\nx WARNING! Batch column '{self.args.batch_column}' not found but valid data in '{self.args.y}'.") 
    #             print(f"\no Batch column created successfully!")
    #         else:
    #             print(f"\nx WARNING! '{self.args.batch_column}' column not found, and '{self.args.y}' has no values! Exiting.")
    #             sys.exit()


    #     # Check if the 'batch' folder already exists
    #     self.data_path_check = Path.cwd() / f'batch_{self.current_number_batch}'
    #     if self.data_path_check.exists():
    #         overwrite = input(f"\nx WARNING! Directory '{self.data_path_check.name}' already exists. Do you want to overwrite it? (y/n): ").strip().lower()
    #         if overwrite == 'y':
    #             shutil.rmtree(self.data_path_check)
    #             print(f"\no Directory '{self.data_path_check.name}' has been deleted suscessfully!")
    #         else:
    #             # Delete the log file and cancel the actual process
    #             log_file = Path.cwd() / "AL_data.dat"  
    #             if log_file.exists():
    #                 log_file.unlink()  # Use .unlink() for a single file 
    #             print("\nx WARNING! Active learning process has been canceled. Exiting.")
    #             exit()

    #     # Add batch column to ignore list and save options
    #     self.args.ignore.append(self.args.batch_column)
    #     self.args.ignore = list(set(self.args.ignore))

    #     options_df = pd.DataFrame({
    #         'y': [self.args.y],
    #         'csv_name': [self.args.csv_name],
    #         'ignore': [str(self.args.ignore)],
    #         'name': [self.args.name],
    #     })
    #     options_df.to_csv('options.csv', index=False)
    #     print("\no Options saved successfully!\n")
        
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
        self.args.log.write("\n")
        self.args.log.write("====================================\n")
        self.args.log.write("  Starting Active Learning process\n")
        self.args.log.write("====================================\n")

        # Log parameters for the process
        self.args.log.write("--- Parameters ---\n")
        self.args.log.write(f"CSV test file          : {self.args.csv_name}\n")
        self.args.log.write(f"Name column            : {self.args.name}\n")
        self.args.log.write(f"Y column               : {self.args.y}\n")
        self.args.log.write(f"Points exploration     : {self.args.n_points[0]}\n")
        self.args.log.write(f"Points explotation     : {self.args.n_points[1]}\n")
        self.args.log.write(f"Ignore columns         : {self.args.ignore}\n")
        self.args.log.write(f"Convergence tolerance  : {self.args.tolerance} ({self.args.levels_tolerance[self.args.tolerance] * 100:.2f}%)\n")
        self.args.log.write("-------------------------------\n")

        # Filter rows where value in the batch_column is not NaN for updating the model
        robert_model_df = self.args.df_raw[self.args.df_raw[self.args.batch_column].notna()]

        # Create the CSV filename and save it for ROBERT
        filename_model_csv = f"{self.args.base_name}_ROBERT_b{self.args.current_number_batch}.csv"
        robert_model_df.to_csv(filename_model_csv, index=False)

        if os.path.exists(filename_model_csv):
            # Create directory for saving ROBERT model results
            self.robert_folder = f'ROBERT_b{self.args.current_number_batch}'
            robert_path = Path.cwd() / self.robert_folder
            robert_path.mkdir(parents=True, exist_ok=True)

            # Move the generated file into the new folder
            shutil.move(filename_model_csv, robert_path / filename_model_csv)

            # Change to ROBERT directory
            os.chdir(robert_path)
        else:
            print(f"x WARNING! The file '{filename_model_csv}' has not been found. Please check that the file exists.")
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
        command = f'python -m robert --name {self.args.name} --csv_test {self.args.csv_name} --ignore "{self.args.ignore}" --predict'
        self.args.log.write("\n")
        self.args.log.write("==================================================\n")
        self.args.log.write("  Generating predictions with ROBERT model updated\n")
        self.args.log.write("==================================================\n")

        # Run the command and check for errors
        exit_code = os.system(command)
        if exit_code != 0:
            self.args.log.write(f"x WARNING! Command failed with exit code {exit_code}. Exiting.\n")
            sys.exit(exit_code)

        # Check if predictions were created correctly
        self.path_predictions = robert_path / 'PREDICT' / 'csv_test' / f"{self.args.base_name_raw}_predicted_PFI.csv"
        if self.path_predictions.exists():
            # Clean up, remove the test CSV file if it exists in main directory
            os.remove(destination)
            self.args.log.write("o New predictions generated successfully!")
        else:
            self.args.log.write(f"x WARNING! Predictions were not generated in {self.path_predictions}")
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
        self.args.df_raw[[predictions_column, sd_column]] = df_predictions[[predictions_column, sd_column]]
        
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

        # Create variables for exploration vs exploitation using n_points explore:exploit
        explore_points = int(self.args.n_points[0])
        exploit_points = int(self.args.n_points[1])
        
        # Exploitation: Select top rows for q4 based on the predictions
        top_q4_df = predictions_copy_df.nlargest(exploit_points, predictions_column)
        predictions_copy_df.loc[top_q4_df.index, self.args.batch_column] = self.args.current_number_batch

        # Exploration: Assign values to the first three quartiles based on proximity to quartile medians
        assigned_points, min_size_quartiles = assign_values(
            predictions_copy_df[predictions_copy_df[self.args.batch_column].isna()],
            explore_points,
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
                predictions_copy_df.loc[indices_to_update, self.args.batch_column] = self.args.current_number_batch

        self.args.log.write(f"Quartile medians of dataset: {quartile_medians}\n")
        self.args.log.write(f"Boundaries range: Min = {min(boundaries)}, Max = {max(boundaries)}\n")

        # Exploration results
        self.args.log.write("\n--- Exploration ---\n")
        self.args.log.write(f"Ordered assigned points: {min_size_quartiles}\n\n")
        self.args.log.write(f"Number of points assigned for exploration: {explore_points}\n")
        for q in ['q1', 'q2', 'q3']:
            self.args.log.write(f"    Points assigned to {q}: {assigned_points[q]}\n")

        # Exploitation results
        self.args.log.write("\n--- Exploitation ---\n")
        self.args.log.write(f"Number of points assigned for exploitation: {exploit_points}\n")
        self.args.log.write(f"    Points: {top_q4_df[predictions_column].tolist()}\n")
          
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
        """Stop the timer and calculate the total time taken"""
        
        elapsed_time = round(time.time() - start_time_overall, 2)

        # Log the total time and finalize
        self.args.log.write("==========================================\n")
        self.args.log.write(f"Process Completed! Total time taken for the process: {elapsed_time:.2f} seconds")
        self.args.log.finalize()

        # Move the .dat file to the proper batch folder
        log_file = Path.cwd() / "AL_data.dat"  # Path to the log file in the current directory
        log_destination = os.path.join(self.data_path, "AL_data.dat")  # Define the destination path
        shutil.move(log_file, log_destination)  # Move the file