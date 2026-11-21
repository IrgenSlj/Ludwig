"""PLAN 6.5-6.9: migrations, personal logins, activity log, project delete/export, retention."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from test_api import FIX, ROOT, database_url, put  # noqa: E402

from ludwig import cli  # noqa: E402
from ludwig.api import auth, data  # noqa: E402
from ludwig.api.app import create_app  # noqa: E402
from ludwig.api.db import Base, Project, Upload, connect, migrate  # noqa: E402
from ludwig.api.settings import Settings  # noqa: E402
from ludwig.api.storage import Storage  # noqa: E402

PASSWORD = "correct horse battery"


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=database_url(tmp_path), storage_dir=tmp_path / "storage",
                    packs_dir=ROOT / "packs")  # fmt: skip


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def admin_client(settings):
    """A client signed in as the first user (an admin)."""
    c = TestClient(create_app(settings))
    assert c.post("/api/users", json={"name": "anna", "password": PASSWORD}).status_code == 201
    assert c.post("/api/auth/login", json={"name": "anna", "password": PASSWORD}).status_code == 200
    return c


# Migrations


def test_migrations_build_exactly_the_models():
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = create_engine("sqlite://")
    migrate(engine)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []


def test_a_database_from_before_migrations_is_stamped_and_upgraded(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = create_engine(url)
    from alembic import command
    from alembic.config import Config

    from ludwig.api.db import MIGRATIONS

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
        conn.execute(text("DROP TABLE alembic_version"))
        conn.execute(text("INSERT INTO project (name, created) VALUES ('old', '2026-01-01')"))
    sessions = connect(url)
    with sessions() as session:
        assert session.query(Project).one().name == "old"
    columns = {c["name"] for c in inspect(create_engine(url)).get_columns("review")}
    assert "user_name" in columns


# Personal logins


def test_open_until_the_first_user_then_sign_in_required(client):
    assert client.get("/api/auth/me").json() == {"signed_in": True, "user": None, "name": None,
                                                 "login_required": False,
                                                 "no_users": True}  # fmt: skip
    assert client.get("/api/projects").status_code == 200
    first = client.post("/api/users", json={"name": "anna", "password": PASSWORD}).json()
    assert first["admin"] is True  # the first user always manages the others
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/login",
                       json={"name": "anna", "password": "wrong password"}).status_code == 401
    r = client.post("/api/auth/login", json={"name": "anna", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/projects").status_code == 200
    assert client.get("/api/auth/me").json()["user"]["name"] == "anna"
    client.post("/api/auth/logout")
    assert client.get("/api/projects").status_code == 401


def test_password_hash_is_scrypt_and_verifies():
    stored = auth.hash_password(PASSWORD)
    assert stored.startswith("scrypt$131072$8$1$") and PASSWORD not in stored
    assert auth.verify_password(PASSWORD, stored)
    assert not auth.verify_password("other password", stored)
    assert not auth.verify_password(PASSWORD, "garbage")


def test_admin_manages_users_and_members_cannot(settings):
    admin = admin_client(settings)
    assert admin.post("/api/users", json={"name": "bob", "password": "short"}).status_code == 422
    bob = admin.post("/api/users", json={"name": "bob", "password": PASSWORD}).json()
    assert bob["admin"] is False
    assert admin.post("/api/users", json={"name": "bob", "password": PASSWORD}).status_code == 422

    member = TestClient(create_app(settings))
    member.post("/api/auth/login", json={"name": "bob", "password": PASSWORD})
    assert member.get("/api/projects").status_code == 200
    assert member.get("/api/users").status_code == 403

    # Deactivating ends bob's sessions at once.
    admin.patch(f"/api/users/{bob['id']}", json={"active": False})
    assert member.get("/api/projects").status_code == 401
    assert member.post("/api/auth/login",
                       json={"name": "bob", "password": PASSWORD}).status_code == 401
    me = admin.get("/api/auth/me").json()["user"]
    assert admin.patch(f"/api/users/{me['id']}", json={"admin": False}).status_code == 422


def test_repeated_wrong_passwords_are_slowed_down(settings, monkeypatch):
    monkeypatch.setattr(auth, "_FAILS", {})
    c = admin_client(settings)
    c.post("/api/auth/logout")
    for _ in range(auth.FAIL_LIMIT):
        assert c.post("/api/auth/login", json={"name": "anna", "password": "x"}).status_code == 401
    r = c.post("/api/auth/login", json={"name": "anna", "password": PASSWORD})
    assert r.status_code == 429


def test_api_token_still_works_for_scripts(tmp_path):
    settings = Settings(database_url=database_url(tmp_path), storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", api_token="s3cret")  # fmt: skip
    c = TestClient(create_app(settings))
    assert c.get("/api/projects").status_code == 401
    ok = c.get("/api/projects", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_reviews_and_limit_changes_record_who(settings):
    c = admin_client(settings)
    project = c.post("/api/projects", json={"name": "P"}).json()["id"]
    model = put(c, project, FIX / "ifc" / "duplex_architectural_ifc2x3.ifc", "architect")
    sched = put(c, project, FIX / "schedule" / "duplex_joinery_schedule_seeded.csv", "architect")
    mapping = FIX / "schedule" / "duplex_joinery_schedule_seeded.mapping.yaml"
    m = put(c, project, mapping, "mapping", sched)
    run = c.post(f"/api/projects/{project}/runs",
                 json={"pack": "joinery-nl", "uploads": [model, sched, m]}).json()  # fmt: skip
    fail = c.get(f"/api/runs/{run['id']}/findings", params={"status": "fail"}).json()[0]
    c.post(f"/api/findings/{fail['id']}/review", json={"decision": "accept"})
    assert c.get(f"/api/findings/{fail['id']}").json()["review"]["by"] == "anna"

    actions = [e["action"] for e in c.get("/api/activity", params={"project_id": project}).json()]
    assert actions == ["finding accepted", "check run", "file uploaded", "file uploaded",
                       "file uploaded", "project created"]  # fmt: skip
    every = c.get("/api/activity").json()
    assert {"sign in", "user added"} <= {e["action"] for e in every}
    assert all(e["user"] in ("anna", None) for e in every)


# Data controls


def test_delete_removes_everything_but_shared_files(settings, tmp_path):
    c = TestClient(create_app(settings))
    keep = c.post("/api/projects", json={"name": "keep"}).json()["id"]
    gone = c.post("/api/projects", json={"name": "gone"}).json()["id"]
    sched = FIX / "schedule" / "duplex_joinery_schedule.csv"
    put(c, keep, sched, "architect")
    a = put(c, gone, sched, "architect")
    put(c, gone, FIX / "schedule" / "duplex_joinery_schedule.mapping.yaml", "mapping", a)
    erp = put(c, gone, FIX / "erp" / "duplex_erp_export.csv", "erp")
    put(c, gone, FIX / "erp" / "duplex_erp_export.mapping.yaml", "mapping", erp)
    model = put(c, gone, FIX / "ifc" / "duplex_architectural_ifc2x3.ifc", "architect")
    ids = [u["id"] for u in c.get(f"/api/projects/{gone}/uploads").json()]
    run = c.post(f"/api/projects/{gone}/runs", json={"pack": "joinery-nl", "uploads": ids}).json()
    assert model in ids and (tmp_path / "storage" / "runs" / str(run["id"])).is_dir()

    r = c.delete(f"/api/projects/{gone}").json()
    assert r["files"] == 5 and r["runs"] == 1 and r["findings"] > 0
    assert c.get(f"/api/projects/{gone}").status_code == 404
    assert c.get(f"/api/runs/{run['id']}").status_code == 404
    assert not (tmp_path / "storage" / "runs" / str(run["id"])).exists()
    objects = [p for p in (tmp_path / "storage" / "objects").rglob("*") if p.is_file()]
    assert len(objects) == 1  # the schedule the other project still uses
    assert c.get(f"/api/projects/{keep}/uploads").json()[0]["filename"] == sched.name
    assert c.get("/api/activity", params={"project_id": gone}).json() == []
    last = c.get("/api/activity").json()[0]
    assert last["action"] == "project deleted" and "gone" not in json.dumps(last)


def test_export_holds_files_reports_findings_and_activity(client):
    c = client
    project = c.post("/api/projects", json={"name": "Duplex"}).json()["id"]
    sched = put(c, project, FIX / "schedule" / "duplex_joinery_schedule_seeded.csv", "architect")
    m = put(c, project, FIX / "schedule" / "duplex_joinery_schedule_seeded.mapping.yaml",
            "mapping", sched)  # fmt: skip
    run = c.post(f"/api/projects/{project}/runs",
                 json={"pack": "joinery-nl", "uploads": [sched, m]}).json()  # fmt: skip
    r = c.get(f"/api/projects/{project}/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        assert {"project.json", "files.json", "runs.json", "activity.json"} <= names
        assert f"files/{sched}-duplex_joinery_schedule_seeded.csv" in names
        assert f"runs/{run['id']}/report.json" in names
        runs = json.loads(zf.read("runs.json"))
        assert runs[0]["findings"] and "reviews" in runs[0]["findings"][0]


def test_retention_deletes_only_idle_projects(settings):
    sessions = connect(settings.database_url)
    storage = Storage(settings.storage_dir)
    old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40)
    with sessions() as session:
        old = Project(name="old", created=old_time)
        new = Project(name="new")
        session.add_all([old, new])
        session.flush()
        session.add(Upload(project_id=old.id, role="architect", filename="a.csv",
                           sha256=storage.put(b"a"), size=1, created=old_time))  # fmt: skip
        session.commit()
        assert data.purge_expired(session, storage, 30) == [old.id]
        assert [p.name for p in session.query(Project)] == ["new"]
        assert not storage.object(hashlib.sha256(b"a").hexdigest()).exists()
        assert data.purge_expired(session, storage, 30) == []


def test_command_line_adds_a_user_and_purges(settings, monkeypatch, capsys):
    monkeypatch.setenv("LUDWIG_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("LUDWIG_STORAGE_DIR", str(settings.storage_dir))
    monkeypatch.setenv("LUDWIG_NEW_PASSWORD", PASSWORD)
    assert cli.main(["user", "add", "anna", "--admin"]) == 0
    assert "added anna (admin)" in capsys.readouterr().out
    assert cli.main(["user", "add", "anna"]) == 2
    assert cli.main(["user", "password", "anna"]) == 0
    assert cli.main(["purge"]) == 2  # no retention period given
    assert cli.main(["purge", "--days", "30"]) == 0
    c = TestClient(create_app(settings))
    assert c.post("/api/auth/login", json={"name": "anna", "password": PASSWORD}).status_code == 200


def test_settings_from_environment(monkeypatch):
    monkeypatch.setenv("LUDWIG_SECURE_COOKIES", "1")
    monkeypatch.setenv("LUDWIG_RETENTION_DAYS", "90")
    s = Settings.from_env()
    assert s.secure_cookies and s.retention_days == 90 and s.session_days == 14
    assert Path(s.storage_dir) == Path("storage")


def test_hosted_instance_is_never_open(tmp_path):
    settings = Settings(database_url=database_url(tmp_path), storage_dir=tmp_path / "s",
                        packs_dir=ROOT / "packs", require_login=True)  # fmt: skip
    c = TestClient(create_app(settings))
    me = c.get("/api/auth/me").json()
    assert me["signed_in"] is False and me["login_required"] and me["no_users"]
    assert c.get("/api/projects").status_code == 401
    # Nobody can make themselves the first admin over the web.
    assert c.post("/api/users", json={"name": "eve", "password": PASSWORD}).status_code == 401


def test_people_change_their_own_password(settings):
    c = admin_client(settings)
    other = TestClient(create_app(settings))
    other.post("/api/auth/login", json={"name": "anna", "password": PASSWORD})
    new = "a much better passphrase"
    assert c.post("/api/auth/password",
                  json={"current": "wrong one!!", "new": new}).status_code == 403
    short = {"current": PASSWORD, "new": "short"}
    assert c.post("/api/auth/password", json=short).status_code == 422
    assert c.post("/api/auth/password", json={"current": PASSWORD, "new": new}).status_code == 200
    assert c.get("/api/projects").status_code == 200  # this browser stays signed in
    assert other.get("/api/projects").status_code == 401  # the other one does not
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"name": "anna", "password": new}).status_code == 200
    assert "password changed" in {e["action"] for e in c.get("/api/activity").json()}
