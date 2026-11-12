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
    r = client.post(f"/api/projects/{project}/uploads", data=data,
                    files={"file": (path.name, path.read_bytes())})  # fmt: skip
    assert r.status_code == 201, r.text
    return r.json()["id"]


def project_with_files(client, export="duplex_erp_export_seeded.csv"):
    project = client.post("/api/projects", json={"name": "Duplex"}).json()["id"]
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
    uploads = client.get(f"/api/projects/{project}/uploads").json()
    mapping_ids = [u["id"] for u in uploads if u["role"] == "mapping"]
    r = client.post(f"/api/projects/{project}/runs", json={"pack": "joinery-nl",
                                                      "uploads": files + mapping_ids})  # fmt: skip
    assert r.status_code == 202
    run = client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["status"] == "done", run["error"]
    assert run["pack"]["name"] == "joinery-nl" and run["pack"]["hash"].startswith("sha256:")
    assert len(run["upload_hashes"]) == 5
    assert run["summary"]["fails_by_severity"] == {"blocker": 8, "warning": 2}
    fails = client.get(f"/api/runs/{run['id']}/findings", params={"status": "fail"}).json()
    assert sorted((f["rule_id"], f["mark"]) for f in fails)[:2] == [
        ("erp-fire-rating", "33"), ("erp-glazing-type", "01")]  # fmt: skip
    assert all(f["evidence"] for f in fails)
    for name in ("report.json", "report.xlsx", "report.bcf"):
        assert client.get(f"/api/runs/{run['id']}/reports/{name}").status_code == 200
    assert client.get(f"/api/runs/{run['id']}/reports/..%2Fsecret").status_code == 404


def test_same_file_twice_is_stored_once(client, tmp_path):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    path = FIX / "schedule" / "duplex_joinery_schedule.csv"
    a, b = put(client, project, path, "architect"), put(client, project, path, "architect")
    uploads = client.get(f"/api/projects/{project}/uploads").json()
    assert a != b and uploads[0]["sha256"] == uploads[1]["sha256"]
    assert len(list((tmp_path / "storage" / "objects").rglob("*"))) == 2  # one dir, one file


def test_input_problems_fail_the_run_with_a_reason(client):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    sched = put(client, project, FIX / "schedule" / "duplex_joinery_schedule.csv", "architect")
    body = {"pack": "joinery-nl", "uploads": [sched]}
    r = client.post(f"/api/projects/{project}/runs", json=body)
    run = client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["status"] == "failed"
    assert "duplex_joinery_schedule.mapping.yaml" in run["error"]


@pytest.mark.parametrize(("body", "detail"), [
    ({"pack": "nope", "uploads": [1]}, "no pack named"),
    ({"pack": "joinery-nl", "uploads": [999]}, "uploads must be files of this project"),
])  # fmt: skip
def test_bad_run_requests_are_refused(client, body, detail):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    r = client.post(f"/api/projects/{project}/runs", json=body)
    assert r.status_code == 422 and detail in r.text


def test_upload_rules(client):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    url = f"/api/projects/{project}/uploads"
    file = {"file": ("x.csv", b"a;b")}
    assert client.post(url, data={"role": "boss"}, files=file).status_code == 422
    assert client.post(url, data={"role": "mapping"}, files=file).status_code == 422
    missing = client.post("/api/projects/99/uploads", data={"role": "erp"}, files=file)
    assert missing.status_code == 404
    bad_name = {"file": ("..", b"x")}
    assert client.post(url, data={"role": "erp"}, files=bad_name).status_code == 422
    sneaky = {"file": ("../../etc/passwd", b"x")}
    assert client.post(url, data={"role": "erp"}, files=sneaky).json()["filename"] == "passwd"


