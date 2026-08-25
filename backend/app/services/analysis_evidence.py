from __future__ import annotations

import hashlib
import ipaddress
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping
from urllib.parse import urljoin, urlsplit, urlunsplit

import urllib3

from app.contracts.analysis_persistence import normalize_evidence_uri
from app.contracts.analysis_v2 import AnalysisEvidenceCandidate


EVIDENCE_VERIFICATION_POLICY_VERSION = "evidence-http.v1"
MAX_EVIDENCE_URLS_PER_RUN = 12
MAX_EVIDENCE_REDIRECTS = 3
MAX_EVIDENCE_BODY_BYTES = 2 * 1024 * 1024
EVIDENCE_CONNECT_TIMEOUT_SECONDS = 3.0
EVIDENCE_READ_TIMEOUT_SECONDS = 8.0
ALLOWED_CONTENT_TYPES = frozenset(
    {"text/html", "text/plain", "application/json", "application/pdf"}
)
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class EvidenceVerificationError(RuntimeError):
    reason_code = "evidence_retrieval_failed"


class EvidenceUriBlocked(EvidenceVerificationError):
    reason_code = "evidence_uri_blocked"


class EvidencePolicyRejected(EvidenceVerificationError):
    reason_code = "evidence_policy_rejected"


@dataclass(frozen=True)
class EvidenceHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class VerifiedEvidenceCandidate:
    candidate_key: str
    candidate: AnalysisEvidenceCandidate
    source_uri: str
    content_hash: str
    retrieved_at: str


@dataclass(frozen=True)
class EvidenceCandidateFailure:
    candidate_key: str
    candidate: AnalysisEvidenceCandidate
    reason_code: str


@dataclass(frozen=True)
class EvidenceBatchResult:
    verified: tuple[VerifiedEvidenceCandidate, ...]
    failures: tuple[EvidenceCandidateFailure, ...]


Resolver = Callable[[str, int], tuple[str, ...]]
Fetcher = Callable[[str, str, str, int], EvidenceHttpResponse]


