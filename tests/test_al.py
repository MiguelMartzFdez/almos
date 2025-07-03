#!/usr/bin/env python

######################################################.
# 	        Testing AL module with pytest 	         #
######################################################.

import os
import glob
import pytest
import shutil
import subprocess
import pandas as pd
import re

# saves the working directories and names of important files
path_tests = os.getcwd() + "/tests"
path_plots = os.getcwd() + "/batch_plots"
path_batch = os.getcwd() + "/batch_1"
batch_pattern = os.path.join(os.getcwd(), "batch_*")
csv_to_remove = os.path.join(os.getcwd(), "options.csv")

# AL tests
@pytest.mark.parametrize(
    "test_job",
    [
        (
            "standard"
        ),  # standard test  
        (
            "firewall_missing_target_values"
        ),  # test if target column values are missing
        (
            "firewall_missing_batch"
        ),  # test if batch column is missing but values of target column are valid
        (
            "missing_input"
        ),  # test that if the --names, --y or --csv_name options are empty, a prompt pops up and asks for them
        (
            "tolerance"
        ),  # check if change in tolerance parameter works   
        (
            "reverse"
        ),  # check if we look for minimum values for exploitation with reverse parameter
    ],
)


def test_AL(test_job):

   # Directories to delete if they exist
    for dir_path in glob.glob(batch_pattern):
        if os.path.isdir(dir_path):  
            shutil.rmtree(dir_path)
    if os.path.isdir(path_plots):
        shutil.rmtree(path_plots)

    # Remove the CSV file 'options.csv' if it exists
    if os.path.exists(csv_to_remove):
        os.remove(csv_to_remove)

    # runs the program with the different tests
    cmd_almos = [
        "python",
        "-m",
        "almos",
        "--el",
        '--robert_keywords "--model RF --repeat_kfolds 1 "',
        "--ignore", "index",
    ]

    if test_job != 'missing_input':
        cmd_almos = cmd_almos + ['--y','target',
                                   "--csv_name", f"{path_tests}/AL_example.csv",
                                   "--name","name",
                                   "--n_exps","5",]
        
        
    if test_job == 'firewall_missing_target_values':

        # Run the command and capture the output
        cmd_almos = (
            f"python -m almos --el --robert_keywords "
            f'"--model RF --repeat_kfolds 1 " '
            f"--ignore index --y target "
            f"--csv_name {path_tests}/AL_example_missing_targets.csv "
            f"--name name --n_exps 5"
        )

        result = subprocess.run(
            cmd_almos,
            capture_output=True,  # Capture information from subprocess
            text=True, # As text 
            shell=True  
        )

        # Verify that the program displays the warning message
        assert "WARNING! The column 'target' contains missing values. Please check the data before proceeding! Exiting." in result.stdout, \
                f"The expected warning message was not found in '{test_job}' test." 
        
    if test_job == 'firewall_missing_batch':

        # Path to the test CSV file
        test_csv_path = 'tests/AL_example_missing_batch.csv'
        backup_csv_path = 'tests/AL_example_missing_batch_backup.csv'

        # Backup the CSV file for keep the csv without batch column for further tests
        shutil.copyfile(test_csv_path, backup_csv_path)

        try:
            # Change the csv file for detect no batch column but valid values
            cmd_almos = (
                f"python -m almos --el --robert_keywords "
                f'"--model RF --repeat_kfolds 1 " '
                f"--ignore index --y target "
                f"--csv_name {test_csv_path} "
                f"--name name --n_exps 5"
            )
            subprocess.run(cmd_almos, shell=True)

            # Load results
            output_csv_path = 'batch_1/AL_example_missing_batch_b1.csv'
            output_data = pd.read_csv(output_csv_path)

            # Count rows for each value in the 'batch' column
            batch_counts = output_data['batch'].value_counts()

            # Validate the expected counts
            assert batch_counts.get(0, 0) == 60, f"Expected 60 rows with batch = 0, but found {batch_counts.get(0, 0)}"
            assert batch_counts.get(1, 0) == 5, f"Expected 5 rows with batch = 1, but found {batch_counts.get(1, 0)}"
        
        finally:
            # Restore the original CSV file by copying the backup file back, then delete the backup file
            shutil.copyfile(backup_csv_path, test_csv_path)
            os.remove(backup_csv_path)
    

    if test_job == "tolerance":
        cmd_almos = (
            f'python -m almos --el --robert_keywords '
            f'"--model RF --repeat_kfolds 1 " '
            f'--ignore index --y target '
            f'--csv_name {path_tests}/AL_example.csv '
            f'--name name --n_exps 5 --tolerance tight'
        )

        # Run the command and capture the output
        result = subprocess.run(
            cmd_almos,
            capture_output=True,  # Capture information from subprocess
            text=True, # As text 
            shell=True  
        )

        # Check that the DAT file is created and has the correct information
        filepath = os.path.join(os.getcwd(), "batch_1", "EL_data.dat")
        assert os.path.exists(filepath), f"EL_data.dat file not found in '{test_job}' test."

        # Read .dat file as a string
        with open(filepath, "r") as file:
            text = file.read()
        
        input_found, al_valid = False,False
        input_found = "Convergence tolerance  : tight (1.00%)" in text      
        al_valid = 'o Subplot figures have been generated and saved successfully!' in text

        assert input_found, f"Converence input not found in batch_1/EL_data.dat file in '{test_job}' test."
        assert al_valid, f"Process was not successfully completed in '{test_job}' test."
    
    if test_job == "standard":

        def run_subprocess_and_validate(cmd, validation_functions, delete=False): 
            """
            Run the subprocess command and execute the list of validation functions.
            """
            if not delete:
                subprocess.run(cmd)

            for func in validation_functions:
                func()  # Execute each validation function

        def validate_csv_options(expected_values):
            """
            Validate that the 'options.csv' file matches the expected values.
            """
            db_save = pd.read_csv("options.csv")
            assert db_save['y'][0] == expected_values['y'], f"'y' mismatch! Expected {expected_values['y']}, got {db_save['y'][0]} in 'options.csv' "
            assert db_save['name'][0] == expected_values['name'], f"'name' mismatch! Expected {expected_values['name']}, got {db_save['name'][0]} in 'options.csv'"
            assert all(word in db_save['ignore'][0] for word in expected_values['ignore']), (
                f"'ignore' values mismatch! Expected {expected_values['ignore']}, got {db_save['ignore'][0]} in 'options.csv'"
            )

            # Extract filename starting with "AL_example" and capturing everything after
            actual_filename = re.search(r"(AL_example.*?\.csv)$", str(db_save['csv_name'][0]))
            actual_filename = actual_filename.group(1) if actual_filename else None

            assert expected_values['csv_name'] == actual_filename, (
                f"'csv_name' mismatch! Expected {expected_values['csv_name']}, got {actual_filename} in 'options.csv'"
            )
        def validate_batches(path_batches, expected_values_al, csv_name_robert, csv_name_b1, batch_number):
            """
            Validate the points and batch results in the specified batch files.
            """
            path_robert = os.path.join(path_batches, csv_name_robert)
            path_b1 = os.path.join(path_batches, csv_name_b1)

            db_save_rb1 = pd.read_csv(path_robert)
            db_save_b1 = pd.read_csv(path_b1)

            assert len(db_save_rb1) == expected_values_al['num_points'], (
                f"Number of points mismatch! Expected {expected_values_al['num_points']}, got {len(db_save_rb1)}"
            )

            db_save_b1 = db_save_b1.loc[db_save_b1['batch'] == batch_number, ["name", "index", "batch"]]
            db_save_b1['batch'] = db_save_b1['batch'].astype('int64')

            expected_df = pd.DataFrame(expected_values_al['rows'])

            # Sort both DataFrames to ensure row equality regardless of order
            db_save_b1_sorted = db_save_b1.sort_values(by=["name", "index", "batch"]).reset_index(drop=True)
            expected_df_sorted = expected_df.sort_values(by=["name", "index", "batch"]).reset_index(drop=True)

            assert db_save_b1_sorted.equals(expected_df_sorted), "Selected rows in batch do not match!"
            assert len(db_save_b1) == len(expected_df), "Number of selected rows mismatch!"

        def validate_plots(path_plots, expected_structure, expected_values_plot):
            """
            Validate the folder structure, files, and plot data.
            """
            for folder, files in expected_structure.items():
                folder_path = os.path.join(path_plots, folder)
                assert os.path.exists(folder_path), f"Folder '{folder}' is missing in '{path_plots}'!"
                
                for file in files:
                    file_path = os.path.join(folder_path, file)
                    assert os.path.exists(file_path), f"File '{file}' is missing in '{folder_path}'!"

            for key, value in expected_values_plot.items():
                file_path = os.path.join(path_plots, f"{key}_plots", value["file"])
                columns_to_convert = [f"rmse_{key}", f"SD_{key}"]
                expected_df = pd.DataFrame(value["data"]).round(1)
                expected_df[columns_to_convert] = expected_df[columns_to_convert].astype(float)
                actual_df = pd.read_csv(file_path).round(1)
                actual_df[columns_to_convert] = actual_df[columns_to_convert].astype(float)
                assert actual_df.equals(expected_df), f"{value['file']} does not match expected values!"


        def validate_dat_file(filepath, expected_values):
            """
            Validate the .dat file contents.
            """
            assert os.path.exists(filepath), f"EL_data.dat file not found!"

            with open(filepath, "r") as file:
                text = file.read()

            # Validate initial sizes
            actual_initial_sizes = eval(text.split("Initial sizes of dataset: ")[1].split("\n")[0])
            assert actual_initial_sizes == expected_values['initial_sizes'], f"Initial sizes mismatch! {actual_initial_sizes}"

            # Validate selection order
            actual_order = eval(text.split("Ordered assigned points: ")[1].split("\n")[0])
            assert actual_order == expected_values['order'], f"Selection order mismatch! {actual_order}"

            # Validate convergence reports
            for model, messages in expected_values['convergence_reports'].items():
                if isinstance(messages, dict):
                    # Check if the values expected are in the dictionary such as batch_2 and batch_3
                    for key, message in messages.items():
                        if isinstance(message, list):
                            # Chech if the dict contains a list such batch_3. We present the info in different ways in order to look up for different patterns
                            search_key = f"Evaluating Model {model} batch {key.replace('batch_', '')}:"
                            if search_key not in text:
                                raise AssertionError(f"Batch section '{search_key}' for {model} is missing!")
                            
                            batch_section = text.split(search_key)[1].split("\n")
                            for msg in message:
                                assert any(msg in line for line in batch_section), (
                                    f"Convergence message '{msg}' for {model} ({key}) is missing!"
                                )
                        else:
                            # Msg are in dict but only once such as batch_2
                            assert message in text, f"Convergence message '{message}' for {model} is missing!"
                else:
                    # Flat dictionary with single message
                    assert messages in text, f"Convergence message '{messages}' for {model} is missing!"

            # Validate subplot generation message
            assert expected_values['subplot_message'] in text, "Subplot figures generation message is missing!"


        # Define validations for batch_1 and the proper cmd command
        cmd_almos = [
            'python', '-m', 'almos', '--el', '--robert_keywords', '--model RF --repeat_kfolds 1 ',
            '--ignore', 'index', '--y', 'target',
            '--csv_name', f'{path_tests}/AL_example.csv',
            '--name', 'name', '--n_exps', '5'
        ]

        expected_values_plot ={
            'no_PFI': {
                'file': 'results_plot_no_PFI.csv',
                'data': {
                    'batch': [1],
                    'rmse_no_PFI': [0.28],
                    'SD_no_PFI': [0.15],
                    'score_no_PFI': [1],
                    'Training_points_no_PFI': [18],
                    'test_points_no_PFI': [4],
                    'rmse_converged': [0],
                    'SD_converged': [0],
                    'score_converged': [0],
                    'convergence': ['no']
                    }
                },
            'PFI': {
                'file': 'results_plot_PFI.csv',
                'data': {
                    'batch': [1],
                    'rmse_PFI': [0.39],
                    'SD_PFI': [0.15],
                    'score_PFI': [0],
                    'Training_points_PFI': [18],
                    'test_points_PFI': [4],
                    'rmse_converged': [0],
                    'SD_converged': [0],
                    'score_converged': [0],
                    'convergence': ['no']
                    }
                }
            }

        validation_functions_batch_1 = [
            lambda: validate_csv_options({
                'y': 'target',
                'name': 'name',
                'ignore': ['index', 'batch'],
                'csv_name': 'AL_example.csv'
            }),

            lambda: validate_batches('batch_1',
                {'num_points': 22,
                'rows': {'name': [19, 23, 22, 21, 20],
                'index': [119, 123, 122, 121, 120],
                'batch': [1, 1, 1, 1, 1]}},
                'ROBERT_b1/AL_example_ROBERT_b1.csv',
                'AL_example_b1.csv',
                1),    

            lambda: validate_plots(
                "batch_plots", 
                {
                    "PFI_plots": ["results_plot_PFI.csv", "PFI_subplots_vertical.png"],
                    "no_PFI_plots": ["results_plot_no_PFI.csv", "no_PFI_subplots_vertical.png"]
                }, 
                expected_values_plot
            ),
            lambda: validate_dat_file('batch_1/EL_data.dat',
                {'initial_sizes': {'q1': 6, 'q2': 8, 'q3': 0, 'q4': 8},
                'order': ['q3', 'q3', 'q3', 'q3', 'q3'],
                'convergence_reports': {'no_PFI': 'o Not enough batches to check for convergence for Model no_PFI!',
                                        'PFI': 'o Not enough batches to check for convergence for Model PFI!'},
                'subplot_message': 'o Subplot figures have been generated and saved successfully!'})
        ]
        
        # Run validations for batch_1
        run_subprocess_and_validate(cmd_almos, validation_functions_batch_1)
    
    elif test_job == 'missing_input':
        # since we're inputting values for input() prompts, we use command lines and provide
        # the answers with external files using "< FILENAME_WITH_ANSWERS" in the command line

        missing_options = ['csv_name', 'y', 'name'] 
        for missing_option in missing_options:

            # Directory to delete if it exists because we are gonna repeat the process.
            if os.path.isdir(path_batch):
                shutil.rmtree(path_batch)
            # Remove the CSV file 'options.csv' if it exists
            if os.path.exists(csv_to_remove):
                os.remove(csv_to_remove)

            if missing_option == 'csv_name':
                cmd_missing = cmd_almos + ['--y','target',
                                            "--name","name",
                                            "--n_exps", "5"]
            
            elif missing_option == 'y':
                cmd_missing = cmd_almos + ["--csv_name", f"{path_tests}/AL_example.csv",
                                            "--name","name",
                                            "--n_exps", "5"]
            
            elif missing_option == 'name':
                cmd_missing = cmd_almos + ['--y','target',
                                            "--csv_name", f"{path_tests}/AL_example.csv",
                                            "--n_exps", "5"]

            cmd_missing = f'{" ".join(cmd_missing)} < {path_tests}/{missing_option}.txt'
            os.system(cmd_missing)

            # Check that the DAT file is created and has the correct information
            filepath = os.path.join(os.getcwd(), "batch_1", "EL_data.dat")
            assert os.path.exists(filepath), f"EL_data.dat file not found in '{test_job}' test."

            # Read .dat file as a string
            with open(filepath, "r") as file:
                text = file.read()

            input_found, al_valid = False, False
            exploration_found, exploitation_found = False, False
            # Check the input based on the missing option
            if missing_option == 'csv_name':
                input_found = "CSV test file          : AL_example.csv" in text
            elif missing_option == 'y':
                input_found = "Y column               : target" in text
            elif missing_option == 'name':
                input_found = "Name column            : name" in text
            elif missing_option == 'n_points':
                exploration_found = "Points exploration     : 3" in text
                exploitation_found = "Points explotation     : 2" in text
                input_found = exploration_found and exploitation_found

            # Check if subplot figures were successfully generated
            al_valid = 'o Subplot figures have been generated and saved successfully!' in text

            # Assertions
            assert input_found, f"Missing input not found in batch_1/EL_data.dat for option {missing_option} in '{test_job}' test."
            assert al_valid, f"Subplot figures were not generated successfully! Option {missing_option} in '{test_job}' test."

    elif test_job == 'reverse':

        # Check if reverse works with negative values.
        cmd = (
            f'python -m almos --el --robert_keywords "--model RF --repeat_kfolds 1" '
            f'--csv_name "{path_tests}/AL_example_reverse.csv" '
            f'--n_exps "5" --ignore "index" --y "target" --name "name" --reverse'
        )
      
        # Execute the command with shell=True to enable redirection
        result = subprocess.run(
            cmd,
            shell=True,           # Enable redirection and shell usage
            capture_output=True,  # Capture stdout and stderr
            text=True             # Decode output as text
        )
        print(result.stdout)  
        print(result.stderr)  

        # Check that the DAT file is created and has the correct information
        filepath = os.path.join(os.getcwd(), "batch_1", "EL_data.dat")
        assert os.path.exists(filepath), f"EL_data.dat file not found in '{test_job}' test."

        # Read .dat file as a string
        with open(filepath, "r") as file:
            text = file.read()

        q1_found, q2_found, q3_found, q4_found, al_valid = False, False, False, False, False

      # Check the input is found in the .dat file
        q1_found = "Points assigned to q1: [-67.01214697818145, -64.82118804567081]" in text
        q2_found = "Points assigned to q2: [-65.49380394190739]" in text
        q3_found = "Points assigned to q3: [-29.373948848086776, -33.587532965119166]" in text
        q4_found = "Points assigned to q4: []" in text

        # Check if subplot figures were successfully generated
        al_valid = 'o Subplot figures have been generated and saved successfully!' in text

        # Assertions
        assert q1_found and q2_found and q3_found and q4_found, f"Missing input not found in batch_1/EL_data.dat in '{test_job}' test."
        assert al_valid, f"Subplot figures were not generated successfully! In '{test_job}' test."

        # Directories to delete if they exist
        for dir_path in glob.glob(batch_pattern):
            if os.path.isdir(dir_path):  
                shutil.rmtree(dir_path)
        if os.path.isdir(path_plots):
            shutil.rmtree(path_plots)

        # Remove the CSV file 'options.csv' if it exists
        if os.path.exists(csv_to_remove):
            os.remove(csv_to_remove)