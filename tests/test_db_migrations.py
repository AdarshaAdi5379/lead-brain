import sqlite3
import unittest

from src.storage.db import init_db


class TestDbMigrations(unittest.TestCase):
    def test_init_db_adds_outreach_sent_at_column(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            init_db(connection)
            cols = {r["name"] for r in connection.execute("PRAGMA table_info(leads)").fetchall()}
            self.assertIn("outreach_sent_at", cols)
        finally:
            connection.close()

