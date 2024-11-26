######################################################.
#     This file stores active learning functions     #
######################################################.

import pandas as pd
import os
import glob
import re
import pdfplumber
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import ast
import os , sys
import shutil

def check_missing_outputs(self):
        """
        Validates input parameters for active learning.

        This method:
        - Loads default options and adds values for missing attributes ('target_column', 'name_column', 'ignore_list').
        - Prompts for and locates the CSV file if not specified, loading it into a DataFrame.
        - Ensures that required columns for molecule names and target values exist, prompting for values if necessary.
        - Validates 'n_points' and 'tolerance' ensuring valid ranges.
        - Manages the 'batch_column', adding or updating it as needed for data completeness.
        - Updates 'ignore_list' and saves final options to a file.

        Raises:
            SystemExit: If any required input is missing, invalid, or the file is not found.
        """
        # Load options if attributes are missing
        if not self.y or not self.name or not self.ignore:
            options = load_options_from_csv(self.options_file)
            if options:
                if not self.y:
                    self.y = options['y']
                    self.extra_cmd += f' --y {self.y}'
                if not self.name:
                    self.name = options['name']
                    self.extra_cmd += f' --name {self.name}'
                if not self.ignore and options['ignore']:
                    self.ignore = ast.literal_eval(options['ignore'])
                    self.extra_cmd += f' --ignore "[{",".join(self.ignore)}]"'


        # Validate CSV file 
        if not self.csv_name:
            self.csv_name = input("\nx WARNING! The name of the file was not introduced. Introduce name of the CSV file: ")
            self.extra_cmd += f' --csv_name {self.csv_name}'
            if not self.csv_name:
                print("\nx WARNING! The name of the file was not introduced. Exiting.")
                sys.exit()

        if os.path.exists(self.csv_name):
            print(f"\no File '{self.csv_name}' found in the current directory.")
            self.path_csv_name = Path.cwd() / self.csv_name
        else:
            print(f"\no File '{self.csv_name}' was not found in the current directory. Searching in batch directories...")
            for batch_dir in Path.cwd().glob('batch_*'):
                if batch_dir.name != 'batch_plots':
                    potential_path = batch_dir / self.csv_name
                    if potential_path.exists():
                        print(f"\no File '{self.csv_name}' found in '{batch_dir}' directory.")
                        self.path_csv_name = potential_path
                        break
            else:
                print(f"\nx WARNING! The file '{self.csv_name}' was not found. Exiting.")
                sys.exit()

        self.base_name_raw = os.path.splitext(self.csv_name)[0]
        self.df_raw = pd.read_csv(self.path_csv_name)

        # Validate column names and set base name
        match = re.search(r'_b(\d+)', self.base_name_raw)
        self.base_name = re.sub(r'_b\d+', '', self.base_name_raw) if match else self.base_name_raw
        if 'code_name' in self.df_raw.columns:
            self.name = 'code_name'

        if not self.name:
            self.name = input("\nx WARNING! Specify the column containing molecule names: ")
            self.extra_cmd += f' --name {self.name}'
            if self.name not in self.df_raw.columns:
                print(f"\nx WARNING! The column '{self.name}' hasn't been found. Exiting.")
                sys.exit()

        # Validate target column
        if not self.y:
            self.y = input("\nx WARNING! The target column has not been specified correctly. Specify the column: ")
            self.extra_cmd += f' --y {self.y}'

        if self.y not in self.df_raw.columns:
            print(f"\nx WARNING! The target column '{self.y}' hasn't been found. Exiting.")
            sys.exit()

       # Validate n_points
        if self.n_points is None or not isinstance(self.n_points, tuple) or len(self.n_points) != 2:
            self.n_points = input("\nx WARNING! The number of points to explore and exploit has not been specified correctly. Introduce the values as 'explore:exploit': ")
            try:
                # Ensure the input is in the correct format and contains two positive integers
                parts = self.n_points.split(":")
                n_points = tuple(map(int, parts))  # Convert parts to integers
                if len(parts) != 2 or n_points[0] <= 0 or n_points[1] <= 0:
                    raise ValueError
                self.n_points = n_points
                # Add to extra_cmd if the input is valid
                self.extra_cmd += f' --n_points {self.n_points[0]}:{self.n_points[1]}'
            except ValueError:
                print(f"\nx WARNING! Invalid input '{self.n_points}'. Expected format: 'explore:exploit' with two positive integers. Exiting.")
                sys.exit()


        # Validate tolerance level
        if self.tolerance not in self.levels_tolerance:
            self.tolerance = input("\nx WARNING! Enter a valid tolerance level ('tight':1%, 'medium':5%, 'wide':10%): ")
            self.extra_cmd += f' --tolerance {self.tolerance}'
            if self.tolerance not in self.levels_tolerance:
                print(f"\nx WARNING! The tolerance level '{self.tolerance}' is not valid. Exiting.")
                sys.exit()

        # Validate batch column and assign batch number
        if self.batch_column in self.df_raw.columns:
            max_batch_number = int(self.df_raw[self.batch_column].max())
            self.current_number_batch = max_batch_number + 1

            # Check if there are missing values in y column
            last_batch = self.df_raw[self.df_raw[self.batch_column] == max_batch_number]
            if not last_batch[self.y].notna().all():
                print(f"\nx WARNING! The column '{self.y}' contains missing values. Please check the data before proceeding! Exiting.")
                sys.exit()
            # Check if there are values in y but no values in batch column
            if not self.df_raw[self.df_raw[self.y].notna() & self.df_raw[self.batch_column].isna()].empty:
                print(f"\nx WARNING! The column '{self.y}' contains values, but there are missing entries in the column '{self.batch_column}'. Please fix the data before proceeding. Exiting.")
                sys.exit()

        else:
            # Create batch column if it doesn't exist when y has valid data
            if self.y in self.df_raw.columns and self.df_raw[self.y].notna().any():
                self.df_raw[self.batch_column] = 0
                self.df_raw.loc[~self.df_raw[self.y].notna(), self.batch_column] = None
                self.df_raw.to_csv(self.path_csv_name, index=False)
                self.current_number_batch = 1
                print(f"\nx WARNING! Batch column '{self.batch_column}' not found but valid data in '{self.y}'.") 
                print(f"\no Batch column created successfully!")
            else:
                print(f"\nx WARNING! '{self.batch_column}' column not found, and '{self.y}' has no values! Exiting.")
                sys.exit()


        # Check if the 'batch' folder already exists
        self.data_path_check = Path.cwd() / f'batch_{self.current_number_batch}'
        if self.data_path_check.exists():
            overwrite = input(f"\nx WARNING! Directory '{self.data_path_check.name}' already exists. Do you want to overwrite it? (y/n): ").strip().lower()
            if overwrite == 'y':
                shutil.rmtree(self.data_path_check)
                print(f"\no Directory '{self.data_path_check.name}' has been deleted suscessfully!")
            else:
                # Delete the log file and cancel the actual process
                log_file = Path.cwd() / "AL_data.dat"  
                if log_file.exists():
                    log_file.unlink()  # Use .unlink() for a single file 
                print("\nx WARNING! Active learning process has been canceled. Exiting.")
                exit()

        # Add batch column to ignore list and save options
        self.ignore.append(self.batch_column)
        self.ignore = list(set(self.ignore))

        options_df = pd.DataFrame({
            'y': [self.y],
            'csv_name': [self.csv_name],
            'ignore': [str(self.ignore)],
            'name': [self.name],
        })
        options_df.to_csv('options.csv', index=False)
        print("\no Options saved successfully!\n")   

        return self

