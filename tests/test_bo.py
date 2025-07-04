#!/usr/bin/env python

######################################################.
#           Testing BO module with pytest             #
######################################################.

import os
import glob
import pytest
import shutil
import subprocess
import pandas as pd

# Define paths
w_dir_main = os.getcwd()
path_batch0 = w_dir_main + "/tests/batch_0"
path_batch1 = w_dir_main + "/tests/batch_1"
batch_pattern = w_dir_main + "/tests/batch_*"

@pytest.mark.parametrize(
    "test_job",
    [
        "bo"
    ],
)
def test_bo(test_job):
    # Clean up any previous batch folders except batch_0 (input folder)
    for dir_path in glob.glob(batch_pattern):
        # Do not remove batch_0, only clean batch_1, batch_2, etc.
        if os.path.isdir(dir_path) and not dir_path.endswith('batch_0'):
            shutil.rmtree(dir_path)
    # Remove backup if exists
    backup_csv = os.path.join(path_batch0, 'BO_optimization_original.csv')
    if os.path.exists(backup_csv):
        os.remove(backup_csv)

    # Check that the input CSV exists in batch_0
    input_csv = os.path.join(path_batch0, 'BO_optimization.csv')
    assert os.path.exists(input_csv), f"Input CSV not found: {input_csv}"

    if test_job == "bo":
        # Run the BO process as a subprocess (to mimic real usage)
        cmd = (
            f'python -m almos --bo '
            f'--csv_name "BO_optimization" '
            f'--name "combination" '
            f'--y "[ee,yield]" '
            f'--n_exps "3" '
            f'--batch_number "0"'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(result.stdout)
        print(result.stderr)

        # Check that the output for the next batch was created
        assert os.path.exists(path_batch1), "Output batch_1 folder was not created."

        # Check that a new CSV was created in the output batch
        output_csvs = [f for f in os.listdir(path_batch1) if f.endswith('.csv')]
        assert output_csvs, "No CSV file was created in batch_1."

        # Check the contents of the output CSV
        output_csv_path = os.path.join(path_batch1, output_csvs[0])
        df = pd.read_csv(output_csv_path)
        assert not df.empty, "Output CSV is empty."

        # Check that both targets are present in the output
        assert 'ee' in df.columns, "Column 'ee' not found in output CSV."
        assert 'yield' in df.columns, "Column 'yield' not found in output CSV."

        # Check that the combination column is present
        assert 'combination' in df.columns, "Column 'combination' not found in output CSV."

        # Check that the number of new experiments matches n_exps and have priority == 1
        assert 'priority' in df.columns, "Column 'priority' not found in output CSV."
        assert (df['priority'].iloc[:3] == 1).all(), "The first 3 rows in batch_1 do not all have priority == 1."

        # Check that the original CSV was backed up
        backup_csv = os.path.join(path_batch0, 'BO_optimization_original.csv')
        assert os.path.exists(backup_csv), "Original CSV backup was not created."

        # Check that categorical columns are encoded as integers (not object)
        for col in df.columns:
            if df[col].dtype == object and col not in ['combination', 'ee', 'yield']:
                raise AssertionError(f"Column {col} should be encoded as integer, but is object.")

        # Check that prediction columns are present in the output csv 
        prediction_suffixes = ['_predicted_mean', '_predicted_variance', 'expected_improvement']
        for suf in prediction_suffixes:
            assert any(col.endswith(suf) for col in df.columns), f"Prediction column with suffix '{suf}' is not present in output CSV."

    # --- CLEANUP: Remove all generated folders and files except batch_0 and its CSV ---
    for dir_path in glob.glob(batch_pattern):
        if os.path.isdir(dir_path) and not dir_path.endswith('batch_0'):
            shutil.rmtree(dir_path)
    # Remove backup again if generated
    backup_csv = os.path.join(path_batch0, 'BO_optimization_original.csv')
    if os.path.exists(backup_csv):
        os.remove(backup_csv)
    # remove the DAT file if it exists
    if os.path.exists("BO_data.dat"):
        os.remove("BO_data.dat")   
