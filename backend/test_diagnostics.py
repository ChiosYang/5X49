import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import requests
from sqlmodel import Session
from app.canonical_models import ProjectionState
from app.services import diagnostics
import test_projections as fixtures


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ProjectionTests()
        self.fixture.setUp()

    def tearDown(self): self.fixture.tearDown()

    def test_local_checks_are_read_only_and_redact_paths_and_credentials(self):
        path = self.fixture.database_path
        before = path.read_bytes()
        with patch.object(diagnostics.database,"sqlite_path",path), patch.object(diagnostics,"get_media_dir",return_value=str(self.fixture.root)), patch.object(diagnostics,"get_tmdb_api_key",return_value="private-placeholder"), patch.object(diagnostics.requests,"Session") as network:
            result = diagnostics.system_diagnostics()
            network.assert_not_called()
        self.assertEqual(result["database"]["state"],"ready")
        self.assertEqual(len(result["projections"]),8)
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn(str(self.fixture.root),json.dumps(result))
        self.assertNotIn("private-placeholder",json.dumps(result))

    def test_missing_database_is_not_created_and_low_space_is_reported(self):
        missing = self.fixture.root / "absent" / "library.db"
        with patch.object(diagnostics.database,"sqlite_path",missing), patch.object(diagnostics,"get_media_dir") as media:
            result=diagnostics.system_diagnostics()
            media.assert_not_called()
        self.assertEqual(result["database"]["state"],"unavailable")
        self.assertFalse(missing.parent.exists())
        with patch.object(diagnostics.database,"sqlite_path",self.fixture.database_path), patch.object(diagnostics.shutil,"disk_usage",return_value=SimpleNamespace(free=0)):
            self.assertEqual(diagnostics.system_diagnostics()["backup_space"]["state"],"needs_attention")

    def test_projection_failure_is_reported_without_rebuild(self):
        with Session(self.fixture.engine) as session:
            state=session.get(ProjectionState,"library");state.status="failed";session.add(state);session.commit()
        before=self.fixture.database_path.read_bytes()
        with patch.object(diagnostics.database,"sqlite_path",self.fixture.database_path):
            result=diagnostics.system_diagnostics()
        self.assertEqual(next(item for item in result["projections"] if item["name"]=="library")["state"],"needs_attention")
        self.assertEqual(before,self.fixture.database_path.read_bytes())

    def probe(self, response=None, error=None):
        session=MagicMock()
        if error: session.get.side_effect=error
        else: session.get.return_value=response
        with patch.object(diagnostics,"get_tmdb_api_key",return_value="private-placeholder"), patch.object(diagnostics.requests,"Session") as factory, patch.object(diagnostics.TMDBClient,"rate_limiter",create=True):
            factory.return_value.__enter__.return_value=session
            result=diagnostics.provider_diagnostics()
        self.assertNotIn("private-placeholder",json.dumps(result))
        return result,session

    def test_provider_failures_are_distinct_and_no_raw_error_is_exposed(self):
        for error,state in [(requests.exceptions.SSLError("private URL"),"tls_failed"),(requests.exceptions.ProxyError("private URL"),"proxy_failed"),(requests.Timeout("private URL"),"timeout")]:
            result,_=self.probe(error=error)
            self.assertEqual(result["tmdb"]["state"],state)
            self.assertNotIn("private URL",json.dumps(result))
        for code,state in [(401,"credentials_rejected"),(403,"access_denied"),(429,"rate_limited"),(503,"unavailable")]:
            response=MagicMock(status_code=code)
            self.assertEqual(self.probe(response)[0]["tmdb"],{"state":state,"status_code":code})

    def test_poster_url_cannot_escape_fixed_cdn_and_tls_is_never_disabled(self):
        response=MagicMock(status_code=200)
        response.json.return_value={"id":5511,"poster_path":"//other-host/private"}
        result,session=self.probe(response)
        self.assertEqual(result["artwork"]["state"],"no_artwork")
        self.assertEqual(session.get.call_count,1)
        response.json.return_value={"id":5511,"poster_path":"/valid_poster.jpg"}
        response.__enter__.return_value=response
        result,session=self.probe(response)
        self.assertEqual(result["artwork"],{"state":"ready","status_code":200})
        for call in session.get.call_args_list:
            self.assertNotEqual(call.kwargs.get("verify"),False)
            self.assertFalse(call.kwargs["allow_redirects"])

    def test_no_key_makes_no_provider_request(self):
        with patch.object(diagnostics,"get_tmdb_api_key",return_value=None), patch.object(diagnostics.requests,"Session") as network:
            self.assertEqual(diagnostics.provider_diagnostics()["tmdb"]["state"],"not_configured")
            network.assert_not_called()