def load_options_from_csv(options_file):
    """
    Load default options from a CSV file if user inputs are not provided.

    Parameters:
    -----------
    options_file : str
        The path to the CSV file containing default options.

    Returns:
    --------
    dict or None
        A dictionary containing the default values for 'y', 'ignore', and 'name' 
        if the file is successfully read. Returns None if the file is not found.
    """
    try:
        df_options = pd.read_csv(options_file)
        options = {
            'y': df_options['y'].values[0],
            'ignore': df_options['ignore'].values[0],
            'name': df_options['name'].values[0]
        }
        return options
    except (FileNotFoundError, pd.errors.EmptyDataError, KeyError):
        return None
    
def generate_quartile_medians_df(df_total, df_exp, values_column):
    """
    Assign quartiles (q1, q2, q3, q4) to values in a DataFrame column based on their range.
    Also, calculate the median value for each quartile.

    Parameters:
    -----------
    df_total : pd.DataFrame
        Experimental values and predictions are used to calculate the range of values for determining quartiles.
    df_exp : pd.DataFrame
        The experimental dataset where quartiles will be assigned.
    values_column : str
        The name of the column in df_total and df_exp that contains the target values.

    Returns:
    --------
    df_exp : pd.DataFrame
        The experimental dataset with a new 'quartile' column, assigning each value to q1, q2, q3, or q4.
    quartile_medians : dict
        A dictionary containing the median values for the first three quartiles (q1, q2, q3).

    """
    # Find min and max values in the total dataset and adjust their range
    min_val, max_val = df_total[values_column].min() * 0.7, df_total[values_column].max() * 1.3

    # Calculate the quartile boundaries
    separation_range = (max_val - min_val) / 4
    boundaries = [min_val + i * separation_range for i in range(5)]
    
    # Assign quartiles to the experimental dataset based on the boundaries
    df_exp['quartile'] = df_exp[values_column].apply(
        lambda val: 'q1' if val < boundaries[1] else 'q2' if val < boundaries[2] else 'q3' if val < boundaries[3] else 'q4'
    )

    # Calculate the median value for the first three quartiles (q1, q2, q3)
    quartile_medians = {f'q{q+1}': (boundaries[q] + boundaries[q+1]) / 2 for q in range(3)}

    return df_exp, quartile_medians, boundaries


