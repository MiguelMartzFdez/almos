import csv

import pytest

from almos.campaign import import_measurements, read_run_result


@pytest.mark.parametrize(
    ("measurements", "message"),
    [
        ("0001,2\n0001,3\n", "unique"),
        ("0004,2\n", "Unknown"),
        ("0003,2\n", "not assigned"),
        ("0002,2\n", "existing measurement"),
        ("0001,inf\n", "finite"),
    ],
)
def test_import_measurements_validates_the_entire_update(tmp_path, measurements, message):
    source = tmp_path / "pool_b0.csv"
    source.write_text("Name,target,Batch\n0001,,0\n0002,8,0\n0003,,\n", encoding="utf-8")
    measured = tmp_path / "measurements.csv"
    measured.write_text("Name,target\n" + measurements, encoding="utf-8")
    output = tmp_path / "updated.csv"
    original_input = source.read_bytes()

    with pytest.raises(ValueError, match=message):
        import_measurements(source, measured, output, "Name", "target")

    assert not output.exists()
    assert source.read_bytes() == original_input


def test_import_measurements_preserves_an_existing_output(tmp_path):
    source = tmp_path / "pool_b0.csv"
    source.write_text("Name,target,batch\n0001,,0\n", encoding="utf-8")
    measured = tmp_path / "measurements.csv"
    measured.write_text("Name,target\n0001,2\n", encoding="utf-8")
    output = tmp_path / "updated.csv"
    output.write_bytes(b"an existing output")

    with pytest.raises(FileExistsError):
        import_measurements(source, measured, output, "Name", "target")

    assert output.read_bytes() == b"an existing output"


def test_import_measurements_preserves_other_column_values(tmp_path):
    source = tmp_path / "pool_b0.csv"
    source.write_text(
        "Name,target,batch,lab_code,annotation,descriptor\n"
        "0001,,0,0007,NA,0.1234567890123456789\n",
        encoding="utf-8",
    )
    measurements = tmp_path / "measurements.csv"
    measurements.write_text("Name,target\n0001,2.500\n", encoding="utf-8")
    output = tmp_path / "updated.csv"

    assert import_measurements(source, measurements, output, "Name", "target") == 1

    with output.open(newline="", encoding="utf-8") as file:
        assert list(csv.DictReader(file)) == [{
            "Name": "0001",
            "target": "2.500",
            "batch": "0",
            "lab_code": "0007",
            "annotation": "NA",
            "descriptor": "0.1234567890123456789",
        }]


def test_previous_manifest_is_not_opened_against_current_artifacts(tmp_path):
    previous = tmp_path / "run.previous.json"
    previous.write_text(
        '{"schema_version":1,"status":"completed","module":"cluster",'
        '"summary":{},"effective_options":{},"artifacts":[]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="provenance"):
        read_run_result(previous)
