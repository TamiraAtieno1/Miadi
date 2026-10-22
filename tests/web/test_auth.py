import pytest

from app.models import User
from tests.web.conftest import ADMIN_EMAIL, DEMO_PATIENT, DOCTOR_ONE, PASSWORD, sign_in


def test_home_sends_visitors_to_sign_in(web):
    response = web.get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_page_shows_the_form_and_demo_accounts(web):
    page = web.get("/login")
    assert page.status_code == 200
    assert "Sign in" in page.text
    assert DEMO_PATIENT in page.text
    assert PASSWORD in page.text


def test_demo_accounts_can_be_hidden(web, monkeypatch):
    monkeypatch.setenv("SHOW_DEMO_LOGINS", "0")
    page = web.get("/login")
    assert DEMO_PATIENT not in page.text
    assert PASSWORD not in page.text


@pytest.mark.parametrize(
    ("email", "home"),
    [
        (DEMO_PATIENT, "/portal/patient"),
        (DOCTOR_ONE, "/portal/doctor"),
        (ADMIN_EMAIL, "/portal/admin"),
    ],
)
def test_each_role_lands_on_its_own_page(web, email, home):
    response = sign_in(web, email)
    assert response.status_code == 303
    assert response.headers["location"] == home
    assert web.get("/").headers["location"] == home
    assert web.get("/login").headers["location"] == home
    assert web.get("/register").headers["location"] == home
    assert web.get(home).status_code == 200


def test_a_wrong_password_is_refused_with_a_clear_message(web):
    response = sign_in(web, DEMO_PATIENT, "wrong-password")
    assert response.headers["location"] == "/login"
    assert "email and password" in web.get("/login").text
    assert web.get("/portal/patient").status_code == 303  # still signed out


def test_pages_need_a_sign_in(web):
    for path in ("/portal/patient", "/portal/doctor", "/portal/admin", "/portal/patient/book"):
        response = web.get(path)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    assert "Please sign in" in web.get("/login").text


def test_each_role_is_kept_out_of_the_others_pages(as_patient):
    for path in ("/portal/doctor", "/portal/admin"):
        response = as_patient.get(path)
        assert response.status_code == 403
        assert "for you" in response.text


def test_sign_out_ends_the_session(as_patient):
    response = as_patient.post("/logout")
    assert response.headers["location"] == "/login"
    assert as_patient.get("/portal/patient").status_code == 303
    assert "signed out" in as_patient.get("/login").text


def test_a_cookie_for_a_deleted_account_is_dropped(web, db):
    sign_in(web, DEMO_PATIENT)
    db.query(User).filter(User.email == DEMO_PATIENT).delete()
    db.commit()
    assert web.get("/portal/patient").status_code == 303


def test_register_creates_a_patient_who_is_signed_in(web):
    response = web.post(
        "/register",
        data={"name": "Wanjiku Mwangi", "email": "w@example.com", "password": "longenough"},
    )
    assert response.headers["location"] == "/portal/patient"
    page = web.get("/portal/patient")
    assert "Welcome to Miadi" in page.text
    assert "Wanjiku Mwangi" in page.text
    # ...and can sign in again later
    web.post("/logout")
    assert sign_in(web, "w@example.com", "longenough").headers["location"] == "/portal/patient"


def test_register_page_renders(web):
    assert "Create a patient account" in web.get("/register").text


def test_register_explains_what_is_wrong(web):
    response = web.post("/register", data={"name": "A", "email": "a@example.com", "password": "x"})
    assert response.headers["location"] == "/register"
    assert "at least 8 characters" in web.get("/register").text


def test_register_refuses_an_email_that_is_taken(web):
    response = web.post(
        "/register", data={"name": "Copy", "email": DEMO_PATIENT, "password": "longenough"}
    )
    assert response.headers["location"] == "/register"
    assert "already an account" in web.get("/register").text


def test_the_api_docs_do_not_list_the_html_pages(web):
    paths = web.get("/openapi.json").json()["paths"]
    assert not any(path.startswith(("/portal", "/login", "/register")) for path in paths)
    assert "/appointments" in paths


def test_stylesheet_is_served(web):
    response = web.get("/static/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
