"""PLAN 5.1: the HTTP service. Runs on SQLite; set LUDWIG_TEST_DATABASE_URL for Postgres."""

import io
import os
import uuid
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ludwig.api.app import create_app  # noqa: E402
from ludwig.api.settings import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"


def database_url(tmp_path):
    url = os.environ.get("LUDWIG_TEST_DATABASE_URL")
    if not url:
        return f"sqlite:///{tmp_path / 'ludwig.db'}"
    # One schema per test keeps runs apart on a shared server.
    from sqlalchemy import create_engine, text

    schema = f"t_{uuid.uuid4().hex[:12]}"
    with create_engine(url).begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    return f"{url}{'&' if '?' in url else '?'}options=-csearch_path%3D{schema}"


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_url=database_url(tmp_path), storage_dir=tmp_path / "storage",
                        packs_dir=ROOT / "packs")  # fmt: skip
    return TestClient(create_app(settings))


def put(client, project, path, role, for_upload=None):
    data = {"role": role} | ({"for_upload": str(for_upload)} if for_upload else {})
    r = client.post(f"/projects/{project}/uploads", data=data,
                    files={"file": (path.name, path.read_bytes())})  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()["id"]


def project_with_files(client, export="duplex_erp_export_seeded.csv"):
    project = client.post("/projects", json={"name": "Duplex"}).json()["id"]
    model = put(client, project, FIX / "ifc" / "duplex_architectural_ifc2x3.ifc", "architect")
    sched = put(client, project, FIX / "schedule" / "duplex_joinery_schedule.csv", "architect")
    put(
        client, project, FIX / "schedule" / "duplex_joinery_schedule.mapping.yaml", "mapping", sched
    )
    erp = put(client, project, FIX / "erp" / export, "erp")
    put(client, project, FIX / "erp" / "duplex_erp_export.mapping.yaml", "mapping", erp)
    return project, [model, sched, erp]


def test_full_run_matches_the_command_line(client):
    project, files = project_with_files(client)
    uploads = client.get(f"/projects/{project}/uploads").json()
    mapping_ids = [u["id"] for u in uploads if u["role"] == "mapping"]
    r = client.post(f"/projects/{project}/runs", json={"pack": "joinery-nl",
                                                      "uploads": files + mapping_ids})  # fmt: skip
    assert r.status_code == 202
    run = client.get(f"/runs/{r.json()['id']}").json()
    assert run["status"] == "done", run["error"]
    assert run["pack"]["name"] == "joinery-nl" and run["pack"]["hash"].startswith("sha256:")
    assert len(run["upload_hashes"]) == 5
    assert run["summary"]["fails_by_severity"] == {"blocker": 8, "warning": 2}
    fails = client.get(f"/runs/{run['id']}/findings", params={"status": "fail"}).json()
    assert sorted((f["rule_id"], f["mark"]) for f in fails)[:2] == [
        ("erp-fire-rating", "33"), ("erp-glazing-type", "01")]  # fmt: skip
    assert all(f["evidence"] for f in fails)
    for name in ("report.json", "report.xlsx", "report.bcf"):
        assert client.get(f"/runs/{run['id']}/reports/{name}").status_code == 200
    assert client.get(f"/runs/{run['id']}/reports/..%2Fsecret").status_code == 404


def test_same_file_twice_is_stored_once(client, tmp_path):
    project = client.post("/projects", json={"name": "P"}).json()["id"]
    path = FIX / "schedule" / "duplex_joinery_schedule.csv"
    a, b = put(client, project, path, "architect"), put(client, project, path, "architect")
    uploads = client.get(f"/projects/{project}/uploads").json()
    assert a != b and uploads[0]["sha256"] == uploads[1]["sha256"]
    assert len(list((tmp_path / "storage" / "objects").rglob("*"))) == 2  # one dir, one file


def test_input_problems_fail_the_run_with_a_reason(client):
    project = client.post("/projects", json={"name": "P"}).json()["id"]
    sched = put(client, project, FIX / "schedule" / "duplex_joinery_schedule.csv", "architect")
    r = client.post(f"/projects/{project}/runs", json={"pack": "joinery-nl", "uploads": [sched]})
    run = client.get(f"/runs/{r.json()['id']}").json()
    assert run["status"] == "failed"
    assert "duplex_joinery_schedule.mapping.yaml" in run["error"]


@pytest.mark.parametrize(("body", "detail"), [
    ({"pack": "nope", "uploads": [1]}, "no pack named"),
    ({"pack": "joinery-nl", "uploads": [999]}, "uploads must be files of this project"),
])  # fmt: skip
def test_bad_run_requests_are_refused(client, body, detail):
    project = client.post("/projects", json={"name": "P"}).json()["id"]
    r = client.post(f"/projects/{project}/runs", json=body)
    assert r.status_code == 422 and detail in r.text


def test_upload_rules(client):
    project = client.post("/projects", json={"name": "P"}).json()["id"]
    url = f"/projects/{project}/uploads"
    file = {"file": ("x.csv", b"a;b")}
    assert client.post(url, data={"role": "boss"}, files=file).status_code == 422
    assert client.post(url, data={"role": "mapping"}, files=file).status_code == 422
    assert client.post("/projects/99/uploads", data={"role": "erp"}, files=file).status_code == 404
    bad_name = {"file": ("..", b"x")}
    assert client.post(url, data={"role": "erp"}, files=bad_name).status_code == 422
    sneaky = {"file": ("../../etc/passwd", b"x")}
    assert client.post(url, data={"role": "erp"}, files=sneaky).json()["filename"] == "passwd"


def test_size_limit(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db'}", storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", max_upload_mb=1)  # fmt: skip
    client = TestClient(create_app(settings))
    project = client.post("/projects", json={"name": "P"}).json()["id"]
    big = {"file": ("big.csv", io.BytesIO(b"x" * (1024 * 1024 + 1)))}
    r = client.post(f"/projects/{project}/uploads", data={"role": "erp"}, files=big)
    assert r.status_code == 413


def test_token_and_origin_guards(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db'}", storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", api_token="s3cret")  # fmt: skip
    client = TestClient(create_app(settings))
    assert client.get("/health").status_code == 200
    assert client.get("/projects").status_code == 401
    auth = {"Authorization": "Bearer s3cret"}
    assert client.get("/projects", headers=auth).status_code == 200
    evil = auth | {"Origin": "https://evil.example"}
    assert client.post("/projects", json={"name": "x"}, headers=evil).status_code == 403
    same = auth | {"Origin": "http://testserver"}
    assert client.post("/projects", json={"name": "x"}, headers=same).status_code == 201


def test_packs_are_listed(client):
    names = [p["name"] for p in client.get("/packs").json()]
    assert names == ["joinery-nl"]
