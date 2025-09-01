"""
Quizzych

"""

from pathlib import Path
import hashlib

# import sqlite3
import pandas as pd
import tomllib
import random
import re
import json
import sys
import unicodedata
import numpy as np
from rapidfuzz import fuzz
from markupsafe import Markup
from flask import (
    Flask,
    render_template,
    session,
    redirect,
    request,
    flash,
    url_for,
    send_from_directory,
    jsonify,
)
from functools import wraps
import logging
from sqlalchemy import create_engine, text

import moodle_xml
import quiz

COURSES_DIR = "courses"

logging.basicConfig(
    format="%(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

# engine = create_engine("sqlite:///")
DATABASE_URL = "postgresql://quizzych_user@localhost:5432/quizzych"
engine = create_engine(DATABASE_URL)


def get_course_config(course: str):
    # check config file
    if (Path(COURSES_DIR) / Path(course).with_suffix(".txt")).is_file():
        with open(Path(COURSES_DIR) / Path(course).with_suffix(".txt"), "rb") as f:
            config = tomllib.load(f)
    else:
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
        question_data = moodle_xml.moodle_xml_to_dict_with_images(xml_file, config["QUESTION_TYPES"], f"images/{course_name}")

        # load questions in database
        """
        conn = sqlite3.connect(xml_file.with_suffix(".sqlite"))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM questions")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'questions'")
        conn.commit()

        for topic in question_data:
            for question in question_data[topic]:
                cursor.execute(
                    "INSERT INTO questions (topic, type, name, content) VALUES (?, ?, ?, ?)",
                    (
                        topic,
                        question["type"],
                        question["name"],
                        json.dumps(question),
                    ),
                )
        conn.commit()
        conn.close()

        """

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM questions WHERE course = :course_name"), {"course_name": course})

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

        # re-organize the questions structure
        """
        question_data: dict = {}
        for topic in question_data1:
            question_data[topic] = {}
            for question_type in question_data1[topic]:
                for question in question_data1[topic][question_type]:
                    if question["type"] not in question_data[topic]:
                        question_data[topic][question["type"]] = {}

                    question_data[topic][question["type"]][question["name"]] = question
        """
        # load questions in database
        """
        conn = sqlite3.connect(gift_file_path.with_suffix(".sqlite"))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM questions")
        """

        with engine.connect() as conn:
            conn.execute(text("DELETE FROM questions WHERE course = :course_name"), {"course": course})

            for topic in question_data:
                for type_ in question_data[topic]:
                    for question_name in question_data[topic][type_]:
                        conn.execute(
                            text(
                                "INSERT INTO questions (course, topic, type, name, content) VALUES (:course_name, :topic, :type, :name, :content)"
                            ),
                            {
                                "course": course,
                                "topic": topic,
                                "type": type_,
                                "name": question_name,
                                "content": json.dumps(question_data[topic][type_][question_name]),
                            },
                        )
            conn.commit()

    except Exception:
        raise
        return 1
    return 0


app = Flask(__name__)
app.config.from_object("config")
app.config["DEBUG"] = True
app.secret_key = "votre_clé_secrète_sécurisée_ici"


def create_database(course) -> None:
    """
    create a new course in database
    """

    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO courses (name, question_types, initial_life_number, topics_to_hide, topic_question_number, steps, step_quiz_number, recover_question_number, recover_topics, brush_up_question_number, brush_up_level_names, brush_up_levels) VALUES ("
                ":course_name,"
                """'{"truefalse","multichoice", "shortanswer", "numerical"}',"""
                "5,"
                """'{"Ripasso e recupero vite"}',"""
                "10,"
                """'{"Esploratore", "Ricercatore", "Maestro"}',"""
                "4,"
                "5,"
                """'{"Ripasso e recupero vite"}',"""
                "10,"
                """'{"Easy", "Hard", "Very hard"}',"""
                "'{1, 2, 4}'"
                ")"
            ),
            {"course_name": course},
        )

        conn.commit()


"""
# load courses from XML files in database
for xml_file in Path(COURSES_DIR).glob("*.xml"):
    # check if database sqlite file exists
    if not xml_file.with_suffix(".sqlite").exists():
        logging.info(f"Database file {xml_file.with_suffix('.sqlite')} not found")
        logging.info("Creating a new one")
        create_database(xml_file.stem)

    # populate database with questions
    r, msg = load_questions_xml(xml_file, get_course_config(xml_file))
    if r:
        logging.critical(f"Error loading the question XML file {xml_file}: {msg}")
        sys.exit()
"""

# load courses from GIFT file in database
"""
for gift_file in Path(COURSES_DIR).glob("*.gift"):
    # check if database sqlite file exists
    if not gift_file.with_suffix(".sqlite").exists():
        logging.info(f"Database file {gift_file.with_suffix('.sqlite')} not found")
        logging.info("Creating a new one")
        create_database(gift_file.stem)

    # populate database with questions
    if load_questions_gift(gift_file, get_course_config(gift_file)):
        logging.critical(f"Error loading the questions GIFT file {gift_file}")
        sys.exit()
"""


def check_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "nickname" not in session:
            flash("You must be logged", "error")
            return redirect(url_for("home"), course=kwargs["course"])
        else:
            # check if nickname exists
            with engine.connect() as conn:
                if (
                    conn.execute(
                        text("SELECT * FROM users WHERE nickname = :nickname"),
                        {"nickname": session["nickname"]},
                    ).fetchone()
                    is None
                ):
                    return redirect(url_for("logout", course=kwargs["course"]))
        return f(*args, **kwargs)

    return decorated_function


