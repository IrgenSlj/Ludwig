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


def test_project_stats_count_raised_accepted_dismissed(client):
    run = finished_run(client, [FIX / "ifc" / "duplex_architectural_ifc2x3.ifc"])
    open_items = client.get(
        f"/api/runs/{run['id']}/findings", params={"status": "fail,not_checked"}
    )
    ids = [f["id"] for f in open_items.json()]
    client.post(f"/api/findings/{ids[0]}/review", json={"decision": "accept"})
    client.post(f"/api/findings/{ids[1]}/review", json={"decision": "dismiss", "reason": "ok"})
    stats = client.get(f"/api/projects/{run['project_id']}/stats").json()
    assert stats["total"] == {"raised": len(ids), "accepted": 1, "dismissed": 1,
                              "unreviewed": len(ids) - 2}  # fmt: skip
    assert stats["runs"][0]["run"] == run["id"]


def build_mapping(client, upload):
    """What the web app does: take the proposal and save it unchanged."""
    proposal = client.get(f"/api/uploads/{upload}/columns").json()
    r = client.post(f"/api/uploads/{upload}/mapping",
                    json={"mapping": proposal["mapping"], "save": True})  # fmt: skip
    assert r.status_code == 200, r.text
    return r.json()


def test_mappings_built_in_the_app_give_the_same_findings(client):
    """PLAN 5.7: no YAML written by hand, same findings as the hand-written mappings."""
    project = client.post("/api/projects", json={"name": "Built"}).json()["id"]
    model = put(client, project, FIX / "ifc" / "duplex_architectural_ifc2x3.ifc", "architect")
    sched = put(client, project, FIX / "schedule" / "duplex_joinery_schedule.csv", "architect")
    erp = put(client, project, FIX / "erp" / "duplex_erp_export_seeded.csv", "erp")
    built = [build_mapping(client, sched), build_mapping(client, erp)]
    assert built[0]["elements"] > 0 and built[0]["warnings"] == []
    assert built[1]["upload"]["filename"] == "duplex_erp_export_seeded.mapping.yaml"
    ids = [model, sched, erp] + [b["upload"]["id"] for b in built]
    r = client.post(f"/api/projects/{project}/runs", json={"pack": "joinery-nl", "uploads": ids})
    run = client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["status"] == "done", run["error"]
    assert run["summary"]["fails_by_severity"] == {"blocker": 8, "warning": 2}


def test_preview_does_not_save_and_reports_problems(client):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    sched = put(client, project, FIX / "schedule" / "duplex_joinery_schedule.csv", "architect")
    mapping = {"type": "frame", "columns": {"mark": "Merk", "width_mm": "Breed"}}
    r = client.post(f"/api/uploads/{sched}/mapping", json={"mapping": mapping}).json()
    assert r["upload"] is None and r["elements"] > 0
    assert any("'Breed'" in w for w in r["warnings"])
    uploads = client.get(f"/api/projects/{project}/uploads").json()
    assert [u["role"] for u in uploads] == ["architect"]
    bad = client.post(f"/api/uploads/{sched}/mapping", json={"mapping": {"type": "door"}})
    assert bad.status_code == 422


def test_a_saved_mapping_is_offered_for_the_next_export_with_the_same_columns(client):
    first = client.post("/api/projects", json={"name": "A"}).json()["id"]
    erp = put(client, first, FIX / "erp" / "duplex_erp_export.csv", "erp")
    build_mapping(client, erp)
    second = client.post("/api/projects", json={"name": "B"}).json()["id"]
    again = put(client, second, FIX / "erp" / "duplex_erp_export_seeded.csv", "erp")
    offered = client.get(f"/api/uploads/{again}/columns").json()["previous"]
    assert [o["filename"] for o in offered] == ["duplex_erp_export.mapping.yaml"]
    assert offered[0]["project"] == first
    # A schedule is a different kind of file: export mappings are not offered for it.
    sched = put(client, second, FIX / "schedule" / "duplex_joinery_schedule.csv", "architect")
    assert client.get(f"/api/uploads/{sched}/columns").json()["previous"] == []


def test_columns_only_for_tables(client):
    project = client.post("/api/projects", json={"name": "P"}).json()["id"]
    model = put(client, project, FIX / "ifc" / "duplex_architectural_ifc2x3.ifc", "architect")
    assert client.get(f"/api/uploads/{model}/columns").status_code == 422
    assert client.get("/api/uploads/999/columns").status_code == 404
    book = put(client, project, FIX / "schedule" / "duplex_design_cobie.xlsx", "architect")
    sheets = client.get(f"/api/uploads/{book}/columns").json()["sheets"]
    assert len(sheets) > 1
    chosen = client.get(f"/api/uploads/{book}/columns", params={"sheet": sheets[1]}).json()
    assert chosen["mapping"]["sheet"] == sheets[1]
