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
path_b0 = os.path.join(os.getcwd(), "b0")
path_batch = os.path.join(os.getcwd(), "batch_1")
batch_pattern = os.path.join(os.getcwd(), "batch_*")

@pytest.mark.parametrize(
    "test_job",
    [
        "multitarget"
    ],
)
def test_bo_multitarget(test_job):
    # Clean up any previous batch folders
    for dir_path in glob.glob(batch_pattern):
        if os.path.isdir(dir_path):
            shutil.rmtree(dir_path)
    # Remove backup if exists
    backup_csv = os.path.join(path_b0, 'Mn_optimization.csv_original.csv')
    if os.path.exists(backup_csv):
        os.remove(backup_csv)

    # Run the BO process as a subprocess (to mimic real usage)
    cmd = (
        f'python -m almos --bo '
        f'--csv_name "Mn_optimization" '
        f'--name "combination" '
        f'--y "[ee,yield]" '
        f'--n_exps "3" '
        f'--batch_number "0"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    print(result.stderr)

    # Check that the output for the next batch was created
    assert os.path.exists(path_batch), "Output batch_1 folder was not created."

    # Check that a new CSV was created in the output batch
    output_csvs = [f for f in os.listdir(path_batch) if f.endswith('.csv')]
    assert output_csvs, "No CSV file was created in batch_1."

    # Check the contents of the output CSV
    output_csv_path = os.path.join(path_batch, output_csvs[0])
    df = pd.read_csv(output_csv_path)
    assert not df.empty, "Output CSV is empty."

    # Check that both targets are present in the output
    assert 'ee' in df.columns, "Column 'ee' not found in output CSV."
    assert 'yield' in df.columns, "Column 'yield' not found in output CSV."

    # Check that the combination column is present
    assert 'combination' in df.columns, "Column 'combination' not found in output CSV."

    # Check that the batch column is present
    assert 'batch' in df.columns, "Column 'batch' not found in output CSV."

    # Check that the number of new experiments matches n_exps
    batch_1_rows = df[df['batch'] == 1]
    assert len(batch_1_rows) == 3, f"Expected 3 new experiments in batch 1, found {len(batch_1_rows)}."

    # Check that the original CSV was backed up
    backup_csv = os.path.join(path_b0, 'Mn_optimization.csv_original.csv')
    assert os.path.exists(backup_csv), "Original CSV backup was not created."
