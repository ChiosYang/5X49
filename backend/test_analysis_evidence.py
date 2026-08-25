import unittest
from collections import defaultdict

from app.contracts.analysis_v2 import AnalysisEvidenceCandidate
from app.services.analysis_evidence import (
    MAX_EVIDENCE_BODY_BYTES,
    EvidenceHttpResponse,
    EvidenceRetriever,
)


class AnalysisEvidenceTests(unittest.TestCase):
    def _candidate(self, uri: str) -> AnalysisEvidenceCandidate:
        return AnalysisEvidenceCandidate(
            source_title="Public catalog",
            source_uri=uri,
            publisher="Example",
            claim="A bounded public claim.",
        )

    def test_private_dns_and_nonstandard_ports_are_blocked_before_fetch(self):
        calls = []
        retriever = EvidenceRetriever(
            resolver=lambda _host, _port: ("127.0.0.1",),
            fetcher=lambda *args: calls.append(args),
        )
        result = retriever.verify({"a000:e000": self._candidate("https://example.com/source")})
        self.assertEqual(result.verified, ())
        self.assertEqual(result.failures[0].reason_code, "evidence_uri_blocked")
        self.assertEqual(calls, [])

        result = retriever.verify({"a000:e000": self._candidate("https://example.com:8443/source")})
        self.assertEqual(result.failures[0].reason_code, "evidence_uri_blocked")

    def test_each_redirect_is_resolved_and_the_validated_address_is_pinned(self):
        resolutions = defaultdict(int)
        fetches = []

        def resolve(host, _port):
            resolutions[host] += 1
            return ("93.184.216.34",) if host == "example.com" else ("8.8.8.8",)

        def fetch(uri, address, hostname, port):
            fetches.append((uri, address, hostname, port))
            if hostname == "example.com":
                return EvidenceHttpResponse(302, {"location": "https://example.org/final"}, b"")
            return EvidenceHttpResponse(200, {"content-type": "text/html"}, b"verified")

        retriever = EvidenceRetriever(resolver=resolve, fetcher=fetch)
        result = retriever.verify({"a000:e000": self._candidate("https://example.com/start")})

        self.assertEqual(len(result.verified), 1)
        self.assertEqual(result.verified[0].source_uri, "https://example.org/final")
        self.assertEqual(resolutions, {"example.com": 1, "example.org": 1})
        self.assertEqual(fetches[0][1:3], ("93.184.216.34", "example.com"))
        self.assertEqual(fetches[1][1:3], ("8.8.8.8", "example.org"))

    def test_content_policy_rejects_unsupported_empty_and_oversized_bodies(self):
        cases = (
            EvidenceHttpResponse(200, {"content-type": "image/png"}, b"image"),
            EvidenceHttpResponse(200, {"content-type": "text/plain"}, b""),
            EvidenceHttpResponse(
                200,
                {"content-type": "application/json"},
                b"x" * (MAX_EVIDENCE_BODY_BYTES + 1),
            ),
        )
        for response in cases:
            with self.subTest(response=response):
                retriever = EvidenceRetriever(
                    resolver=lambda _host, _port: ("93.184.216.34",),
                    fetcher=lambda *_args, response=response: response,
                )
                result = retriever.verify(
                    {"a000:e000": self._candidate("https://example.com/source")}
                )
                self.assertEqual(result.verified, ())
                self.assertEqual(result.failures[0].reason_code, "evidence_policy_rejected")

    def test_run_cap_is_applied_after_uri_deduplication(self):
        retriever = EvidenceRetriever(
            resolver=lambda _host, _port: ("93.184.216.34",),
            fetcher=lambda *_args: EvidenceHttpResponse(
                200,
                {"content-type": "text/plain"},
                b"verified",
            ),
        )
        candidates = {
            f"a{index:03d}:e000": self._candidate(f"https://example.com/{index}")
            for index in range(13)
        }
        result = retriever.verify(candidates)
        self.assertEqual(len(result.verified), 12)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].reason_code, "evidence_policy_rejected")


if __name__ == "__main__":
    unittest.main()