def get_size_counters(df):
    """
    Count the number of points in each quartile (q1, q2, q3).

    Parameters:
    -----------
    df : pd.DataFrame
        The DataFrame that contains a 'quartile' column, which categorizes values into quartiles (q1, q2, q3).

    Returns:
    --------
    dict
        A dictionary with keys 'q1', 'q2', and 'q3' where each key represents the number of points in that quartile.
    """
    return {q: df[df['quartile'] == q].shape[0] for q in ['q1', 'q2', 'q3']}


def find_closest_value(df, target_median, target_column):
    """
    Find the value in a specified column of a DataFrame that is closest to a target mean value.

    Parameters:
    -----------
    df : pd.DataFrame
        The DataFrame containing the data to search through.
    target_median : float
        The target median value to compare against.
    target_column : str
        The name of the column in which to find the value closest to the target mean.

    Returns:
    --------
    pd.Series
        The row in the DataFrame where the value in the target_column is closest to the target_mean.
    """
    return df.iloc[(df[target_column] - target_median).abs().argmin()]


def assign_values(df, number_of_values, quartile_medians, size_counters, target_column):
    """
    Assign values to quartiles with the fewest points based on proximity to the quartile medians.

    Parameters:
    -----------
    df : pd.DataFrame
        The DataFrame containing the dataset from which values will be selected.
    number_of_values : int
        The number of values to assign across the quartiles.
    quartile_medians : dict
        A dictionary containing the median values for each quartile.
    size_counters : dict
        A dictionary containing the number of points currently assigned to each quartile (q1, q2, q3).
    target_column : str
        The name of the column in the DataFrame from which values will be assigned.

    Returns:
    --------
    assigned_points : dict
        A dictionary with quartiles ('q1', 'q2', 'q3') as keys and the list of assigned values for each quartile.
    min_size_quartiles : list
        A list of the quartiles with the fewest points during each iteration.
    """
    assigned_points = {q: [] for q in ['q1', 'q2', 'q3']}
    min_size_quartiles = []
    
    for _ in range(number_of_values):
        # Select the quartile with the fewest points
        min_size_quartile = min(size_counters, key=size_counters.get)
        target_median = quartile_medians[min_size_quartile]
        min_size_quartiles.append(min_size_quartile)
        
        # Find the closest value to the quartile mean
        closest_value_name = find_closest_value(df, target_median, target_column)
        if closest_value_name is not None:
            closest_value = closest_value_name[target_column]
            assigned_points[min_size_quartile].append(closest_value)
            size_counters[min_size_quartile] += 1
            
            # Drop the assigned value from the DataFrame to avoid duplicates
            df = df.drop(closest_value_name.name)

    return assigned_points, min_size_quartiles

def extract_rmse_and_score_from_column(page, bbox):
    """
    Extract RMSE and SCORE value from a specific column on a given page of a PDF.
    First tries to match 'Test' results, if not found, tries 'Valid' results.

    Parameters:
    -----------
    page : pdfplumber Page object
        The page from which to extract the data.(PDF report) 
    bbox : tuple
        The bounding box (coordinates) to specify the column area in the PDF (PFI model or non PFI model).

    Returns:
    --------
    tuple
        A tuple containing the extracted RMSE value and SCORE value, or (None, None) if no patterns match.

    """
    # Extract the text from the defined bounding box
    text_page = page.within_bbox(bbox).extract_text()

    # First try to match the "Test" pattern for RMSE
    match_RMSE = re.search(r'Test : R[\d²] = [\d.]+, MAE = [\d.eE\+\-]+, RMSE = ([\d.]+(?:e[\+\-]?\d+)?)', text_page)
    
    # If "Test" pattern not found, try the "Valid" pattern for RMSE
    if not match_RMSE:
        match_RMSE = re.search(r'Valid\. : R[\d²] = [\d.]+, MAE = [\d.eE\+\-]+, RMSE = ([\d.]+(?:e[\+\-]?\d+)?)', text_page)
    
    # Extract the RMSE value if found
    rmse_value = float(match_RMSE.group(1)) if match_RMSE else None

    # Try to match the "Score" pattern
    match_score = re.search(r'Score (\d+)', text_page)

    # Extract the SCORE value if found
    score_value = int(match_score.group(1)) if match_score else None

    # Return the matched values or (None, None) if not found
    return rmse_value, score_value


