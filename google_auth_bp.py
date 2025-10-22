from flask import request, redirect, url_for, flash, session, Blueprint
from requests_oauthlib import OAuth2Session
import json
import os
from sqlalchemy import create_engine, text
from pathlib import Path

import config as cfg

bp = Blueprint("google_auth", __name__)

engine = create_engine(cfg.DATABASE_URL)

# Carico le credenziali dal JSON
if Path("client_secret.json").is_file():
    try:
        with open("client_secret.json") as f:
            config = json.load(f)["web"]

        client_id = config["client_id"]
        client_secret = config["client_secret"]
        authorization_base_url = config["auth_uri"]
        token_url = config["token_uri"]
        redirect_uri = config["redirect_uris"][0]

        scope = [
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
        ]

        # solo per DEV
        if "127.0.0.1" in redirect_uri:
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    except Exception:
        raise


@bp.route(f"{cfg.APPLICATION_ROOT}/login")
def login():
    """
    Reindirizza l'utente alla schermata di autorizzazione di Google
    """
    google = OAuth2Session(client_id, scope=scope, redirect_uri=redirect_uri)
    authorization_url, state = google.authorization_url(authorization_base_url)
    session["oauth_state"] = state
    return redirect(authorization_url)


@bp.route(cfg.APPLICATION_ROOT + "/callback")
def callback():
    """
    Callback dopo il login Google
    """
    google = OAuth2Session(
        client_id, state=session["oauth_state"], redirect_uri=redirect_uri
    )
    try:
        token = google.fetch_token(
            token_url, client_secret=client_secret, authorization_response=request.url
        )
    except Exception:
        return redirect(url_for("main_home"))

    session["oauth_token"] = token

    # Recupero dati utente
    response = google.get("https://www.googleapis.com/oauth2/v1/userinfo")
    userinfo = response.json()

    with engine.connect() as conn:
        user = (
            conn.execute(
                text("SELECT id, quizz FROM users WHERE email = :email"),
                {"email": userinfo["email"]},
            )
            .mappings()
            .fetchone()
        )
        if user is None:
            flash(
                f"Spiacente {userinfo['name']}, non sei autorizzato ad accedere",
                "danger",
            )
            return redirect(url_for("main_home"))

    session["authorized_quizz"] = user["quizz"] if user["quizz"] else []

    if not session["authorized_quizz"]:
        flash(
            f"{userinfo['name']}, you are not authorized to access quizz",
            "danger",
        )
        return redirect(url_for("main_home"))

    # check if first login
    with engine.connect() as conn:
        for quiz in session["authorized_quizz"]:
            if not conn.execute(
                text(
                    "SELECT id FROM lives WHERE user_id = :user_id AND course = :course"
                ),
                {"user_id": user["id"], "course": quiz},
            ).scalar():
                # add lives
                row = (
                    conn.execute(
                        text(
                            "SELECT initial_life_number FROM courses WHERE name = :course"
                        ),
                        {"course": quiz},
                    )
                    .mappings()
                    .fetchone()
                )
                conn.execute(
                    text(
                        "INSERT INTO lives (course, user_id, number) VALUES (:course, :user_id, :number)"
                    ),
                    {
                        "course": quiz,
                        "user_id": user["id"],
                        "number": row["initial_life_number"],
                    },
                )
                conn.commit()

    session["nickname"] = userinfo["name"]
    session["name"] = userinfo["name"]
    session["email"] = userinfo["email"]
    session["user_id"] = user["id"]

    if len(session["authorized_quizz"]) > 1:
        return redirect(url_for("my_quizz"))

    return redirect(url_for("home", course=session["authorized_quizz"][0]))


@bp.route(cfg.APPLICATION_ROOT + "/logout/<course>")
def logout(course: str):
    """
    logout and return to quizz home
    """
    session.clear()

    return redirect(url_for("home", course=course))
