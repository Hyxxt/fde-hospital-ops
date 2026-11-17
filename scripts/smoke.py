import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
STAFF = os.getenv("STAFF_TOKEN", "")
OPS = os.getenv("OPS_TOKEN", "")


def request(path, question=None, token="", strategy="hybrid"):
    headers = {}
    data = None
    if question is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps({"question": question, "strategy": strategy}).encode()
    if token:
        headers["Authorization"] = "Bearer " + token
    return urlopen(Request(BASE + path, data, headers), timeout=50)


def read(path, question=None, token="", strategy="hybrid"):
    with request(path, question, token, strategy) as response:
        return json.load(response)


def main():
    with request("/") as response:
        assert "医院后勤制度助手" in response.read().decode()
    ready = read("/readyz")
    assert ready["status"] == "ready" and ready["database"].startswith("pgvector ")
    assert "ONNX" in ready["embedding"]
    config = read("/api/config")
    if not config["public_demo"]:
        try:
            request("/api/ask", "报修需要提供什么")
        except HTTPError as error:
            assert error.code == 401, error
        else:
            raise AssertionError("Private endpoint allowed anonymous access")

    for strategy in ("bm25", "vector", "hybrid"):
        result = read("/api/ask", "报修单需要提供哪些信息？", STAFF, strategy)
        assert "EQ-01" in {row["id"] for row in result["citations"]}, result
        assert result["retrieval_ms"] >= 0

    unrelated = read("/api/ask", "今天上海会下雨吗？", STAFF)
    assert unrelated["outcome"] == "abstain" and not unrelated["citations"], unrelated
    restricted = "夜间内部巡检先核对哪里并在哪里登记？"
    staff = read("/api/ask", restricted, STAFF, "vector")
    assert "FH-03" not in {row["id"] for row in staff["citations"]}, staff
    if OPS and not config["public_demo"]:
        ops = read("/api/ask", restricted, OPS, "vector")
        assert "FH-03" in {row["id"] for row in ops["citations"]}, ops
    evaluated = read("/api/eval", token=STAFF)
    summary = {key: value for key, value in evaluated.items() if key != "cases"}
    assert summary["relevant_count"] == 12 and summary["out_of_scope_count"] == 4
    assert summary["recall_at_3"]["hybrid"] >= 9, summary
    assert summary["accepted_reference_count"] >= 9, summary
    assert summary["reject_count"] >= 3, summary
    with request("/metrics") as response:
        assert b"hospital_questions_total" in response.read()
    print(json.dumps({"runtime": ready, "eval": summary}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