def extract_sd_from_column(page, bbox):
    """
    Extract SD value from a specific column on a given page of a PDF.

    Parameters:
    -----------
    page : pdfplumber Page object
        The page from which to extract the data.(PDF report) 
    bbox : tuple
        The bounding box (coordinates) to specify the column area in the PDF. (PFI model or non PFI model).

    Returns:
    --------
    float or None
        The extracted SD value, or None if no pattern matches.
    """
    # Extract the text from the defined bounding box
    text_page = page.within_bbox(bbox).extract_text()

    # Search for SD pattern
    match_sd = re.search(r'High variation,\s*4\*SD\s*\((valid\.|test)\)\s*=\s*([\d.]+)\s*\([\d]+% y-range\)', text_page)
    
    if match_sd:
        return float(match_sd.group(2)) / 4  # Dividing SD value by 4 as it's 4*SD in the PDF
    return None

def extract_points_from_csv(batch_number):
    """
    Extract validation and test points from CSV files for both PFI and No_PFI models.
    
    Args:
        batch_number (int): The batch number to process.

    Returns:
        dict: A dictionary with the number of validation and test points for No_PFI and PFI models.
    """
    # Define the base path for the batch
    base_path = Path.cwd() / f'batch_{batch_number}' / f'ROBERT_b{batch_number}' / 'GENERATE' / 'Best_model'
    
    points = {}
    
    # Loop through No_PFI and PFI model to process both
    for model in ['No_PFI', 'PFI']:
        # Build the path for the current model (No_PFI or PFI)
        csv_path = base_path / model
        # Search for CSV files matching the pattern '*_db.csv' in which points are stored
        csv_file = glob.glob(os.path.join(csv_path, '*_db.csv'))
        
        # If a file is found, read it and count validation and test points
        if csv_file:
            df = pd.read_csv(csv_file[0])
            points[f'{model}_validation_points'] = len(df[df['Set'] == 'Validation'])
            points[f'{model}_test_points'] = len(df[df['Set'] == 'Test'])
        else:
            # If no file is found, set point counts to 0
            points[f'{model}_validation_points'] = 0
            points[f'{model}_test_points'] = 0
    
    return points


def process_batch(batch_number):
    """
    Extract RMSE, SD, score data from both left and right columns of the PDF report for a specific batch. (PFI model and non PFI model).
    Extract number or points from CSV files for both PFI and No_PFI models.

    Parameters:
    -----------
    batch_number : int
        The batch number to process (e.g., 1, 2, 3).

    Returns:
    --------
    dict 
        A dictionary containing the batch number, RMSE, and SD values for both columns (no_PFI and PFI).
    """
    pdf_robert_path = Path.cwd() / f'batch_{batch_number}' / f'ROBERT_b{batch_number}' / 'ROBERT_report.pdf'  
    
    try:
        # Open the PDF file
        with pdfplumber.open(pdf_robert_path) as pdf:
            # Define the bounding box coordinates for left (no_PFI) and right (PFI) columns
            bbox_no_PFI = (0, 0, 300, pdf.pages[0].height)  # Left column for no_PFI
            bbox_PFI = (300, 0, pdf.pages[0].width, pdf.pages[0].height)  # Right column for PFI

            # Extract RMSE from page 0
            page_0 = pdf.pages[0]
            rmse_no_PFI, score_no_PFI = extract_rmse_and_score_from_column(page_0, bbox_no_PFI)
            rmse_PFI, score_PFI = extract_rmse_and_score_from_column(page_0, bbox_PFI)

            # Extract SD from page 2
            page_2 = pdf.pages[2]
            sd_no_PFI = extract_sd_from_column(page_2, bbox_no_PFI)
            sd_PFI = extract_sd_from_column(page_2, bbox_PFI)

            # Extract validation and test points from CSV files
            points = extract_points_from_csv(batch_number)

            # Ensure both columns contain data
            if all(x is not None for x in [rmse_no_PFI, rmse_PFI, sd_no_PFI, sd_PFI]):
                # Return two separate dictionaries for PFI and no_PFI
                no_pfi_dict = {
                    'batch': batch_number,
                    'rmse_no_PFI': rmse_no_PFI,
                    'SD_no_PFI': sd_no_PFI,
                    'score_no_PFI': score_no_PFI,
                    'validation_points_no_PFI': points['No_PFI_validation_points'],
                    'test_points_no_PFI': points['No_PFI_test_points']
                }
                
                pfi_dict = {
                    'batch': batch_number,
                    'rmse_PFI': rmse_PFI,
                    'SD_PFI': sd_PFI,
                    'score_PFI': score_PFI,
                    'validation_points_PFI': points['PFI_validation_points'],
                    'test_points_PFI': points['PFI_test_points']
                }
                
                return no_pfi_dict, pfi_dict
            else:
                print(f"x WARNING! Could not find RMSE or SD in batch {batch_number}")
                return None

    except Exception as e:
        print(f"x WARNING! Fail processing batch {batch_number}: {e}")
        return None

