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
        ),  # test that if the --names, --y, --n_points or --csv_name options are empty, a prompt pops up and asks for them
        (
            "tolerance"
        ),  # check if change in tolerance parameter works   
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
        "--al",
        '--robert_keywords "--model RF --train [80]"',
        "--ignore", "index",
    ]

    if test_job != 'missing_input':
        cmd_almos = cmd_almos + ['--y','target',
                                   "--csv_name", f"{path_tests}/AL_example.csv",
                                   "--name","name",
                                   "--n_points","5:5",]
        
        
    if test_job == 'firewall_missing_target_values':

        # Run the command and capture the output
        cmd_almos = (
            f"python -m almos --al --robert_keywords "
            f'"--model RF --train [80]" '
            f"--ignore index --y target "
            f"--csv_name {path_tests}/AL_example_missing_targets.csv "
            f"--name name --n_points 3:2"
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
                f"python -m almos --al --robert_keywords "
                f'"--model RF --train [80]" '
                f"--ignore index --y target "
                f"--csv_name {test_csv_path} "
                f"--name name --n_points 3:2"
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
            f'python -m almos --al --robert_keywords '
            f'"--model RF --train [80]" '
            f'--ignore index --y target '
            f'--csv_name {path_tests}/AL_example.csv '
            f'--name name --n_points 5:5 --tolerance tight'
        )

        # Run the command and capture the output
        result = subprocess.run(
            cmd_almos,
            capture_output=True,  # Capture information from subprocess
            text=True, # As text 
            shell=True  
        )

        # Check that the DAT file is created and has the correct information
        filepath = os.path.join(os.getcwd(), "batch_1", "AL_data.dat")
        assert os.path.exists(filepath), f"AL_data.dat file not found in '{test_job}' test."

        # Read .dat file as a string
        with open(filepath, "r") as file:
            text = file.read()
        
        input_found, al_valid = False,False
        input_found = "Convergence tolerance  : tight (1.00%)" in text      
        al_valid = 'o Subplot figures have been generated and saved successfully!' in text

        assert input_found, f"Converence input not found in batch_1/AL_data.dat file in '{test_job}' test."
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
            assert expected_values['csv_name'] in db_save['csv_name'][0], (
                f"'csv_name' mismatch! Expected {expected_values['csv_name']}, got {db_save['csv_name'][0]} in 'options.csv'"
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
            
            assert db_save_b1.reset_index(drop=True).equals(expected_df), "Selected rows in batch do not match!"
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
            assert os.path.exists(filepath), f"AL_data.dat file not found!"

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
            'python', '-m', 'almos', '--al', '--robert_keywords', '--model RF --train [80]',
            '--ignore', 'index', '--y', 'target',
            '--csv_name', f'{path_tests}/AL_example.csv',
            '--name', 'name', '--n_points', '3:2'
        ]

        expected_values_plot = {
            "no_PFI": {
                "file": "results_plot_no_PFI.csv",
                "data": {
                    "batch": [1],
                    "rmse_no_PFI": [23],
                    "SD_no_PFI": [30.8],
                    "score_no_PFI": [3],
                    "validation_points_no_PFI": [11],
                    "test_points_no_PFI": [6],
                    "rmse_converged": [0],
                    "SD_converged": [0],
                    "score_converged": [0],
                    "convergence": ["no"]
                }
            },
            "PFI": {
                "file": "results_plot_PFI.csv",
                "data": {
                    "batch": [1],
                    "rmse_PFI": [23],
                    "SD_PFI": [30.75],
                    "score_PFI": [4],
                    "validation_points_PFI": [11],
                    "test_points_PFI": [6],
                    "rmse_converged": [0],
                    "SD_converged": [0],
                    "score_converged": [0],
                    "convergence": ["no"]
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
            lambda: validate_batches(
                "batch_1", 
                {
                    'num_points': 60,
                    'rows': {
                    'name': ["Molecule_1929", "Molecule_enant_5879", "Molecule_20", "Molecule_54", "Molecule_69"],
                    'index': [1929, 5879, 20, 54, 69],
                    'batch': [1] * 5
                    }
                },
                "ROBERT_b1/AL_example_ROBERT_b1.csv",
                "AL_example_b1.csv",
                1
            ),
            lambda: validate_plots(
                "batch_plots", 
                {
                    "PFI_plots": ["results_plot_PFI.csv", "PFI_subplots_vertical.png"],
                    "no_PFI_plots": ["results_plot_no_PFI.csv", "no_PFI_subplots_vertical.png"]
                }, 
                expected_values_plot
            ),
            lambda: validate_dat_file(
                "batch_1/AL_data.dat", 
                {
                    'initial_sizes': {"q1": 19, "q2": 20, "q3": 20},
                    'order': ['q1', 'q1', 'q2'],
                    'convergence_reports': {
                        'no_PFI': "o Not enough batches to check for convergence for Model no_PFI!",
                        'PFI': "o Not enough batches to check for convergence for Model PFI!"
                    },
                    'subplot_message': 'o Subplot figures have been generated and saved successfully!'
                }
            )
        ]

        # Run validations for batch_1
        run_subprocess_and_validate(cmd_almos, validation_functions_batch_1)

        # Define validations and cmd for batch_2. Checking if the the program is reading correctly 'options.csv'.
        cmd_almos = [
            'python', '-m', 'almos', '--al', '--robert_keywords', '--model RF --train [80]',
            '--csv_name', f'{path_tests}/AL_example_b1.csv',
            '--n_points', '3:2'
        ]

        # Define expected values for CSV from plots and validation for batch 2
        expected_values_plot = {
            "no_PFI": {
                "file": "results_plot_no_PFI.csv",
                "data": {
                    "batch": [1, 2],
                    "rmse_no_PFI": [23, 25],
                    "SD_no_PFI": [30.8, 32.55],
                    "score_no_PFI": [3, 3],
                    "validation_points_no_PFI": [11, 12],
                    "test_points_no_PFI": [6, 6],
                    "rmse_converged": [0, 0],
                    "SD_converged": [0, 0],
                    "score_converged": [0, 1],
                    "convergence": ["no", "no"]
                }
            },
            "PFI": {
                "file": "results_plot_PFI.csv",
                "data": {
                    "batch": [1, 2],
                    "rmse_PFI": [23, 29],
                    "SD_PFI": [30.75, 27.45],
                    "score_PFI": [4, 4],
                    "validation_points_PFI": [11, 12],
                    "test_points_PFI": [6, 6],
                    "rmse_converged": [0, 0],
                    "SD_converged": [0, 0],
                    "score_converged": [0, 1],
                    "convergence": ["no", "no"]
                }
            }
        }

        # Define validation functions for Batch 2
        validation_functions_batch_2 = [

            # Validate options.csv
            lambda: validate_csv_options({
                'y': 'target',
                'name': 'name',
                'ignore': ['index', 'batch'],
                'csv_name': 'AL_example_b1.csv'
            }),

            # Validate batch files
            lambda: validate_batches(
                "batch_2", 
                {
                    'num_points': 65,
                    'rows': {
                    "name": ["Molecule_262", "Molecule_2466", "Molecule_2559", "Molecule_29", "Molecule_61"],
                    "index": [262, 2466, 2559, 29, 61],
                    "batch": [2] * 5
                    }
                },
                "ROBERT_b2/AL_example_ROBERT_b2.csv",
                "AL_example_b2.csv",
                2
            ),
            # Validate plots
            lambda: validate_plots(
                "batch_plots", 
                {
                    "PFI_plots": ["results_plot_PFI.csv", "PFI_subplots_vertical.png"],
                    "no_PFI_plots": ["results_plot_no_PFI.csv", "no_PFI_subplots_vertical.png"]
                }, 
                expected_values_plot
            ),

            #validate .dat file
            lambda: validate_dat_file(
            "batch_2/AL_data.dat", 
            {
                'initial_sizes': {"q1": 21, "q2": 21, "q3": 22},
                'order': ['q1', 'q2', 'q1'],
                'convergence_reports': {
                    'no_PFI': {
                        'rmse': "X rmse for no_PFI model has not converged.",
                        'SD': "X SD for no_PFI model has not converged.",
                        'score': "o score for no_PFI model has converged."
                    },
                    'PFI': {
                        'rmse': "X rmse for PFI model has not converged.",
                        'SD': "X SD for PFI model has not converged.",
                        'score': "o score for PFI model has converged."
                    }
                },
                'subplot_message': 'o Subplot figures have been generated and saved successfully!'
            }
        )

        ]
        # Run validations for batch_2
        run_subprocess_and_validate(cmd_almos, validation_functions_batch_2)


        # Define validations and cmd for batch_2. Checking if the the program is reading correctly 'options.csv'.
        cmd_almos = [
            'python', '-m', 'almos', '--al', '--robert_keywords', '--model RF --train [80]',
            '--csv_name', f'{path_tests}/AL_example_b2.csv',
            '--n_points', '3:2'
        ]

        # Define expected values for CSV from plots and validation for batch 3
        expected_values_plot = {
            "no_PFI": {
                "file": "results_plot_no_PFI.csv",
                "data": {
                    "batch": [1, 2, 3],
                    "rmse_no_PFI": [23, 25, 30],
                    "SD_no_PFI": [30.8, 32.55, 33.2],
                    "score_no_PFI": [3, 3, 2],
                    "validation_points_no_PFI": [11, 12, 13],
                    "test_points_no_PFI": [6, 6, 7],
                    "rmse_converged": [0, 0, 0],
                    "SD_converged": [0, 0, 0],
                    "score_converged": [0, 1, 0],
                    "convergence": ["no", "no", "no"]
                }
            },
            "PFI": {
                "file": "results_plot_PFI.csv",
                "data": {
                    "batch": [1, 2, 3],
                    "rmse_PFI": [23, 29, 28],
                    "SD_PFI": [30.75, 27.45, 35.425],
                    "score_PFI": [4, 4, 2],
                    "validation_points_PFI": [11, 12, 13],
                    "test_points_PFI": [6, 6, 7],
                    "rmse_converged": [0, 0, 1],
                    "SD_converged": [0, 0, 0],
                    "score_converged": [0, 1, 0],
                    "convergence": ["no", "no", "no"]
                }
            }
        }

        # Define validation functions for Batch 3
        validation_functions_batch_3 = [

            # Validate options.csv
            lambda: validate_csv_options({
                'y': 'target',
                'name': 'name',
                'ignore': ['index', 'batch'],
                'csv_name': 'AL_example_b2.csv'
            }),

            # Validation for batch 3
            lambda: validate_batches(
                "batch_3", 
                {
                    'num_points': 70,
                    'rows': {
                    "name": ["Molecule_2869", "Molecule_enant_3803", "Molecule_21", "Molecule_34", "Molecule_48"],
                    "index": [2869, 3803, 21, 34, 48],
                    "batch": [3] * 5
                                    }
                                },
                                "ROBERT_b3/AL_example_ROBERT_b3.csv",
                                "AL_example_b3.csv",
                                3
            ),

            # Validate plots
            lambda: validate_plots(
                "batch_plots", 
                {
                    "PFI_plots": ["results_plot_PFI.csv", "PFI_subplots_vertical.png"],
                    "no_PFI_plots": ["results_plot_no_PFI.csv", "no_PFI_subplots_vertical.png"]
                }, 
                expected_values_plot
            ),

            # Validate .dat file
            lambda: validate_dat_file(
                "batch_3/AL_data.dat", 
                {
                    'initial_sizes': {"q1": 24, "q2": 21, "q3": 23},
                    'order': ['q2', 'q2', 'q2'],
                    'convergence_reports': {
                        'no_PFI': {
                            'batch_3': [
                                "X rmse for no_PFI model has not converged.",
                                "X SD for no_PFI model has not converged.",
                                "X score for no_PFI model has not converged."
                            ],
                            'batch_2': [
                                "X rmse for no_PFI model has not converged.",
                                "X SD for no_PFI model has not converged.",
                                "o score for no_PFI model has converged."
                            ]
                        },
                        'PFI': {
                            'batch_3': [
                                "o rmse for PFI model has converged.",
                                "X SD for PFI model has not converged.",
                                "X score for PFI model has not converged."
                            ],
                            'batch_2': [
                                "X rmse for PFI model has not converged.",
                                "X SD for PFI model has not converged.",
                                "o score for PFI model has converged."
                            ]
                        }
                    },
                    'subplot_message': 'o Subplot figures have been generated and saved successfully!'
                }
            )
        ]

        # Run validations for batch_3
        run_subprocess_and_validate(cmd_almos, validation_functions_batch_3)

        
        # ALMOS only check the last 2 batches for convergence, ensure the convergence of the first one are saved correctly.
        cmd_almos = [
            'python', '-m', 'almos', '--al', '--robert_keywords', '--model RF --train [80]',
            '--csv_name', f'{path_tests}/AL_example_b3.csv',
            '--n_points', '3:2'
        ]
        subprocess.run(cmd_almos)
    
        # Define expected values for CSV from plots and validation for batch 3
        expected_values_plot = {
            "no_PFI": {
                "file": "results_plot_no_PFI.csv",
                "data": {
                    "batch": [1, 2, 3, 4 ],
                    "rmse_no_PFI": [23, 25, 30, 26],
                    "SD_no_PFI": [30.8, 32.55, 33.2, 37],
                    "score_no_PFI": [3, 3, 2, 1],
                    "validation_points_no_PFI": [11, 12, 13, 14],
                    "test_points_no_PFI": [6, 6, 7, 7],
                    "rmse_converged": [0, 0, 0, 0],
                    "SD_converged": [0, 0, 0, 0],
                    "score_converged": [0, 1, 0, 0],
                    "convergence": ["no", "no", "no", "no"]
                }
            },
            "PFI": {
                "file": "results_plot_PFI.csv",
                "data": {
                    "batch": [1, 2, 3, 4],
                    "rmse_PFI": [23, 29, 28, 27],
                    "SD_PFI": [30.75, 27.45, 35.425, 31.225],
                    "score_PFI": [4, 4, 2, 1],
                    "validation_points_PFI": [11, 12, 13, 14],
                    "test_points_PFI": [6, 6, 7, 7],
                    "rmse_converged": [0, 0, 1, 1],
                    "SD_converged": [0, 0, 0, 0],
                    "score_converged": [0, 1, 0, 0],
                    "convergence": ["no", "no", "no", "no"]
                }
            }
        }
        # Validate plots
        validate_plots(
            "batch_plots", 
            {
                "PFI_plots": ["results_plot_PFI.csv", "PFI_subplots_vertical.png"],
                "no_PFI_plots": ["results_plot_no_PFI.csv", "no_PFI_subplots_vertical.png"]
            }, 
            expected_values_plot
        )
        
        # Check if we cancel to repeat a batch
        # Subprocess need a list
        cmd_no_delete_batch = (
            "python -m almos --al "
            "--csv_name tests/AL_example_deleted_batch_b3.csv "
            "--n_points 5:5 < tests/no_delete.txt"
        )

        # Execute the command with shell=True to enable redirection
        result = subprocess.run(
            cmd_no_delete_batch,
            shell=True,           # Enable redirection and shell usage
            capture_output=True,  # Capture stdout and stderr
            text=True             # Decode output as text
        )

        # Validate the output
        assert "x WARNING! Active learning process has been canceled. Exiting." in result.stdout, \
            f"The expected warning message was not found in the output. Captured output:\n{result.stdout}"

        # Validate that the file does not exist
        assert not os.path.exists('AL_data.dat'), "AL_data.dat file was not deleted correctly after canceling the batch!"


        # Check if we attempt to repeat a batch that is not the last one.
        cmd_delete_error_batch = [
            "python", "-m", "almos", "--al",
            "--csv_name", "tests/AL_example_b2.csv",
            "--n_points", "5:5"
        ]

        # Run the command and capture the output
        result = subprocess.run(
            cmd_delete_error_batch,  # Command to run
            capture_output=True,  # Capture stdout and stderr
            text=True  # Decode output as text
        )

        # Verify that the program displays the expected firewall message
        assert "x WARNING! Directory 'batch_3' already exists and the last batch is 'batch_4'. Exiting." in result.stdout, \
            f"The expected warning message was not found in the output. Captured stdout:\n{result.stdout}"
        
        
        # Check if we repeat the same last batch (after deleting it) with different information, the results are not the same.
        cmd_delete_batch = (
            f"python -m almos --al --robert_keywords '--model RF --train [80]' "
            f"--csv_name {path_tests}/AL_example_deleted_batch_b3.csv "
            f"--n_points 3:2 < tests/delete.txt"
        )

        # Execute the command with shell=True to enable redirection
        subprocess.run(
            cmd_delete_batch,
            shell=True,           # Enable redirection and shell usage
            capture_output=True,  # Capture stdout and stderr
            text=True             # Decode output as text
        )

        # Define expected values for CSV from plots and validation for batch 3
        expected_values_plot = {
            "no_PFI": {
                "file": "results_plot_no_PFI.csv",
                "data": {
                    "batch": [1, 2, 3, 4],
                    "rmse_no_PFI": [23, 25, 30, 26],
                    "SD_no_PFI": [30.8, 32.55, 33.2, 35],
                    "score_no_PFI": [3, 3, 2, 2],
                    "validation_points_no_PFI": [11, 12, 13, 14],
                    "test_points_no_PFI": [6, 6, 7, 7],
                    "rmse_converged": [0, 0, 0, 0],
                    "SD_converged": [0, 0, 0, 0],
                    "score_converged": [0, 1, 0, 1],
                    "convergence": ["no", "no", "no", "no"]
                }
            },
            "PFI": {
                "file": "results_plot_PFI.csv",
                "data": {
                    "batch": [1, 2, 3, 4],
                    "rmse_PFI": [23, 29, 28, 26],
                    "SD_PFI": [30.75, 27.45, 35.425, 35.45],
                    "score_PFI": [4, 4, 2, 3],
                    "validation_points_PFI": [11, 12, 13, 14],
                    "test_points_PFI": [6, 6, 7, 7],
                    "rmse_converged": [0, 0, 1, 0],
                    "SD_converged": [0, 0, 0, 0],
                    "score_converged": [0, 1, 0, 1],
                    "convergence": ["no", "no", "no", "no"]
                }
            }
        }
            # Validate plots
        validate_plots(
            "batch_plots", 
            {
                "PFI_plots": ["results_plot_PFI.csv", "PFI_subplots_vertical.png"],
                "no_PFI_plots": ["results_plot_no_PFI.csv", "no_PFI_subplots_vertical.png"]
            }, 
            expected_values_plot
        )

    
    elif test_job == 'missing_input':
        # since we're inputting values for input() prompts, we use command lines and provide
        # the answers with external files using "< FILENAME_WITH_ANSWERS" in the command line

        missing_options = ['csv_name', 'y', 'name', 'n_points'] 
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
                                            "--n_points", "3:2"]
            
            elif missing_option == 'y':
                cmd_missing = cmd_almos + ["--csv_name", f"{path_tests}/AL_example.csv",
                                            "--name","name",
                                            "--n_points", "3:2"]
            
            elif missing_option == 'name':
                cmd_missing = cmd_almos + ['--y','target',
                                            "--csv_name", f"{path_tests}/AL_example.csv",
                                            "--n_points", "3:2"]
            elif missing_option == 'n_points':
                cmd_missing = cmd_almos + ['--y','target',
                                            "--csv_name", f"{path_tests}/AL_example.csv",
                                            "--name","name"]

            cmd_missing = f'{" ".join(cmd_missing)} < {path_tests}/{missing_option}.txt'
            os.system(cmd_missing)

            # Check that the DAT file is created and has the correct information
            filepath = os.path.join(os.getcwd(), "batch_1", "AL_data.dat")
            assert os.path.exists(filepath), f"AL_data.dat file not found in '{test_job}' test."

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
            assert input_found, f"Missing input not found in batch_1/AL_data.dat for option {missing_option} in '{test_job}' test."
            assert al_valid, f"Subplot figures were not generated successfully! Option {missing_option} in '{test_job}' test."

            # Directories to delete if they exist for finalize the process
            for dir_path in glob.glob(batch_pattern):
                if os.path.isdir(dir_path):  
                    shutil.rmtree(dir_path)
            if os.path.isdir(path_plots):
                shutil.rmtree(path_plots)

            # Remove the CSV file 'options.csv' if it exists
            if os.path.exists(csv_to_remove):
                os.remove(csv_to_remove)