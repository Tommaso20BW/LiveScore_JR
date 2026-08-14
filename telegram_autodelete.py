"""Persist and delete expiring Telegram messages sent to Bot JR."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

import requests


QUEUE_PREFIX = "telegram_autodelete_"
GITHUB_API_VERSION = "2022-11-28"


def _gist_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


def _queue_filename(chat_id: str | int, message_id: int) -> str:
    safe_chat_id = re.sub(r"[^0-9A-Za-z_-]", "_", str(chat_id).strip())
    return f"{QUEUE_PREFIX}{safe_chat_id}_{int(message_id)}.json"


def extract_message_ids(result: Any) -> list[int]:
    """Extract Telegram message IDs from a Message or a list of Messages."""
    candidates = result if isinstance(result, list) else [result]
    message_ids: list[int] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        try:
            message_id = int(item["message_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if message_id not in message_ids:
            message_ids.append(message_id)
    return message_ids


def should_enqueue(
    method: str,
    target_chat_id: str | int | None,
    bot_jr_chat_id: str | int | None,
    ttl_seconds: int,
) -> bool:
    """Return True only for new messages sent to Bot JR with expiry enabled."""
    return bool(
        ttl_seconds > 0
        and method.startswith("send")
        and target_chat_id not in (None, "")
        and bot_jr_chat_id not in (None, "")
        and str(target_chat_id).strip() == str(bot_jr_chat_id).strip()
    )


def enqueue_response(
    session: requests.Session,
    response: requests.Response,
    gh_token: str | None,
    gist_id: str | None,
    chat_id: str | int | None,
    ttl_seconds: int,
    *,
    now_ts: int | None = None,
) -> int:
    """Queue every Message contained in a successful Telegram response."""
    if ttl_seconds <= 0 or not gh_token or not gist_id or chat_id in (None, ""):
        return 0
    if response is None or response.status_code != 200:
        return 0

    try:
        body = response.json()
        if not body.get("ok"):
            return 0
        message_ids = extract_message_ids(body.get("result"))
    except (TypeError, ValueError):
        return 0

    if not message_ids:
        return 0

    created_at = int(time.time() if now_ts is None else now_ts)
    files: dict[str, dict[str, str]] = {}
    for message_id in message_ids:
        entry = {
            "version": 1,
            "chat_id": str(chat_id).strip(),
            "message_id": message_id,
            "created_at": created_at,
            "delete_after": created_at + int(ttl_seconds),
        }
        files[_queue_filename(chat_id, message_id)] = {
            "content": json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        }

    url = f"https://api.github.com/gists/{gist_id}"
    for attempt in range(3):
        try:
            result = session.patch(
                url,
                headers=_gist_headers(gh_token),
                json={"files": files},
                timeout=15,
            )
            if result.status_code == 200:
                return len(files)
            print(
                f"Coda auto-delete: GitHub Gist HTTP {result.status_code} "
                f"(tentativo {attempt + 1}/3)"
            )
        except requests.RequestException as exc:
            print(
                f"Coda auto-delete: errore Gist (tentativo {attempt + 1}/3): {exc}"
            )
        if attempt < 2:
            time.sleep(2)
    return 0


def _load_queue_files(
    session: requests.Session, gh_token: str, gist_id: str
) -> tuple[bool, dict[str, dict[str, Any]]]:
    url = f"https://api.github.com/gists/{gist_id}"
    for attempt in range(3):
        try:
            response = session.get(
                url, headers=_gist_headers(gh_token), timeout=15
            )
            if response.status_code == 200:
                all_files = response.json().get("files", {})
                queue_files = {
                    name: metadata
                    for name, metadata in all_files.items()
                    if name.startswith(QUEUE_PREFIX)
                }
                return True, queue_files
            print(
                f"Lettura coda auto-delete: Gist HTTP {response.status_code} "
                f"(tentativo {attempt + 1}/3)"
            )
        except (requests.RequestException, TypeError, ValueError) as exc:
            print(
                f"Lettura coda auto-delete fallita "
                f"(tentativo {attempt + 1}/3): {exc}"
            )
        if attempt < 2:
            time.sleep(2)
    return False, {}


def _delete_telegram_message(
    session: requests.Session,
    bot_token: str,
    chat_id: str,
    message_id: int,
) -> tuple[str, str]:
    url = f"https://api.telegram.org/bot{bot_token}/deleteMessage"
    for attempt in range(3):
        try:
            response = session.post(
                url,
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=15,
            )
            try:
                body = response.json()
            except ValueError:
                body = {}

            if response.status_code == 200 and body.get("ok"):
                return "deleted", ""

            description = str(body.get("description", ""))
            description_lower = description.lower()
            if response.status_code == 400 and (
                "message to delete not found" in description_lower
                or "message can't be deleted" in description_lower
                or "message cannot be deleted" in description_lower
            ):
                return "discarded", description

            if response.status_code == 429:
                try:
                    retry_after = int(
                        body.get("parameters", {}).get("retry_after", 3)
                    )
                except (TypeError, ValueError):
                    retry_after = 3
                if attempt < 2:
                    time.sleep(min(retry_after, 30))
                    continue

            if response.status_code >= 500 and attempt < 2:
                time.sleep(2)
                continue
            return "failed", description or f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(2)
                continue
            return "failed", str(exc)
    return "failed", "Tentativi Telegram esauriti"


def _remove_queue_files(
    session: requests.Session,
    gh_token: str,
    gist_id: str,
    filenames: list[str],
) -> bool:
    if not filenames:
        return True
    url = f"https://api.github.com/gists/{gist_id}"
    try:
        response = session.patch(
            url,
            headers=_gist_headers(gh_token),
            json={"files": {name: None for name in filenames}},
            timeout=15,
        )
        if response.status_code == 200:
            return True
        print(f"Pulizia coda auto-delete: Gist HTTP {response.status_code}")
    except requests.RequestException as exc:
        print(f"Pulizia coda auto-delete fallita: {exc}")
    return False


def cleanup_due_messages(
    session: requests.Session,
    bot_token: str,
    gh_token: str,
    gist_id: str,
    expected_chat_id: str | int,
    *,
    now_ts: int | None = None,
) -> dict[str, int | bool]:
    """Delete due Bot JR messages and remove completed queue entries."""
    stats: dict[str, int | bool] = {
        "ok": True,
        "queued": 0,
        "due": 0,
        "deleted": 0,
        "discarded": 0,
        "failed": 0,
        "invalid": 0,
    }
    loaded, queue_files = _load_queue_files(session, gh_token, gist_id)
    if not loaded:
        stats["ok"] = False
        stats["failed"] = 1
        return stats

    stats["queued"] = len(queue_files)
    current_time = int(time.time() if now_ts is None else now_ts)
    expected_chat = str(expected_chat_id).strip()
    completed_files: list[str] = []

    for filename, metadata in queue_files.items():
        try:
            entry = json.loads(metadata.get("content", ""))
            chat_id = str(entry["chat_id"]).strip()
            message_id = int(entry["message_id"])
            delete_after = int(entry["delete_after"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            stats["invalid"] = int(stats["invalid"]) + 1
            completed_files.append(filename)
            continue

        if chat_id != expected_chat or delete_after > current_time:
            continue

        stats["due"] = int(stats["due"]) + 1
        outcome, detail = _delete_telegram_message(
            session, bot_token, chat_id, message_id
        )
        if outcome == "deleted":
            stats["deleted"] = int(stats["deleted"]) + 1
            completed_files.append(filename)
        elif outcome == "discarded":
            stats["discarded"] = int(stats["discarded"]) + 1
            completed_files.append(filename)
            print(
                f"Messaggio {message_id} già assente/non eliminabile: {detail}"
            )
        else:
            stats["failed"] = int(stats["failed"]) + 1
            print(f"Eliminazione messaggio {message_id} fallita: {detail}")

    if not _remove_queue_files(
        session, gh_token, gist_id, completed_files
    ):
        stats["ok"] = False
        stats["failed"] = int(stats["failed"]) + len(completed_files)
    if int(stats["failed"]) > 0:
        stats["ok"] = False
    return stats


def main() -> int:
    config = {
        "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN"),
        "TELEGRAM_TO_BOT": os.getenv("TELEGRAM_TO_BOT"),
        "GH_PAT": os.getenv("GH_PAT"),
        "GIST_ID": os.getenv("GIST_ID"),
    }
    missing = [name for name, value in config.items() if not value]
    if missing:
        print(f"Configurazione mancante: {', '.join(missing)}")
        return 2

    stats = cleanup_due_messages(
        requests.Session(),
        str(config["TELEGRAM_TOKEN"]),
        str(config["GH_PAT"]),
        str(config["GIST_ID"]),
        str(config["TELEGRAM_TO_BOT"]),
    )
    print(f"Risultato auto-delete Bot JR: {json.dumps(stats, ensure_ascii=False)}")
    return 0 if stats["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
