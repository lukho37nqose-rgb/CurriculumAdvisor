import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import CatalogueBaselineManifest, FileChecksum, ManifestMetadata


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _list_data_files(data_root: Path) -> list[Path]:
    files = []
    for path in sorted(data_root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            files.append(path)
    return files


def snapshot(
    data_root: Path,
    output: Path,
    release_id: str,
    academic_year: int,
    created_by: str,
    force: bool = False,
) -> Path:
    data_root = Path(data_root)
    output = Path(output)
    if output.exists() and not force:
        raise FileExistsError(f"Manifest already exists: {output}")

    files = []
    for path in _list_data_files(data_root):
        checksum = _compute_sha256(path)
        rel_path = path.relative_to(data_root).as_posix()
        files.append(FileChecksum(path=rel_path, sha256=checksum, size=path.stat().st_size))

    manifest = CatalogueBaselineManifest(
        metadata=ManifestMetadata(
            release_id=release_id,
            academic_year=academic_year,
            created_by=created_by,
            created_at=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            data_root=str(data_root),
        ),
        files=files,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "metadata": asdict(manifest.metadata),
                "files": [asdict(file) for file in manifest.files],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def verify(data_root: Path, manifest_path: Path) -> dict[str, Any]:
    data_root = Path(data_root)
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)

    expected_files = {entry["path"]: entry for entry in manifest.get("files", [])}
    found_files = {path.relative_to(data_root).as_posix(): path for path in _list_data_files(data_root)}

    missing = []
    changed = []
    for rel_path, expected in expected_files.items():
        if rel_path not in found_files:
            missing.append(rel_path)
            continue
        actual_sha = _compute_sha256(found_files[rel_path])
        if actual_sha != expected.get("sha256"):
            changed.append(rel_path)

    unexpected = sorted([path for path in found_files if path not in expected_files])
    ok = not missing and not changed

    return {
        "ok": ok,
        "missing": sorted(missing),
        "changed": sorted(changed),
        "unexpected": unexpected,
        "expected_count": len(expected_files),
        "actual_count": len(found_files),
        "manifest_path": str(manifest_path),
        "data_root": str(data_root),
    }


def validate_offerings(template_path: Path) -> None:
    template_path = Path(template_path)
    with template_path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)

    if not isinstance(payload, list):
        raise ValueError("Offerings manifest must be a JSON array of course offering objects.")

    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValueError(f"Offerings entry at index {index} must be an object.")
        if "course_code" not in entry:
            raise ValueError(f"Missing required field 'course_code' in offering at index {index}.")
        if "term" not in entry:
            raise ValueError(f"Missing required field 'term' in offering at index {index}.")
        if "campus" not in entry:
            raise ValueError(f"Missing required field 'campus' in offering at index {index}.")


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Curriculum dataset governance tooling."
    )
    subparsers = parser.add_subparsers(dest="command")

    snapshot_parser = subparsers.add_parser("snapshot", help="Create a baseline manifest for curriculum data.")
    snapshot_parser.add_argument("--data-root", required=True, help="Path to the curriculum data root.")
    snapshot_parser.add_argument("--output", required=True, help="Path to write the baseline manifest JSON.")
    snapshot_parser.add_argument("--release-id", required=True, help="Unique release identifier.")
    snapshot_parser.add_argument("--academic-year", type=int, required=True, help="Academic year for this baseline.")
    snapshot_parser.add_argument("--created-by", required=True, help="Name of the person or team creating the manifest.")
    snapshot_parser.add_argument("--force", action="store_true", help="Overwrite an existing manifest file.")

    verify_parser = subparsers.add_parser("verify", help="Verify curriculum data against a baseline manifest.")
    verify_parser.add_argument("--data-root", required=True, help="Path to the curriculum data root.")
    verify_parser.add_argument("--manifest", required=True, help="Path to an existing baseline manifest JSON.")

    offerings_parser = subparsers.add_parser(
        "validate-offerings",
        help="Validate an operational course offerings template against the governance schema.",
    )
    offerings_parser.add_argument("--template", required=True, help="Path to a course offerings template JSON file.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_cli()
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        snapshot(
            data_root=Path(args.data_root),
            output=Path(args.output),
            release_id=args.release_id,
            academic_year=args.academic_year,
            created_by=args.created_by,
            force=args.force,
        )
        print(f"Created baseline manifest: {args.output}")
        return 0

    if args.command == "verify":
        result = verify(data_root=Path(args.data_root), manifest_path=Path(args.manifest))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 2

    if args.command == "validate-offerings":
        validate_offerings(Path(args.template))
        print(f"Offerings template is valid: {args.template}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
