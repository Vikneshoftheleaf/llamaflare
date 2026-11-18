from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch
import urllib.error

from model_server.config import AppConfig, AppPaths, ConfigStore
from model_server.models import (
    DEFAULT_MODEL_FILE,
    DEFAULT_MODEL_REPOSITORY,
    _validate_download_request,
    list_models,
    model_path_from_config,
    model_relative_path,
)
from model_server.server import LocalServer


class ConfigAndModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.paths = AppPaths(
            repository_root=root / "repo",
            config_home=root / "config",
            state_home=root / "state",
        )
        self.paths.repository_root.mkdir()
        self.paths.models_dir.mkdir()
        self.store = ConfigStore(self.paths)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_default_model_is_sub_one_billion_qwen_gguf(self) -> None:
        self.assertIn("0.5B", DEFAULT_MODEL_REPOSITORY)
        self.assertTrue(DEFAULT_MODEL_FILE.endswith(".gguf"))

    def test_config_round_trip_and_private_permissions(self) -> None:
        config = AppConfig(selected_model="models/example.gguf", api_key="local-secret")
        self.store.save(config)

        self.assertEqual(self.store.load(), config)
        if os.name == "posix":
            self.assertEqual(self.paths.config_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.paths.config_dir.stat().st_mode & 0o777, 0o700)

    def test_tunnel_token_is_stored_in_private_file(self) -> None:
        self.store.save_tunnel_token("tunnel-secret")

        self.assertEqual(self.store.load_tunnel_token(), "tunnel-secret")
        if os.name == "posix":
            self.assertEqual(self.paths.tunnel_token_file.stat().st_mode & 0o777, 0o600)

    def test_model_discovery_and_configured_path_are_confined_to_models(self) -> None:
        model = self.paths.models_dir / "example" / "tiny.gguf"
        model.parent.mkdir()
        model.write_bytes(b"test")

        self.assertEqual([item.path for item in list_models(self.paths)], [model.resolve()])
        relative = model_relative_path(model, self.paths)
        self.assertEqual(model_path_from_config(relative, self.paths), model.resolve())
        with self.assertRaises(ValueError):
            model_path_from_config("../outside.gguf", self.paths)

    def test_download_request_rejects_path_traversal_and_non_gguf_files(self) -> None:
        _validate_download_request("owner/model", "model-q4.gguf")
        for repository_id, filename in [
            ("../outside", "model.gguf"),
            ("owner/model", "../model.gguf"),
            ("owner/model", "..\\model.gguf"),
            ("owner/model", "weights.bin"),
        ]:
            with self.subTest(repository_id=repository_id, filename=filename):
                with self.assertRaises(ValueError):
                    _validate_download_request(repository_id, filename)

    def test_authenticated_proxy_unauthorized_health_is_ready(self) -> None:
        server = LocalServer(self.paths, self.store)
        unauthorized = urllib.error.HTTPError(
            "http://127.0.0.1:8081/health",
            401,
            "Unauthorized",
            {},
            None,
        )
        with patch("model_server.server.urllib.request.urlopen", side_effect=unauthorized):
            self.assertTrue(server._health(8081, expected_status=401))


if __name__ == "__main__":
    unittest.main()
