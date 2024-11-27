"""
Duolinzoo

"""

from pathlib import Path
import hashlib
import quiz
import sqlite3
import pandas as pd
import tomllib
import random
import re
import json
import sys
from markupsafe import Markup
from flask import (
    Flask,
    render_template,
    session,
    redirect,
    request,
    g,
    flash,
    url_for,
    send_from_directory,
    jsonify,
)
from functools import wraps
import moodle_xml


def get_course_config(course: str):
    # check config file
    xml_file = Path(course).with_suffix(".xml")
    if xml_file.with_suffix(".txt").is_file():
        with open(xml_file.with_suffix(".txt"), "rb") as f:
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
            "N_QUESTIONS_BY_RECOVER": 3,
            "MAX_RECOVER_ERRORS": 2,
            "RECOVER_TOPICS": [],
        }
    return config


def get_translation(language: str):
    """
    get translation
    """
    print("translation")
    if Path(f"translations_{language}.txt").is_file():
        with open(Path(f"translations_{language}.txt"), "rb") as f:
            translation = tomllib.load(f)

        return translation
    else:
        return None


def load_questions_xml(xml_file: Path, config: dict) -> int:
    try:
        # load questions from xml moodle file
        question_data1 = moodle_xml.moodle_xml_to_dict_with_images(xml_file, config["QUESTION_TYPES"], f"images/{xml_file.stem}")

        # re-organize the questions structure
        question_data: dict = {}
        for topic in question_data1:
            question_data[topic] = {}
            for question_type in question_data1[topic]:
                for question in question_data1[topic][question_type]:
                    if question["type"] not in question_data[topic]:
                        question_data[topic][question["type"]] = {}

                    question_data[topic][question["type"]][question["name"]] = question

        # load questions in database
        conn = sqlite3.connect(xml_file.with_suffix(".sqlite"))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM questions")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'questions'")

        conn.commit()
        for topic in question_data:
            for type_ in question_data[topic]:
                for question_name in question_data[topic][type_]:
                    cursor.execute(
                        "INSERT INTO questions (topic, type, name, content) VALUES (?, ?, ?, ?)",
                        (
                            topic,
                            type_,
                            question_name,
                            json.dumps(question_data[topic][type_][question_name]),
                        ),
                    )
        conn.commit()
        conn.close()
    except Exception:
        raise
        return 1
    return 0


app = Flask(__name__)
app.config.from_object("config")
app.config["DEBUG"] = True
app.secret_key = "votre_clé_secrète_sécurisée_ici"


def get_db(course):
    database_name = Path(course).with_suffix(".sqlite")
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(database_name)
        db.row_factory = sqlite3.Row
    return db


