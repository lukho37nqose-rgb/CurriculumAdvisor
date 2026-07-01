from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfWriter

import app as app_module
from engine.web_security import SlidingWindowRateLimitMiddleware

client = TestClient(app_module.app)


def _pdf_bytes(*, pages: int = 1, password: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    if password:
        writer.encrypt(password)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_security_headers_are_present_on_html_and_api():
    for path in ("/", "/health"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["x-request-id"]


def test_static_catalogue_endpoints_support_gzip_etag_and_conditional_get():
    response = client.get("/faculties", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert "public" in response.headers["cache-control"]
    etag = response.headers["etag"]

    cached = client.get("/faculties", headers={"If-None-Match": etag})
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == etag


def test_health_is_shallow_and_readiness_loads_catalogues(monkeypatch):
    def fail_if_loaded(_faculty_key: str):
        raise AssertionError("liveness probe must not load catalogue data")

    monkeypatch.setattr(app_module, "get_catalogue", fail_if_loaded)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_catalogue_returns_route_specific_course_roles():
    general = client.get(
        "/catalogue",
        params={
            "faculty_key": "uct_humanities",
            "programme_key": "bsocsc_regular",
        },
    )
    assert general.status_code == 200
    courses = general.json()
    assert courses["ACC1021F"]["route_role"] == "elective"
    assert courses["POL1004F"]["route_role"] == "major_requirement"
    assert set(courses["POL1004F"]["route_roles"]) == {
        "major_requirement",
        "elective",
    }

    structured = client.get(
        "/catalogue",
        params={
            "faculty_key": "uct_humanities",
            "programme_key": "advanced_diploma_theatre",
        },
    )
    assert structured.status_code == 200
    assert {course["route_role"] for course in structured.json().values()} == {"required"}


def test_json_and_text_analysis_inputs_are_bounded():
    too_many_results = [
        {
            "code": f"TST{index:04d}F",
            "name": "Test",
            "nqf_level": 5,
            "nqf_credits": 12,
            "mark": 60,
            "grade": "2-",
        }
        for index in range(app_module.MAX_RESULTS + 1)
    ]
    response = client.post(
        "/analyse/json",
        json={
            "faculty": "uct_humanities",
            "programme_key": "bsocsc_regular",
            "results": too_many_results,
        },
    )
    assert response.status_code == 422
    assert "at most" in response.json()["detail"]

    response = client.post(
        "/analyse/text",
        json={"text": "X" * (app_module.MAX_TRANSCRIPT_TEXT_CHARACTERS + 1)},
    )
    assert response.status_code == 413


def test_simulated_semester_size_is_bounded():
    response = client.post(
        "/simulate/semester",
        json={
            "faculty": "uct_humanities",
            "programme_key": "bsocsc_regular",
            "student": {"results": []},
            "courses": [
                [f"TST{index:04d}F", 60]
                for index in range(app_module.MAX_SIMULATED_COURSES + 1)
            ],
        },
    )
    assert response.status_code == 422
    assert "at most" in response.json()["detail"]


def test_pdf_upload_rejects_encrypted_and_excessively_long_documents():
    encrypted = client.post(
        "/analyse?faculty=uct_humanities&programme=bsocsc_regular",
        files={"file": ("encrypted.pdf", _pdf_bytes(password="secret"), "application/pdf")},
    )
    assert encrypted.status_code == 422
    assert "Encrypted" in encrypted.json()["detail"]

    too_many_pages = client.post(
        "/analyse?faculty=uct_humanities&programme=bsocsc_regular",
        files={
            "file": (
                "long.pdf",
                _pdf_bytes(pages=app_module.MAX_PDF_PAGES + 1),
                "application/pdf",
            )
        },
    )
    assert too_many_pages.status_code == 422
    assert "pages" in too_many_pages.json()["detail"]


def test_streaming_upload_limit_rejects_oversized_file():
    content = b"%PDF-1.7\n" + b"0" * app_module.MAX_UPLOAD_BYTES
    response = client.post(
        "/analyse?faculty=uct_humanities&programme=bsocsc_regular",
        files={"file": ("too-large.pdf", content, "application/pdf")},
    )
    assert response.status_code == 413


def test_rate_limiter_returns_retry_after_without_touching_get_requests():
    limited_app = FastAPI()
    limited_app.add_middleware(
        SlidingWindowRateLimitMiddleware,
        requests_per_window=2,
        window_seconds=60,
    )

    @limited_app.post("/analyse/test")
    def analyse_test():
        return {"ok": True}

    @limited_app.get("/analyse/test")
    def read_test():
        return {"ok": True}

    limited_client = TestClient(limited_app)
    assert limited_client.get("/analyse/test").status_code == 200
    assert limited_client.post("/analyse/test").status_code == 200
    assert limited_client.post("/analyse/test").status_code == 200
    blocked = limited_client.post("/analyse/test")
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]


def test_frontend_contains_public_release_state_and_accessibility_controls():
    html = Path("static/index.html").read_text(encoding="utf-8")
    javascript = Path("static/app.js").read_text(encoding="utf-8")

    assert '<script src="/static/app.js" defer></script>' in html
    assert 'role="tablist"' in html
    assert 'aria-live="polite"' in html
    assert "processed in memory" in html
    assert "not retained" in html
    assert "function resetRouteState" in javascript
    assert "routeLoaded" in javascript
    assert "Readmission position could not be verified" in javascript
    assert "blocking rules satisfied" in javascript
    assert "Showing ${visible.length} of ${allCourses.length}" in javascript
    assert "course.route_roles" in javascript
