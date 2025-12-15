"""
Parameters
----------
    csv_name : str
        Name of the CSV file containing the database. (i.e. 'FILE.csv'). 
    y : str
        Name of the column(s) containing the response variable(s) in the input CSV file.
        - For a single column, just provide the column name as a string (e.g., 'solubility').
        - To optimize two columns simultaneously, provide a list in the format: [y1,y2]
          where y1 and y2 are the names of the columns (e.g., '[yield,ee]').
    name : str
        Name of the column containing the molecule names in the input CSV file (i.e. 'names').
    ignore : list, default=[]
        List containing the columns of the input CSV file that will be ignored during the BO process
        (i.e. --ignore "[name,SMILES]"). The descriptors will be included in the final CSV file. The y value, name column and batch column
        are automatically ignored.
    batch_number : int, default=0
        Number of the batch to be processed. The CSV file is always taken from the specified batch folder, 
        and a new folder named 'batch_{batch_number+1}' will be generated for the output.
    n_exps : int, default=1
        Specifies the number of new points for exploration and exploitation in the next batch. 
    reverse : bool, default=False
        If False (default), the target value (y) is maximized. If True, the target value is minimized.
"""

#####################################################
#           This file stores the BO class           #
#        used in the active learning process        #
#####################################################

from edbo.optimizer_botorch import EDBOplus
from almos.utils import load_variables
import time
import pandas as pd
import sys
from pathlib import Path
import shutil
import os
import re