def create_database(course) -> None:
    """
    create a new database
    """
    database_name = Path(course).with_suffix(".sqlite")

    conn = sqlite3.connect(database_name)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    topic TEXT NOT NULL,
    question_type TEXT NOT NULL,
    question_name TEXT NOT NULL,
    good_answer BOOL NOT NULL)""")

    cursor.execute("""
    CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT not NULL
    )""")

    cursor.execute(
        """
    CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
    )"""
    )
    cursor.execute(
        """
        CREATE TABLE lives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT NOT NULL UNIQUE,
        number INTEGER DEFAULT 10
        )
        """
    )

    cursor.execute(
        """
    CREATE TABLE steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL,
    topic TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    number INTEGER NOT NULL
    )"""
    )

    cursor.execute(
        """
    CREATE TABLE bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nickname TEXT NOT NULL UNIQUE,
    question_id INTEGER NOT NULL
    )"""
    )

    conn.commit()
    conn.close()


# load courses in database
for xml_file in Path(".").glob("*.xml"):
    # check if database sqlite file exists
    if not xml_file.with_suffix(".sqlite").exists():
        print(f"Database file {xml_file.with_suffix('.sqlite')} not found")
        print("Creating a new one")
        create_database(xml_file.stem)

    # populate database with questions
    if load_questions_xml(xml_file, get_course_config(xml_file)):
        print(f"Error loading the question XML file {xml_file}")
        sys.exit()


def check_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "nickname" not in session:
            flash("You must be logged", "error")
            return redirect(url_for("home"), course=kwargs["course"])
        else:
            # check if nickname in course
            with get_db(kwargs["course"]) as db:
                if db.execute("SELECT * FROM users WHERE nickname = ?", (session["nickname"],)).fetchone() is None:
                    return redirect(url_for("logout", course=kwargs["course"]))
        return f(*args, **kwargs)

    return decorated_function


def course_exists(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not Path(kwargs["course"]).with_suffix(".sqlite").is_file():
            return "The course does not exists"
        return f(*args, **kwargs)

    return decorated_function


@app.route(f"{app.config["APPLICATION_ROOT"]}/static/<path:filename>")
def send_static(filename):
    return send_from_directory("static", filename)


@app.route(f"{app.config["APPLICATION_ROOT"]}/images/<course>/<path:filename>")
def images(course: str, filename):
    return send_from_directory(f"images/{course}", filename)


def get_lives_number(course: str, nickname: str) -> int | None:
    """
    get number of lives for nickname
    """
    if not Path(course).with_suffix(".sqlite").is_file():
        return None
    with get_db(course) as db:
        cursor = db.execute("SELECT number FROM lives WHERE nickname = ?", (nickname,))
        lives = cursor.fetchone()
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


@app.route(f"{app.config["APPLICATION_ROOT"]}/<course>", methods=["GET"])
@course_exists
def home(course: str):
    """
    course home page
    """
    if "recover" in session:
        del session["recover"]
    if "brush-up" in session:
        del session["brush-up"]
    if "quiz" in session:
        del session["quiz"]

    config = get_course_config(course)
    translation = get_translation("it")

    lives = None
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])
        # check if nickname in course
        with get_db(course) as db:
            if db.execute("SELECT * FROM users WHERE nickname = ?", (session["nickname"],)).fetchone() is None:
                return redirect(url_for("logout", course=course))

    # check if brush-up available
    brushup_availability: bool = False
    if "nickname" in session:
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
        course_name=config["QUIZ_NAME"],
        course=course,
        lives=lives,
        translation=translation,
        brushup_availability=brushup_availability,
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/topic_list/<course>", methods=["GET"])
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

    with get_db(course) as db:
        topics: list = [
            row["topic"]
            for row in db.execute("SELECT DISTINCT topic FROM questions").fetchall()
            if row["topic"] not in config["TOPICS_TO_HIDE"]
        ]
        scores = {topic: get_score(course, topic) for topic in topics}

    return render_template(
        "topic_list.html",
        course_name=config["QUIZ_NAME"],
        course=course,
        topics=topics,
        scores=scores,
        lives=lives,
        translation=get_translation("it"),
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/recover_lives/<course>", methods=["GET"])
@course_exists
@check_login
def recover_lives(course: str):
    """
    display recover_lives
    """

    config = get_course_config(course)
    translation = get_translation("it")

    # create questions dataframe
    with get_db(course) as db:
        # Execute the query
        query = """
                SELECT 
                    q.id AS question_id,
                    q.topic AS topic, 
                    q.type AS type, 
                    q.name AS question_name, 
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r 
                    ON q.topic=r.topic 
                        AND q.type=r.question_type 
                        AND q.name=r.question_name
                        AND nickname = ?
                GROUP BY 
                    q.topic, 
                    q.type, 
                    q.name
                """

        cursor = db.execute(query, (session["nickname"],))
        # Fetch all rows
        rows = cursor.fetchall()
        # Get column names from the cursor description
        columns = [description[0] for description in cursor.description]
        # create dataframe
        questions_df = pd.DataFrame(rows, columns=columns)

    session["quiz"] = quiz.get_quiz_recover(questions_df, config["RECOVER_TOPICS"], config["N_QUESTIONS_BY_RECOVER"])

    print(f"{config["N_QUESTIONS_BY_RECOVER"]=}")

    print(f"{session["quiz"]=}")
    print(f"{len(session["quiz"])=}")

    session["recover"] = 0  # count number of errors

    return redirect(url_for("question", course=course, topic=translation["Recover lives"], step=1, idx=0))


def get_questions_dataframe(course: str, nickname: str) -> pd.DataFrame:
    with get_db(course) as db:
        # Execute the query
        query = """
                SELECT 
                    q.id AS question_id,
                    q.topic AS topic, 
                    q.type AS type, 
                    q.name AS question_name, 
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r 
                    ON q.topic=r.topic 
                        AND q.type=r.question_type 
                        AND q.name=r.question_name
                        AND nickname = ?
                GROUP BY 
                    q.topic, 
                    q.type, 
                    q.name
                """

        cursor = db.execute(query, (nickname,))
        # Fetch all rows
        rows = cursor.fetchall()
        # Get column names from the cursor description
        columns = [description[0] for description in cursor.description]
        # create dataframe
        return pd.DataFrame(rows, columns=columns)


@app.route(f"{app.config["APPLICATION_ROOT"]}/brush_up_home/<course>", methods=["GET"])
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


@app.route(f"{app.config["APPLICATION_ROOT"]}/brush_up/<course>/<int:level>", methods=["GET"])
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
                f'<div class="notification is-danger"><p class="is-size-5 has-text-weight-bold">{translation['The brush-up is not available']}</p></div>'
            ),
            "",
        )

        return redirect(url_for("home", course=course))

    session["brush-up"] = True

    return redirect(url_for("question", course=course, topic=translation["Brush-up"], step=1, idx=0))


def get_seed(nickname, topic):
    return int(hashlib.md5((nickname + topic).encode()).hexdigest(), 16)


@app.route(f"{app.config["APPLICATION_ROOT"]}/steps/<course>/<topic>", methods=["GET"])
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
    with get_db(course) as db:
        rows = db.execute(
            ("SELECT step_index, number FROM steps WHERE nickname = ? AND topic = ? "),
            (session["nickname"], topic),
        ).fetchall()
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
    f"{app.config["APPLICATION_ROOT"]}/step/<course>/<topic>/<int:step>",
    methods=["GET"],
)
@course_exists
@check_login
def step(course: str, topic: str, step: int):
    """
    create the step
    """

    config = get_course_config(course)

    with get_db(course) as db:
        # Execute the query
        query = """
                SELECT 
                    q.id AS question_id,
                    q.topic AS topic, 
                    q.type AS type, 
                    q.name AS question_name, 
                    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
                FROM questions q LEFT JOIN results r 
                    ON q.topic=r.topic 
                        AND q.type=r.question_type 
                        AND q.name=r.question_name
                        AND nickname = ?
                GROUP BY 
                    q.topic, 
                    q.type, 
                    q.name
                """

        cursor = db.execute(query, (session["nickname"],))
        # Fetch all rows
        rows = cursor.fetchall()
        # Get column names from the cursor description
        columns = [description[0] for description in cursor.description]
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
    return redirect(url_for("question", course=course, topic=topic, step=step, idx=0))


def get_score(course: str, topic: str, nickname: str = "") -> float:
    """
    get score of nickname user for topic
    if nickname is empty get score of current user
    """
    with get_db(course) as db:
        query = """
    SELECT (SUM(percentage_ok) / (SELECT COUNT(*) FROM questions WHERE topic = ?)) AS score
    FROM      (
    SELECT 
        CAST(SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS FLOAT) / NULLIF((SELECT COUNT(*) FROM results WHERE question_name = r.question_name), 0) AS percentage_ok
    FROM 
        results r

    WHERE topic = ? AND nickname = ?

    GROUP BY question_name
    ) AS subquery;
    """
        cursor = db.execute(query, (topic, topic, session["nickname"] if nickname == "" else nickname))
        # Fetch all rows
        score = cursor.fetchone()[0]
        if score is not None:
            return round(score, 3)
        else:
            return 0


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/toggle-checkbox/<course>/<int:question_id>",
    methods=["POST"],
)
def toggle_checkbox(course: str, question_id: int):
    print(f"{question_id=}")
    if request.is_json:
        is_checked = request.json.get("checked")
        print(is_checked)
        with get_db(course) as db:
            if is_checked:
                db.execute(
                    ("INSERT INTO bookmarks (nickname, question_id) VALUES (?, ?)"),
                    (session["nickname"], question_id),
                )
            else:
                db.execute(
                    ("DELETE FROM bookmarks WHERE nickname = ? AND question_id = ?"),
                    (session["nickname"], question_id),
                )

            db.commit()

    return jsonify({"message": ""})


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/question/<course>/<topic>/<int:step>/<int:idx>",
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

    # check if quiz is finished
    if idx < len(session["quiz"]):
        question_id = session["quiz"][idx]
        # get question content
        with get_db(course) as db:
            question = json.loads(
                db.execute(
                    "SELECT content FROM questions WHERE id = ?",
                    (question_id,),
                ).fetchone()["content"]
            )
    else:
        # step/quiz finished
        del session["quiz"]

        if "recover" in session:
            del session["recover"]

            return redirect(url_for("home", course=course))
        else:
            # normal quiz
            with get_db(course) as db:
                row = db.execute(
                    ("SELECT number FROM steps WHERE nickname = ? AND topic = ? AND step_index = ?"),
                    (session["nickname"], topic, step),
                ).fetchone()
                if row is None:
                    db.execute(
                        ("INSERT INTO steps (nickname, topic, step_index, number) VALUES (?, ?, ?, ?)"),
                        (session["nickname"], topic, step, 1),
                    )
                    db.commit()

                else:
                    db.execute(
                        ("UPDATE steps SET number = number + 1 WHERE nickname = ? AND topic = ? AND step_index = ?"),
                        (session["nickname"], topic, step),
                    )
                    db.commit()
                    if row["number"] == 4:
                        flash(
                            Markup(
                                f'<div class="notification is-success"><p class="is-size-3 has-text-weight-bold">Good! You just finished the step #{step}</p></div>'
                            ),
                            "",
                        )

            return redirect(url_for("steps", course=course, topic=topic))

    image_list = []
    for image in question.get("files", []):
        image_list.append(f"{app.config["APPLICATION_ROOT"]}/images/{course}/{image}")

    if question["type"] == "multichoice" or question["type"] == "truefalse":
        answers = random.sample(question["answers"], len(question["answers"]))
        placeholder = translation["Input a text"]
        type_ = "text"
    elif question["type"] in ("shortanswer", "numerical"):
        answers = ""
        type_ = "number" if question["type"] == "numerical" else "text"
        placeholder = translation["Input un numero"] if question["type"] == "numerical" else translation["Input a text"]

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
        total=len(session["quiz"]),
        score=get_score(course, topic),
        lives=get_lives_number(course, session["nickname"] if "nickname" in session else ""),
        recover="recover" in session,
        translation=translation,
    )


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/check_answer/<course>/<topic>/<int:step>/<int:idx>/<path:user_answer>",
    methods=["GET"],
)
@app.route(
    f"{app.config["APPLICATION_ROOT"]}/check_answer/<course>/<topic>/<int:step>/<int:idx>",
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

    def correct_answer(answer_feedback):
        out: list = []
        if answer_feedback:
            out.append(answer_feedback)
        out.append(translation["You selected the correct answer"])
        return "<br>".join(out)

    def wrong_answer(correct_answer, answer_feedback):
        # feedback
        out: list = []
        if answer_feedback:
            out.append(answer_feedback)
        out.append(translation["The correct answer is:"])
        if correct_answer in ("true", "false"):
            correct_answer = translation[correct_answer.upper()]
        out.append(correct_answer)
        return "<br>".join(out)

    question_id = session["quiz"][idx]
    # get question content
    with get_db(course) as db:
        question = json.loads(db.execute("SELECT content FROM questions WHERE id = ?", (question_id,)).fetchone()["content"])

    if request.method == "GET":
        # get user answer
        if question["type"] in ("truefalse", "multichoice"):
            user_answer = user_answer
        else:
            print(f"Question type error: {question["type"]}")

    if request.method == "POST":
        # form_data = request.form
        user_answer = request.form.get("user_answer")

    # print(f"{user_answer=} {type(user_answer)}")

    # get correct answer
    correct_answer_str: str = ""
    feedback: str = ""
    answer_feedback: str = ""
    for answer in question["answers"]:
        if answer["fraction"] == "100":
            correct_answer_str = answer["text"]
        # if user_answer == answer["text"]:
        if str_match(user_answer, answer["text"]):
            answer_feedback = answer["feedback"] if answer["feedback"] is not None else ""

    feedback = {"questiontext": question["questiontext"]}

    flag_max_recover_errors = False

    # check answer
    if str_match(user_answer, correct_answer_str):
        # good answer
        feedback["result"] = correct_answer(answer_feedback)
        feedback["correct"] = True

    else:
        # error
        feedback["result"] = Markup(wrong_answer(correct_answer_str, answer_feedback))
        feedback["correct"] = False

        # remove a life if not recover
        if "recover" not in session:
            with get_db(course) as db:
                db.execute(
                    ("UPDATE lives SET number = number - 1 WHERE number > 0 AND nickname = ? "),
                    (session["nickname"],),
                )
                db.commit()
        else:
            # count recover errors
            session["recover"] += 1
            if session["recover"] >= config["MAX_RECOVER_ERRORS"]:
                flag_max_recover_errors = True

    # translate user answer if true or false
    if user_answer in ("true", "false"):
        user_answer = translation[user_answer.upper()]

    # check if recover is ended
    flag_recovered = False
    if "recover" in session and idx + 1 >= config["N_QUESTIONS_BY_RECOVER"] and not flag_max_recover_errors:
        flag_recovered = True

        # add a new life
        with get_db(course) as db:
            db.execute(
                (f"UPDATE lives SET number = number + 1 WHERE nickname = ? and number < {config['INITIAL_LIFE_NUMBER']}"),
                (session["nickname"],),
            )
            db.commit()

    # save result
    if "recover" not in session:
        with get_db(course) as db:
            db.execute(
                ("INSERT INTO results (nickname, topic, question_type, question_name, good_answer) VALUES (?, ?, ?, ?, ?)"),
                (
                    session["nickname"],
                    topic,
                    question["type"],
                    question["name"],
                    feedback["correct"],
                ),
            )
            db.commit()

    print()
    print(f"{idx=}")
    print(f"{"recover" in session=}")
    print(f"{config["N_QUESTIONS_BY_RECOVER"]=}")
    print(f"{flag_max_recover_errors=}")
    print(f"{flag_recovered=}")
    print()

    return render_template(
        "feedback.html",
        course=course,
        question_id=question_id,
        feedback=feedback,
        user_answer=user_answer,
        config=config,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session["quiz"]),
        score=get_score(course, topic),
        lives=get_lives_number(course, session["nickname"] if "nickname" in session else ""),
        flag_max_recover_errors=flag_max_recover_errors,
        flag_recovered=flag_recovered,
        recover="recover" in session,
        translation=get_translation("it"),
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/results/<course>", methods=["GET"])
@course_exists
@check_login
def results(course: str):
    """
    display results for all users
    """

    # check if admin
    if session["nickname"] != "admin":
        flash(
            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
            "",
        )
        return redirect(url_for("home", course=course))

    with get_db(course) as db:
        cursor = db.execute("SELECT * FROM users")
        scores: dict = {}
        for user in cursor.fetchall():
            scores[user["nickname"]] = {}
            topics: list = [row["topic"] for row in db.execute("SELECT DISTINCT topic FROM questions").fetchall()]
            for topic in topics:
                scores[user["nickname"]][topic] = get_score(course, topic, nickname=user["nickname"])

    return render_template("results.html", course=course, topics=topics, scores=scores)


@app.route(f"{app.config["APPLICATION_ROOT"]}/admin/<course>", methods=["GET"])
@course_exists
@check_login
def admin(course: str):
    """
    administration page
    """

    # check if admin
    if session["nickname"] != "admin":
        flash(
            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
            "",
        )
        return redirect(url_for("home", course=course))

    config = get_course_config(course)

    with get_db(course) as db:
        questions_number = db.execute("SELECT COUNT(*) AS questions_number FROM questions").fetchone()["questions_number"]

        users_number = db.execute("SELECT COUNT(*) AS users_number FROM users").fetchone()["users_number"]

        topics = db.execute("SELECT topic,  type, count(*) AS n_questions FROM questions GROUP BY topic, type ORDER BY id").fetchall()

    if Path(course).with_suffix(".txt").exists():
        with open(Path(course).with_suffix(".txt"), "r") as f_in:
            data_content = f_in.read()
    else:
        data_content = f"File {Path(course).with_suffix(".txt")} not found"

    return render_template(
        "admin.html",
        course_name=config["QUIZ_NAME"],
        questions_number=questions_number,
        course=course,
        topics=topics,
        users_number=users_number,
        data_content=data_content,
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/all_questions/<course>", methods=["GET"])
@course_exists
@check_login
def all_questions(course: str):
    """
    display all questions
    """

    # check if admin
    if session["nickname"] != "admin":
        flash(
            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
            "",
        )
        return redirect(url_for("home", course=course))

    out = []
    with get_db(course) as db:
        cursor = db.execute("SELECT * FROM questions ORDER BY id")
        for row in cursor.fetchall():
            out.append(str(row["id"]))
            out.append(row["topic"])
            out.append(row["name"])
            content = json.loads(row["content"])
            out.append(content["questiontext"])
            for answer in content["answers"]:
                out.append(f"""{answer["fraction"]}  {answer["text"]}   <span style="color: gray;">feedback: {answer["feedback"]}</span>""")
            out.append("<hr>")

    return "<br>".join(out)


@app.route(f"{app.config["APPLICATION_ROOT"]}/all_questions_gift/<course>", methods=["GET"])
@course_exists
@check_login
def all_questions_gift(course: str):
    """
    display all questions in gift format
    """

    # check if admin
    if session["nickname"] != "admin":
        flash(
            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
            "",
        )
        return redirect(url_for("home", course=course))

    out = []
    with get_db(course) as db:
        cursor = db.execute("SELECT * FROM questions ORDER BY id")
        for row in cursor.fetchall():
            out.append(f"::{row['id']}")
            # category / topic
            out.append(f"$CATEGORY: {row["topic"]}")
            out.append(f"::{row['name']}")

            content = json.loads(row["content"])
            if row["type"] == "truefalse":
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        ans = answer["text"][0].upper()

                out.append(f"::{content['questiontext']} {{{ans}}}")

            if row["type"] == "multichoice":
                out.append(f"::{content['questiontext']} " + "{")
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        out.append(f"={answer["text"]}")
                    else:
                        out.append(f"~{answer["text"]}")
                    out.append(f"#{answer["feedback"]}")
                out.append("}")

            if row["type"] == "shortanswer":
                out.append(f"::{content['questiontext']}" + "{")
                for answer in content["answers"]:
                    if answer["fraction"] == "100":
                        out.append(f"={answer['text']}# {answer['feedback']}")
                out.append("}")

            '''
            out.append(str(row["id"]))
            out.append(row["topic"])
            out.append(row["name"])
            content = json.loads(row["content"])
            out.append(content["questiontext"])
            for answer in content["answers"]:
                out.append(f"""{answer["fraction"]}  {answer["text"]}   <span style="color: gray;">feedback: {answer["feedback"]}</span>""")
            '''
            out.append("<hr>")

    return "<br>".join(out)


@app.route(f"{app.config["APPLICATION_ROOT"]}/saved_questions/<course>", methods=["GET"])
@course_exists
@check_login
def saved_questions(course: str):
    """
    display saved questions
    """

    # check if admin
    if session["nickname"] != "admin":
        flash(
            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
            "",
        )
        return redirect(url_for("home", course=course))

    out = []
    with get_db(course) as db:
        cursor = db.execute("select topic, name from bookmarks, questions WHERE bookmarks.question_id = questions.id ORDER BY topic, name")
        for row in cursor.fetchall():
            out.append(str(row["topic"]))
            out.append(row["name"])
            out.append("<hr>")

    return "<br>".join(out)


@app.route(f"{app.config["APPLICATION_ROOT"]}/reset_saved_questions/<course>", methods=["GET"])
@course_exists
@check_login
def reset_saved_questions(course: str):
    """
    reset saved questions
    """

    # check if admin
    if session["nickname"] != "admin":
        flash(
            Markup('<div class="notification is-danger">You are not allowed to access this page</div>'),
            "",
        )
        return redirect(url_for("home", course=course))

    with get_db(course) as db:
        db.execute("DELETE FROM bookmarks")
        db.commit()

    return redirect(url_for("admin", course=course))


@app.route(f"{app.config["APPLICATION_ROOT"]}/login/<course>", methods=["GET", "POST"])
@course_exists
def login(course: str):
    """
    manage login
    """

    translation = get_translation("it")

    if request.method == "GET":
        return render_template("login.html", course=course, translation=translation)

    if request.method == "POST":
        form_data = request.form
        password_hash = hashlib.sha256(form_data.get("password").encode()).hexdigest()
        with get_db(course) as db:
            cursor = db.execute(
                "SELECT count(*) AS n_users FROM users WHERE nickname = ? AND password_hash = ?",
                (
                    form_data.get("nickname"),
                    password_hash,
                ),
            )
            n_users = cursor.fetchone()
            if not n_users[0]:
                flash(translation["Incorrect login. Retry"], "error")
                return redirect(url_for("login", course=course))

            else:
                session["nickname"] = form_data.get("nickname")
                return redirect(url_for("home", course=course))


@app.route(f"{app.config["APPLICATION_ROOT"]}/new_nickname/<course>", methods=["GET", "POST"])
@course_exists
def new_nickname(course: str):
    """
    create a nickname
    """
    config = get_course_config(course)

    if request.method == "GET":
        return render_template("new_nickname.html", course=course)

    if request.method == "POST":
        form_data = request.form
        # Then, access form data with .get()
        nickname = form_data.get("nickname")
        password1 = form_data.get("password1")
        password2 = form_data.get("password2")

        # if nickname == "admin":
        #    flash("This nickname is not allowed", "error")
        #    return render_template("new_nickname.html", course=course)

        if not password1 or not password2:
            flash("A password is missing", "error")
            return render_template("new_nickname.html", course=course)

        if password1 != password2:
            flash("Passwords are not the same", "error")
            return render_template("new_nickname.html", course=course)

        password_hash = hashlib.sha256(password1.encode()).hexdigest()

        with get_db(course) as db:
            cursor = db.execute("SELECT count(*) AS n_users FROM users WHERE nickname = ?", (nickname,))
            n_users = cursor.fetchone()

            if n_users[0]:
                flash("Nickname already taken", "error")
                return render_template("new_nickname.html", course=course)

            try:
                db.execute(
                    "INSERT INTO users (nickname, password_hash) VALUES (?, ?)",
                    (nickname, password_hash),
                )
                db.execute(
                    "INSERT INTO lives (nickname, number) VALUES (?, ?)",
                    (nickname, config["INITIAL_LIFE_NUMBER"]),
                )
                db.commit()

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


@app.route(f"{app.config["APPLICATION_ROOT"]}/<course>/delete", methods=["GET", "POST"])
@course_exists
@check_login
def delete(course: str):
    """
    delete nickname and results
    """
    with get_db(course) as db:
        db.execute("DELETE FROM users WHERE nickname = ?", (session["nickname"],))
        db.execute("DELETE FROM lives WHERE nickname = ?", (session["nickname"],))
        db.execute("DELETE FROM steps WHERE nickname = ?", (session["nickname"],))
        db.execute("DELETE FROM bookmarks WHERE nickname = ?", (session["nickname"],))
        db.commit()

    del session["nickname"]
    return redirect(url_for("home", course=course))


@app.route(f"{app.config["APPLICATION_ROOT"]}/logout/<course>", methods=["GET", "POST"])
def logout(course):
    """
    logout
    """

    if "nickname" in session:
        del session["nickname"]
        if "quiz" in session:
            del session["quiz"]
            del session["position"]

    return redirect(url_for("home", course=course))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
