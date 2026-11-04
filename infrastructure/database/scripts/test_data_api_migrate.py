"""Offline parsing checks for our actual PostgreSQL migrations (no AWS access)."""
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("data_api_migrate", HERE / "data_api_migrate.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SqlSplitterTests(unittest.TestCase):
    def test_all_five_existing_migrations_parse(self):
        for number in range(1, 6):
            paths = list((HERE.parent / "migrations").glob(f"{number:03d}_*.sql"))
            self.assertEqual(len(paths), 1, paths)
            statements = MODULE.split_statements(paths[0].read_text(encoding="utf-8"))
            self.assertTrue(statements, paths[0])
            self.assertTrue(all(s.strip() for s in statements))

    def test_plpgsql_dollar_quote_is_one_statement(self):
        sql = "DO $$ BEGIN PERFORM 1; PERFORM 2; END $$; SELECT 1;"
        self.assertEqual(len(MODULE.split_statements(sql)), 2)

    def test_quoted_and_comment_semicolons(self):
        sql = """-- semicolon;
        SELECT 'x;y' AS value; /* comment ; */ SELECT "a;b" FROM abc;
        """
        self.assertEqual(len(MODULE.split_statements(sql)), 2)

    def test_rejects_truncated_sql(self):
        with self.assertRaises(ValueError):
            MODULE.split_statements("DO $$ BEGIN SELECT 1;")


if __name__ == "__main__":
    unittest.main()