class bo:
    """
    Active Learning class using
    Bayesian Optimization with EDBOplus.
    """
    def __init__(self, **kwargs):

        # Initialize the timer
        start_time = time.time()

        # load default and user-specified variables
        self.args = load_variables(kwargs, "bo")

        # Check if the user has specified a batch number
        self._load_initial_csv()

        # Run EDBOplus with the specified parameters
        self._run_edbo()

        # Log the total time and finalize
        self._finalize(start_time)

    def _load_initial_csv(self):
        """
        Loads the input CSV from the batch folder, ensures required columns exist,
        fills missing target values with 'PENDING', and selects numeric features.
        """
        csv_name = self.args.csv_name
        batch = self.args.batch_number
        name = self.args.name

        if not csv_name:
            self.args.log.write(f"\nx WARNING. Please, specify your CSV file required, e.g. --csv_name example.csv")
            self.args.log.finalize()
            sys.exit()
        batch_folder = Path.cwd() / f"batch_{batch}"
        
        if not batch_folder.exists():
            self.args.log.write(f"\nx WARNING. Folder {batch_folder} not found.")
            self.args.log.finalize()
            sys.exit()
        file = batch_folder / (csv_name if csv_name.endswith('.csv') else f"{csv_name}.csv")
        if not file.exists():
            self.args.log.write(f"\nx WARNING. CSV '{csv_name}' not found in {batch_folder}.")
            self.args.log.finalize()
            sys.exit()

        # Make a copy as csv_original in the same folder
        original_copy = batch_folder / f"{csv_name}_original.csv"
        shutil.copy(str(file), str(original_copy))
        
        # Parse y columns, handling cases like '[ee, yield]'
        y_arg = self.args.y
        if isinstance(y_arg, str) and y_arg.startswith('[') and y_arg.endswith(']'):
            y_cols = [col.strip() for col in y_arg[1:-1].split(',')]
        elif isinstance(y_arg, str) and ',' in y_arg:
            y_cols = [col.strip() for col in y_arg.split(',')]
        else:
            y_cols = [y_arg]

        # For each target column, ensure it exists and fill missing values
        df = pd.read_csv(file)
        for col in y_cols:
            if col not in df.columns:
                sys.exit(f"ERROR: Target column '{col}' not found in CSV.")
            # Fill missing or empty values with "PENDING"
            df[col] = df[col].fillna("PENDING").replace("", "PENDING")


        # Delete any existing batch column if it exists
        prediction_suffixes = ['_predicted_mean', '_predicted_variance', 'expected_improvement']
        cols_to_drop = [c for c in df.columns if any(c.endswith(suf) for suf in prediction_suffixes)]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
            
        # Encode categorical columns as integer codes (1, 2, 3, ...) instead of one-hot
        categorical_cols = [
            col for col in df.select_dtypes(include=['object']).columns
            if col not in y_cols and col != name and col not in self.args.ignore
        ]
        for col in categorical_cols:
            df[col] = df[col].astype('category').cat.codes + 1  # 1-based encoding
        df.to_csv(file, index=False)  # Save back to ensure consistency

        self.df = df
        self.csv_path = file
        self.csv_dir = file.parent
        self.current_batch = batch + 1

        # Build the ignore set more simply
        ignore = {'batch', 'SMILES', name}
        ignore.update(y_cols)
        ignore |= set(self.args.ignore)

        # Select only numeric columns as features
        self.features = [c for c in df.columns if c not in ignore]
        if not self.features:
            sys.exit("ERROR: No numeric features found after filtering. Check your ignore list and input data.")

    def _run_edbo(self):
        """
        Runs EDBOplus in the batch folder to ensure all files are generated in the correct location.
        """
        n_points = int(getattr(self.args, "n_exps", 1) or 1)
        out_folder = self.csv_dir.parent / f"batch_{self.current_batch}"
        out_folder.mkdir(exist_ok=True)

        # Determine objectives and objective_mode based on y and reverse
        if isinstance(self.args.y, str) and self.args.y.startswith('[') and self.args.y.endswith(']'):
            objectives = [col.strip() for col in self.args.y[1:-1].split(',')]
        elif isinstance(self.args.y, str) and ',' in self.args.y:
            objectives = [col.strip() for col in self.args.y.split(',')]
        else:
            objectives = [self.args.y]

        # objective_mode must be a list with one entry per objective
        if isinstance(self.args.reverse, list):
            objective_mode = ['min' if rev else 'max' for rev in self.args.reverse]
        else:
            objective_mode = (['min'] if self.args.reverse else ['max']) * len(objectives)

        print(f"objectives={objectives}")
        print(f"objective_mode={objective_mode}")

        # Change working directory to the batch folder so EDBOplus reads/writes files there
        original_cwd = os.getcwd()
        try:
            os.chdir(self.csv_dir)
            EDBOplus().run(
            filename=str(self.csv_path.name),
            objectives=objectives,
            objective_mode=objective_mode,
            batch=n_points,
            columns_features=self.features,
            init_sampling_method='cvtsampling',
            )
            print(f"EDBOplus optimization completed. Results saved in {out_folder}")
        finally:
            os.chdir(original_cwd)

    def _finalize(self, start_time):
        """
        Waits for the prediction file to appear, moves it to the next batch folder,
        and prints the elapsed time.
        """
        elapsed = time.time() - start_time
        out_folder = self.csv_dir.parent / f"batch_{self.current_batch}"
        out_folder.mkdir(exist_ok=True)

        # Wait up to 2 seconds for the pred_*.csv file to appear
        pred_file = None
        for _ in range(2):
            pred_file = next(self.csv_dir.glob("pred_*.csv"), None)
            if pred_file:
                break
            time.sleep(1)

        if pred_file:
            # Remove .csv extension if present in csv_name
            base_name = self.args.csv_name
            if base_name.lower().endswith('.csv'):
                base_name = base_name[:-4]

            # If base_name ends with _number, increment number
            match = re.match(r"^(.*)_(\d+)$", base_name)
            if match:
                prefix, num = match.groups()
                new_base = f"{prefix}_{int(num) + 1}"
            else:
                new_base = f"{base_name}_{self.current_batch}"

            new_name = f"{new_base}.csv"
            shutil.move(str(pred_file), str(out_folder / new_name))
            
            print(f"Moved {new_name} to {out_folder}")
        else:
            print("WARNING: pred_*.csv not found after waiting.")

        print(f"Process completed in {elapsed:.2f}s.")