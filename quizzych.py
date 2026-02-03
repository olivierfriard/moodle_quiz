"""
Quizzych

"""

import hashlib
import io
import json
import logging
import random
import re
import tempfile
import tomllib
import unicodedata
from functools import wraps
from pathlib import Path

import geojson
import markdown
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np

# import sqlite3
import pandas as pd
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup
from PIL import Image
from rapidfuzz import fuzz
from shapely.geometry import Point, shape
from sqlalchemy import bindparam, create_engine, text
from tabulate import tabulate

import google_auth_bp
import moodle_xml
import quiz

__version__ = "0.2.0"
__version_date__ = "2026-02-03_13:16:46Z"

logging.basicConfig(
    format="%(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)


def get_course_config(course: str) -> dict[str, str | list[str]]:
    # check config file
    with engine.connect() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM courses WHERE name = :course"), {"course": course}
            )
            .mappings()
            .fetchone()
        )
        if row:
            config = {}
            config["QUIZ_NAME"] = row["name"]
            config["managers"] = row["managers"]
            config["INITIAL_LIFE_NUMBER"] = row["initial_life_number"]
            config["N_QUESTIONS"] = row["topic_question_number"]
            config["QUESTION_TYPES"] = row["question_types"]
            config["TOPICS_TO_HIDE"] = row["topics_to_hide"]
            config["STEP_NAMES"] = row["steps"]
            config["N_STEPS"] = len(config["STEP_NAMES"])
            config["N_QUIZ_BY_STEP"] = row["step_quiz_number"]
            config["N_QUESTIONS_FOR_RECOVER"] = row["recover_question_number"]
            config["RECOVER_TOPICS"] = row["recover_topics"]
            config["BRUSH_UP_LEVELS"] = row["brush_up_levels"]
            config["N_QUESTIONS_BY_BRUSH_UP"] = row["brush_up_question_number"]
            config["BRUSH_UP_LEVEL_NAMES"] = row["brush_up_level_names"]
            config["login_mode"] = row["mode"]

            return config

    config = {
        "QUIZ_NAME": course,
        "INITIAL_LIFE_NUMBER": 5,
        "N_QUESTIONS": 10,
        "QUESTION_TYPES": ["truefalse", "multichoice", "shortanswer", "numerical"],
        "TOPICS_TO_HIDE": [],
        "N_STEPS": 3,
        "N_QUIZ_BY_STEP": 4,
        "STEP_NAMES": ["STEP #1", "STEP #2", "STEP #3"],
        "N_QUESTIONS_FOR_RECOVER": 5,
        "RECOVER_TOPICS": [],
        "login_mode": "free",
    }
    return config


def get_translation(language: str):
    """
    get translations
    """
    if Path(f"translations_{language}.txt").is_file():
        with open(Path(f"translations_{language}.txt"), "rb") as f:
            translation = tomllib.load(f)

        return translation
    else:
        return None


def load_questions_xml(xml_file: Path, course: str, config: dict) -> int:
    try:
        # load questions from xml moodle file
        question_data = moodle_xml.moodle_xml_to_dict_with_images(
            xml_file, config["QUESTION_TYPES"], f"images/{course}"
        )

        with engine.connect() as conn:
            conn.execute(
                text("DELETE FROM questions WHERE course = :course_name"),
                {"course_name": course},
            )

            for topic in question_data:
                for question in question_data[topic]:
                    conn.execute(
                        text(
                            "INSERT INTO questions (course, topic, type, name, content) VALUES (:course_name, :topic, :type, :name, :content)"
                        ),
                        {
                            "course_name": course,
                            "topic": topic,
                            "type": question["type"],
                            "name": question["name"],
                            "content": json.dumps(question),
                        },
                    )

            conn.commit()

    except Exception as e:
        raise
        return 1, f"{e}"
    return 0, ""


def load_questions_gift(gift_file_path: Path, course: str, config: dict) -> int:
    import gift

    try:
        # load questions from GIFT file
        question_data = gift.gift_to_dict(
            gift_file_path,
            config["QUESTION_TYPES"],
        )

        count_questions = 0

        with engine.connect() as conn:
            conn.execute(
                text("DELETE FROM questions WHERE course = :course"),
                {"course": course},
            )

            for topic in question_data:
                for type_ in question_data[topic]:
                    for question_name in question_data[topic][type_]:
                        count_questions += 1
                        conn.execute(
                            text(
                                "INSERT INTO questions (course, topic, type, name, content) VALUES (:course, :topic, :type, :name, :content)"
                            ),
                            {
                                "course": course,
                                "topic": topic,
                                "type": type_,
                                "name": question_name,
                                "content": json.dumps(
                                    question_data[topic][type_][question_name]
                                ),
                            },
                        )
            conn.commit()

    except Exception as e:
        return 1, f"{e}"
    return 0, f"{count_questions} questions loaded"


app = Flask(__name__)
app.config.from_object("config")
app.config["DEBUG"] = True
app.secret_key = "votre_clé_secrète_sécurisée_ici"

app.register_blueprint(google_auth_bp.bp)

DATABASE_URL = app.config["DATABASE_URL"]
engine = create_engine(DATABASE_URL)


def create_database(course) -> None:
    """
    create a new course in database
    all fields blank except name
    """

    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO courses (name) VALUES (:course_name)"),
            {"course_name": course},
        )
        conn.commit()

    # create image directory if not already exists
    (Path("images") / Path(course)).mkdir(parents=True, exist_ok=True)


def check_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "nickname" not in session:
            flash("You must be logged", "error")
            return redirect(url_for("home"), course=kwargs["course"])
        else:
            if session["nickname"] != "admin":
                # check if nickname exists
                with engine.connect() as conn:
                    if not conn.execute(
                        text(
                            "SELECT count(*) FROM users WHERE nickname = :nickname OR email = :email"
                        ),
                        {
                            "nickname": session["nickname"],
                            "email": session.get("email", "x"),
                        },
                    ).scalar():
                        return redirect(
                            url_for("google_auth.logout", course=kwargs["course"])
                        )

        return f(*args, **kwargs)

    return decorated_function


