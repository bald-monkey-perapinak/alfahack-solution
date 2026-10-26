from pathlib import Path
from zipfile import ZipFile

import pytest

from backend.package_organizer_data import extract_archive


def test_extracts_organizer_files_without_archive_prefix(tmp_path):
    archive_path = tmp_path / "organizers.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("data/classification_classes/companies.csv", "SYNTHETIC_U\nU1\n")
        archive.writestr("data/alfa-bank_materials_for_large_business/brief.md", "Analysis")

    destination = tmp_path / "out"
    extract_archive(archive_path, destination)

    assert (destination / "classification_classes/companies.csv").read_text() == "SYNTHETIC_U\nU1\n"
    assert (destination / "alfa-bank_materials_for_large_business/brief.md").read_text() == "Analysis"


def test_rejects_paths_outside_organizer_data_root(tmp_path):
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("data/../../outside.txt", "no")

    with pytest.raises(ValueError, match="Unexpected path"):
        extract_archive(archive_path, tmp_path / "out")


def test_rejects_archive_entries_without_expected_root(tmp_path):
    archive_path = tmp_path / "wrong-root.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("other/file.csv", "no")

    with pytest.raises(ValueError, match="Unexpected path"):
        extract_archive(archive_path, tmp_path / "out")