def get_metrics_from_batches():
    """
    Generates metrics for plotting by processing each batch directory.

    Iterates over directories named 'batch_*' (excluding 'batch_plots' and 'batch_0') 
    and collects metrics with and without PFI for each batch by calling 'process_batch'.

    Returns:
        tuple: (results_plot_no_PFI, results_plot_PFI), lists of metrics without 
               and with PFI for each batch.
    """
    results_plot_no_PFI = []
    results_plot_PFI = []

    # Process each valid batch directory
    for batch_dir in Path.cwd().glob('batch_*'):
        # Exclude batch_plots directory and batch_0 directory
        if batch_dir.name != 'batch_plots' and batch_dir.name != 'batch_0':
            batch_number = batch_dir.name.split('_')[1]
            no_pfi_result, pfi_result = process_batch(batch_number)

            if no_pfi_result:
                results_plot_no_PFI.append(no_pfi_result)
            if pfi_result:
                results_plot_PFI.append(pfi_result)

    return   results_plot_no_PFI, results_plot_PFI 

class EarlyStopping:
    """
    Monitors model performance to determine convergence based on specified tolerances for different metrics.

    This class tracks metrics (e.g., RMSE, SD, and score) over iterations, marking convergence if improvements
    fall below specified thresholds for a set number of iterations (patience). Results are logged and saved 
    for analysis.

    """
    def __init__(self, patience=2, score_tolerance=0, rmse_min_delta=0.05, sd_min_delta=0.05, logger=None ):
        
        """
        patience : int
            Number of iterations with no significant improvement after which training will be stopped.
        score_tolerance : int
            Minimum integer improvement in the score to reset patience.
        rmse_min_delta : float
            Minimum change in RMSE to consider an improvement.
        sd_min_delta : float
            Minimum change in SD to consider an improvement.
        ----------
        output_folder : Path
            The root folder where all plots and convergence results will be saved.
        output_folder_no_pfi : Path
            The subfolder within 'output_folder' where results for the "no_PFI" model type will be stored.
        output_folder_pfi : Path
            The subfolder within 'output_folder' where results for the "PFI" model type will be stored.

        """
        self.patience = patience
        self.score_tolerance = score_tolerance
        self.rmse_min_delta = rmse_min_delta
        self.sd_min_delta = sd_min_delta
        self.log = logger

        # Define output folders for PFI and no_PFI
        self.output_folder = Path.cwd() / "batch_plots"
        self.output_folder.mkdir(exist_ok=True)
        self.output_folder_no_pfi = self.output_folder / 'no_PFI_plots'
        self.output_folder_pfi = self.output_folder / 'PFI_plots'
        self.output_folder_no_pfi.mkdir(exist_ok=True)
        self.output_folder_pfi.mkdir(exist_ok=True)


    def check_metric_convergence(self, previous_row, last_row, metric_name, tolerance):
        """
        Checks if a specific metric has converged.
        The metric is considered converged if:
        - It has not worsened (i.e., no negative changes).
        - It has improved, but by less than the specified tolerance.
        
        Parameters:
        ----------
        previous_row : pd.Series
            The metrics from the previous iteration.
        last_row : pd.Series
            The metrics from the current iteration.
        metric_name : str
            The name of the metric being checked.
        tolerance : float
            The minimum percentage change required for improvement.
            
        Returns:
        -------
        bool
            True if the metric has converged (no worsening or minimal improvement),
            False if the metric has worsened or improved significantly.
        """
        # Calculate the difference between the previous and current metric values
        difference = previous_row[metric_name] - last_row[metric_name]
        
        print(f"difference: {difference}")
        print(f"previous: {previous_row[metric_name]}")
        print(f"current: {last_row[metric_name]}")
        print(f"tolerance: {tolerance * previous_row[metric_name]}")
        
        # If the metric has worsened (negative difference), return False (not converged)
        if difference < 0:
            return False

        # If the improvement is less than the tolerance, consider it converged
        return difference <= (tolerance * previous_row[metric_name])

    
    def check_score_convergence(self, previous_row, last_row, score_column,score_tolerance):
        """
        Checks if the score has improved beyond the score tolerance.
        If the score has not worsened, it has converged. Return True.

        """
        return (last_row[score_column] - previous_row[score_column]) >= score_tolerance
    
    def show_summary(self, df, model_type):
        """
        Displays a final summary for either PFI or no_PFI metrics.
        
        Parameters:
        -----------
        df : pd.DataFrame
            The DataFrame containing the batch results.
        model_type : str
            Either 'PFI' or 'no_PFI' to determine which set of metrics to display.
        """
        batch = df['batch'].tolist()

        if model_type == 'PFI':
            scores = df['score_PFI'].tolist()
            rmse = df['rmse_PFI'].tolist()
            sd = df['SD_PFI'].tolist()

        elif model_type == 'no_PFI':
            scores = df['score_no_PFI'].tolist()
            rmse = df['rmse_no_PFI'].tolist()
            sd = df['SD_no_PFI'].tolist()

        # Display the summary for the given model type
        self.log.write(f"\nTotal Iterations: {len(batch)}")
        self.log.write(f"Final Score Model {model_type}: {scores[-1]} (Started at {scores[0]})")
        self.log.write(f"Final RMSE Model {model_type}: {rmse[-1]:.2f} (Started at {rmse[0]:.2f})")
        self.log.write(f"Final SD Model {model_type}: {sd[-1]:.2f} (Started at {sd[0]:.2f})")
        self.log.write(f"\nModel {model_type} has stabilized and will no longer improve significantly.\n")

    def check_convergence_model(self, df, model_type):
        """
        Check for convergence for either the PFI or no_PFI model separately.
        
        Parameters:
        -----------
        df : pd.DataFrame
            The DataFrame containing the batch results.
        model_type : str
            Either 'PFI' or 'no_PFI' to determine which set of metrics to check.
        
        Returns:
        --------
        pd.DataFrame
            The updated DataFrame with convergence columns and status.
        """
         # Print convergence report header
        self.log.write("\n===============================================")
        self.log.write(f"      Model {model_type} Convergence Report")
        self.log.write("===============================================")
                
        # Determine column names based on model type
        if model_type == 'PFI':
            score_column = 'score_PFI'
            rmse_column = 'rmse_PFI'
            sd_column = 'SD_PFI'
        else:
            score_column = 'score_no_PFI'
            rmse_column = 'rmse_no_PFI'
            sd_column = 'SD_no_PFI'

        # Initialize convergence columns if they don't already exist
        for metric in ['rmse', 'SD', 'score']:
            column_name = f"{metric}_converged"
            if column_name not in df.columns:
                df[column_name] = 0  # Initialize with 0 by default (not converged)

        # Add a "convergence" column initialized with "no" for all rows if it doesn't exist
        if 'convergence' not in df.columns:
            df['convergence'] = 'no'
        
        # Check if there are enough rows to proceed with convergence checking
        if df.shape[0] < 2:
            # Not enough data to check for convergence
            self.log.write(f"\no Not enough batches to check for convergence for Model {model_type}!")
            return df  # Return the DataFrame with initialized columns

        # Initialize the no_improvement_streak variable
        no_improvement_streak = 0

        # Loop over the iterations, considering the patience
        for i in range(1, min(self.patience + 1, df.shape[0])):
            current_row = df.iloc[-i]
            previous_row = df.iloc[-(i+1)]
            
            # Check for improvements in the selected model
            patience_convergence = {
                'rmse': self.check_metric_convergence(previous_row, current_row, rmse_column, self.rmse_min_delta),
                'SD': self.check_metric_convergence(previous_row, current_row, sd_column, self.sd_min_delta),
                'score': self.check_score_convergence(previous_row, current_row, score_column, self.score_tolerance)
            }
            print(patience_convergence)
            # Log convergence status for each metric in this row
            self.log.write(f"\nEvaluating Model {model_type} batch {int(current_row['batch'])}:")
            for metric, converged in patience_convergence.items():
                column_name = f"{metric}_converged"
                if not converged:
                    self.log.write(f" X {metric} for {model_type} model has not converged.")
                    df.at[current_row.name, column_name] = 0  # Did not converge
                else:
                    self.log.write(f" o {metric} for {model_type} model has converged.")
                    df.at[current_row.name, column_name] = 1  # Converged

            # Check if all metrics have converged; if so, increment the no improvement streak
            if all(patience_convergence.values()):
                no_improvement_streak += 1

        # If the patience limit is reached (no improvements), declare convergence
        if no_improvement_streak >= self.patience:
            # Mark the last rows (based on patience) with "yes" for convergence
            df.loc[df.index[-self.patience:], 'convergence'] = 'yes'
            self.show_summary(df, model_type)  # Show final summary after convergence
        else:
            self.log.write('\no Not converged yet, keep working with active learning process!')

        return df  # Return the DataFrame with convergence results
 
    
    def check_convergence(self, results_plot_no_PFI, results_plot_PFI):
        """
        Check for convergence for both PFI and no_PFI models independently.
        This function also creates appropriate folders for storing plots and saves the results in CSV format.
        
        Parameters:
        -----------
        results_plot_no_PFI : list of dicts
            A list of dictionaries containing batch data metrics for the no_PFI model.
        results_plot_PFI : list of dicts
            A list of dictionaries containing batch data metrics for the PFI model.
        """
        
        # Paths to the CSV files for no_PFI and PFI
        no_pfi_csv_path = self.output_folder_no_pfi / 'results_plot_no_PFI.csv'
        pfi_csv_path = self.output_folder_pfi / 'results_plot_PFI.csv'

        # Process no_PFI results
        no_pfi_df = pd.DataFrame(results_plot_no_PFI)
        no_pfi_df = self.check_convergence_model(no_pfi_df, 'no_PFI')
        no_pfi_df['batch'] = no_pfi_df['batch'].astype(int)  # Ensure batch column is integer
        if no_pfi_csv_path.exists():
            existing_no_pfi_df = pd.read_csv(no_pfi_csv_path)
            existing_no_pfi_df['batch'] = existing_no_pfi_df['batch'].astype(int)  # Ensure batch column is integer
            last_batch_no_pfi = existing_no_pfi_df['batch'].max()
            new_no_pfi_df = no_pfi_df[no_pfi_df['batch'] > last_batch_no_pfi]
            updated_no_pfi_df = pd.concat([existing_no_pfi_df, new_no_pfi_df], ignore_index=True)
        else:
            updated_no_pfi_df = no_pfi_df
        updated_no_pfi_df.to_csv(no_pfi_csv_path, index=False)

        # Process PFI results
        pfi_df = pd.DataFrame(results_plot_PFI)
        pfi_df = self.check_convergence_model(pfi_df, 'PFI')
        pfi_df['batch'] = pfi_df['batch'].astype(int)  # Ensure batch column is integer
        if pfi_csv_path.exists():
            existing_pfi_df = pd.read_csv(pfi_csv_path)
            existing_pfi_df['batch'] = existing_pfi_df['batch'].astype(int)  # Ensure batch column is integer
            last_batch_pfi = existing_pfi_df['batch'].max()
            new_pfi_df = pfi_df[pfi_df['batch'] > last_batch_pfi]
            updated_pfi_df = pd.concat([existing_pfi_df, new_pfi_df], ignore_index=True)
        else:
            updated_pfi_df = pfi_df
        updated_pfi_df.to_csv(pfi_csv_path, index=False)

        # Return the updated DataFrames for further use if needed
        return updated_no_pfi_df, updated_pfi_df

