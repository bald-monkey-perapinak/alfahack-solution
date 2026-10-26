"""Expand the approved organizer archive into the runtime data directory."""

from pathlib import Path, PurePosixPath
from shutil import copyfileobj
from zipfile import ZipFile


def extract_archive(archive_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            parts = PurePosixPath(entry.filename).parts
            if entry.is_dir():
                continue
            if not parts or parts[0] != "data" or ".." in parts:
                raise ValueError(f"Unexpected path in organizer archive: {entry.filename}")
            relative = Path(*parts[1:])
            if not relative.parts:
                continue
            target = (destination / relative).resolve()
            target.relative_to(destination)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                copyfileobj(source, output, length=1024 * 1024)


def main() -> None:
    extract_archive(Path("/tmp/organizer-data.zip"), Path("/app/ml/data"))


if __name__ == "__main__":
    main()