def course_exists(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        with engine.connect() as conn:
            if (
                conn.execute(
                    text("SELECT name FROM courses WHERE name = :course"),
                    {"course": kwargs["course"]},
                )
                .mappings()
                .fetchone()
                is None
            ):
                print("The course does not exists")
                return "The course does not exists"
        return f(*args, **kwargs)

    return decorated_function


def is_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # check if admin
        if session.get("nickname", "") != "admin":
            return redirect(url_for("main_home"))

        return f(*args, **kwargs)

    return decorated_function


def is_manager_or_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # check if admin
        flag_admin = session.get("nickname", "") == "admin"

        # check if manager
        config = get_course_config(kwargs["course"])
        if config["login_mode"] == "google_auth":
            flag_manager = session.get("email", "") in config["managers"]
        else:
            flag_manager = session.get("nickname", "") in config["managers"]

        if not flag_admin and not flag_manager:
            flash(
                Markup(
                    '<div class="notification is-danger">You are not allowed to access this page</div>'
                ),
                "",
            )
            return redirect(url_for("home", course=kwargs["course"]))

        return f(*args, **kwargs)

    return decorated_function


@app.route(f"{app.config['APPLICATION_ROOT']}/static/<path:filename>")
def send_static(filename):
    return send_from_directory("static", filename)


@app.route(f"{app.config['APPLICATION_ROOT']}/images/<course>/<path:filename>")
def images(course: str, filename):
    return send_from_directory(f"images/{course}", filename)


def get_lives_number(course: str, user_id: int) -> int | None:
    """
    get number of lives for nickname
    """
    with engine.connect() as conn:
        lives = (
            conn.execute(
                text(
                    "SELECT number FROM lives WHERE user_id = :user_id AND course = :course"
                ),
                {"course": course, "user_id": user_id},
            )
            .mappings()
            .fetchone()
        )
        if lives is not None:
            return lives["number"]
        else:
            return None


def str_match(stringa: str, template: str) -> bool:
    """
    check match between str and pattern with *
    """
    # Sostituisce ogni asterisco con '.*' per indicare "qualsiasi sequenza di caratteri"
    regex_pattern = re.escape(template).replace(r"\*", ".*")
    # Verifica se la stringa corrisponde al pattern
    return re.fullmatch(regex_pattern, stringa, re.IGNORECASE) is not None


@app.route(f"{app.config['APPLICATION_ROOT']}", methods=["GET"])
@app.route(f"{app.config['APPLICATION_ROOT']}/", methods=["GET"])
def main_home():
    """
    Quizzych home page
    """

    # get list of courses
    if session.get("nickname", "") == "admin":
        with engine.connect() as conn:
            courses = (
                conn.execute(text("SELECT name FROM courses ORDER BY name"))
                .mappings()
                .all()
            )
        courses_list = [row["name"] for row in courses]
    elif "nickname" in session:
        return redirect(url_for("my_quizz"))
    else:
        courses_list = None
    return render_template(
        "main_home.html",
        courses_list=courses_list,
        translation=get_translation("it"),
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/my_quizz", methods=["GET"])
def my_quizz():
    """
    authorized_quizz
    """

    # get list of courses
    with engine.connect() as conn:
        courses = (
            conn.execute(text("SELECT name FROM courses ORDER BY name"))
            .mappings()
            .all()
        )

    if session.get("nickname", "") == "admin":
        courses_list = [row["name"] for row in courses]
    else:
        courses_list = [
            row["name"] for row in courses if row["name"] in session["authorized_quizz"]
        ]
    return render_template(
        "my_quizz.html",
        courses_list=courses_list,
        translation=get_translation("it"),
    )


def clear_session():
    """
    clear some elements from session
    """
    if "recover" in session:
        del session["recover"]
    if "check" in session:
        del session["check"]
    if "brush-up" in session:
        del session["brush-up"]
    if "quiz" in session:
        del session["quiz"]
    if "quiz_position" in session:
        del session["quiz_position"]


@app.route(f"{app.config['APPLICATION_ROOT']}/<course>", methods=["GET"])
@course_exists
def home(course: str = ""):
    """
    Course home page
    """

    clear_session()

    config = get_course_config(course)
    translation = get_translation("it")

    if config["login_mode"] == "google_auth":
        session["manager"] = session.get("email", "") and (
            session["email"] in config["managers"]
        )
    elif "nickname" in session:
        session["manager"] = session.get("nickname", "") and (
            session["nickname"] in config["managers"]
        )
    else:
        session["manager"] = False

    lives: int | None = None
    if "user_id" in session and session["user_id"] != 0:
        lives = get_lives_number(course, session["user_id"])

    # check if brush-up available
    brushup_availability: bool = False

    if session.get("user_id", None) not in (None, 0):
        questions_df = get_questions_dataframe(course, session["user_id"])
        for idx, level in enumerate(config["BRUSH_UP_LEVELS"]):
            if (
                quiz.get_quiz_brushup(
                    questions_df,
                    config["RECOVER_TOPICS"],
                    config["N_QUESTIONS_BY_BRUSH_UP"],
                    level,
                )
                != []
            ):
                brushup_availability = True
                break

    return render_template(
        "home.html",
        no_home=1,
        course_name=config["QUIZ_NAME"],
        course=course,
        lives=lives,
        translation=translation,
        brushup_availability=brushup_availability,
        login_mode=config["login_mode"],
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/settings/<course>", methods=["GET"])
@course_exists
@check_login
def settings(course: str):
    """ """
    return render_template(
        "settings.html",
        course=course,
        translation=get_translation("it"),
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/topic_list/<course>", methods=["GET"])
@course_exists
@check_login
def topic_list(course: str):
    """
    display list of topics for selected course
    """

    if "recover" in session:
        del session["recover"]
    if "quiz" in session:
        del session["quiz"]

    config = get_course_config(course)

    lives = None
    if "user_id" in session:
        lives = get_lives_number(course, session["user_id"])

    print(f"{lives=}")

    topics = get_visible_topics(course)

    print(f"{topics=}")

    return render_template(
        "topic_list.html",
        course_name=config["QUIZ_NAME"],
        course=course,
        topics=topics,
        # scores=scores,
        lives=lives,
        translation=get_translation("it"),
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/recover_lives/<course>", methods=["GET"])
@course_exists
@check_login
def recover_lives(course: str):
    """
    display recover lives page
    """

    config = get_course_config(course)
    translation = get_translation("it")

    return render_template(
        "recover_lives.html",
        course=course,
        course_name=config["QUIZ_NAME"],
        n_questions_ok=config["N_QUESTIONS_FOR_RECOVER"],
        translation=translation,
        lives=get_lives_number(course, session["user_id"]),
    )


def get_visible_topics(course: str) -> list[str]:
    """
    returns list of topic the are not in TOPICS_TO_HIDE list
    """
    config = get_course_config(course)

    print(f"{config["TOPICS_TO_HIDE"]=}")

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT DISTINCT topic FROM questions WHERE course = :course AND deleted IS NULL ORDER BY topic"
                ),
                {"course": course},
            )
            .mappings()
            .fetchall()
        )
        print(f"{rows=}")
        if rows:
            topics = [
                row["topic"]
                for row in rows
                if row["topic"] not in config["TOPICS_TO_HIDE"]
            ]
        else:
            topics = []
    return topics


@app.route(f"{app.config['APPLICATION_ROOT']}/position/<course>", methods=["GET"])
@course_exists
@check_login
def position(course: str):
    """
    display position
    """

    topics = get_visible_topics(course)
    current_score = sum([get_score(course, topic) for topic in topics]) / len(topics)

    # all scores
    scores = []
    with engine.connect() as conn:
        users = (
            conn.execute(
                text(
                    "SELECT nickname FROM users WHERE nickname NOT IN ('admin', 'manager') AND nickname != :nickname"
                ),
                {"nickname": session["nickname"]},
            )
            .mappings()
            .fetchall()
        )
        for user in users:
            scores.append(
                (
                    sum([get_score(course, topic) for topic in topics]) / len(topics),
                    user["nickname"],
                )
            )
    scores.sort(reverse=True)

    out: list = []
    for score, user in scores:
        if current_score <= score:
            out.append(f"<strong>{session['nickname']}: {current_score}</strong>")
        out.append(f"{user}: {score}")

    return "<br>".join(out)


@app.route(f"{app.config['APPLICATION_ROOT']}/recover_quiz/<course>", methods=["GET"])
@course_exists
@check_login
def recover_quiz(course: str):
    """
    recover lives quiz
    """

    config = get_course_config(course)
    translation = get_translation("it")

    # create questions dataframe
    questions_df = get_questions_dataframe(course, session["user_id"])

    with engine.connect() as conn:
        # get number of questions in recover topic
        if config["RECOVER_TOPICS"]:
            stmt = text(
                "SELECT COUNT(*) AS n_questions FROM questions WHERE deleted IS NULL AND topic IN :topics"
            ).bindparams(bindparam("topics", expanding=True))

            n_recover_questions = conn.execute(
                stmt, {"topics": config["RECOVER_TOPICS"]}
            ).scalar()

            session["quiz"] = quiz.get_quiz_recover(
                questions_df, config["RECOVER_TOPICS"], n_recover_questions
            )

        else:  # no recover topic
            # count all questions
            n_recover_questions = (
                conn.execute(
                    text(
                        "SELECT COUNT(*) AS n_questions FROM questions WHERE deleted IS NULL"
                    )
                )
                .mappings()
                .fetchone()["n_questions"]
            )
            topics: list = [
                row["topic"]
                for row in conn.execute(
                    text("SELECT DISTINCT topic FROM questions WHERE deleted IS NULL")
                )
                .mappings()
                .fetchall()
                if row["topic"] not in config["TOPICS_TO_HIDE"]
            ]
            session["quiz"] = quiz.get_quiz_recover(
                questions_df, topics, n_recover_questions
            )

    session["quiz_position"] = 0
    session["recover"] = 0  # count number of good answer

    return redirect(
        url_for(
            "question", course=course, topic=translation["Recover lives"], step=1, idx=0
        )
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/all_topic_quiz/<course>/<topic>", methods=["GET"]
)
@course_exists
@check_login
@is_manager_or_admin
def all_topic_quiz(course: str, topic: str):
    """
    create a quiz with all questions of a topic
    """
    with engine.connect() as conn:
        query = text(
            "SELECT id FROM questions WHERE deleted IS NULL AND course = :course AND topic = :topic"
        )
        rows = (
            conn.execute(query, {"course": course, "topic": topic})
            .mappings()
            .fetchall()
        )

    session["quiz"] = [row["id"] for row in rows]
    session["quiz_position"] = 0
    session["check"] = 1

    return redirect(url_for("question", course=course, topic=topic, step=1, idx=0))


def get_questions_dataframe(course: str, user_id: int) -> pd.DataFrame:
    """
    returns pandas dataframe with questions and results for nickname
    """
    with engine.connect() as conn:
        query = text("""
                SELECT
                    q.id AS question_id,
                    q.topic AS topic,
                    q.type AS type,
                    q.name AS question_name,
                    SUM(CASE WHEN good_answer = TRUE THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = FALSE THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r
                    ON q.course = r.course
                        AND q.topic=r.topic
                        AND q.type=r.question_type
                        AND q.name=r.question_name
                        AND r.user_id = :user_id
                WHERE q.course = :course AND q.deleted IS NULL
                GROUP BY
                    q.id,
                    q.topic,
                    q.type,
                    q.name
                """)

        result = conn.execute(query, {"course": course, "user_id": user_id})
        columns = result.keys()
        rows = result.mappings().fetchall()

        # create dataframe
        return pd.DataFrame(rows, columns=columns)


@app.route(f"{app.config['APPLICATION_ROOT']}/brush_up_home/<course>", methods=["GET"])
@course_exists
@check_login
def brush_up_home(course: str):
    """
    display brush-up home page
    """
    config = get_course_config(course)
    translation = get_translation("it")

    # check if brush-up available
    brushup_availability = {}
    if "user_id" in session:
        questions_df = get_questions_dataframe(course, session["user_id"])
        for idx, level in enumerate(config["BRUSH_UP_LEVELS"]):
            brushup_availability[idx] = (
                quiz.get_quiz_brushup(
                    questions_df,
                    config["RECOVER_TOPICS"],
                    config["N_QUESTIONS_BY_BRUSH_UP"],
                    level,
                )
                != []
            )

    return render_template(
        "brush_up.html",
        course_name=config["QUIZ_NAME"],
        course=course,
        levels=config["BRUSH_UP_LEVELS"],
        level_names=config["BRUSH_UP_LEVEL_NAMES"],
        brushup_availability=brushup_availability,
        translation=translation,
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/brush_up/<course>/<int:level>", methods=["GET"]
)
@course_exists
@check_login
def brush_up(course: str, level: int):
    """
    display brush-up
    """

    config = get_course_config(course)
    translation = get_translation("it")

    questions_df = get_questions_dataframe(course, session["user_id"])

    session["quiz"] = quiz.get_quiz_brushup(
        questions_df, config["RECOVER_TOPICS"], config["N_QUESTIONS_BY_BRUSH_UP"], level
    )

    if session["quiz"] == []:
        del session["quiz"]
        flash(
            Markup(
                f'<div class="notification is-danger"><p class="is-size-5 has-text-weight-bold">{translation["The brush-up is not available"]}</p></div>'
            ),
            "",
        )

        return redirect(url_for("home", course=course))

    session["quiz_position"] = 0
    session["brush-up"] = True

    return redirect(
        url_for("question", course=course, topic=translation["Brush-up"], step=1, idx=0)
    )


def get_seed(nickname, topic):
    return int(hashlib.md5((nickname + topic).encode()).hexdigest(), 16)


@app.route(f"{app.config['APPLICATION_ROOT']}/steps/<course>/<topic>", methods=["GET"])
@course_exists
@check_login
def steps(course: str, topic: str):
    """
    display steps
    """

    config = get_course_config(course)

    lives = None
    if "user_id" in session:
        lives = get_lives_number(course, session["user_id"])

    steps_active = {x: 0 for x in range(1, config["N_STEPS"] + 1)}
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT step_index, number FROM steps WHERE course = :course AND user_id = :user_id AND topic = :topic "
                ),
                {"course": course, "user_id": session["user_id"], "topic": topic},
            )
            .mappings()
            .fetchall()
        )
        if rows is not None:
            for row in rows:
                steps_active[row["step_index"]] = row["number"]

    return render_template(
        "steps.html",
        course_name=config["QUIZ_NAME"],
        course=course,
        topic=topic,
        lives=lives,
        n_steps=config["N_STEPS"],
        n_quiz_by_step=config["N_QUIZ_BY_STEP"],
        steps_active=steps_active,
        step_name=config["STEP_NAMES"],
        translation=get_translation("it"),
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/step/<course>/<topic>/<int:step>",
    methods=["GET"],
)
@course_exists
@check_login
def step(course: str, topic: str, step: int):
    """
    create the step
    """

    config = get_course_config(course)

    with engine.connect() as conn:
        query = text("""
                SELECT
                    q.id AS question_id,
                    q.topic AS topic,
                    q.type AS type,
                    q.name AS question_name,
                    SUM(CASE WHEN good_answer = TRUE THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = FALSE THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r
                    ON q.course = r.course
                        AND q.topic=r.topic
                        AND q.type=r.question_type
                        AND q.name=r.question_name
                        AND r.user_id = :user_id
                        AND q.deleted IS NULL
                WHERE q.course = :course
                GROUP BY
                    q.id,
                    q.topic,
                    q.type,
                    q.name
                """)

        result = conn.execute(query, {"course": course, "user_id": session["user_id"]})
        columns = result.keys()
        rows = result.mappings().fetchall()

        # convert results in dataframe
        questions_df = pd.DataFrame(rows, columns=columns)

        steps_df = quiz.crea_tappe(
            questions_df,
            topic,
            config["N_STEPS"],
            config["N_QUESTIONS"],
            seed=get_seed(session["nickname"], topic),
        )

    session["quiz"] = quiz.get_quiz(
        topic,
        config["N_QUESTIONS"],
        steps_df[step - 1],
        get_lives_number(course, session["user_id"]),
    )
    session["quiz_position"] = 0
    return redirect(url_for("question", course=course, topic=topic, step=step, idx=0))