def plot_metrics_subplots(data, model_type, output_dir="batch_plots", batch_count=0):
    """
    Function to plot different metrics in a 4x1 subplot layout and save as a single image.
    """
    # Configure output folder based on model type
    folder_name = "PFI_plots" if model_type == "PFI" else "no_PFI_plots"
    save_path = os.path.join(output_dir, folder_name)
    os.makedirs(save_path, exist_ok=True)
    filename = os.path.join(save_path, f"{model_type}_subplots_vertical.png")

    # Extract data for each metric from the DataFrame
    batches = data['batch'].astype(int).values
    score_values = data[f'score_{model_type}'].values
    rmse_values = data[f'rmse_{model_type}'].values
    sd_values = data[f'SD_{model_type}'].values
    validation_values = data[f'validation_points_{model_type}'].values
    test_values = data[f'test_points_{model_type}'].values
    rmse_converged = data['rmse_converged'].values
    sd_converged = data['SD_converged'].values
    score_converged = data['score_converged'].values

    # Figure and 4x1 subplot layout
    base_weight_per_batch = 2.5
    height = 14  # Adjust this value to control spacing per batch
    base_width = base_weight_per_batch + batch_count/2
    width = 0.5  # Width of the bars
    edge_linewidth = 1.5  # Edge thickness

    # Create subplots with dynamic figsize
    fig, axs = plt.subplots(4, 1, figsize=(base_width, height))
    
    # Custom legend for converged metrics
    converged_patch = mpatches.Patch(edgecolor='black', facecolor='none', label='Metric Converged', linewidth=edge_linewidth)

    # Plot 1 - Stacked Validation and Test Points
    bars_val = axs[0].bar(batches, validation_values, width, color='#FFA500', label='Validation Points')
    bars_test = axs[0].bar(batches, test_values, width, bottom=validation_values, color='#FF0000', label='Test Points')
    axs[0].set_title('Number of Points')
    axs[0].set_xlabel('Batch')
    axs[0].set_ylabel('Number of Points')
    axs[0].set_xticks(batches)
    axs[0].set_ylim(0, (max(validation_values + test_values) * 1.3))
    axs[0].legend(loc='upper right', fancybox=True, shadow=True)

    # Add individual values for validation and test points
    for bar_val, bar_test, val, test in zip(bars_val, bars_test, validation_values, test_values):
        # Text for validation points
        axs[0].text(bar_val.get_x() + bar_val.get_width() / 2, bar_val.get_height() / 2,
                    f'{val}', ha='center', va='center', color='black', fontsize=10)
        
        # Text for test points
        axs[0].text(bar_test.get_x() + bar_test.get_width() / 2, bar_val.get_height() + bar_test.get_height() / 2,
                    f'{test}', ha='center', va='center', color='black', fontsize=10)


    # Plot 2 - Standard Deviation (SD)
    bars = axs[1].bar(batches, sd_values, width, color='#87CEEB', label='SD',
                    edgecolor=['black' if c else 'none' for c in sd_converged],
                    linewidth=edge_linewidth)
    axs[1].set_title('SD (Standard Deviation)')
    axs[1].set_xlabel('Batch')
    axs[1].set_ylabel('SD Value')
    axs[1].set_xticks(batches)
    axs[1].set_ylim(0, max(sd_values) * 1.3)
    for bar in bars:
        axs[1].text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{bar.get_height():.2f}', 
                    ha='center', va='bottom')
    axs[1].legend(handles=[converged_patch], loc='upper right', fancybox=True, shadow=True)

    # Plot 3 - RMSE
    bars = axs[2].bar(batches, rmse_values, width, color='#4682B4', label='RMSE',
                    edgecolor=['black' if c else 'none' for c in rmse_converged],
                    linewidth=edge_linewidth)
    axs[2].set_title('RMSE (Root Mean Square Error)')
    axs[2].set_xlabel('Batch')
    axs[2].set_ylabel('RMSE Value')
    axs[2].set_xticks(batches)
    axs[2].set_ylim(0, max(rmse_values) * 1.3)
    for bar in bars:
        axs[2].text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{bar.get_height():.2f}', 
                    ha='center', va='bottom')
    axs[2].legend(handles=[converged_patch], loc='upper right', fancybox=True, shadow=True)


    # Plot 4 - Score
    bars = axs[3].bar(batches, score_values, width, color='#32CD32', label='Score',
                    edgecolor=['black' if c else 'none' for c in score_converged],
                    linewidth=edge_linewidth)
    axs[3].set_title('ROBERT Score')
    axs[3].set_xlabel('Batch')
    axs[3].set_ylabel('Score Value')
    axs[3].set_xticks(batches)
    axs[3].set_ylim(0, max(score_values) * 1.3)
    for bar in bars:
        axs[3].text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{bar.get_height():.0f}', 
                    ha='center', va='bottom')
    axs[3].legend(handles=[converged_patch], loc='upper right', fancybox=True, shadow=True)

    plt.tight_layout()
    # plt.subplots_adjust(hspace=0.001)  # Reduce hspace to bring subplots closer together
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()  