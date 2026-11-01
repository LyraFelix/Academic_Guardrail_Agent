"""Immutable local packets and append-only review records, addressed by UUID."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from academic_guardrail.core import cache
from academic_guardrail.core.claim_review import validate_client_judgment
from academic_guardrail.core.review_models import ClientJudgment, ReviewPacket


def content_digest(value: dict) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


class ReviewStore:
    def __init__(self, directory: Path | None = None):
        configured = os.environ.get("ACADEMIC_GUARDRAIL_REVIEW_DIR")
        self.directory = Path(directory or configured or cache._DEFAULT_CACHE_DIR / "claim_reviews")

    def _path(self, identifier: str, kind: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Invalid review/packet ID")
        return self.directory / f"{identifier}.{kind}.json"

    def _write_new(self, path: Path, content: dict):
        self.directory.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as handle:
            json.dump(content, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

    def save_packet(self, packet: ReviewPacket):
        content = packet.model_dump(mode="json")
        self._write_new(self._path(packet.packet_id, "packet"),
                        {"sha256": content_digest(content), "packet": content})

    def load_packet(self, packet_id: str) -> ReviewPacket:
        saved = json.loads(self._path(packet_id, "packet").read_text(encoding="utf-8"))
        if content_digest(saved["packet"]) != saved["sha256"]:
            raise ValueError("Review packet checksum mismatch")
        packet = ReviewPacket.model_validate(saved["packet"])
        if packet.packet_id != packet_id:
            raise ValueError("Stored packet ID differs from requested ID")
        return packet

    def record(self, packet_id: str, judgment: ClientJudgment) -> dict:
        packet = self.load_packet(packet_id)
        record = validate_client_judgment(packet, judgment)
        record.update(review_id=uuid4().hex, recorded_utc=datetime.now(timezone.utc).isoformat(),
                      packet_sha256=content_digest(packet.model_dump(mode="json")))
        path = self._path(record["review_id"], "review")
        self._write_new(path, record)
        return {**record, "record_path": str(path.resolve())}