@app.route(
    f"{app.config['APPLICATION_ROOT']}/step_testing/<course>/<topic>/<int:step>",
    methods=["GET"],
)
@course_exists
def step_testing(course: str, topic: str, step: int):
    """
    create the step
    login disabled for testing
    """

    if "nickname" not in session:
        session["nickname"] = "admin"
        session["user_id"] = 0

    config = get_course_config(course)

    questions_df = get_questions_dataframe(course, session["user_id"])

    steps_df = quiz.crea_tappe(
        questions_df,
        topic,
        config["N_STEPS"],
        config["N_QUESTIONS"],
        seed=get_seed(session["nickname"], topic),
    )

    session["quiz"] = quiz.get_quiz(
        topic,
        config["N_QUESTIONS"],
        steps_df[step - 1],
        get_lives_number(course, session["user_id"]),
    )
    session["quiz_position"] = 0

    return "OK"


def get_score(course: str, topic: str, user_id: int = 0) -> float:
    """
    get score of nickname user for topic
    if nickname is empty get score of current user
    """

    with engine.connect() as conn:
        query = text(
            """
             SELECT
                SUM(percentage_ok) / COUNT(DISTINCT question_name) AS score
             FROM (
                SELECT
                    q.name AS question_name,
                    CAST(SUM(CASE WHEN r.good_answer = true THEN 1 ELSE 0 END) AS FLOAT) /
                    NULLIF(COUNT(r.good_answer), 0) AS percentage_ok
                FROM questions q
                LEFT JOIN results r
                    ON q.course = r.course
                    AND q.name = r.question_name
                    AND r.user_id = :user_id
                WHERE q.topic = :topic AND q.deleted IS NULL
                GROUP BY q.name
             ) AS subquery
             """
            #            """
            # WITH filtered_results AS (
            #    SELECT *
            #    FROM results
            #    WHERE user_id = :user_id
            # )
            # SELECT
            #    AVG(percentage_ok) AS score
            # FROM (
            #    SELECT
            #        q.name AS question_name,
            #        AVG(CASE WHEN r.good_answer THEN 1.0 ELSE 0.0 END) AS percentage_ok
            #    FROM questions q
            #    LEFT JOIN filtered_results r
            #        ON q.course = r.course
            #       AND q.name = r.question_name
            #    WHERE q.topic = :topic
            #      AND q.deleted IS NULL
            #    GROUP BY q.name
            # ) AS per_question;
            #
            #
            #
            # """
        )
        cursor = conn.execute(
            query,
            {
                "course": course,
                "topic": topic,
                "user_id": session["user_id"] if user_id == 0 else user_id,
            },
        )

        score = cursor.fetchone()[0]
        if score is not None:
            return round(score, 3)
        else:
            return 0


@app.route(
    f"{app.config['APPLICATION_ROOT']}/bookmark_checkbox/<int:question_id>",
    methods=["POST"],
)
def bookmark_checkbox(question_id: int):
    if request.is_json:
        is_checked = request.json.get("checked")
        with engine.connect() as conn:
            if is_checked:
                conn.execute(
                    text(
                        "INSERT INTO bookmarks (nickname, question_id) VALUES (:nickname, :question_id)"
                    ),
                    {"nickname": session["nickname"], "question_id": question_id},
                )
            else:
                conn.execute(
                    text("DELETE FROM bookmarks WHERE question_id = :question_id"),
                    {"question_id": question_id},
                )

            conn.commit()

    return jsonify({"message": ""})


@app.route(
    f"{app.config['APPLICATION_ROOT']}/delete_bookmark/<course>/<int:question_id>",
)
def delete_bookmark(course: str, question_id: int):
    """
    delete a question from bookmarks
    """
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM bookmarks WHERE question_id = :question_id"),
            {"question_id": question_id},
        )
        conn.commit()

    return redirect(url_for("bookmarked_questions", course=course))


def md2html(s: str, markup: bool = True) -> str:
    """
    convert markdown in HTML
    """
    out = markdown.markdown(s).replace("<p>", "").replace("</p>", "")
    return Markup(out) if markup else out


@app.route(
    f"{app.config['APPLICATION_ROOT']}/question/<course>/<topic>/<int:step>/<int:idx>",
    methods=["GET"],
)
@course_exists
@check_login
def question(course: str, topic: str, step: int, idx: int):
    """
    show question idx
    """

    config = get_course_config(course)
    translation = get_translation("it")

    if "recover" not in session and "brush-up" not in session:
        # check step index
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    (
                        text(
                            "SELECT number FROM steps WHERE course = :course AND user_id = :user_id AND topic = :topic and step_index < :step"
                        )
                    ),
                    {
                        "course": course,
                        "user_id": session["user_id"],
                        "topic": topic,
                        "step": step,
                    },
                )
                .mappings()
                .fetchall()
            )
            if rows is not None:
                for row in rows:
                    if row["number"] < config["N_QUIZ_BY_STEP"]:
                        flash(
                            Markup(
                                '<div class="notification is-danger">You are not allowed to access this page</div>'
                            ),
                            "",
                        )
                        return redirect(url_for("home", course=course))

        # check quiz_position
        if session["nickname"] != "admin" and idx != session["quiz_position"]:
            flash(
                Markup(
                    '<div class="notification is-danger">You are not allowed to access this page</div>'
                ),
                "",
            )
            return redirect(url_for("home", course=course))

    # check if quiz is finished
    if idx < len(session["quiz"]):
        question_id = session["quiz"][idx]
        # get question content
        with engine.connect() as conn:
            question = json.loads(
                conn.execute(
                    text(
                        "SELECT content FROM questions WHERE course= :course AND deleted IS NULL AND id = :question_id"
                    ),
                    {"course": course, "question_id": question_id},
                )
                .mappings()
                .fetchone()["content"]
            )
    else:
        # step/quiz finished
        del session["quiz"]
        del session["quiz_position"]

        if "recover" in session or "brush-up" in session:
            return redirect(url_for("home", course=course))

        elif "check" in session:
            del session["check"]
            return redirect(url_for("admin", course=course))

        else:
            # normal quiz
            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT number FROM steps "
                        "WHERE course= :course AND user_id = :user_id AND topic = :topic AND step_index = :step_index"
                    ),
                    {
                        "course": course,
                        "user_id": session["user_id"],
                        "topic": topic,
                        "step_index": step,
                    },
                )

                row = result.mappings().fetchone()

                if row is None:
                    conn.execute(
                        text(
                            "INSERT INTO steps (course, user_id, topic, step_index, number) "
                            "VALUES (:course, :user_id, :topic, :step_index, :number)"
                        ),
                        {
                            "course": course,
                            "user_id": session["user_id"],
                            "topic": topic,
                            "step_index": step,
                            "number": 1,
                        },
                    )
                    conn.commit()
                else:
                    conn.execute(
                        text(
                            "UPDATE steps "
                            "SET number = number + 1 "
                            "WHERE course = :course AND user_id = :user_id AND topic = :topic AND step_index = :step_index"
                        ),
                        {
                            "course": course,
                            "user_id": session["user_id"],
                            "topic": topic,
                            "step_index": step,
                        },
                    )

                    conn.commit()
                    if row["number"] == 4:
                        flash(
                            Markup(
                                f'<div class="notification is-success"><p class="is-size-3 has-text-weight-bold">Good! You just finished the step #{step}</p></div>'
                            ),
                            "",
                        )

            return redirect(url_for("steps", course=course, topic=topic))

    # check presence of images
    image_list: list = []
    for image in question.get("files", []):
        if image.startswith("http"):
            image_list.append(image)
        else:
            image_list.append(
                f"{app.config['APPLICATION_ROOT']}/images/{course}/{image}"
            )
    # check if geojson file is present (areas definition) if one image
    image_area = (len(image_list) == 1) and (
        Path("images")
        / Path(course)
        / Path(Path(image_list[0]).name).with_suffix(
            Path(image_list[0]).suffix + ".json"
        )
    ).is_file()

    if question["type"] in ("multichoice", "truefalse"):
        answers = random.sample(question["answers"], len(question["answers"]))
        placeholder = translation["Input a text"]
        type_ = "text"
    elif question["type"] in ("shortanswer", "numerical"):
        answers = ""
        type_ = "number" if question["type"] == "numerical" else "text"
        placeholder = (
            translation["Input a number"]
            if question["type"] == "numerical"
            else translation["Input a text"]
        )

    question["questiontext"] = md2html(question["questiontext"])

    return render_template(
        "question.html",
        course_name=config["QUIZ_NAME"],
        config=config,
        question=question,
        question_id=question_id,
        image_list=image_list,
        image_area=image_area,
        answers=answers,
        type_=type_,
        placeholder=placeholder,
        course=course,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session["quiz"])
        if "recover" not in session
        else config["N_QUESTIONS_FOR_RECOVER"],
        lives=get_lives_number(
            course, session["user_id"] if "user_id" in session else 0
        ),
        recover="recover" in session,
        translation=translation,
        return_url=url_for("question", course=course, topic=topic, step=step, idx=idx),
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/map_image/<course>/<image>")
def map_image(course: str, image: str):
    """
    Plotta elementi di un file GeoJSON su un'immagine e salva il risultato.
    Le coordinate GeoJSON sono normalizzate (x e y tra 0 e 1).

    :param image_path: Path all'immagine di sfondo
    :param geojson_path: Path al file GeoJSON
    :param output_path: Path del file di output (es. 'output.png')
    """

    image_path = Path("images") / Path(course) / Path(image).name
    geojson_path = Path(image_path).with_suffix(Path(image_path).suffix + ".json")

    # Carica immagine
    img = Image.open(image_path)
    img_width, img_height = img.size

    # Carica GeoJSON
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Prepara figura
    dpi = 100
    fig, ax = plt.subplots(figsize=(img_width / dpi, img_height / dpi), dpi=dpi)
    ax.imshow(img)

    # Colormap vivace
    cmap = cm.get_cmap("tab20", len(data["features"]))

    # Disegna features
    for i, feature in enumerate(data["features"]):
        geom = shape(feature["geometry"])
        name = feature.get("properties", {}).get("name", "Senza Nome")
        color = cmap(i)

        if geom.geom_type == "MultiPolygon":
            for polygon in geom.geoms:
                xs = [p[0] * img_width for p in polygon.exterior.coords]
                ys = [p[1] * img_height for p in polygon.exterior.coords]
                ax.plot(xs, ys, color=color, linewidth=2)

                # Etichetta al centro
                centroid = polygon.centroid
                ax.text(
                    centroid.x * img_width,
                    centroid.y * img_height,
                    name,
                    fontsize=12,
                    color="black",
                    ha="center",
                    va="center",
                    bbox=dict(facecolor="white", alpha=0.9, edgecolor="none", pad=1),
                )

    ax.set_xlim([0, img_width])
    ax.set_ylim([img_height, 0])
    ax.axis("off")

    # Salva in memoria (buffer)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    buf.seek(0)

    return send_file(buf, mimetype="image/png")