def test_size_limit(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db'}", storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", max_upload_mb=1)  # fmt: skip
    client = TestClient(create_app(settings))
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    big = {"file": ("big.csv", io.BytesIO(b"x" * (1024 * 1024 + 1)))}
    r = client.post(f"/api/projects/{project}/uploads", data={"role": "erp"}, files=big)
    assert r.status_code == 413


def test_token_and_origin_guards(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db'}", storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", api_token="s3cret")  # fmt: skip
    client = TestClient(create_app(settings))
    assert client.get("/health").status_code == 200
    assert client.get("/api/projects").status_code == 401
    auth = {"Authorization": "Bearer s3cret"}
    assert client.get("/api/projects", headers=auth).status_code == 200
    evil = auth | {"Origin": "https://evil.example"}
    assert client.post("/api/projects", json={"name": "x"}, headers=evil).status_code == 403
    same = auth | {"Origin": "http://testserver"}
    assert client.post("/api/projects", json={"name": "x"}, headers=same).status_code == 201


def test_packs_are_listed(client):
    names = [p["name"] for p in client.get("/api/packs").json()]
    assert names == ["joinery-nl"]


def finished_run(client, architect, erp=FIX / "erp" / "duplex_erp_export_seeded.csv"):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    ids = []
    for path in architect:
        upload = put(client, project, path, "architect")
        ids.append(upload)
        mapping = path.with_suffix(".mapping.yaml")
        if mapping.exists():
            ids.append(put(client, project, mapping, "mapping", upload))
    export = put(client, project, erp, "erp")
    ids += [export, put(client, project, FIX / "erp" / "duplex_erp_export.mapping.yaml",
                        "mapping", export)]  # fmt: skip
    run = client.post(f"/api/projects/{project}/runs",
                      json={"pack": "joinery-nl", "uploads": ids}).json()  # fmt: skip
    return client.get(f"/api/runs/{run['id']}").json()


def test_findings_name_uploaded_files_not_temporary_paths(client):
    run = finished_run(client, [FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"])
    assert run["status"] == "done"
    assert set(run["files"]) == {"duplex_architectural_ifc2x3.ifc", "duplex_erp_export_seeded.csv"}
    data = client.get(f"/api/runs/{run['id']}/reports/report.json").json()
    files = {e["file"] for f in data["findings"] for e in f["evidence"]}
    assert files <= set(run["files"])
    quantity = next(f for f in data["findings"]
                    if f["rule_id"] == "erp-quantity" and f["mark"] == "02")  # fmt: skip
    assert quantity["measured"]["erp.quantity"] == {"duplex_erp_export_seeded.csv": 6}


def test_review_accept_and_dismiss_with_reason(client):
    run = finished_run(client, [FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"])
    fail = client.get(f"/api/runs/{run['id']}/findings", params={"status": "fail"}).json()[0]
    url = f"/api/findings/{fail['id']}/review"
    assert client.post(url, json={"decision": "dismiss"}).status_code == 422
    assert client.post(url, json={"decision": "maybe", "reason": "x"}).status_code == 422
    assert client.post(url, json={"decision": "accept"}).status_code == 201
    r = client.post(url, json={"decision": "dismiss", "reason": "agreed with architect on site"})
    assert r.status_code == 201
    detail = client.get(f"/api/findings/{fail['id']}").json()
    assert [x["decision"] for x in detail["reviews"]] == ["accept", "dismiss"]
    assert detail["review"]["reason"] == "agreed with architect on site"
    listed = client.get(f"/api/runs/{run['id']}/findings", params={"status": "fail"}).json()
    assert listed[0]["review"]["decision"] == "dismiss"
    csv_text = client.get(f"/api/runs/{run['id']}/findings.csv").text
    assert "dismiss,agreed with architect on site" in csv_text


def test_pdf_page_preview_and_marked_copy(client):
    run = finished_run(client, [FIX / "dxf" / "duplex_joinery_plan.dxf",
                                FIX / "pdf" / "duplex_joinery_schedule.pdf"])  # fmt: skip
    assert run["status"] == "done", run["error"]
    upload = run["files"]["duplex_joinery_schedule.pdf"]
    page = client.get(f"/api/uploads/{upload}/pages/1.png")
    assert page.status_code == 200 and page.content[:4] == b"\x89PNG"
    assert page.headers["x-points-scale"] == "1.5"
    assert client.get(f"/api/uploads/{upload}/pages/9.png").status_code == 404
    marked = client.get(f"/api/runs/{run['id']}/reports/duplex_joinery_schedule.marked.pdf")
    assert marked.status_code == 200 and marked.content[:4] == b"%PDF"


def test_web_build_is_served_beside_the_api(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>Ludwig</title>")
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db'}", storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", web_dir=web)  # fmt: skip
    client = TestClient(create_app(settings))
    assert "Ludwig" in client.get("/").text
    assert client.get("/api/packs").status_code == 200


def test_assist_is_off_unless_configured_and_never_changes_findings(tmp_path):
    import sys

    plain = Settings(database_url=f"sqlite:///{tmp_path / 'a'}", storage_dir=tmp_path / "s",
                     packs_dir=ROOT / "packs")  # fmt: skip
    off = TestClient(create_app(plain))
    assert off.get("/api/assist").json() == {"enabled": False}
    assert off.post("/api/assist/explain/1").status_code == 409

    answers = tmp_path / "answers.txt"
    answers.write_text("Frame 02 is ordered 6 times but drawn 8 times.\n=====\nx\n=====\ny")
    command = f"{sys.executable} {ROOT / 'tests' / 'assist' / 'fake_model.py'} {answers}"
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'b'}", storage_dir=tmp_path / "s2",
                        packs_dir=ROOT / "packs", assist_command=command)  # fmt: skip
    client = TestClient(create_app(settings))
    assert client.get("/api/assist").json() == {"enabled": True}
    run = finished_run(client, [FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"])
    fail = client.get(f"/api/runs/{run['id']}/findings", params={"status": "fail"}).json()[0]
    r = client.post(f"/api/assist/explain/{fail['id']}").json()
    assert r["explanation"].startswith("Frame 02") and r["original"] == fail["message"]
    after = client.get(f"/api/findings/{fail['id']}").json()
    assert after["status"] == fail["status"] and after["message"] == fail["message"]
    assert after["review"] is None
    draft = client.post("/api/assist/rule", json={"pack": "joinery-nl", "text": "x"}).json()
    assert draft["problems"]  # "y" is not a rule; shown to the person, never saved
