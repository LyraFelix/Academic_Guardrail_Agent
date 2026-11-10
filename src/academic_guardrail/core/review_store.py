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
from academic_guardrail.core.followup_models import LocalReviewContext


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

    def save_packet(self, packet: ReviewPacket) -> str:
        content = packet.model_dump(mode="json")
        digest = content_digest(content)
        self._write_new(self._path(packet.packet_id, "packet"),
                        {"sha256": digest, "packet": content})
        return digest

    def load_packet(self, packet_id: str) -> ReviewPacket:
        saved = json.loads(self._path(packet_id, "packet").read_text(encoding="utf-8"))
        if content_digest(saved["packet"]) != saved["sha256"]:
            raise ValueError("Review packet checksum mismatch")
        packet = ReviewPacket.model_validate(saved["packet"])
        if packet.packet_id != packet_id:
            raise ValueError("Stored packet ID differs from requested ID")
        return packet

    def record(self, packet_id: str, judgment: ClientJudgment, expected_packet_sha256: str) -> dict:
        packet = self.load_packet(packet_id)
        digest = content_digest(packet.model_dump(mode="json"))
        if digest != expected_packet_sha256:
            raise ValueError("Stored packet differs from the client-reviewed snapshot")
        context = self.load_context(packet_id)
        if context is not None:
            from academic_guardrail.core.local_evidence import ensure_current_source
            ensure_current_source(context.source)
        record = validate_client_judgment(packet, judgment)
        record.update(review_id=uuid4().hex, recorded_utc=datetime.now(timezone.utc).isoformat(),
                      packet_sha256=digest)
        if context is not None:
            record["local_context_sha256"] = content_digest(context.model_dump(mode="json"))
        record["review_sha256"] = content_digest(record)
        path = self._path(record["review_id"], "review")
        self._write_new(path, record)
        return {**record, "record_path": str(path.resolve())}

    def load_review(self, review_id: str) -> dict:
        """Verify the saved snapshot and recheck quote links, not the model's reasoning."""
        record = json.loads(self._path(review_id, "review").read_text(encoding="utf-8"))
        if record.get("review_id") != review_id:
            raise ValueError("Stored review ID differs from requested ID")
        unsigned = {key: value for key, value in record.items() if key != "review_sha256"}
        digest = content_digest(unsigned)
        if "review_sha256" in record and record["review_sha256"] != digest:
            raise ValueError("Review record checksum mismatch")
        packet = self.load_packet(record["packet_id"])
        if record.get("packet_sha256") != content_digest(packet.model_dump(mode="json")):
            raise ValueError("Review record no longer matches its packet")
        checked = validate_client_judgment(packet, ClientJudgment.model_validate(record["judgment"]))
        if record.get("quotes") != checked["quotes"] or record.get("semantic_judgment_verified") is not False:
            raise ValueError("Saved review quote links or verification boundary differ from the packet")
        context = self.load_context(packet.packet_id)
        if context is not None:
            if "review_sha256" not in record:
                raise ValueError("A local workflow review requires its stored record checksum")
            if record.get("local_context_sha256") != content_digest(context.model_dump(mode="json")):
                raise ValueError("Review record no longer matches its local context")
        # Legacy records have no stored record digest; this is their current content hash.
        return {**record, "review_sha256": digest}

    def save_context(self, context: LocalReviewContext) -> None:
        packet = self.load_packet(context.packet_id)
        if context.packet_sha256 != content_digest(packet.model_dump(mode="json")):
            raise ValueError("Local context must bind the exact stored packet")
        self._check_source_binding(packet, context)
        content = context.model_dump(mode="json")
        self._write_new(self._path(context.packet_id, "context"),
                        {"sha256": content_digest(content), "context": content})

    def load_context(self, packet_id: str) -> LocalReviewContext | None:
        packet = self.load_packet(packet_id)
        path = self._path(packet_id, "context")
        if not path.exists():
            if (packet.reference or {}).get("local_source_binding"):
                raise ValueError("Local source context is missing; prepare a fresh packet")
            return None
        saved = json.loads(path.read_text(encoding="utf-8"))
        if content_digest(saved["context"]) != saved["sha256"]:
            raise ValueError("Local context checksum mismatch")
        context = LocalReviewContext.model_validate(saved["context"])
        if context.packet_id != packet_id or context.packet_sha256 != content_digest(packet.model_dump(mode="json")):
            raise ValueError("Local context does not match the stored packet")
        self._check_source_binding(packet, context)
        return context

    @staticmethod
    def _check_source_binding(packet: ReviewPacket, context: LocalReviewContext) -> None:
        binding = (packet.reference or {}).get("local_source_binding")
        if binding != context.source.model_dump(mode="json"):
            raise ValueError("Local context source differs from the packet source binding")
        source_path, refs_root = Path(context.source.path), Path(context.refs_root)
        if not source_path.is_absolute() or not refs_root.is_absolute():
            raise ValueError("Local context must contain absolute source/root paths")
        # These were canonical paths when prepared. Do not follow a newly
        # replaced symlink here: reports must still load the historical snapshot
        # and let source_status mark it CHANGED before any source bytes are read.
        if not Path(os.path.abspath(source_path)).is_relative_to(Path(os.path.abspath(refs_root))):
            raise ValueError("Local source is outside the declared reference directory")

    def reserve_followup(self, packet_id: str, request: dict) -> None:
        """Exclusive creation bounds even concurrent clients to one lookup per root packet."""
        try:
            self._write_new(self._path(packet_id, "followup_request"), request)
        except FileExistsError as exc:
            raise ValueError("This packet already has a follow-up attempt; prepare a new review for another search") from exc

    def save_followup_result(self, packet_id: str, result: dict) -> None:
        self._write_new(self._path(packet_id, "followup_result"), result)
