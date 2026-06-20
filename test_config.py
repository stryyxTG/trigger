import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from config import load_config


VALID_ENV = {
    "BOT_TOKEN": "123456789:valid-test-token",
    "ADMIN_ID": "123456789",
    "API_ID": "12345678",
    "API_HASH": "0123456789abcdef0123456789abcdef",
}


class ConfigTests(unittest.TestCase):
    def test_valid_environment_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            values = {**VALID_ENV, "DATA_DIR": temp_dir}
            with patch.dict(os.environ, values, clear=True):
                config = load_config()
            self.assertEqual(config.admin_id, 123456789)
            self.assertEqual(config.api_id, 12345678)
            self.assertEqual(config.data_dir, Path(temp_dir))

    def test_invalid_bot_token(self) -> None:
        values = {**VALID_ENV, "BOT_TOKEN": "invalid"}
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaisesRegex(ValueError, "BOT_TOKEN"):
                load_config()

    def test_invalid_api_hash(self) -> None:
        values = {**VALID_ENV, "API_HASH": "not-a-hash"}
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaisesRegex(ValueError, "API_HASH"):
                load_config()

if __name__ == "__main__":
    unittest.main()
