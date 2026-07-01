from dataclasses import dataclass


@dataclass(frozen=True)
class FileChecksum:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ManifestMetadata:
    release_id: str
    academic_year: int
    created_by: str
    created_at: str
    data_root: str


@dataclass(frozen=True)
class CatalogueBaselineManifest:
    metadata: ManifestMetadata
    files: list[FileChecksum]