@app.route(
    f"{app.config['APPLICATION_ROOT']}/view_question_id/<course>/<int:question_id>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def view_question_id(course: str = "", question_id: int = 0):
    """
    display question by id
    useful to check an arbitrary question
    Can view deleted question
    """

    translation = get_translation("it")
    config = get_course_config(course)

    # get question content
    with engine.connect() as conn:
        question = json.loads(
            conn.execute(
                text(
                    "SELECT content FROM questions WHERE course= :course AND id = :question_id"
                ),
                {"course": course, "question_id": question_id},
            )
            .mappings()
            .fetchone()["content"]
        )

    # check presence of images
    image_list: list = []
    for image in question.get("files", []):
        if image.startswith("http"):
            image_list.append(image)
        else:
            image_list.append(
                f"{app.config['APPLICATION_ROOT']}/images/{course}/{image}"
            )
    # check if json file is present (areas definition) if one image
    image_area = (len(image_list) == 1) and (
        Path("images")
        / Path(course)
        / Path(Path(image_list[0]).name).with_suffix(
            Path(image_list[0]).suffix + ".json"
        )
    ).is_file()

    if question["type"] in ("multichoice", "truefalse"):
        answers = random.sample(question["answers"], len(question["answers"]))
        placeholder = translation["Input a text"]
        type_ = "text"
    elif question["type"] in ("shortanswer", "numerical"):
        answers = ""
        type_ = "number" if question["type"] == "numerical" else "text"
        placeholder = (
            translation["Input a number"]
            if question["type"] == "numerical"
            else translation["Input a text"]
        )

    question["questiontext"] = md2html(question["questiontext"])

    return render_template(
        "question.html",
        course_name=config["QUIZ_NAME"],
        config=config,
        question=question,
        question_id=question_id,
        image_list=image_list,
        image_area=image_area,
        answers=answers,
        type_=type_,
        placeholder=placeholder,
        course=course,
        topic="VIEW_QUESTION",
        step=0,
        idx=0,
        total=0,
        lives=1,
        recover=False,
        translation=translation,
        return_url=url_for("view_question_id", course=course, question_id=question_id),
    )


def normalize_text(text):
    """
    Converts text to lowercase, removes accents, and extra spaces.
    """
    text = text.lower()
    # Normalize text to remove accents and special characters
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    # Remove extra spaces
    text = " ".join(text.split())
    return text


def checked_text(text):
    if "*" in text:
        text_revised = text.split("*")[0]
    else:
        text_revised = text
    return text_revised


def calculate_similarity_score(
    student_answer, correct_answer, response_thresholds, response_phrases
):
    """
    Calculates a similarity score between the student's answer and the correct answer,
    considering both word order and the presence of words.

    :param student_answer: The answer provided by the student
    :param correct_answer: The correct answer to compare against

    """

    if correct_answer == "*":
        return True, 100.0, "Ottimo!"

    response_thresholds = [80, 90, 95]  # set the thresholds
    response_phrases = [
        "NO. Sbagliato!",
        "OK, qualche imprecisione, controlla!",
        "OK, ma rivedi la sintassi",
    ]

    # Normalize both the student's answer and the correct answer
    student_answer = normalize_text(student_answer)
    st_answer = student_answer.split()
    length_st_answer = len(st_answer)
    correct_answer = normalize_text(correct_answer)

    cor_answer = correct_answer.split()
    length_cor_answer = len(cor_answer)
    score_array = np.zeros(length_cor_answer)
    for i in range(length_cor_answer):
        score_max = 0
        text_correct = checked_text(cor_answer[i])
        for ii in range(length_st_answer):
            text_student = st_answer[ii][0 : len(text_correct)]
            score = fuzz.ratio(text_student, text_correct)
            if score > score_max:
                score_max = score
            score_array[i] = score_max
    final_score = np.mean(score_array)
    for i in np.arange(len(response_thresholds)):
        if final_score <= response_thresholds[i]:
            reply = response_phrases[i]
            break
        reply = "Ottimo!"
    return final_score > response_thresholds[0], final_score, reply


@app.route(
    f"{app.config['APPLICATION_ROOT']}/check_answer/<course>/<topic>/<int:step>/<int:idx>/<path:user_answer>",
    methods=["GET"],
)
@app.route(
    f"{app.config['APPLICATION_ROOT']}/check_answer/<course>/<topic>/<int:step>/<int:idx>",
    methods=["POST"],
)
@course_exists
@check_login
def check_answer(course: str, topic: str, step: int, idx: int, user_answer: str = ""):
    """
    check user answer and display feedback and score
    """

    config = get_course_config(course)
    translation = get_translation("it")

    def format_correct_answer(answer_feedback):
        """
        format feedback for good answer
        """
        out: list = []
        if answer_feedback:
            answer_feedback = md2html(answer_feedback, markup=False)

            """if answer_feedback.count("*") == 2:
                answer_feedback = answer_feedback.replace("*", "<i>", 1)
                answer_feedback = answer_feedback.replace("*", "</i>", 1)
            """

            out.append(answer_feedback)
        if not out:
            out.append(translation["You selected the correct answer"])
        return "<br>".join(out)

    def format_wrong_answer(answer_feedback, correct_answers):
        """
        format feedback for wrong answer
        """
        out: list = []
        if answer_feedback:
            answer_feedback = md2html(answer_feedback, markup=False)
            """
            if answer_feedback.count("*") == 2:
                answer_feedback = answer_feedback.replace("*", "<i>", 1)
                answer_feedback = answer_feedback.replace("*", "</i>", 1)
            """
            out.append(answer_feedback)

            out.append(translation["The correct answer is:"])
            if correct_answers in (["true"], ["false"]):
                correct_answers = [translation[correct_answers[0].upper()]]
            out.append(" o ".join(correct_answers))

        else:
            out.append("Sbagliato...")
            out.append(translation["The correct answer is:"])
            if correct_answers in (["true"], ["false"]):
                correct_answers = [translation[correct_answers[0].upper()]]

            out.append(" o ".join(correct_answers))
        # out.append(correct_answer)
        return "<br>".join(out)

    def find_feature_name(data: dict, x: float, y: float) -> list | None:
        """
        Ritorna il nome della feature che contiene il punto (x, y).
        Se nessuna feature contiene il punto, ritorna None.
        """

        aree: list = []

        point = Point(x, y)

        for feature in data.get("features", []):
            geom = feature.get("geometry")
            if not geom:
                continue

            polygon = shape(geom)  # Converte MultiPolygon/Polygon in geometria shapely
            if polygon.contains(point):
                aree.append(feature["properties"]["name"])

        return aree if aree else None

    if step:
        print(f"{idx=}")
        print(session["quiz"])
        print()
        question_id = session["quiz"][idx]
    else:
        # view question id
        question_id = idx

    # print(f"{question_id=}")

    # get question content
    print(question_id)
    print(course)
    with engine.connect() as conn:
        question = json.loads(
            conn.execute(
                text(
                    "SELECT content FROM questions WHERE course = :course AND id = :id"
                ),
                {"course": course, "id": question_id},
            )
            .mappings()
            .fetchone()["content"]
        )

    if request.method == "GET":
        # get user answer
        if question["type"] in ("truefalse", "multichoice"):
            user_answer = user_answer
        else:
            logging.error(f"Question type error: {question['type']}")

    if request.method == "POST":
        # check if image area
        if request.form.get("image_area") is not None:
            if not (
                Path("images")
                / Path(course)
                / Path(Path(request.form.get("image_path")).name).with_suffix(
                    Path(request.form.get("image_path")).suffix + ".json"
                )
            ).is_file():
                return "geojson not found"
            else:
                with open(
                    Path("images")
                    / Path(course)
                    / Path(Path(request.form.get("image_path")).name).with_suffix(
                        Path(request.form.get("image_path")).suffix + ".json"
                    ),
                    "r",
                ) as f:
                    data = geojson.load(f)

                x, y = [
                    float(x) for x in request.form.get("normalized_coord").split(",")
                ]
                area = find_feature_name(data, x, y)

                user_answer_list = area if area is not None else []

                # print(f"{user_answer_list=}")

        else:
            user_answer = request.form.get("user_answer")

    logging.debug(f"{user_answer=}")

    correct_answers: list = []

    response = {"questiontext": question["questiontext"]}

    # convert *word* to italic
    response["questiontext"] = md2html(response["questiontext"])
    """
    if response["questiontext"].count("*") == 2:
        response["questiontext"] = response["questiontext"].replace("*", "<i>", 1)
        response["questiontext"] = response["questiontext"].replace("*", "</i>", 1)
        response["questiontext"] = Markup(response["questiontext"])
    """

    if request.form.get("image_area"):
        for answer in question["answers"]:
            if answer["fraction"] == "100":
                correct_answers.append(answer["text"])
            for user_answer in user_answer_list:
                if user_answer == answer["text"]:
                    response["correct_answer"] = answer["fraction"] == "100"
                    response["feedback"] = (
                        answer["feedback"] if answer["feedback"] is not None else ""
                    )

        if "correct_answer" not in response:
            response["correct"] = False
        else:
            response["correct"] = response["correct_answer"]
        if response["correct"]:
            response["result"] = Markup(
                format_correct_answer(response.get("feedback", ""))
            )
        else:
            print(response)
            response["result"] = Markup(
                format_wrong_answer(response.get("feedback", ""), correct_answers)
            )

        # print(f"{response=}")

        user_answer = ", ".join(user_answer_list)

    else:
        # iterate over correct answers
        answers: dict = {}
        negative_feedback: str = ""
        for answer in question["answers"]:
            if answer["fraction"] == "100":
                correct_answers.append(answer["text"])

                match, score, reply = calculate_similarity_score(
                    user_answer, answer["text"], [], []
                )
                answers[score] = {
                    "correct_answer": answer["fraction"] == "100",
                    "match": match,
                    "feedback": answer["feedback"]
                    if answer["feedback"] is not None
                    else "",
                    "reply": reply,
                }
            else:
                negative_feedback = (
                    answer["feedback"] if answer["feedback"] is not None else ""
                )

        logging.debug(f"good {answers=}")

        if answers[sorted(answers)[-1]]["match"]:  # user gave correct answer
            if session["nickname"] == "admin":
                score = f"{sorted(answers)[-1]}<br>"
            else:
                score = ""

            # score = ""
            logging.debug(f"{score=}")

            response = response | answers[sorted(answers)[-1]]
            if sorted(answers)[-1] < 95:
                negative_feedback = negative_feedback.replace("Sbagliato!", "")
                negative_feedback = negative_feedback.replace("Sbagliato,", "")
                negative_feedback = negative_feedback.replace("Sbagliato", "")
                if not negative_feedback:
                    negative_feedback = (
                        f'<br>La risposta giustà è "{correct_answers[0]}"'
                    )

                response["result"] = Markup(
                    format_correct_answer(response["reply"] + " " + negative_feedback)
                )
            elif sorted(answers)[-1] < 100:
                response["result"] = Markup(
                    format_correct_answer(
                        response["reply"] + " " + response["feedback"]
                    )
                )
            else:
                positive_feedback = response["feedback"].replace("Esatto!", "")
                positive_feedback = positive_feedback.replace("Esatto", "")
                positive_feedback = positive_feedback.replace("Corretto!", "")
                response["result"] = Markup(
                    format_correct_answer(response["reply"] + " " + positive_feedback)
                )

            response["correct"] = True
            if "recover" in session:
                # add one good answer
                session["recover"] += 1
        else:
            # iterate over wrong answers
            answers = {}
            for answer in question["answers"]:
                if answer["fraction"] != "100":
                    match, score, reply = calculate_similarity_score(
                        user_answer, answer["text"], [], []
                    )
                    answers[score] = {
                        "correct_answer": False,
                        "match": match,
                        "feedback": answer["feedback"]
                        if answer["feedback"] is not None
                        else "",
                    }

            logging.debug(f"wrong {answers=}")

            if not answers:
                response["result"] = Markup(format_wrong_answer("", correct_answers))
                response["correct"] = False

                # remove a life if not recover
                if "recover" not in session:
                    with engine.connect() as conn:
                        conn.execute(
                            text(
                                "UPDATE lives SET number = number - 1 WHERE course = :course AND number > 0 AND user_id = :user_id "
                            ),
                            {"course": course, "user_id": session["user_id"]},
                        )
                        conn.commit()

            else:
                if answers[sorted(answers)[-1]]["match"]:  # user gave wrong answer
                    response = response | answers[sorted(answers)[-1]]

                    logging.debug(f"{correct_answers=}")

                    response["result"] = Markup(
                        format_wrong_answer(response["feedback"], correct_answers)
                    )
                    response["correct"] = False

                    # remove a life if not recover
                    if "recover" not in session:
                        with engine.connect() as conn:
                            conn.execute(
                                text(
                                    "UPDATE lives SET number = number - 1 WHERE course = :course AND number > 0 AND user_id = :user_id "
                                ),
                                {"course": course, "user_id": session["user_id"]},
                            )
                            conn.commit()
                else:
                    response["result"] = Markup(
                        format_wrong_answer("", correct_answers)
                    )
                    response["correct"] = False

        logging.debug(f"{response=}")

        # translate user answer if true or false
        if user_answer in ("true", "false"):
            user_answer = translation[user_answer.upper()]

    nlives = 1000
    flag_recovered = False
    popup: str = ""
    popup_text: str = ""

    if "quiz" in session:
        # check if recover is ended
        flag_recovered = False
        if (
            "recover" in session
            and session["recover"] >= config["N_QUESTIONS_FOR_RECOVER"]
        ):
            flag_recovered = True

            # add a new life
            with engine.connect() as conn:
                conn.execute(
                    text(
                        f"UPDATE lives SET number = number + 1 WHERE course = :course AND user_id = :user_id and number < {config['INITIAL_LIFE_NUMBER']}"
                    ),
                    {"course": course, "user_id": session["user_id"]},
                )
                conn.commit()

        # save result
        if "recover" not in session:
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "INSERT INTO results (course, user_id, topic, question_type, question_name, good_answer) "
                        "VALUES (:course, :user_id, :topic, :question_type, :question_name, :good_answer)"
                    ),
                    {
                        "course": course,
                        "user_id": session["user_id"],
                        "topic": topic,
                        "question_type": question["type"],
                        "question_name": question["name"],
                        "good_answer": response["correct"],
                    },
                )
                conn.commit()

        popup: str = ""
        popup_text: str = ""
        if flag_recovered:
            popup_text = translation["Congratulations! You've recovered one life!"]

        nlives = get_lives_number(
            course, session["user_id"] if "user_id" in session else 0
        )

        if nlives == 0 and "recover" not in session:
            popup_text = Markup(f"{translation["You've lost all your lives..."]}")

        session["quiz_position"] += 1

    # get overall score (for admin)
    if session["nickname"] == "admin" or session["manager"]:
        with engine.connect() as conn:
            overall = {}

            for row in (
                conn.execute(
                    text(
                        "SELECT good_answer, count(*) AS n "
                        "FROM results "
                        "WHERE course = :course "
                        "AND topic = :topic "
                        "AND question_name = :question_name "
                        "AND user_id != 0 "  # admin
                        "GROUP BY good_answer "
                    ),
                    {
                        "course": course,
                        "topic": topic,
                        "question_name": question["name"],
                    },
                )
                .mappings()
                .all()
            ):
                overall[row["good_answer"]] = row["n"]

        overall_str = (
            f"{overall.get(1, 0) / (overall.get(1, 0) + overall.get(0, 0)):0.3f} ({overall.get(1, 0) + overall.get(0, 0)} answers)"
            if overall
            else ""
        )
    else:
        overall_str = ""

    # check if question in bookmarks
    if session["nickname"] == "admin" or session["manager"]:
        with engine.connect() as conn:
            bookmarked = conn.execute(
                text("SELECT COUNT(*) FROM bookmarks WHERE question_id = :question_id"),
                {"question_id": question_id},
            ).scalar()
    else:
        bookmarked = 0

    if step:
        return_url = url_for("question", course=course, topic=topic, step=step, idx=idx)
    else:
        return_url = url_for("view_question_id", course=course, question_id=idx)

    return render_template(
        "feedback.html",
        course=course,
        question_id=question_id,
        feedback=response,
        user_answer=user_answer,
        config=config,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session.get("quiz", {})),
        lives=nlives,
        flag_recovered=flag_recovered,
        recover="recover" in session,
        overall_str=overall_str,
        popup=popup,
        popup_text=popup_text,
        bookmarked=bookmarked,
        translation=translation,
        return_url=return_url,
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/results/<course>/<mode>", methods=["GET"])
@course_exists
@check_login
@is_manager_or_admin
def results(course: str, mode: str = "mean"):
    """
    display results for all users
    """

    with engine.connect() as conn:
        topics = get_visible_topics(course)

        users = (
            conn.execute(
                text(
                    (
                        "SELECT * FROM users WHERE "
                        ":course = ANY(quizz) "
                        "AND email <> ALL(SELECT unnest(managers) FROM courses WHERE name = :course)"
                    )
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )
        scores: dict = {}
        scores_by_topic: dict = {}
        n_questions: dict = {}
        n_topics: dict = {}
        n_questions_by_topic = None

        for user in users:
            tot_score = 0

            user_topics = (
                conn.execute(
                    text(
                        "SELECT DISTINCT topic FROM results WHERE course = :course AND user_id = :user_id"
                    ),
                    {"course": course, "user_id": user["id"]},
                )
                .mappings()
                .all()
            )

            n_topics[user["email"]] = len(user_topics)

            if mode == "by_topic":
                n_questions_by_topic: dict = {}
                n_questions_topic = (
                    conn.execute(
                        text(
                            "SELECT user_id, topic, count(*) AS n_questions FROM results WHERE course = :course GROUP BY user_id, topic"
                        ),
                        {"course": course},
                    )
                    .mappings()
                    .all()
                )

                for row in n_questions_topic:
                    n_questions_by_topic[(row["user_id"], row["topic"])] = row[
                        "n_questions"
                    ]

            for row in user_topics:
                score = get_score(course, row["topic"], user_id=user["id"])

                logging.debug(
                    f"user name: {user['email']} topic: {row['topic']}  score: {score}"
                )

                if user["email"] not in scores_by_topic:
                    scores_by_topic[user["email"]] = {}

                if row["topic"] not in scores_by_topic[user["email"]]:
                    scores_by_topic[user["email"]][row["topic"]] = score

                tot_score += score

            if len(user_topics):
                scores[user["email"]] = round(tot_score / len(user_topics), 3)
            else:
                scores[user["email"]] = "-"

            n_questions[user["email"]] = conn.execute(
                text(
                    "SELECT count(*) FROM results WHERE course = :course AND user_id = :user_id"
                ),
                {"course": course, "user_id": user["id"]},
            ).scalar()

    print(f"{scores=}")
    print(f"{scores_by_topic=}")

    return render_template(
        "results.html" if mode == "mean" else "results_by_topic.html",
        course=course,
        topics=topics,
        scores=scores,
        scores_by_topic=scores_by_topic,
        n_questions=n_questions,
        n_questions_by_topic=n_questions_by_topic if mode == "by_topic" else None,
        n_topics=n_topics,
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/course_management/<course>", methods=["GET"]
)
@course_exists
@check_login
@is_manager_or_admin
def course_management(course: str):
    """
    course management page
    """

    config = get_course_config(course)

    with engine.connect() as conn:
        questions_number = conn.execute(
            text(
                "SELECT COUNT(*) FROM questions WHERE deleted IS NULL AND course = :course"
            ),
            {"course": course},
        ).scalar()

        # TODO: add number of users for current quiz
        users_number = conn.execute(
            text(
                "SELECT COUNT(*) FROM users WHERE :course = ANY(quizz) AND email <> ALL(SELECT unnest(managers) FROM courses WHERE name = :course) "
            ),
            {"course": course},
        ).scalar()

        topics = (
            conn.execute(
                text(
                    (
                        "SELECT topic, type, count(*) AS n_questions FROM questions "
                        "WHERE deleted IS NULL AND course = :course "
                        "GROUP BY topic, type "
                        "ORDER BY topic, type"
                    )
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        topics_list = (
            conn.execute(
                text(
                    "SELECT DISTINCT topic FROM questions WHERE deleted IS NULL AND course = :course"
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        n_questions_by_day = (
            conn.execute(
                text(
                    (
                        "SELECT to_char(timestamp, 'YYYY-MM-DD') AS day, count(*) AS n_questions, count(distinct user_id) AS n_users FROM results "
                        "WHERE course = :course AND user_id != 0 GROUP BY day ORDER BY day"
                    )
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        active_users_last_hour = conn.execute(
            text(
                (
                    "SELECT COUNT(distinct user_id)  FROM results "
                    "WHERE course = :course AND  user_id != 0 AND timestamp >= NOW() - INTERVAL '1 hour'"
                )
            ),
            {"course": course},
        ).scalar()

        active_users_last_day = conn.execute(
            text(
                (
                    "SELECT count(distinct user_id) FROM results "
                    "WHERE course = :course AND user_id != 0 AND timestamp >= NOW() - INTERVAL '1 day'"
                )
            ),
            {"course": course},
        ).scalar()

        active_users_last_week = conn.execute(
            text(
                "SELECT count(distinct user_id) FROM results "
                "WHERE course = :course AND user_id != 0 AND timestamp >= NOW() - INTERVAL '7 days'"
            ),
            {"course": course},
        ).scalar()

        active_users_last_month = conn.execute(
            text(
                "SELECT count(distinct user_id) FROM results "
                "WHERE course = :course AND user_id != 0 AND timestamp >= NOW() - INTERVAL '30 days'"
            ),
            {"course": course},
        ).scalar()

        by_hour = (
            conn.execute(
                text(
                    "SELECT "
                    '    EXTRACT(HOUR FROM "timestamp")::integer AS hour, '
                    "    COUNT(*) AS count_by_hour "
                    "FROM results WHERE course = :course "
                    "GROUP BY hour "
                    "ORDER BY hour "
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        # accuracy percentage by question type
        accuracy_percentage_by_question_type = (
            conn.execute(
                text(
                    "SELECT  "
                    "    question_type, "
                    "    ROUND(100.0 * SUM(CASE WHEN good_answer THEN 1 ELSE 0 END) / COUNT(*), 2) AS accuracy_percentage  "
                    "FROM results WHERE course = :course  "
                    "GROUP BY question_type "
                    "ORDER BY accuracy_percentage ASC; "
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        # accuracy percentage by topic
        accuracy_percentage_by_topic = (
            conn.execute(
                text(
                    "SELECT  "
                    "    topic, "
                    "    ROUND(100.0 * SUM(CASE WHEN good_answer THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_rate "
                    "FROM results WHERE course = :course  "
                    "GROUP BY topic "
                    "ORDER BY topic ASC; "
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        accuracy_percentage_by_topic = {
            item["topic"]: round(float(item["success_rate"]), 2)
            for item in accuracy_percentage_by_topic
        }

        # domande più sbagliate
        query = text("""
        SELECT
            q.topic,
            CASE
            WHEN q.type = 'shortanswer' THEN 'short'
            WHEN q.type = 'truefalse' THEN 'TF'
            WHEN q.type = 'multichoice' THEN 'multi'
            ELSE q.type
            END AS type,
            SUBSTRING(q.content::json ->> 'questiontext',1,100) AS question_text,
            COUNT(*) AS num_answers,
            ROUND(100.0 * SUM(CASE WHEN r.good_answer THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_rate
        FROM results r
        JOIN questions q ON r.question_name = q.name
        GROUP BY q.name, q.topic, q.type, q.content
        ORDER BY success_rate ASC
        LIMIT 100;
        """)

        # most wrong questions
        result = conn.execute(query)
        rows = result.fetchall()
        columns = result.keys()

        most_wrong_questions = tabulate(rows, headers=columns, tablefmt="psql")

    return render_template(
        "course_management.html",
        course_name=config["QUIZ_NAME"],
        questions_number=questions_number,
        course=course,
        topics=topics,
        users_number=users_number,
        topics_list=topics_list,
        active_users_last_hour=active_users_last_hour,
        active_users_last_day=active_users_last_day,
        active_users_last_week=active_users_last_week,
        active_users_last_month=active_users_last_month,
        days=Markup(str([x["day"] for x in n_questions_by_day])),
        n_questions_by_day=Markup(str([x["n_questions"] for x in n_questions_by_day])),
        n_users_by_day=Markup(str([x["n_users"] for x in n_questions_by_day])),
        return_url=url_for("course_management", course=course),
        hours=Markup(str([x["hour"] for x in by_hour])),
        count_by_hour=Markup(str([x["count_by_hour"] for x in by_hour])),
        accuracy_percentage_by_topic=accuracy_percentage_by_topic,
        most_wrong_questions=most_wrong_questions,
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/delete_image/<course>/<image_name>/<question_id>/<path:return_url>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def delete_image(course: str, image_name: str, question_id: int, return_url: str):
    """
    delete images and json (if any) from a question
    """
    if (Path("images") / Path(course) / Path(image_name).name).is_file():
        (Path("images") / Path(course) / Path(image_name).name).unlink()

        # check for json file (image areas) to delete
        if (
            Path("images")
            / Path(course)
            / Path(Path(image_name).name).with_suffix(Path(image_name).suffix + ".json")
        ).is_file():
            (
                Path("images")
                / Path(course)
                / Path(Path(image_name).name).with_suffix(
                    Path(image_name).suffix + ".json"
                )
            ).unlink()

        with engine.connect() as conn:
            question = (
                conn.execute(
                    text(
                        "SELECT * FROM questions WHERE course = :course AND id = :question_id"
                    ),
                    {"course": course, "question_id": question_id},
                )
                .mappings()
                .fetchone()
            )
            content = json.loads(question["content"])
            # delete all references to image in question
            while image_name in content["files"]:
                content["files"].remove(image_name)

            conn.execute(
                text("UPDATE questions SET content = :content WHERE id = :question_id"),
                {"content": json.dumps(content), "question_id": question_id},
            )

            conn.commit()

    return redirect(
        url_for(
            "edit_question",
            course=course,
            question_id=question_id,
            return_url=return_url,
        )
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/load_questions/<course>", methods=["GET", "POST"]
)
@course_exists
@check_login
@is_manager_or_admin
def load_questions(course: str):
    """
    load questions from file (XML or GIFT)
    """

    if request.method == "GET":
        return render_template("load_questions.html", course=course)

    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        # check file name
        if Path(file.filename).suffix not in (".xml", ".gift"):
            flash("The file name must end in .xml or .gift")
            return redirect(request.url)

        if file:
            file_path = Path(tempfile.gettempdir()) / Path(file.filename)
            file.save(file_path)

            # load questions in database
            if Path(file_path).suffix == ".gift":
                r, msg = load_questions_gift(
                    file_path, course, get_course_config(course)
                )
            else:
                r, msg = load_questions_xml(
                    file_path, course, get_course_config(course)
                )
            if r:
                flash(f"Error loading questions from {file.filename}: {msg}")
            else:
                flash(f"Questions loaded successfully from {file.filename}! {msg}")

            return redirect(url_for("course_management", course=course))


@app.route(
    f"{app.config['APPLICATION_ROOT']}/edit_parameters/<course>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def edit_parameters(course: str):
    """
    edit course parameters
    """
    if request.method == "GET":
        config = get_course_config(course)
        return render_template("new_course.html", course=course, config=config)


@app.route(f"{app.config['APPLICATION_ROOT']}/add_lives/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager_or_admin
def add_lives(course: str):
    with engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE lives SET number = number + 10 WHERE course = :course AND user_id = :user_id "
            ),
            {"course": course, "user_id": session["user_id"]},
        )
        conn.commit()

    flash(
        Markup('<div class="notification is-success">10 lives added to manager</div>'),
        "error",
    )

    return redirect(url_for("course_management", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/all_questions/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager_or_admin
def all_questions(course: str):
    """
    display all questions
    """

    with engine.connect() as conn:
        questions = (
            conn.execute(
                text(
                    "SELECT * FROM questions WHERE course = :course AND deleted IS NULL ORDER BY id"
                ),
                {"course": course},
            )
            .mappings()
            .fetchall()
        )

        content: dict = {}
        for row in questions:
            content[row["id"]] = json.loads(row["content"])

    return render_template(
        "all_questions.html",
        course=course,
        questions=questions,
        content=content,
        title="All questions",
        return_url=url_for("all_questions", course=course),
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/all_topic_questions/<course>/<path:topic>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def all_topic_questions(course: str, topic: str):
    """
    display all questions from topic
    """

    with engine.connect() as conn:
        questions = (
            conn.execute(
                text(
                    "SELECT * FROM questions WHERE course = :course AND topic = :topic AND deleted IS NULL ORDER BY id"
                ),
                {"course": course, "topic": topic},
            )
            .mappings()
            .fetchall()
        )

        content: dict = {}
        for row in questions:
            content[row["id"]] = json.loads(row["content"])

    return render_template(
        "all_questions.html",
        course=course,
        questions=questions,
        content=content,
        title=Markup(f"Questions for topic <b>{topic}</b>"),
        return_url=url_for("all_topic_questions", course=course, topic=topic),
        topic=topic,
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/deleted_questions/<course>", methods=["GET"]
)
@course_exists
@check_login
@is_manager_or_admin
def deleted_questions(course: str):
    """
    display deleted questions
    """

    with engine.connect() as conn:
        questions = (
            conn.execute(
                text(
                    "SELECT * FROM questions WHERE course = :course AND deleted IS NOT NULL ORDER BY id"
                ),
                {"course": course},
            )
            .mappings()
            .fetchall()
        )

        content: dict = {}
        for row in questions:
            content[row["id"]] = json.loads(row["content"])

    return render_template(
        "all_questions.html",
        course=course,
        questions=questions,
        content=content,
        title="Deleted questions",
        return_url=url_for("deleted_questions", course=course),
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/new_topic/<course>", methods=["GET", "POST"]
)
@course_exists
@check_login
@is_manager_or_admin
def new_topic(course: str):
    """
    new_topic
    """
    pass


@app.route(f"{app.config['APPLICATION_ROOT']}/all_images/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager_or_admin
def all_images(course: str):
    """
    display all images
    """
    with engine.connect() as conn:
        questions = (
            conn.execute(
                text(
                    "SELECT * FROM questions WHERE deleted IS NULL AND course = :course ORDER BY id"
                ),
                {"course": course},
            )
            .mappings()
            .fetchall()
        )

        content: dict = {}
        for row in questions:
            content[row["id"]] = json.loads(row["content"])
            image_list = []
            for image in content[row["id"]].get("files", []):
                if image.startswith("http"):
                    image_list.append(image)
                else:
                    image_list.append(
                        f"{app.config['APPLICATION_ROOT']}/images/{course}/{image}"
                    )
            content[row["id"]]["image_list"] = image_list
            # check if json file is present (areas definition) if one image
            image_area = (len(image_list) == 1) and (
                Path("images")
                / Path(course)
                / Path(Path(image_list[0]).name).with_suffix(
                    Path(image_list[0]).suffix + ".json"
                )
            ).is_file()

    return render_template(
        "all_images.html",
        course=course,
        questions=questions,
        content=content,
        return_url=url_for("all_images", course=course),
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/all_questions_gift/<course>", methods=["GET"]
)
@course_exists
@check_login
@is_manager_or_admin
def all_questions_gift(course: str):
    """
    display all questions in gift format
    """

    out: list = []
    with engine.connect() as conn:
        for row in (
            conn.execute(
                text(
                    "SELECT * FROM questions WHERE deleted IS NULL AND course = :course ORDER BY id"
                ),
                {"course": course},
            )
            .mappings()
            .fetchall()
        ):
            # out.append(f"::{row['id']}")
            # category / topic
            out.append(f"$CATEGORY: {row['topic']}")
            out.append("")
            out.append(f"::{row['name']}")

            content = json.loads(row["content"])
            if row["type"] == "truefalse":
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        ans = answer["text"][0].upper()
                        feed_good = answer["feedback"]
                    else:
                        feed_wrong = answer["feedback"]

                if feed_good and feed_wrong:
                    out.append(f"::{content['questiontext']}" + "{")
                    out.append(f"{ans}#{feed_wrong}#{feed_good}")
                    if content.get("generalfeedback", None):
                        out.append(f"####{content['generalfeedback']}")
                    out.append("}")
                else:
                    out.append(f"::{content['questiontext']}")
                    if content.get("generalfeedback", None):
                        out.append(f"{{{ans}}}####{content['generalfeedback']}")
                    else:
                        out.append(f"{{{ans}}}")

            if row["type"] == "multichoice":
                out.append(f"::{content['questiontext']} " + "{")
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        out.append(f"={answer['text']}#{answer['feedback']}")
                    else:
                        out.append(f"~{answer['text']}#{answer['feedback']}")

                if content.get("generalfeedback", None):
                    out.append(f"####{content['generalfeedback']}")
                out.append("}")

            if row["type"] == "shortanswer":
                out.append(f"::{content['questiontext']}" + "{")
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        out.append(f"=%100%{answer['text']}#{answer['feedback']}")
                    else:
                        out.append(
                            f"=%{answer['fraction']}%{answer['text']}#{answer['feedback']}"
                        )
                if content.get("generalfeedback", None):
                    out.append(f"####{content['generalfeedback']}")

                out.append("}")

            out.append("<hr>")

    return "<br>".join(out)


@app.route(
    f"{app.config['APPLICATION_ROOT']}/edit_question/<course>/<question_id>",
    methods=["GET", "POST"],
)
@app.route(
    f"{app.config['APPLICATION_ROOT']}/edit_question/<course>/<question_id>/<path:return_url>",
    methods=["GET", "POST"],
)
@course_exists
@check_login
@is_manager_or_admin
def edit_question(course: str, question_id: int, return_url: str = ""):
    """
    edit question
    """

    translation = get_translation("it")

    if request.method == "GET":
        # get topics
        with engine.connect() as conn:
            topics = [
                row["topic"]
                for row in conn.execute(
                    text(
                        "SELECT topic FROM questions WHERE course = :course GROUP BY topic ORDER BY topic"
                    ),
                    {"course": course},
                )
                .mappings()
                .all()
            ]

        if int(question_id) > 0:
            with engine.connect() as conn:
                question = (
                    conn.execute(
                        text(
                            "SELECT * FROM questions WHERE course = :course AND id = :question_id"
                        ),
                        {"course": course, "question_id": question_id},
                    )
                    .mappings()
                    .fetchone()
                )
            content = json.loads(question["content"])

            content["answers"] = [
                x | {"id": f"answer{idx + 1}"}
                for idx, x in enumerate(content["answers"])
            ]

            # check presence of images
            image_list: list = []
            for image in content.get("files", []):
                if image.startswith("http"):
                    image_list.append(image)
                else:
                    image_list.append(
                        f"{app.config['APPLICATION_ROOT']}/images/{course}/{image}"
                    )
            # check if json file is present (areas definition) if one image
            image_area = (len(image_list) == 1) and (
                Path("images")
                / Path(course)
                / Path(Path(image_list[0]).name).with_suffix(
                    Path(image_list[0]).suffix + ".json"
                )
            ).is_file()

            # referrer
            referrer = request.referrer
        else:  # new question
            question = {}
            content = {}
            image_area = False
            image_list = []
            referrer = url_for("course_management", course=course)

        return render_template(
            "edit_question.html",
            course=course,
            topics=topics,
            question_id=int(question_id),
            question=question,
            content=content,
            translation=translation,
            image_area=image_area,
            image_list=image_list,
            referrer=referrer,
            return_url=return_url,
        )

    if request.method == "POST":
        if int(question_id) > 0:  # edit question
            with engine.connect() as conn:
                question = (
                    conn.execute(
                        text(
                            "SELECT * FROM questions WHERE course = :course AND id = :question_id"
                        ),
                        {"course": course, "question_id": question_id},
                    )
                    .mappings()
                    .fetchone()
                )
            content = json.loads(question["content"])

            content["answers"] = [
                x | {"id": f"answer{idx + 1}"}
                for idx, x in enumerate(content["answers"])
            ]

            content["questiontext"] = request.form["questiontext"]
            answers: list = []
            for x in request.form:
                if x.startswith("answer"):
                    if not request.form[x]:
                        continue
                    answers.append(
                        {
                            "text": request.form[x],
                            "feedback": request.form[f"feedback_{x}"],
                            "fraction": request.form[f"score_{x}"],
                        }
                    )
            content["answers"] = answers

        elif int(question_id) == -1:  # true false
            content = {}
            content["questiontext"] = request.form["questiontext"]
            content["type"] = "truefalse"
            content["name"] = request.form["name"]

            match request.form["TF1"]:
                case "TRUE":
                    content["answers"] = [
                        {
                            "fraction": "100",
                            "text": "true",
                            "feedback": "",
                            "id": "answer1",
                        },
                        {
                            "fraction": "0",
                            "text": "false",
                            "feedback": "",
                            "id": "answer2",
                        },
                    ]
                case "FALSE":
                    content["answers"] = [
                        {
                            "fraction": "0",
                            "text": "true",
                            "feedback": "",
                            "id": "answer1",
                        },
                        {
                            "fraction": "100",
                            "text": "false",
                            "feedback": "",
                            "id": "answer2",
                        },
                    ]
        elif int(question_id) in (-2, -3):  # short answer
            content = {}
            content["questiontext"] = request.form["questiontext"]
            content["type"] = "shortanswer" if int(question_id) == -3 else "multichoice"
            content["name"] = request.form["name"]

            answers: list = []
            flag_good_answer = False
            for id in range(1, 6):
                if not request.form[f"answer_{id}"]:
                    continue
                if request.form[f"score_{id}"] == "100":
                    flag_good_answer = True

                # check if text already present
                for answer in answers:
                    if answer["text"] == request.form[f"answer_{id}"].strip():
                        flash(
                            Markup(
                                f'<div class="notification is-danger">An answer was found twice (<b>{request.form[f"answer_{id}"].strip()}</b>)</div>'
                            ),
                            "error",
                        )
                        return redirect(
                            url_for(
                                "edit_question",
                                course=course,
                                question_id=question_id,
                                return_url=return_url,
                            )
                        )

                answers.append(
                    {
                        "text": request.form[f"answer_{id}"].strip(),
                        "fraction": request.form[f"score_{id}"],
                        "feedback": request.form[f"feedback_{id}"].strip(),
                        "id": f"answer{id}",
                    }
                )

            if not answers:
                flash(
                    Markup(
                        '<div class="notification is-danger">No answers were given</div>'
                    ),
                    "error",
                )

                return redirect(
                    url_for(
                        "edit_question",
                        course=course,
                        question_id=question_id,
                        return_url=return_url,
                    )
                )

            if not flag_good_answer:
                flash(
                    Markup(
                        '<div class="notification is-danger">No correct answer (100) was given</div>'
                    ),
                    "error",
                )

                return redirect(
                    url_for(
                        "edit_question",
                        course=course,
                        question_id=question_id,
                        return_url=return_url,
                    )
                )

            content["answers"] = answers

        # check for files
        # image
        img_file = request.files["file"]
        if img_file:
            file_path = Path("images") / Path(course) / Path(img_file.filename)
            img_file.save(file_path)
            # add image
            if "files" not in content:
                content["files"] = []
            content["files"].append(img_file.filename)

            # json
            if "json_file" in request.files:
                json_file = request.files["json_file"]
                if json_file:
                    file_content = json_file.read()  # Reads the file content

                    try:
                        json_content = json.loads(file_content)
                        # area_names
                        area_names = [
                            feature["properties"]["name"].lower()
                            for feature in json_content["features"]
                        ]

                    except json.decoder.JSONDecodeError:
                        flash(
                            Markup(
                                '<div class="notification is-danger">The JSON file is not correct</div>'
                            ),
                            "error",
                        )
                        return redirect(
                            url_for(
                                "edit_question",
                                course=course,
                                question_id=question_id,
                                return_url=return_url,
                            )
                        )

                    # check if correct answer if present in areas
                    for answer in answers:
                        if answer["fraction"] != "100":
                            continue
                        if answer["text"].lower() in area_names:
                            break
                    else:
                        flash(
                            Markup(
                                f'<div class="notification is-danger">The correct answer is not in the image areas ({",".join(area_names)})</div>'
                            ),
                            "error",
                        )
                        return redirect(
                            url_for(
                                "edit_question",
                                course=course,
                                question_id=question_id,
                                return_url=return_url,
                            )
                        )

                    # save json file with image file name with .json
                    file_path = (
                        Path("images")
                        / Path(course)
                        / Path(img_file.filename).with_suffix(
                            Path(img_file.filename).suffix + ".json"
                        )
                    )
                    json_file.seek(0)
                    json_file.save(file_path)

        # save to db
        with engine.connect() as conn:
            if int(question_id) > 0:
                conn.execute(
                    text(
                        "UPDATE questions SET content = :content WHERE course = :course AND id = :id"
                    ),
                    {
                        "course": course,
                        "content": json.dumps(content),
                        "id": question_id,
                    },
                )

            else:
                conn.execute(
                    text(
                        "INSERT INTO questions (course, topic, type, name, content) VALUES (:course, :topic, :type, :name, :content)"
                    ),
                    {
                        "course": course,
                        "content": json.dumps(content),
                        "name": request.form["name"],
                        "topic": request.form["topic"],
                        "type": content["type"],
                    },
                )
            conn.commit()

        return redirect(f"/{return_url}")


@app.route(
    f"{app.config['APPLICATION_ROOT']}/delete_question/<course>/<question_id>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def delete_question(course: str, question_id: int):
    """
    set question as deleted
    """
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE questions SET deleted = NOW() WHERE id = :question_id "),
            {"question_id": question_id},
        )
        conn.commit()
    return redirect(request.referrer)


@app.route(
    f"{app.config['APPLICATION_ROOT']}/undelete_question/<course>/<question_id>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def undelete_question(course: str, question_id: int):
    """
    set question as not deleted
    """
    with engine.connect() as conn:
        conn.execute(
            text("UPDATE questions SET deleted = NULL WHERE id = :question_id "),
            {"question_id": question_id},
        )
        conn.commit()
    return redirect(request.referrer)


@app.route(
    f"{app.config['APPLICATION_ROOT']}/bookmarked_questions/<course>", methods=["GET"]
)
@course_exists
@check_login
@is_manager_or_admin
def bookmarked_questions(course: str):
    """
    display bookmarked questions
    """

    translation = get_translation("it")

    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT questions.id AS id, type, topic, name, content "
                "FROM bookmarks, questions "
                "WHERE bookmarks.question_id = questions.id "
                "AND nickname = :nickname "
                "AND questions.deleted IS NULL "
                "ORDER BY questions.id "
            ),
            {"nickname": session["nickname"]},
        )

        questions = result.mappings().all()

    q: list = []
    for question in questions:
        content = json.loads(question["content"])
        q.append(dict(question) | {"questiontext": content["questiontext"]})

    return render_template(
        "bookmarked_questions.html",
        course=course,
        translation=translation,
        questions=q,
        return_url=url_for("bookmarked_questions", course=course),
    )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/reset_bookmarked_questions/<course>",
    methods=["GET"],
)
@course_exists
@check_login
@is_manager_or_admin
def reset_bookmarked_questions(course: str):
    """
    reset_bookmarked_questions
    """

    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM bookmarks WHERE nickname = :nickname "),
            {"nickname": session["nickname"]},
        )
        conn.commit()

    return redirect(url_for("admin", course=course))


@app.route(
    f"{app.config['APPLICATION_ROOT']}/local_login/<course>", methods=["GET", "POST"]
)
@course_exists
def local_login(course: str):
    """
    manage login
    """

    config = get_course_config(course)
    translation = get_translation("it")

    if request.method == "GET":
        return render_template(
            "login.html",
            course_name=config["QUIZ_NAME"],
            course=course,
            lives=None,
            translation=translation,
        )

    if request.method == "POST":
        form_data = request.form
        # check if admin login (quizzych administrator)
        if form_data.get("nickname").strip() == "admin":
            if (
                hashlib.sha256(form_data.get("password").encode()).hexdigest()
                != app.config["ADMIN_PASSWORD_SHA256"]
            ):
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("local_login", course=course))
            session["nickname"] = "admin"
            session["user_id"] = 0
            return redirect(url_for("home", course=course))

        password_hash = hashlib.sha256(form_data.get("password").encode()).hexdigest()
        with engine.connect() as conn:
            cursor = conn.execute(
                text(
                    "SELECT id FROM users WHERE nickname = :nickname AND password_hash = :password_hash"
                ),
                {
                    "nickname": form_data.get("nickname"),
                    "password_hash": password_hash,
                },
            )
            row = cursor.mappings().fetchone()
            if row is not None:
                session["nickname"] = form_data.get("nickname")
                session["user_id"] = row["id"]
                # check if manager
                with engine.connect() as conn:
                    flag_manager = conn.execute(
                        text(
                            "SELECT COUNT(*) FROM courses WHERE name = :course AND :nickname = ANY(managers)"
                        ),
                        {"course": course, "nickname": session["nickname"]},
                    ).scalar()
                    session["manager"] = flag_manager != 0

                return redirect(url_for("home", course=course))
            else:
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("local_login", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/admin_login", methods=["GET", "POST"])
def admin_login():
    """
    manage admin login
    """

    translation = get_translation("it")

    if request.method == "GET":
        return render_template(
            "admin_login.html",
            translation=translation,
        )

    if request.method == "POST":
        form_data = request.form
        # check if admin login (quizzych administrator)
        if form_data.get("nickname").strip() == "admin":
            if (
                hashlib.sha256(form_data.get("password").encode()).hexdigest()
                != app.config["ADMIN_PASSWORD_SHA256"]
            ):
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("admin_login"))
            session["nickname"] = "admin"
            session["user_id"] = 0

            return redirect(url_for("main_home"))


@app.route(f"{app.config['APPLICATION_ROOT']}/admin_logout")
def admin_logout():
    """
    Logout admin
    """

    del session["nickname"]
    del session["user_id"]
    return redirect(url_for("main_home"))


@app.route(f"{app.config['APPLICATION_ROOT']}/new_course", methods=["GET", "POST"])
@check_login
def new_course():
    """
    create a new course or edit an existing one
    """

    if request.method == "GET":
        # check if admin
        if session.get("nickname", "") != "admin":
            flash(
                Markup(
                    '<div class="notification is-danger">You must be administrator to create a new quizz</div>'
                ),
                "",
            )
            return redirect(url_for("main_home"))

        return render_template("new_course.html", course="", config={})

    if request.method == "POST":
        if not request.form["course_name"]:
            return render_template("new_course.html")

        # check if course exists
        with engine.connect() as conn:
            # check if course exists
            n_courses = conn.execute(
                text("SELECT count(*) FROM courses WHERE name = :course"),
                {
                    "course": request.form["course_name"],
                },
            ).scalar()
        if n_courses == 0:
            # check if admin
            if session.get("nickname", "") != "admin":
                flash(
                    Markup(
                        '<div class="notification is-danger">You must be administrator to create a new quizz</div>'
                    ),
                    "",
                )
                return redirect(url_for("main_home"))

            create_database(request.form["course_name"])

        else:
            # check if admin or manager

            # check if admin
            flag_admin = session.get("nickname", "") == "admin"

            # check if manager
            config = get_course_config(request.form["course_name"])
            if config["login_mode"] == "google_auth":
                flag_manager = session.get("email", "") in config["managers"]
            else:
                flag_manager = session.get("nickname", "") in config["managers"]

            if not flag_admin and not flag_manager:
                flash(
                    Markup(
                        '<div class="notification is-danger">You must be administrator or manager to modify quizz</div>'
                    ),
                    "",
                )
                return redirect(url_for("main_home"))

        with engine.connect() as conn:
            conn.execute(
                text(
                    "UPDATE courses SET "
                    "managers = :managers,"
                    "question_types = :question_types,"
                    "initial_life_number = :initial_life_number,"
                    "topics_to_hide = :topics_to_hide,"
                    "topic_question_number = :topic_question_number,"
                    "steps = :steps,"
                    "step_quiz_number = :step_quiz_number,"
                    "recover_question_number = :recover_question_number,"
                    "recover_topics = :recover_topics,"
                    "brush_up_question_number = :brush_up_question_number,"
                    "brush_up_level_names = :brush_up_level_names,"
                    "brush_up_levels = :brush_up_levels "
                    "WHERE name = :course"
                ),
                {
                    "course": request.form["course_name"],
                    "managers": eval(request.form["managers"]),
                    "question_types": eval(request.form["question_types"]),
                    "initial_life_number": request.form["life_number"],
                    "topics_to_hide": eval(request.form["hidden_topics"])
                    if request.form["hidden_topics"]
                    else [],
                    "topic_question_number": request.form["topic_question_number"],
                    "steps": eval(request.form["steps"]),
                    "step_quiz_number": request.form["step_quiz_number"],
                    "recover_question_number": request.form["recover_question_number"],
                    "recover_topics": eval(request.form["recover_topics"])
                    if request.form["recover_topics"]
                    else [],
                    "brush_up_question_number": request.form[
                        "brush_up_question_number"
                    ],
                    "brush_up_level_names": eval(request.form["brush_up_level_names"]),
                    "brush_up_levels": eval(request.form["brush_up_levels"]),
                },
            )
            conn.commit()

        return redirect(
            url_for("course_management", course=request.form["course_name"])
        )


@app.route(
    f"{app.config['APPLICATION_ROOT']}/new_nickname/<course>", methods=["GET", "POST"]
)
@course_exists
def new_nickname(course: str):
    """
    create a nickname
    """
    config = get_course_config(course)
    translation = get_translation("it")

    if request.method == "GET":
        return render_template(
            "new_nickname.html", course=course, translation=translation
        )

    if request.method == "POST":
        form_data = request.form
        nickname = form_data.get("nickname").strip()
        password1 = form_data.get("password1")
        password2 = form_data.get("password2")

        if nickname == "admin":
            flash("This nickname is not allowed", "error")
            return render_template(
                "new_nickname.html", course=course, translation=translation
            )

        if not password1 or not password2:
            flash("A password is missing", "error")
            return render_template(
                "new_nickname.html", course=course, translation=translation
            )

        if password1 != password2:
            flash("Passwords are not the same", "error")
            return render_template(
                "new_nickname.html", course=course, translation=translation
            )

        password_hash = hashlib.sha256(password1.encode()).hexdigest()

        with engine.connect() as conn:
            n_users = conn.execute(
                text(
                    "SELECT COUNT(*) AS n_users FROM users WHERE nickname = :nickname"
                ),
                {"nickname": nickname},
            ).scalar()

            if n_users:
                flash("Nickname already taken", "error")
                return render_template(
                    "new_nickname.html", course=course, translation=translation
                )

            try:
                new_id = conn.execute(
                    text(
                        "INSERT INTO users (nickname, password_hash) VALUES (:nickname, :password_hash) RETURNING id"
                    ),
                    {"nickname": nickname, "password_hash": password_hash},
                ).scalar_one()
                conn.execute(
                    text(
                        "INSERT INTO lives (course, user_id, number) VALUES (:course, :user_id, :number)"
                    ),
                    {
                        "course": course,
                        "user_id": new_id,
                        "number": config["INITIAL_LIFE_NUMBER"],
                    },
                )
                conn.commit()

                flash(
                    Markup(
                        f'<div class="notification is-success">New nickname created with {config["INITIAL_LIFE_NUMBER"]} lives</div>'
                    ),
                    "",
                )
                return redirect(url_for("home", course=course))

            except Exception:
                raise
                flash(
                    Markup(
                        '<div class="notification is-danger">Error creating the new nickname</div>'
                    ),
                    "error",
                )

                return redirect(url_for("home", course=course))


@app.route(
    f"{app.config['APPLICATION_ROOT']}/<course>/delete_nickname",
    methods=["GET"],
)
@course_exists
@check_login
def delete_nickname(course: str):
    """
    delete nickname and all correlated data
    """
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM results WHERE user_id = :user_id"),
            {"user_id": session["user_id"]},
        )
        conn.execute(
            text("DELETE FROM lives WHERE user_id = :user_id"),
            {"user_id": session["user_id"]},
        )
        conn.execute(
            text("DELETE FROM steps WHERE user_id = :user_id"),
            {"user_id": session["user_id"]},
        )
        conn.execute(
            text("DELETE FROM bookmarks WHERE nickname = :nickname"),
            {"nickname": session["nickname"]},
        )
        conn.execute(
            text("DELETE FROM users WHERE id = :user_id"),
            {"user_id": session["user_id"]},
        )
        conn.commit()

    del session["nickname"]
    del session["user_id"]
    return redirect(url_for("home", course=course))


@app.route(
    f"{app.config['APPLICATION_ROOT']}/<course>/delete_data",
    methods=["GET"],
)
@course_exists
@check_login
def delete_data(course: str):
    """
    delete data for user_id
    """
    config = get_course_config(course)

    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM results WHERE course = :course AND user_id = :user_id"),
            {"user_id": session["user_id"], "course": course},
        )
        conn.execute(
            text("DELETE FROM lives WHERE course = :course AND  user_id = :user_id"),
            {"user_id": session["user_id"], "course": course},
        )
        conn.execute(
            text("DELETE FROM steps WHERE course = :course AND  user_id = :user_id"),
            {"user_id": session["user_id"], "course": course},
        )
        conn.execute(
            text(
                "DELETE FROM bookmarks WHERE course = :course AND  nickname = :nickname"
            ),
            {"nickname": session["nickname"], "course": course},
        )
        # insert lives
        conn.execute(
            text(
                "INSERT INTO lives (course, user_id, number) VALUES (:course, :user_id, :number)"
            ),
            {
                "course": course,
                "user_id": session["user_id"],
                "number": config["INITIAL_LIFE_NUMBER"],
            },
        )

        conn.commit()

    return redirect(url_for("home", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/version")
def version():
    return f"v. {__version__}<br>date: {__version_date__}"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
