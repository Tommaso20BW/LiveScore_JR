"""
Persistent Canva snapshot storage on a dedicated GitHub branch.

Snapshots are stored as deterministic ZIP blobs under:
    runtime_snapshots/<event_id>/<kind>_<sha256-prefix>.zip

The branch is created lazily from the repository default branch and then kept
permanently. At match end only the active event folder is deleted.

Uses the Git Database REST API instead of repository Contents uploads so binary
archives are handled as Git blobs directly.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote

import requests


REQUIRED_FILES = (
    "source.pdf",
    "background.png",
    "player.png",
    "manifest.json",
)
DEFAULT_BRANCH_NAME = "runtime-snapshots"
REMOTE_ROOT = "runtime_snapshots"


def _safe_component(value: object) -> str:
    raw = str(value or "").strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._")
    return safe or "unknown"


def _deterministic_zip(snapshot_dir: Path) -> bytes:
    snapshot_dir = Path(snapshot_dir)
    missing = [
        name for name in REQUIRED_FILES
        if not (snapshot_dir / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Snapshot Canva incompleto: " + ", ".join(missing)
        )

    stream = io.BytesIO()
    with zipfile.ZipFile(
        stream,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in REQUIRED_FILES:
            info = zipfile.ZipInfo(
                filename=name,
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (snapshot_dir / name).read_bytes())
    return stream.getvalue()


def _extract_snapshot_zip(
    archive_bytes: bytes,
    destination: Path,
) -> Path:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
        names = set(archive.namelist())
        if names != set(REQUIRED_FILES):
            raise ValueError(
                "Archivio snapshot non valido: "
                f"attesi {sorted(REQUIRED_FILES)}, trovati {sorted(names)}"
            )
        for name in REQUIRED_FILES:
            target = destination / name
            target.write_bytes(archive.read(name))
    return destination


class GitHubSnapshotStore:
    def __init__(
        self,
        *,
        token: str | None,
        repository: str | None,
        session: requests.Session | None = None,
        branch: str = DEFAULT_BRANCH_NAME,
        log: Callable[[str, str, str], None] | None = None,
    ):
        self.token = str(token or "").strip()
        self.repository = str(repository or "").strip()
        self.session = session or requests.Session()
        self.branch = branch
        self.log = log

    @property
    def enabled(self) -> bool:
        return bool(
            self.token
            and self.repository
            and "/" in self.repository
        )

    def _emit(self, level: str, message: str) -> None:
        if self.log:
            self.log(level, "SNAPSHOT", message)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, suffix: str) -> str:
        return (
            f"https://api.github.com/repos/{self.repository}/"
            f"{suffix.lstrip('/')}"
        )

    def _request(
        self,
        method: str,
        suffix: str,
        *,
        expected: Iterable[int] = (200,),
        **kwargs,
    ):
        if not self.enabled:
            raise RuntimeError(
                "Snapshot persistenti non configurati: "
                "servono GH_PAT e GITHUB_REPOSITORY"
            )
        response = self.session.request(
            method,
            self._url(suffix),
            headers=self._headers(),
            timeout=kwargs.pop("timeout", 30),
            **kwargs,
        )
        if response.status_code not in set(expected):
            body = response.text[:1000]
            raise RuntimeError(
                f"GitHub {method} {suffix}: "
                f"HTTP {response.status_code} · {body}"
            )
        return response

    # --------------------------------------------------------------
    # Branch / Git object helpers
    # --------------------------------------------------------------
    def _get_ref(self):
        encoded = quote(self.branch, safe="")
        return self._request(
            "GET",
            f"git/ref/heads/{encoded}",
            expected=(200,),
        ).json()

    def ensure_branch(self) -> str:
        if not self.enabled:
            raise RuntimeError(
                "Snapshot persistenti non configurati: "
                "servono GH_PAT e GITHUB_REPOSITORY"
            )

        encoded = quote(self.branch, safe="")
        response = self.session.get(
            self._url(f"git/ref/heads/{encoded}"),
            headers=self._headers(),
            timeout=20,
        )
        if response.status_code == 200:
            return str(
                ((response.json().get("object") or {}).get("sha")) or ""
            )
        if response.status_code != 404:
            raise RuntimeError(
                f"GitHub GET branch {self.branch}: "
                f"HTTP {response.status_code} · {response.text[:1000]}"
            )

        # Create an orphan technical branch, not a copy of main.
        # GitHub allows commits with an empty parents list, producing a root
        # commit disconnected from the normal repository history.
        readme_blob = self._create_blob(
            (
                "# Runtime snapshots\n\n"
                "Branch tecnico gestito automaticamente dal LiveScore JR.\n"
                "Gli snapshot Canva delle partite vengono creati e rimossi "
                "automaticamente.\n"
            ).encode("utf-8")
        )
        root_tree = self._request(
            "POST",
            "git/trees",
            expected=(201,),
            json={
                "tree": [{
                    "path": "README.md",
                    "mode": "100644",
                    "type": "blob",
                    "sha": readme_blob,
                }]
            },
            timeout=30,
        ).json()
        root_tree_sha = str(root_tree.get("sha") or "")
        if not root_tree_sha:
            raise RuntimeError("Tree iniziale branch snapshot non disponibile")

        root_commit = self._request(
            "POST",
            "git/commits",
            expected=(201,),
            json={
                "message": "Initialize runtime snapshot storage",
                "tree": root_tree_sha,
                "parents": [],
            },
            timeout=30,
        ).json()
        root_commit_sha = str(root_commit.get("sha") or "")
        if not root_commit_sha:
            raise RuntimeError("Commit iniziale branch snapshot non disponibile")

        create = self.session.post(
            self._url("git/refs"),
            headers=self._headers(),
            json={
                "ref": f"refs/heads/{self.branch}",
                "sha": root_commit_sha,
            },
            timeout=20,
        )
        if create.status_code not in (201, 422):
            raise RuntimeError(
                f"Creazione branch {self.branch}: "
                f"HTTP {create.status_code} · {create.text[:1000]}"
            )

        # 422 can simply mean another run created it between GET and POST.
        ref = self._get_ref()
        sha = str(((ref.get("object") or {}).get("sha")) or "")
        if not sha:
            raise RuntimeError(
                f"Branch {self.branch} creato ma SHA non disponibile"
            )
        self._emit(
            "INFO",
            f"Branch snapshot pronto: {self.branch}",
        )
        return sha

    def _head_commit_and_tree(self) -> tuple[str, str]:
        head = self.ensure_branch()
        commit = self._request(
            "GET",
            f"git/commits/{head}",
            expected=(200,),
        ).json()
        tree_sha = str(((commit.get("tree") or {}).get("sha")) or "")
        if not tree_sha:
            raise RuntimeError("Tree SHA del branch snapshot non disponibile")
        return head, tree_sha

    def _create_blob(self, content: bytes) -> str:
        response = self._request(
            "POST",
            "git/blobs",
            expected=(201,),
            json={
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
            timeout=60,
        ).json()
        sha = str(response.get("sha") or "")
        if not sha:
            raise RuntimeError("GitHub non ha restituito lo SHA del blob")
        return sha

    def _commit_tree_entries(
        self,
        entries: list[dict],
        *,
        message: str,
        retries: int = 3,
    ) -> str:
        last_error = None
        for attempt in range(1, retries + 1):
            try:
                parent_sha, base_tree = self._head_commit_and_tree()
                tree = self._request(
                    "POST",
                    "git/trees",
                    expected=(201,),
                    json={
                        "base_tree": base_tree,
                        "tree": entries,
                    },
                    timeout=30,
                ).json()
                tree_sha = str(tree.get("sha") or "")
                if not tree_sha:
                    raise RuntimeError("Nuovo tree SHA assente")

                commit = self._request(
                    "POST",
                    "git/commits",
                    expected=(201,),
                    json={
                        "message": message,
                        "tree": tree_sha,
                        "parents": [parent_sha],
                    },
                    timeout=30,
                ).json()
                commit_sha = str(commit.get("sha") or "")
                if not commit_sha:
                    raise RuntimeError("Nuovo commit SHA assente")

                update = self.session.patch(
                    self._url(
                        f"git/refs/heads/"
                        f"{quote(self.branch, safe='')}"
                    ),
                    headers=self._headers(),
                    json={
                        "sha": commit_sha,
                        "force": False,
                    },
                    timeout=30,
                )
                if update.status_code == 200:
                    return commit_sha

                # A concurrent snapshot commit can move the ref. Retry from
                # the newest parent without ever force-pushing.
                if update.status_code in (409, 422):
                    last_error = RuntimeError(
                        f"Branch mosso durante il commit "
                        f"(tentativo {attempt}/{retries})"
                    )
                    continue

                raise RuntimeError(
                    f"Aggiornamento branch {self.branch}: "
                    f"HTTP {update.status_code} · {update.text[:1000]}"
                )
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
        raise RuntimeError(
            f"Commit snapshot fallito dopo {retries} tentativi: "
            f"{last_error}"
        )

    # --------------------------------------------------------------
    # Public API
    # --------------------------------------------------------------
    def persist_snapshot(
        self,
        *,
        event_id: str,
        kind: str,
        snapshot_dir: Path,
    ) -> dict:
        archive = _deterministic_zip(Path(snapshot_dir))
        digest = hashlib.sha256(archive).hexdigest()
        safe_event = _safe_component(event_id)
        safe_kind = _safe_component(kind)
        remote_path = (
            f"{REMOTE_ROOT}/{safe_event}/"
            f"{safe_kind}_{digest[:24]}.zip"
        )

        # Deterministic path means an already-present object is exactly the
        # snapshot we want. Avoid a duplicate commit during renderer retries.
        existing = self._content_metadata(remote_path, allow_missing=True)
        if existing is None:
            blob_sha = self._create_blob(archive)
            self._commit_tree_entries(
                [{
                    "path": remote_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_sha,
                }],
                message=(
                    f"Save Canva snapshot {safe_event} "
                    f"{safe_kind}"
                ),
            )
            self._emit(
                "INFO",
                f"Snapshot remoto salvato: {remote_path}",
            )
        else:
            self._emit(
                "DEBUG",
                f"Snapshot remoto già presente: {remote_path}",
            )

        return {
            "branch": self.branch,
            "path": remote_path,
            "sha256": digest,
            "size": len(archive),
        }

    def restore_snapshot(
        self,
        metadata: dict,
        *,
        destination_root: Path,
    ) -> Path:
        remote_path = str(metadata.get("path") or "")
        expected_digest = str(metadata.get("sha256") or "")
        branch = str(metadata.get("branch") or self.branch)

        if branch != self.branch:
            raise ValueError(
                f"Branch snapshot inatteso: {branch}"
            )
        if not remote_path or not expected_digest:
            raise ValueError("Metadati snapshot remoto incompleti")

        info = self._content_metadata(remote_path, allow_missing=False)
        blob_sha = str((info or {}).get("sha") or "")
        if not blob_sha:
            raise RuntimeError(
                f"Blob SHA non disponibile per {remote_path}"
            )

        blob = self._request(
            "GET",
            f"git/blobs/{blob_sha}",
            expected=(200,),
            timeout=60,
        ).json()
        if blob.get("encoding") != "base64":
            raise RuntimeError(
                f"Encoding blob inatteso per {remote_path}"
            )
        archive = base64.b64decode(
            str(blob.get("content") or "").replace("\n", "")
        )
        digest = hashlib.sha256(archive).hexdigest()
        if digest != expected_digest:
            raise ValueError(
                "SHA256 snapshot remoto non corrisponde al Gist: "
                f"atteso {expected_digest}, trovato {digest}"
            )

        destination = (
            Path(destination_root)
            / f"remote_{digest[:20]}"
        )
        _extract_snapshot_zip(archive, destination)
        self._emit(
            "INFO",
            f"Snapshot remoto ripristinato: {remote_path}",
        )
        return destination

    def cleanup_event(self, event_id: str) -> int:
        safe_event = _safe_component(event_id)
        prefix = f"{REMOTE_ROOT}/{safe_event}/"

        # Get the current tree and delete every blob below this event prefix
        # in a single commit.
        head, tree_sha = self._head_commit_and_tree()
        tree_response = self._request(
            "GET",
            f"git/trees/{tree_sha}?recursive=1",
            expected=(200,),
            timeout=30,
        ).json()
        if tree_response.get("truncated"):
            raise RuntimeError(
                "Tree GitHub troncato; cleanup snapshot non sicuro"
            )

        paths = [
            str(entry.get("path") or "")
            for entry in (tree_response.get("tree") or [])
            if entry.get("type") == "blob"
            and str(entry.get("path") or "").startswith(prefix)
        ]
        if not paths:
            self._emit(
                "DEBUG",
                f"Nessuno snapshot remoto da eliminare per {safe_event}",
            )
            return 0

        entries = [
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": None,
            }
            for path in paths
        ]
        self._commit_tree_entries(
            entries,
            message=f"Cleanup Canva snapshots {safe_event}",
        )
        self._emit(
            "INFO",
            f"Snapshot remoti eliminati per {safe_event}: {len(paths)}",
        )
        return len(paths)

    # --------------------------------------------------------------
    def _content_metadata(
        self,
        remote_path: str,
        *,
        allow_missing: bool,
    ) -> dict | None:
        self.ensure_branch()
        encoded_path = quote(remote_path, safe="/")
        response = self.session.get(
            self._url(f"contents/{encoded_path}"),
            headers=self._headers(),
            params={"ref": self.branch},
            timeout=30,
        )
        if response.status_code == 404 and allow_missing:
            return None
        if response.status_code != 200:
            raise RuntimeError(
                f"Lettura snapshot {remote_path}: "
                f"HTTP {response.status_code} · {response.text[:1000]}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Risposta Contents inattesa per {remote_path}"
            )
        return payload
