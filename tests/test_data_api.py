"""Aurora Data API adapter (DB_MODE=data_api) against a stubbed rds-data client. No AWS call."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

import pytest
from fakes import FakeBedrock

from quantic_hr import bedrock, db, tools

CLUSTER = "arn:aws:rds:us-east-2:123456789012:cluster:example"
SECRET = "arn:aws:secretsmanager:us-east-2:123456789012:secret:example-AbCdEf"


class ResumingError(Exception):
    def __init__(self) -> None:
        super().__init__("Database is resuming after being auto-paused")
        self.response = {"Error": {"Code": "DatabaseResumingException"}}


class StubRdsData:
    """Records calls; answers from a queue of canned responses (or raises queued errors)."""

    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _next(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((operation, request))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def execute_statement(self, **request: Any) -> dict[str, Any]:
        return self._next("execute_statement", request)

    def batch_execute_statement(self, **request: Any) -> dict[str, Any]:
        return self._next("batch_execute_statement", request)


def result(columns: list[tuple[str, str]], *records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "columnMetadata": [{"label": name, "name": name, "typeName": type_name} for name, type_name in columns],
        "records": list(records),
    }


@pytest.fixture
def data_api(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DB_MODE", "data_api")
    monkeypatch.setenv("DB_CLUSTER_ARN", CLUSTER)
    monkeypatch.setenv("DB_SECRET_ARN", SECRET)
    monkeypatch.setenv("DB_NAME", "quantic_hr_agent")

    def install(responses: list[Any]) -> StubRdsData:
        stub = StubRdsData(responses)
        db.set_data_api_client(stub)
        return stub

    yield install
    db.set_data_api_client(None)


def test_placeholders_become_named_parameters_and_casts() -> None:
    sql, names = db.to_data_api_sql("SELECT 1 - (e <=> %s::vector) FROM t WHERE a = %s AND d = %s::date LIMIT %s")
    assert names == ["p1", "p2", "p3", "p4"]
    assert sql == "SELECT 1 - (e <=> CAST(:p1 AS vector)) FROM t WHERE a = :p2 AND d = CAST(:p3 AS date) LIMIT :p4"


def test_parameter_types() -> None:
    assert db.to_parameter("p", None) == {"name": "p", "value": {"isNull": True}}
    assert db.to_parameter("p", True) == {"name": "p", "value": {"booleanValue": True}}
    assert db.to_parameter("p", 5) == {"name": "p", "value": {"longValue": 5}}
    assert db.to_parameter("p", 0.5) == {"name": "p", "value": {"doubleValue": 0.5}}
    assert db.to_parameter("p", "x") == {"name": "p", "value": {"stringValue": "x"}}
    assert db.to_parameter("p", dt.date(2026, 11, 3))["typeHint"] == "DATE"
    assert db.to_parameter("p", Decimal("1.50")) == {
        "name": "p", "value": {"stringValue": "1.50"}, "typeHint": "DECIMAL"
    }
    with pytest.raises(TypeError):
        db.to_parameter("p", object())


def test_typed_results() -> None:
    assert db.from_field({"stringValue": "12.5"}, "numeric") == Decimal("12.5")
    assert db.from_field({"stringValue": "2026-11-03"}, "date") == dt.date(2026, 11, 3)
    assert db.from_field({"stringValue": "2026-11-03 10:00:00"}, "timestamp") == dt.datetime(2026, 11, 3, 10)
    assert db.from_field({"doubleValue": 0.75}, "float8") == 0.75
    assert db.from_field({"booleanValue": True}, "bool") is True
    assert db.from_field({"isNull": True}, "text") is None
    assert db.from_field({"arrayValue": {"stringValues": ["a", "b"]}}, "_text") == ["a", "b"]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO employees VALUES (1)",
        "SELECT 1; DELETE FROM employees",
        "WITH x AS (DELETE FROM employees RETURNING *) SELECT * FROM x",
        "UPDATE employees SET title = 'x'",
        "DROP TABLE employees",
        "SET ROLE admin",
    ],
)
def test_read_only_guard_rejects_writes(sql: str) -> None:
    with pytest.raises(db.ReadOnlyViolation):
        db.check_read_only(sql)


def test_read_only_guard_allows_selects_with_keywords_in_literals() -> None:
    db.check_read_only("SELECT * FROM t WHERE note = 'please delete; update later'")
    db.check_read_only("WITH a AS (SELECT 1) SELECT * FROM a;")


def test_execute_sends_arns_and_returns_dict_rows(data_api) -> None:
    stub = data_api([result([("employee_id", "varchar"), ("found", "bool")],
                            [{"stringValue": "E1007"}, {"booleanValue": True}])])
    with db.connection() as conn:
        row = conn.execute("SELECT employee_id, true AS found FROM employees WHERE employee_id = %s", ("E1007",)).fetchone()
    assert row == {"employee_id": "E1007", "found": True}
    operation, request = stub.calls[0]
    assert operation == "execute_statement"
    assert request["resourceArn"] == CLUSTER and request["secretArn"] == SECRET
    assert request["database"] == "quantic_hr_agent" and request["includeResultMetadata"] is True
    assert request["parameters"] == [{"name": "p1", "value": {"stringValue": "E1007"}}]


def test_connection_refuses_writes_before_calling_aws(data_api) -> None:
    stub = data_api([])
    with pytest.raises(db.ReadOnlyViolation), db.connection() as conn:
        conn.execute("DELETE FROM employees WHERE employee_id = %s", ("E1007",))
    with pytest.raises(db.ReadOnlyViolation), db.connection() as conn:
        conn.executemany("INSERT INTO t VALUES (%s)", [(1,), (2,)])
    assert stub.calls == []


def test_batch_execute_when_write_enabled() -> None:
    stub = StubRdsData([{"updateResults": [{}, {}]}])
    conn = db.DataApiConnection(stub, CLUSTER, SECRET, "quantic_hr_agent", read_only=False)
    assert conn.executemany("INSERT INTO t VALUES (%s)", [(1,), (2,)]) == 2
    operation, request = stub.calls[0]
    assert operation == "batch_execute_statement"
    assert request["sql"] == "INSERT INTO t VALUES (:p1)"
    assert request["parameterSets"] == [[{"name": "p1", "value": {"longValue": 1}}],
                                        [{"name": "p1", "value": {"longValue": 2}}]]


def test_waits_while_auto_paused_cluster_resumes() -> None:
    slept: list[float] = []
    stub = StubRdsData([ResumingError(), ResumingError(), result([("one", "int4")], [{"longValue": 1}])])
    conn = db.DataApiConnection(stub, CLUSTER, SECRET, "db", sleep=slept.append)
    assert conn.execute("SELECT 1 AS one").fetchone() == {"one": 1}
    assert slept == [2.0, 4.0]


def test_gives_up_after_resume_wait() -> None:
    stub = StubRdsData([ResumingError()] * 5)
    conn = db.DataApiConnection(stub, CLUSTER, SECRET, "db", resume_wait_seconds=3, sleep=lambda _: None)
    with pytest.raises(ResumingError):
        conn.execute("SELECT 1")


def test_missing_settings_fail_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_MODE", "data_api")
    monkeypatch.delenv("DB_CLUSTER_ARN", raising=False)
    monkeypatch.delenv("DB_SECRET_ARN", raising=False)
    with pytest.raises(db.DataApiError, match="DB_CLUSTER_ARN"), db.connection():
        pass


def test_unknown_db_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_MODE", "sqlite")
    with pytest.raises(ValueError):
        db.db_mode()


def test_pto_balance_tool_over_data_api(data_api) -> None:
    columns = [("employee_id", "varchar"), ("plan", "varchar"), ("accrued_days", "numeric"),
               ("available_days", "numeric"), ("carryover_days", "numeric"),
               ("taken_days_this_year", "numeric"), ("pending_days", "numeric"),
               ("balance_year", "int4"), ("as_of", "date")]
    record = [{"stringValue": "E1007"}, {"stringValue": "STANDARD"}, {"stringValue": "15.25"},
              {"stringValue": "9.50"}, {"stringValue": "2.00"}, {"stringValue": "5.00"},
              {"stringValue": "0.00"}, {"longValue": 2026}, {"stringValue": "2026-11-03"}]
    stub = data_api([result(columns, record)])
    out = tools.check_pto_balance("E1007")
    assert out["found"] is True and out["available_days"] == 9.5 and out["as_of"] == "2026-11-03"
    assert out["balance_year"] == 2026
    request = stub.calls[0][1]
    assert "CAST(:p1 AS date)" in request["sql"] and "CAST(:p2 AS date)" in request["sql"]
    assert request["parameters"][2] == {"name": "p3", "value": {"stringValue": "E1007"}}


def test_vector_retrieval_over_data_api(data_api, monkeypatch: pytest.MonkeyPatch) -> None:
    bedrock.set_client(FakeBedrock())
    monkeypatch.setenv("QUANTIC_RETRIEVAL", "vector")
    columns = [("chunk_id", "varchar"), ("document_id", "varchar"), ("section_id", "varchar"),
               ("heading", "text"), ("content", "text"), ("title", "text"), ("source_uri", "text"),
               ("score", "float8")]
    hit = [{"stringValue": "POL-003:4.2"}, {"stringValue": "POL-003"}, {"stringValue": "4.2"},
           {"stringValue": "4.2 Out of state"}, {"stringValue": "Working from another state needs approval."},
           {"stringValue": "Remote Work"}, {"stringValue": "corpus/pol-003.md"}, {"doubleValue": 0.81234}]
    weak = [*hit[:7], {"doubleValue": 0.05}]
    stub = data_api([result([("present", "bool")], [{"booleanValue": True}]), result(columns, hit, weak)])
    try:
        out = tools.search_policy_documents("can I work from another state", limit=3)
    finally:
        bedrock.set_client(None)
    assert out["retrieval"] == "vector"
    assert [m["chunk_id"] for m in out["matches"]] == ["POL-003:4.2"]  # weak match under the floor dropped
    assert out["matches"][0]["score"] == 0.8123
    request = stub.calls[1][1]
    assert request["sql"].count("CAST(:p") == 2 and "AS vector)" in request["sql"]
    vector_param = request["parameters"][0]["value"]["stringValue"]
    assert vector_param.startswith("[") and vector_param.count(",") == 1023
    assert request["parameters"][2] == {"name": "p3", "value": {"longValue": 3}}