class EvidenceRetriever:
    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        fetcher: Fetcher | None = None,
        max_workers: int = 4,
    ) -> None:
        self._resolver = resolver or self._resolve_public_addresses
        self._fetcher = fetcher or self._fetch_once
        self._max_workers = max(1, min(max_workers, 4))

    def verify(
        self,
        candidates: Mapping[str, AnalysisEvidenceCandidate],
    ) -> EvidenceBatchResult:
        normalized: dict[str, list[tuple[str, AnalysisEvidenceCandidate]]] = {}
        failures: list[EvidenceCandidateFailure] = []
        for candidate_key, candidate in candidates.items():
            try:
                uri = normalize_evidence_uri(str(candidate.source_uri))
                self._validate_standard_port(uri)
            except (TypeError, ValueError, EvidenceVerificationError):
                failures.append(
                    EvidenceCandidateFailure(candidate_key, candidate, "evidence_uri_blocked")
                )
                continue
            normalized.setdefault(uri, []).append((candidate_key, candidate))

        allowed_uris = tuple(sorted(normalized))[:MAX_EVIDENCE_URLS_PER_RUN]
        for uri in tuple(sorted(normalized))[MAX_EVIDENCE_URLS_PER_RUN:]:
            failures.extend(
                EvidenceCandidateFailure(key, candidate, "evidence_policy_rejected")
                for key, candidate in normalized[uri]
            )

        fetched: dict[str, tuple[str, str]] = {}
        fetch_failures: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {executor.submit(self._retrieve, uri): uri for uri in allowed_uris}
            for future in as_completed(futures):
                uri = futures[future]
                try:
                    fetched[uri] = future.result()
                except EvidenceVerificationError as exc:
                    fetch_failures[uri] = exc.reason_code
                except Exception:
                    fetch_failures[uri] = "evidence_retrieval_failed"

        verified: list[VerifiedEvidenceCandidate] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()
        for uri in allowed_uris:
            if uri in fetch_failures:
                failures.extend(
                    EvidenceCandidateFailure(key, candidate, fetch_failures[uri])
                    for key, candidate in normalized[uri]
                )
                continue
            final_uri, content_hash = fetched[uri]
            verified.extend(
                VerifiedEvidenceCandidate(
                    candidate_key=key,
                    candidate=candidate,
                    source_uri=final_uri,
                    content_hash=content_hash,
                    retrieved_at=retrieved_at,
                )
                for key, candidate in normalized[uri]
            )
        return EvidenceBatchResult(
            verified=tuple(sorted(verified, key=lambda item: item.candidate_key)),
            failures=tuple(sorted(failures, key=lambda item: item.candidate_key)),
        )

    def _retrieve(self, initial_uri: str) -> tuple[str, str]:
        current_uri = initial_uri
        for redirect_count in range(MAX_EVIDENCE_REDIRECTS + 1):
            current_uri = normalize_evidence_uri(current_uri)
            parsed = urlsplit(current_uri)
            self._validate_standard_port(current_uri)
            hostname = (parsed.hostname or "").encode("idna").decode("ascii")
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = self._resolver(hostname, port)
            self._validate_public_addresses(addresses)
            pinned_address = sorted(addresses)[0]
            response = self._fetcher(current_uri, pinned_address, hostname, port)
            if response.status in REDIRECT_STATUSES:
                if redirect_count >= MAX_EVIDENCE_REDIRECTS:
                    raise EvidencePolicyRejected("Evidence redirect limit exceeded")
                location = response.headers.get("location") or response.headers.get("Location")
                if not location:
                    raise EvidencePolicyRejected("Evidence redirect has no location")
                current_uri = urljoin(current_uri, location)
                continue
            if not 200 <= response.status < 300:
                raise EvidenceVerificationError("Evidence source returned a non-success status")
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip().casefold()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise EvidencePolicyRejected("Evidence content type is not allowed")
            if not response.body:
                raise EvidencePolicyRejected("Evidence body is empty")
            if len(response.body) > MAX_EVIDENCE_BODY_BYTES:
                raise EvidencePolicyRejected("Evidence body exceeds the size limit")
            return current_uri, hashlib.sha256(response.body).hexdigest()
        raise EvidencePolicyRejected("Evidence redirect limit exceeded")

    @staticmethod
    def _validate_standard_port(uri: str) -> None:
        parsed = urlsplit(uri)
        try:
            port = parsed.port
        except ValueError as exc:
            raise EvidenceUriBlocked("Evidence URI port is invalid") from exc
        expected = 443 if parsed.scheme.casefold() == "https" else 80
        if port is not None and port != expected:
            raise EvidenceUriBlocked("Evidence URI must use a standard port")

    @staticmethod
    def _resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
        try:
            values = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise EvidenceVerificationError("Evidence DNS lookup failed") from exc
        addresses = {value[4][0] for value in values}
        EvidenceRetriever._validate_public_addresses(tuple(addresses))
        return tuple(sorted(addresses))

    @staticmethod
    def _validate_public_addresses(addresses: tuple[str, ...]) -> None:
        if not addresses:
            raise EvidenceVerificationError("Evidence DNS lookup returned no addresses")
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise EvidenceUriBlocked("Evidence DNS returned an invalid address") from exc
            if not address.is_global:
                raise EvidenceUriBlocked("Evidence DNS returned a non-public address")

    @staticmethod
    def _fetch_once(
        uri: str,
        pinned_address: str,
        hostname: str,
        port: int,
    ) -> EvidenceHttpResponse:
        parsed = urlsplit(uri)
        path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        timeout = urllib3.Timeout(
            connect=EVIDENCE_CONNECT_TIMEOUT_SECONDS,
            read=EVIDENCE_READ_TIMEOUT_SECONDS,
        )
        headers = {
            "Host": hostname,
            "User-Agent": "5X49-Evidence/1.0",
            "Accept": "text/html,text/plain,application/json,application/pdf",
        }
        if parsed.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(
                pinned_address,
                port,
                maxsize=1,
                block=True,
                assert_hostname=hostname,
                server_hostname=hostname,
                ssl_context=ssl.create_default_context(),
            )
        else:
            pool = urllib3.HTTPConnectionPool(pinned_address, port, maxsize=1, block=True)
        response = None
        try:
            response = pool.urlopen(
                "GET",
                path,
                headers=headers,
                redirect=False,
                retries=False,
                preload_content=False,
                decode_content=True,
                timeout=timeout,
            )
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > MAX_EVIDENCE_BODY_BYTES:
                        raise EvidencePolicyRejected("Evidence body exceeds the size limit")
                except ValueError:
                    pass
            body = bytearray()
            while True:
                chunk = response.read(64 * 1024, decode_content=True)
                if not chunk:
                    break
                body.extend(chunk)
                if len(body) > MAX_EVIDENCE_BODY_BYTES:
                    raise EvidencePolicyRejected("Evidence body exceeds the size limit")
            return EvidenceHttpResponse(
                status=int(response.status),
                headers={key.casefold(): value for key, value in response.headers.items()},
                body=bytes(body),
            )
        except EvidenceVerificationError:
            raise
        except Exception as exc:
            raise EvidenceVerificationError("Evidence request failed") from exc
        finally:
            if response is not None:
                response.release_conn()
            pool.close()


evidence_retriever = EvidenceRetriever()


__all__ = [
    "EVIDENCE_VERIFICATION_POLICY_VERSION",
    "EvidenceBatchResult",
    "EvidenceCandidateFailure",
    "EvidenceHttpResponse",
    "EvidenceRetriever",
    "VerifiedEvidenceCandidate",
    "evidence_retriever",
]