def course_exists(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        with engine.connect() as conn:
            if (
                conn.execute(text("SELECT name FROM courses WHERE course = :course"), {"course": kwargs["course"]}).mappings().fetchone()
                is None
            ):
                return "The course does not exists"
        return f(*args, **kwargs)

    return decorated_function


def is_manager(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # check if admin
        if session["nickname"] not in ("admin", "manager"):
            flash(
                Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
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


def get_lives_number(course: str, nickname: str) -> int | None:
    """
    get number of lives for nickname
    """
    with engine.connect() as conn:
        lives = (
            conn.execute(
                text("SELECT number FROM lives WHERE nickname = :nickname AND course = :course"),
                {"course": course, "nickname": nickname},
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
            courses = conn.execute(text("SELECT name FROM courses ORDER BY name")).mappings().all()
        courses_list = [row["name"] for row in courses]
    else:
        courses_list = None
    return render_template(
        "main_home.html",
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

    lives = None
    if session.get("nickname", "") not in ("", "admin", "manager"):
        lives = get_lives_number(course, session["nickname"])
        # check if nickname in course
        with engine.connect() as conn:
            if (
                conn.execute(
                    text("SELECT * FROM users WHERE nickname = :nickname"),
                    {"nickname": session["nickname"]},
                ).fetchone()
                is None
            ):
                return redirect(url_for("logout", course=course))

    # check if brush-up available
    brushup_availability: bool = False

    if session.get("nickname", "") not in ("", "admin"):
        questions_df = get_questions_dataframe(course, session["nickname"])
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
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])

    topics = get_visible_topics(course)

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
        lives=get_lives_number(course, session["nickname"]),
    )


def get_visible_topics(course):
    """
    returns list of topic the are not in TOPICS_TO_HIDE list
    """
    config = get_course_config(course)

    with engine.connect() as conn:
        topics: list = [
            row["topic"]
            for row in conn.execute(text("SELECT DISTINCT topic FROM questions WHERE course = :course"), {"course": course})
            .mappings()
            .fetchall()
            if row["topic"] not in config["TOPICS_TO_HIDE"]
        ]
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
                text("SELECT nickname FROM users WHERE nickname NOT IN ('admin', 'manager') AND nickname != :nickname"),
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
    with engine.connect() as conn:
        # Execute the query
        query = text(
            """
                SELECT
                    q.id AS question_id,
                    q.topic AS topic,
                    q.type AS type,
                    q.name AS question_name,
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r
                    ON q.course = r.course
                        AND q.topic=r.topic
                        AND q.type=r.question_type
                        AND q.name=r.question_name
                        AND nickname = :nickname
                WHERE course = :course
                GROUP BY
                    q.topic,
                    q.type,
                    q.name
                """
        )

        result = conn.execute(query, {"course": course, "nickname": session["nickname"]})
        columns = result.keys()
        rows = result.mappings().fetchall()
        # Fetch all rows
        # rows = cursor.mappings().fetchall()
        # Get column names from the cursor description

        # columns = [description[0] for description in cursor.description]
        # create dataframe
        questions_df = pd.DataFrame(rows, columns=columns)

        # get number of questions in recover topic
        if config["RECOVER_TOPICS"]:
            """
            placeholders = ", ".join(
                ["?"] * len(config["RECOVER_TOPICS"])
            )  # Creates a placeholder string like "?, ?, ?"
            """

            rec_topics = '"' + '","'.join(config["RECOVER_TOPICS"]) + '"'

            n_recover_questions = (
                conn.execute(
                    text(f"SELECT COUNT(*) AS n_questions FROM questions WHERE topic IN ({rec_topics})"),
                )
                .mappings()
                .fetchone()["n_questions"]
            )
            session["quiz"] = quiz.get_quiz_recover(questions_df, config["RECOVER_TOPICS"], n_recover_questions)

        else:  # no recover topic
            # count all questions
            n_recover_questions = conn.execute(text("SELECT COUNT(*) AS n_questions FROM questions")).mappings().fetchone()["n_questions"]
            topics: list = [
                row["topic"]
                for row in conn.execute(text("SELECT DISTINCT topic FROM questions")).mappings().fetchall()
                if row["topic"] not in config["TOPICS_TO_HIDE"]
            ]
            session["quiz"] = quiz.get_quiz_recover(questions_df, topics, n_recover_questions)

    session["quiz_position"] = 0
    session["recover"] = 0  # count number of good answer

    return redirect(url_for("question", course=course, topic=translation["Recover lives"], step=1, idx=0))


@app.route(f"{app.config['APPLICATION_ROOT']}/all_topic_quiz/<course>/<topic>", methods=["GET"])
@course_exists
@check_login
@is_manager
def all_topic_quiz(course: str, topic: str):
    """
    create a quiz with all questions of a topic
    """
    with engine.connect() as conn:
        query = text("SELECT id from questions WHERE course = :course AND topic = :topic")
        rows = conn.execute(query, {"course": course, "topic": topic}).mappings().fetchall()

    session["quiz"] = [row["id"] for row in rows]
    session["quiz_position"] = 0
    session["check"] = 1

    return redirect(url_for("question", course=course, topic=topic, step=1, idx=0))


def get_questions_dataframe(course: str, nickname: str) -> pd.DataFrame:
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
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r
                    ON q.course = r.course
                        AND q.topic=r.topic
                        AND q.type=r.question_type
                        AND q.name=r.question_name
                        AND nickname = :nickname
                WHERE course = :course
                GROUP BY
                    q.topic,
                    q.type,
                    q.name
                """)

        result = conn.execute(query, {"course": course, "nickname": nickname})
        columns = result.keys()
        rows = result.mappings().fetchall()

        # columns = [description[0] for description in cursor.description]
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
    if "nickname" in session:
        questions_df = get_questions_dataframe(course, session["nickname"])
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


@app.route(f"{app.config['APPLICATION_ROOT']}/brush_up/<course>/<int:level>", methods=["GET"])
@course_exists
@check_login
def brush_up(course: str, level: int):
    """
    display brush-up
    """

    config = get_course_config(course)
    translation = get_translation("it")

    questions_df = get_questions_dataframe(course, session["nickname"])

    session["quiz"] = quiz.get_quiz_brushup(questions_df, config["RECOVER_TOPICS"], config["N_QUESTIONS_BY_BRUSH_UP"], level)

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

    return redirect(url_for("question", course=course, topic=translation["Brush-up"], step=1, idx=0))


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
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])

    steps_active = {x: 0 for x in range(1, config["N_STEPS"] + 1)}
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text("SELECT step_index, number FROM steps WHERE course = :course AND nickname = :nickname AND topic = :topic "),
                {"course": course, "nickname": session["nickname"], "topic": topic},
            )
            .mappings()
            .fetchall()
        )
        if rows is not None:
            for row in rows:
                steps_active[row["step_index"]] = row["number"]

        print(steps_active)

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
        # Execute the query
        query = text("""
                SELECT
                    q.id AS question_id,
                    q.topic AS topic,
                    q.type AS type,
                    q.name AS question_name,
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r
                    ON q.course = r.course
                        AND q.topic=r.topic
                        AND q.type=r.question_type
                        AND q.name=r.question_name
                        AND nickname = :nickname
                WHERE course = :course
                GROUP BY
                    q.topic,
                    q.type,
                    q.name
                """)

        result = conn.execute(query, {"course": course, "nickname": session["nickname"]})
        columns = result.keys()
        rows = result.mappings().fetchall()

        # Fetch all rows
        # Get column names from the cursor description
        # columns = [description[0] for description in cursor.description]
        # create dataframe
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
        get_lives_number(course, session["nickname"]),
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

    config = get_course_config(course)

    with engine.connect() as conn:
        # Execute the query
        query = text("""
                SELECT
                    q.id AS question_id,
                    q.topic AS topic,
                    q.type AS type,
                    q.name AS question_name,
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r
                    ON q.course = r.course
                        AND q.topic=r.topic
                        AND q.type=r.question_type
                        AND q.name=r.question_name
                        AND nickname = :nickname
                GROUP BY
                    q.topic,
                    q.type,
                    q.name
                """)

        result = conn.execute(query, {"course": course, "nickname": session["nickname"]})
        columns = result.keys()

        # Fetch all rows
        rows = result.mappings().fetchall()
        # create dataframe
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
        get_lives_number(course, session["nickname"]),
    )
    session["quiz_position"] = 0
    return redirect(url_for("question", course=course, topic=topic, step=step, idx=0))


def get_score(course: str, topic: str, nickname: str = "") -> float:
    """
    get score of nickname user for topic
    if nickname is empty get score of current user
    """

    """
        SELECT (SUM(percentage_ok) / (SELECT COUNT(*) FROM questions WHERE topic = :topic)) AS score
    FROM      (
    SELECT
        CAST(SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS FLOAT) / NULLIF((SELECT COUNT(*) 
             FROM results WHERE question_name = r.question_name AND nickname = :nickname), 0) AS percentage_ok
    FROM
        results r

    WHERE topic = :topic AND nickname = :nickname

    GROUP BY question_name
    ) AS subquery;
    """

    with engine.connect() as conn:
        query = text("""
SELECT
    SUM(percentage_ok) / COUNT(DISTINCT q.name) AS score
FROM (
    SELECT
        q.name AS question_name,
        CAST(SUM(CASE WHEN r.good_answer = 1 THEN 1 ELSE 0 END) AS FLOAT) /
        NULLIF(COUNT(r.good_answer), 0) AS percentage_ok
    FROM questions q
    LEFT JOIN results r
        ON q.course = r.course
        AND q.name = r.question_name
        AND r.nickname = :nickname
    WHERE q.course = r.course AND q.topic = :topic
    GROUP BY q.name
) AS subquery
""")
        cursor = conn.execute(
            query,
            {
                "course": course,
                "topic": topic,
                "nickname": session["nickname"] if nickname == "" else nickname,
            },
        )

        score = cursor.fetchone()[0]
        if score is not None:
            return round(score, 3)
        else:
            return 0


@app.route(
    f"{app.config['APPLICATION_ROOT']}/toggle-checkbox/<course>/<int:question_id>",
    methods=["POST"],
)
def toggle_checkbox(course: str, question_id: int):
    if request.is_json:
        is_checked = request.json.get("checked")
        with engine.connect() as conn:
            if is_checked:
                conn.execute(
                    text("INSERT INTO bookmarks (course, question_id) VALUES (:course, :question_id)"),
                    {"course": course, "question_is": question_id},
                )
            else:
                conn.execute(
                    text("DELETE FROM bookmarks WHERE course= :course AND question_id = :question_id"),
                    {"course": course, "question_is": question_id},
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
            text("DELETE FROM bookmarks WHERE course = :course AND question_id = :question_id"),
            {"course": course, "question_is": question_id},
        )
    conn.commit()

    return redirect(url_for("saved_questions", course=course))


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
                            "SELECT number FROM steps WHERE course = :course AND nickname = :nickname AND topic = :topic and step_index < :step"
                        )
                    ),
                    {"course": course, "nickname": session["nickname"], "topic": topic, "step": step},
                )
                .mappings()
                .fetchall()
            )
            if rows is not None:
                for row in rows:
                    if row["number"] < config["N_QUIZ_BY_STEP"]:
                        flash(
                            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
                            "",
                        )
                        return redirect(url_for("home", course=course))

        # check quiz_position
        if session["nickname"] not in ("admin", "manager") and idx != session["quiz_position"]:
            flash(
                Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
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
                    text("SELECT content FROM questions WHERE course= :course AND id = :question_id"),
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
            with engine as conn:
                result = conn.execute(
                    text(
                        "SELECT number FROM steps WHERE course= :course AND nickname = :nickname AND topic = :topic AND step_index = :step_index"
                    ),
                    {
                        "course": course,
                        "nickname": session["nickname"],
                        "topic": topic,
                        "step_index": step,
                    },
                )

                row = result.mappings().fetchone()  # restituisce un dict-like MappingRow o None

                if row is None:
                    conn.execute(
                        text("""
                            INSERT INTO steps (course, nickname, topic, step_index, number)
                            VALUES (:course, :nickname, :topic, :step_index, :number)
                        """),
                        {
                            "course": course,
                            "nickname": session["nickname"],
                            "topic": topic,
                            "step_index": step,
                            "number": 1,
                        },
                    )

                    conn.commit()

                else:
                    conn.execute(
                        text("""
            UPDATE steps
            SET number = number + 1
            WHERE course = :course AND nickname = :nickname AND topic = :topic AND step_index = :step_index
        """),
                        {
                            "course": course,
                            "nickname": session["nickname"],
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

    image_list: list = []
    for image in question.get("files", []):
        if image.startswith("http"):
            image_list.append(image)
        else:
            image_list.append(f"{app.config['APPLICATION_ROOT']}/images/{course}/{image}")

    if question["type"] == "multichoice" or question["type"] == "truefalse":
        answers = random.sample(question["answers"], len(question["answers"]))
        placeholder = translation["Input a text"]
        type_ = "text"
    elif question["type"] in ("shortanswer", "numerical"):
        answers = ""
        type_ = "number" if question["type"] == "numerical" else "text"
        placeholder = translation["Input a number"] if question["type"] == "numerical" else translation["Input a text"]

    if question["questiontext"].count("*") == 2:
        question["questiontext"] = question["questiontext"].replace("*", "<i>", 1)
        question["questiontext"] = question["questiontext"].replace("*", "</i>", 1)
        question["questiontext"] = Markup(question["questiontext"])

    return render_template(
        "question.html",
        course_name=config["QUIZ_NAME"],
        config=config,
        question=question,
        question_id=question_id,
        image_list=image_list,
        answers=answers,
        type_=type_,
        placeholder=placeholder,
        course=course,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session["quiz"]) if "recover" not in session else config["N_QUESTIONS_FOR_RECOVER"],
        lives=get_lives_number(course, session["nickname"] if "nickname" in session else ""),
        recover="recover" in session,
        translation=translation,
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


def calculate_similarity_score(student_answer, correct_answer, response_thresholds, response_phrases):
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
            if answer_feedback.count("*") == 2:
                answer_feedback = answer_feedback.replace("*", "<i>", 1)
                answer_feedback = answer_feedback.replace("*", "</i>", 1)

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
            if answer_feedback.count("*") == 2:
                answer_feedback = answer_feedback.replace("*", "<i>", 1)
                answer_feedback = answer_feedback.replace("*", "</i>", 1)
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

    question_id = session["quiz"][idx]
    # get question content
    with engine.connect() as conn:
        question = json.loads(
            conn.execute(
                text("SELECT content FROM questions WHERE course = :course AND id = :id"),
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
        user_answer = request.form.get("user_answer")

    logging.debug(f"{user_answer=}")

    correct_answers: list = []

    response = {"questiontext": question["questiontext"]}

    if response["questiontext"].count("*") == 2:
        response["questiontext"] = response["questiontext"].replace("*", "<i>", 1)
        response["questiontext"] = response["questiontext"].replace("*", "</i>", 1)
        response["questiontext"] = Markup(response["questiontext"])

    # iterate over correct answers
    answers: dict = {}
    negative_feedback: str = ""
    for answer in question["answers"]:
        if answer["fraction"] == "100":
            correct_answers.append(answer["text"])

            match, score, reply = calculate_similarity_score(user_answer, answer["text"], [], [])
            answers[score] = {
                "correct_answer": answer["fraction"] == "100",
                "match": match,
                "feedback": answer["feedback"] if answer["feedback"] is not None else "",
                "reply": reply,
            }
        else:
            negative_feedback = answer["feedback"] if answer["feedback"] is not None else ""

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
                negative_feedback = f'<br>La risposta giustà è "{correct_answers[0]}"'

            # response["result"] = Markup(format_correct_answer(f"{sorted(answers)[-1]}<br>" + response["reply"] + " " + negative_feedback))
            response["result"] = Markup(format_correct_answer(response["reply"] + " " + negative_feedback))
        elif sorted(answers)[-1] < 100:
            # positive_feedback = response["feedback"]
            response["result"] = Markup(format_correct_answer(response["reply"] + " " + response["feedback"]))
        else:
            positive_feedback = response["feedback"].replace("Esatto!", "")
            positive_feedback = positive_feedback.replace("Esatto", "")
            positive_feedback = positive_feedback.replace("Corretto!", "")
            response["result"] = Markup(format_correct_answer(response["reply"] + " " + positive_feedback))

        response["correct"] = True
        if "recover" in session:
            # add one good answer
            session["recover"] += 1
    else:
        # iterate over wrong answers
        answers = {}
        for answer in question["answers"]:
            if answer["fraction"] != "100":
                match, score, reply = calculate_similarity_score(user_answer, answer["text"], [], [])
                answers[score] = {
                    "correct_answer": False,
                    "match": match,
                    "feedback": answer["feedback"] if answer["feedback"] is not None else "",
                }

        logging.debug(f"wrong {answers=}")

        if not answers:
            response["result"] = Markup(format_wrong_answer("", correct_answers))
            response["correct"] = False

            # remove a life if not recover
            if "recover" not in session:
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE lives SET number = number - 1 WHERE course = :course AND number > 0 AND nickname = :nickname "),
                        {"course": course, "nickname": session["nickname"]},
                    )
                    conn.commit()

        else:
            if answers[sorted(answers)[-1]]["match"]:  # user gave wrong answer
                response = response | answers[sorted(answers)[-1]]

                logging.debug(f"{correct_answers=}")

                response["result"] = Markup(format_wrong_answer(response["feedback"], correct_answers))
                response["correct"] = False

                # remove a life if not recover
                if "recover" not in session:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE lives SET number = number - 1 WHERE course = :course AND number > 0 AND nickname = :nickname "),
                            {"course": course, "nickname": session["nickname"]},
                        )
                        conn.commit()
            else:
                response["result"] = Markup(format_wrong_answer("", correct_answers))
                response["correct"] = False

    logging.debug(f"{response=}")

    # translate user answer if true or false
    if user_answer in ("true", "false"):
        user_answer = translation[user_answer.upper()]

    # check if recover is ended
    flag_recovered = False
    if "recover" in session and session["recover"] >= config["N_QUESTIONS_FOR_RECOVER"]:
        flag_recovered = True

        # add a new life
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"UPDATE lives SET number = number + 1 WHERE course = :course AND nickname = :nickname and number < {config['INITIAL_LIFE_NUMBER']}"
                ),
                {"course": course, "nickname": session["nickname"]},
            )
            conn.commit()

    # save result
    if "recover" not in session:
        with engine.connect() as conn:
            """conn.execute(
                text(
                    "INSERT INTO results (course, nickname, topic, question_type, question_name, good_answer) VALUES (?, ?, ?, ?, ?)"
                ),
                (
                    session["nickname"],
                    topic,
                    question["type"],
                    question["name"],
                    response["correct"],
                ),
            )"""

            conn.execute(
                text("""
        INSERT INTO results (course,nickname, topic, question_type, question_name, good_answer)
        VALUES (:course, :nickname, :topic, :question_type, :question_name, :good_answer)
    """),
                {
                    "course": course,
                    "nickname": session["nickname"],
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

    nlives = get_lives_number(course, session["nickname"] if "nickname" in session else "")

    if nlives == 0 and "recover" not in session:
        popup_text = Markup(f"{translation["You've lost all your lives..."]}")

    session["quiz_position"] += 1

    # get overall score (for admin)
    if session["nickname"] in ("admin", "manager"):
        with engine.connect() as conn:
            overall = {}

            for row in (
                conn.execute(
                    text("""
                    SELECT good_answer, count(*) AS n
                    FROM results
                    WHERE course = :course
                    AND topic = :topic
                    AND question_name = :question_name
                    AND nickname != 'admin'
                    GROUP BY good_answer
                """),
                    {"course": course, "topic": topic, "question_name": question["name"]},
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
        total=len(session["quiz"]),
        lives=nlives,
        flag_recovered=flag_recovered,
        recover="recover" in session,
        overall_str=overall_str,
        popup=popup,
        popup_text=popup_text,
        translation=translation,
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/results/<course>/<mode>", methods=["GET"])
@course_exists
@check_login
@is_manager
def results(course: str, mode: str = "mean"):
    """
    display results for all users
    """

    with engine.connect() as conn:
        topics = get_visible_topics(course)

        users = (
            conn.execute(text("SELECT * FROM users WHERE nickname NOT IN ('admin', 'manager') ORDER BY LOWER(nickname)")).mappings().all()
        )
        scores: dict = {}
        scores_by_topic: dict = {}
        n_questions: dict = {}
        n_topics: dict = {}

        for user in users:
            tot_score = 0

            user_topics = (
                conn.execute(
                    "SELECT DISTINCT topic FROM results WHERE course = :course AND nickname = :nickname",
                    {"course": course, "nickname": user["nickname"]},
                )
                .mappings()
                .all()
            )

            n_topics[user["nickname"]] = len(user_topics)

            if mode == "by_topic":
                n_questions_topic = (
                    conn.execute(
                        text(
                            "SELECT nickname, topic, count(*) AS n_questions FROM results WHERE course = :course GROUP BY nickname, topic"
                        ),
                        {"course": course},
                    )
                    .mappings()
                    .all()
                )
                n_questions_by_topic = {}
                for row in n_questions_topic:
                    n_questions_by_topic[(row["nickname"], row["topic"])] = row["n_questions"]

            for row in user_topics:
                score = get_score(course, row["topic"], nickname=user["nickname"])

                logging.debug(f"user name: {user['nickname']} topic: {row['topic']}  score: {score}")

                if user["nickname"] not in scores_by_topic:
                    scores_by_topic[user["nickname"]] = {}

                if row["topic"] not in scores_by_topic[user["nickname"]]:
                    scores_by_topic[user["nickname"]][row["topic"]] = score

                tot_score += score

            if len(user_topics):
                scores[user["nickname"]] = round(tot_score / len(user_topics), 3)
            else:
                scores[user["nickname"]] = "-"

            n_questions[user["nickname"]] = (
                conn.execute(
                    text("SELECT count(*) AS n_questions FROM results WHERE course = :course AND nickname = :nickname"),
                    {"course": course, "nickname": user["nickname"]},
                )
                .mappings()
                .fetchone()["n_questions"]
            )

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


@app.route(f"{app.config['APPLICATION_ROOT']}/course_management/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager
def course_management(course: str):
    """
    course management page
    """

    config = get_course_config(course)

    with engine.connect() as conn:
        questions_number = (
            conn.execute(text("SELECT COUNT(*) AS questions_number FROM questions WEHRE course = :course"), {"course": course})
            .mappings()
            .fetchone()["questions_number"]
        )

        # TODO: add number of users for current course
        users_number = (
            conn.execute(text("SELECT COUNT(*) AS users_number FROM users WHERE nickname NOT IN ('admin', 'manager') "))
            .mappings()
            .fetchone()["users_number"]
        )

        topics = (
            conn.execute(
                text("SELECT topic, type, count(*) AS n_questions FROM questions WHERE course = :course GROUP BY topic, type ORDER BY id"),
                {"course": course},
            )
            .mappings()
            .all()
        )

        topics_list = (
            conn.execute(text("SELECT DISTINCT topic FROM questions WHERE course = :course  ORDER BY id"), {"course": course})
            .mappings()
            .all()
        )

        n_questions_by_day = (
            conn.execute(
                text(
                    "select DATE(timestamp) AS day, count(*) AS n_questions, count(distinct nickname) AS n_users FROM results WHERE course = :course AND nickname NOT IN ('admin', 'manager') GROUP BY day ORDER BY day"
                ),
                {"course": course},
            )
            .mappings()
            .all()
        )

        active_users_last_hour = (
            conn.execute(
                text(
                    "SELECT count(distinct nickname) AS active_users_last_hour FROM results WHERE course = :course AND  nickname NOT IN ('admin', 'manager') AND timestamp >= DATETIME('now', '-1 hour')"
                ),
                {"course": course},
            )
            .mappings()
            .fetchone()["active_users_last_hour"]
        )

        active_users_last_day = (
            conn.execute(
                text(
                    "SELECT count(distinct nickname) AS active_users_last_day FROM results WHERE course = :course AND nickname NOT IN ('admin', 'manager') AND timestamp >= DATETIME('now', '-1 day')"
                ),
                {"course": course},
            )
            .mappings()
            .fetchone()["active_users_last_day"]
        )

        active_users_last_week = (
            conn.execute(
                text(
                    "SELECT count(distinct nickname) AS active_users_last_week FROM results WHERE course = :course AND nickname NOT IN ('admin', 'manager') AND timestamp >= DATETIME('now', '-7 days')"
                ),
                {"course": course},
            )
            .mappings()
            .fetchone()["active_users_last_week"]
        )

        active_users_last_month = (
            conn.execute(
                text(
                    "SELECT count(distinct nickname) AS active_users_last_month FROM results WHERE course = :course AND  nickname NOT IN ('admin', 'manager') AND timestamp >= DATETIME('now', '-30 days')"
                ),
                {"course": course},
            )
            .mappings()
            .fetchone()["active_users_last_month"]
        )

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
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/load_questions/<course>", methods=["GET", "POST"])
@course_exists
@check_login
@is_manager
def load_questions(course: str):
    """
    load questions
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
        if file.filename not in (f"{course}.xml", f"{course}.gift"):
            flash("The file name must be COURSE_NAME.xml or COURSE_NAME.gift")
            return redirect(request.url)

        if file:
            file_path = Path(COURSES_DIR) / Path(file.filename)
            file.save(file_path)

            # load questions in database
            if load_questions_xml(file_path, course, get_course_config(course)):
                flash(f"Error loading questions from {file.filename}")
            else:
                flash(f"Questions loaded successfully from {file.filename}!")

            return redirect(url_for("admin", course=course))


@app.route(
    f"{app.config['APPLICATION_ROOT']}/edit_parameters/<course>",
    methods=["GET", "POST"],
)
@course_exists
@check_login
@is_manager
def edit_parameters(course: str):
    """
    edit course parameters
    """
    if request.method == "GET":
        # get parameters from .txt
        if (Path(COURSES_DIR) / Path(course).with_suffix(".txt")).is_file():
            with open(Path(COURSES_DIR) / Path(course).with_suffix(".txt"), "r") as f_in:
                parameters = f_in.read()
        else:
            parameters = f"File {Path(COURSES_DIR) / Path(course).with_suffix('.txt')} not found"

        return render_template("parameters.html", course=course, parameters=parameters)

    if request.method == "POST":
        # test if file is valid toml
        try:
            _ = tomllib.loads(request.form["parameters"])
        except Exception as e:
            logging.warning(f"Error loading the parameters {e}")
            flash(
                Markup(f'<div class="notification is-danger">The parameters contain the following error:<br>{e}</div>'),
                "error",
            )
            return render_template("parameters.html", course=course, parameters=request.form["parameters"])

        try:
            with open(Path(COURSES_DIR) / Path(course).with_suffix(".txt"), "w") as f_out:
                f_out.write(request.form["parameters"])

        except Exception as e:
            logging.warning(f"Error saving the parameters file {e}")

            flash(
                Markup('<div class="notification is-danger">Error saving parameters</div>'),
                "error",
            )

        flash(
            Markup('<div class="notification is-success">Parameters saved</div>'),
            "error",
        )

        return redirect(url_for("admin", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/add_lives/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager
def add_lives(course: str):
    with engine.connect() as conn:
        conn.execute(text("UPDATE lives SET number = number + 10 WHERE course = :course AND nickname = 'manager'"), {"course": course})
        conn.commit()

    flash(
        Markup('<div class="notification is-success">10 lives added to manager</div>'),
        "error",
    )

    return redirect(url_for("admin", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/all_questions/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager
def all_questions(course: str):
    """
    display all questions
    """

    out: list = []
    with engine.connect() as conn:
        for row in (
            conn.execute(text("SELECT * FROM questions WHERE course = :course ORDER BY id"), {"course": course}).mappings().fetchall()
        ):
            out.append(str(row["id"]))
            out.append(row["topic"])
            out.append(row["name"])
            content = json.loads(row["content"])
            out.append(content["questiontext"])
            for answer in content["answers"]:
                out.append(f"""{answer["fraction"]}  {answer["text"]}   <span style="color: gray;">feedback: {answer["feedback"]}</span>""")
            out.append("<hr>")

    return "<br>".join(out)


@app.route(f"{app.config['APPLICATION_ROOT']}/all_questions_gift/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager
def all_questions_gift(course: str):
    """
    display all questions in gift format
    """

    out: list = []
    with engine.connect() as conn:
        for row in (
            conn.execute(text("SELECT * FROM questions WHERE course = :course ORDER BY id"), {"course": course}).mappings().fetchall()
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
                    if content["generalfeedback"]:
                        out.append(f"####{content['generalfeedback']}")
                    out.append("}")
                else:
                    out.append(f"::{content['questiontext']}")
                    if content["generalfeedback"]:
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

                if content["generalfeedback"]:
                    out.append(f"####{content['generalfeedback']}")
                out.append("}")

            if row["type"] == "shortanswer":
                out.append(f"::{content['questiontext']}" + "{")
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        out.append(f"=%100%{answer['text']}#{answer['feedback']}")
                    else:
                        out.append(f"=%{answer['fraction']}%{answer['text']}#{answer['feedback']}")
                if content["generalfeedback"]:
                    out.append(f"####{content['generalfeedback']}")

                out.append("}")

            out.append("<hr>")

    return "<br>".join(out)


@app.route(
    f"{app.config['APPLICATION_ROOT']}/edit_question/<course>/<question_id>",
    methods=["GET", "POST"],
)
def edit_question(course: str, question_id):
    """
    edit question
    """

    translation = get_translation("it")

    with engine.connect() as conn:
        question = (
            conn.execute(
                text("SELECT * FROM questions WHERE course = :course AND id = :question_id"),
                {"course": course, "question_is": question_id},
            )
            .mappings()
            .fetchone()
        )
    content = json.loads(question["content"])

    if request.method == "GET":
        content["answers"] = [x | {"id": f"answer{idx + 1}"} for idx, x in enumerate(content["answers"])]
        return render_template(
            "edit_question.html",
            course=course,
            question_id=question_id,
            question=question,
            content=content,
            translation=translation,
        )
    if request.method == "POST":
        if not request.form["questiontext"]:
            return redirect(url_for("edit_question", course=course, question_id=question_id))
        content["questiontext"] = request.form["questiontext"]
        answers: list = []
        for x in request.form:
            if x.startswith("answer"):
                answers.append(
                    {
                        "text": request.form[x],
                        "feedback": request.form[f"feedback_{x}"],
                        "fraction": request.form[f"score_{x}"],
                    }
                )
        content["answers"] = answers

        # image
        file = request.files["file"]
        if file:
            file_path = Path("images") / Path(course) / Path(file.filename)
            file.save(file_path)
            content["files"].append(file.filename)

        # update db
        with engine.connect() as conn:
            conn.execute(
                text("UPDATE questions SET content = :content WHERE course = :course AND id = :id"),
                {"course": course, "content": json.dumps(content), "id": question_id},
            )
            conn.commit()
        return redirect(url_for("saved_questions", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/saved_questions/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager
def saved_questions(course: str):
    """
    display saved questions
    """

    translation = get_translation("it")

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT questions.id AS id, type, topic, name, content
                FROM bookmarks, questions
                WHERE bookmarks.course = questions.course AND bookmarks.question_id = questions.id AND course = :course
                ORDER BY questions.id
            """),
            {"course": course},
        )

        questions = result.mappings().all()

    q: list = []
    for question in questions:
        content = json.loads(question["content"])
        q.append(dict(question) | {"questiontext": content["questiontext"]})

    return render_template(
        "saved_questions.html",
        course=course,
        translation=translation,
        questions=q,
    )


@app.route(f"{app.config['APPLICATION_ROOT']}/reset_saved_questions/<course>", methods=["GET"])
@course_exists
@check_login
@is_manager
def reset_saved_questions(course: str):
    """
    reset saved questions
    """

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM bookmarks WHERE course = :course"), {"course": course})
        conn.commit()

    return redirect(url_for("admin", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/login/<course>", methods=["GET", "POST"])
@course_exists
def login(course: str):
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
            if hashlib.sha256(form_data.get("password").encode()).hexdigest() != app.config["ADMIN_PASSWORD_SHA256"]:
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("login", course=course))
            session["nickname"] = "admin"
            print(f"{session["nickname"]=}")
            return redirect(url_for("home", course=course))

        password_hash = hashlib.sha256(form_data.get("password").encode()).hexdigest()
        with engine.connect() as conn:
            cursor = conn.execute(
                text("SELECT count(*) AS n_users FROM users WHERE nickname = :nickname AND password_hash = :password_hash"),
                {
                    "nickname": form_data.get("nickname"),
                    "password_hash": password_hash,
                },
            )
            row = cursor.mappings().fetchone()
            if not row["n_users"]:
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("login", course=course))

            else:
                session["nickname"] = form_data.get("nickname")
                return redirect(url_for("home", course=course))


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
            if hashlib.sha256(form_data.get("password").encode()).hexdigest() != app.config["ADMIN_PASSWORD_SHA256"]:
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("admin_login"))
            session["nickname"] = "admin"
            return redirect(url_for("main_home"))


@app.route(f"{app.config['APPLICATION_ROOT']}/admin_logout")
def admin_logout():
    """
    Logout admin
    """

    del session["nickname"]
    return redirect(url_for("main_home"))


@app.route(f"{app.config['APPLICATION_ROOT']}/new_course", methods=["GET", "POST"])
def new_course():
    """
    new_course
    """

    if request.method == "GET":
        return render_template("new_course.html")
    if request.method == "POST":
        if not request.form["course_name"]:
            return render_template("new_course.html")
    create_database(request.form["course_name"])
    return redirect(url_for("main_home"))


@app.route(f"{app.config['APPLICATION_ROOT']}/new_nickname/<course>", methods=["GET", "POST"])
@course_exists
def new_nickname(course: str):
    """
    create a nickname
    """
    config = get_course_config(course)
    translation = get_translation("it")

    if request.method == "GET":
        return render_template("new_nickname.html", course=course, translation=translation)

    if request.method == "POST":
        form_data = request.form
        nickname = form_data.get("nickname").strip()
        password1 = form_data.get("password1")
        password2 = form_data.get("password2")

        if nickname in ("admin", "manager"):
            flash("This nickname is not allowed", "error")
            return render_template("new_nickname.html", course=course, translation=translation)

        if not password1 or not password2:
            flash("A password is missing", "error")
            return render_template("new_nickname.html", course=course, translation=translation)

        if password1 != password2:
            flash("Passwords are not the same", "error")
            return render_template("new_nickname.html", course=course, translation=translation)

        password_hash = hashlib.sha256(password1.encode()).hexdigest()

        with engine.connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) AS n_users FROM users WHERE nickname = :nickname",
                {"nickname": nickname},
            )
            n_users = cursor.mappings().fetchone()

            if n_users[0]:
                flash("Nickname already taken", "error")
                return render_template("new_nickname.html", course=course, translation=translation)

            try:
                conn.execute(
                    text("INSERT INTO users (nickname, password_hash) VALUES (:nickname, :password_hash)"),
                    {"nickname": nickname, "password_hash": password_hash},
                )
                conn.execute(
                    text("INSERT INTO lives (course, nickname, number) VALUES (:course, :nickname, :number)"),
                    {"course": course, "nickname": nickname, "number": config["INITIAL_LIFE_NUMBER"]},
                )
                conn.commit()

                flash(
                    Markup(f'<div class="notification is-success">New nickname created with {config["INITIAL_LIFE_NUMBER"]} lives</div>'),
                    "",
                )
                return redirect(url_for("home", course=course))

            except Exception:
                flash(
                    Markup('<div class="notification is-danger">Error creating the new nickname</div>'),
                    "error",
                )

                return redirect(url_for("home", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/<course>/delete", methods=["GET", "POST"])
@course_exists
@check_login
def delete(course: str):
    """
    delete nickname and all correlated data
    """
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM users WHERE nickname = :nickname"),
            {"nickname": session["nickname"]},
        )
        conn.execute(
            text("DELETE FROM lives WHERE nickname = :nickname"),
            {"nickname": session["nickname"]},
        )
        conn.execute(
            text("DELETE FROM questions WHERE nickname = :nickname"),
            {"nickname": session["nickname"]},
        )
        conn.execute(
            text("DELETE FROM steps WHERE nickname = :nickname"),
            {"nickname": session["nickname"]},
        )
        conn.execute(
            text("DELETE FROM bookmarks WHERE nickname = :nickname"),
            {"nickname": session["nickname"]},
        )
        conn.commit()

    del session["nickname"]
    return redirect(url_for("home", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/logout/<course>", methods=["GET", "POST"])
def logout(course):
    """
    logout
    """
    if "nickname" in session:
        del session["nickname"]
        clear_session()

    return redirect(url_for("home", course=course))


@app.route(f"{app.config['APPLICATION_ROOT']}/click_image/<course>", methods=["GET", "POST"])
@course_exists
@check_login
def click_image(course: str):
    """ """
    # config = get_course_config(course)
    translation = get_translation("it")

    if request.method == "GET":
        return render_template("click_image.html", course=course, translation=translation)


@app.route(f"{app.config['APPLICATION_ROOT']}/test_popup", methods=["GET", "POST"])
def test_popup():
    """ """
    return render_template("test_popup.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
