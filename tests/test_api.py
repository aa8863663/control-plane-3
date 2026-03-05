import pytest
from fastapi.testclient import TestClient
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api_server import app
from auth import create_user, init_users_table

client = TestClient(app, follow_redirects=False)

@pytest.fixture(autouse=True)
def setup():
    init_users_table()
    create_user("testuser", "testpass123")

def get_session():
    resp = client.post("/login", data={"username": "testuser", "password": "testpass123"})
    return resp.cookies.get("session", "")

def test_login_page():
    r = client.get("/login")
    assert r.status_code == 200

def test_register_page():
    r = client.get("/register")
    assert r.status_code == 200

def test_login_redirects_home():
    r = client.post("/login", data={"username": "testuser", "password": "testpass123"})
    assert r.status_code == 302

def test_home_requires_login():
    r = client.get("/")
    assert r.status_code == 302

def test_home_with_session():
    session = get_session()
    r = client.get("/", cookies={"session": session})
    assert r.status_code == 200

def test_health():
    session = get_session()
    r = client.get("/health", cookies={"session": session})
    assert r.status_code == 200

def test_stats():
    session = get_session()
    r = client.get("/stats", cookies={"session": session})
    assert r.status_code == 200

def test_actuarial():
    session = get_session()
    r = client.get("/api/actuarial", cookies={"session": session})
    assert r.status_code == 200

def test_costs():
    session = get_session()
    r = client.get("/api/costs", cookies={"session": session})
    assert r.status_code == 200

def test_compare():
    session = get_session()
    r = client.get("/api/compare", cookies={"session": session})
    assert r.status_code == 200

def test_runs_json():
    session = get_session()
    r = client.get("/api/runs", cookies={"session": session})
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_results_json():
    session = get_session()
    r = client.get("/api/results", cookies={"session": session})
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_run_benchmark_page():
    session = get_session()
    r = client.get("/run-benchmark", cookies={"session": session})
    assert r.status_code == 200
