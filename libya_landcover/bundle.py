"""Local run evidence and serialized EE graphs, not exported raster data."""

import hashlib
import json
from pathlib import Path
import shutil
from uuid import UUID


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def canonical_uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Expected canonical UUID")
    return value


class GraphArtifactStore:
    """One local run, committed as one directory only after all images serialize.

    Credentials and evaluated pixel data are not included. Loading a graph still
    needs an initialized EE session with access to the referenced assets.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    def save_many(self, run_id, entries):
        canonical_uuid(run_id)
        if not entries:
            raise ValueError("No images to store")
        target = self.directory / "graphs"
        pending = self.directory / "graphs.pending"
        if target.exists() or pending.exists():
            raise FileExistsError("Graph batch already exists")
        pending.mkdir()
        try:
            index = {"run_id": run_id, "representation": "earthengine_serialized_graph",
                     "ee_version": "1.7.48", "artifacts": {}}
            for identifier, image in entries.items():
                canonical_uuid(identifier)
                serialized = image.serialize()
                json.loads(serialized)  # Reject incomplete/non-JSON graph serialization.
                data = serialized.encode("utf-8")
                filename = identifier + ".json"
                (pending / filename).write_bytes(data)
                index["artifacts"][identifier] = {"file": filename,
                    "sha256": hashlib.sha256(data).hexdigest()}
            write_json(pending / "index.json", index)
            pending.rename(target)
        except Exception:
            shutil.rmtree(pending)
            raise

    def get(self, run_id, artifact_id):
        import ee
        canonical_uuid(run_id)
        canonical_uuid(artifact_id)
        index = json.loads((self.directory / "graphs" / "index.json").read_text(encoding="utf-8"))
        if index["run_id"] != run_id:
            raise KeyError("Artifact belongs to another run")
        record = index["artifacts"][artifact_id]
        # Never trust a path stored in an externally supplied manifest.
        if record["file"] != artifact_id + ".json":
            raise ValueError("Invalid artifact filename")
        data = (self.directory / "graphs" / record["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Graph checksum mismatch")
        return ee.Image(ee.deserializer.fromJSON(data.decode("utf-8")))
