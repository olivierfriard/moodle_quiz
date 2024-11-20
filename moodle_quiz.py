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
from flask import Flask, render_template, session, redirect, request, g, flash, url_for
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
            "N_QUESTIONS": 5,
            "QUESTION_TYPES": ["truefalse", "multichoice", "shortanswer", "numerical"],
            "DATABASE_NAME": "quiz.sqlite",
            "INITIAL_LIFE_NUMBER": 10,
        }
    return config


def load_questions_xml(xml_file: str, config: dict) -> int:
    try:
        # load questions from xml moodle file
        question_data1 = moodle_xml.moodle_xml_to_dict_with_images(
            xml_file, config["QUESTION_TYPES"], "duolinzoo/images"
        )

        # print(f"{question_data1['11 - Molluschi'].keys()=}")

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
        conn = sqlite3.connect(config["DATABASE_NAME"])
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


app = Flask(__name__, static_folder="duolinzoo")
app.config.from_object("config")
app.config["DEBUG"] = True
# print(app.config)
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
        CREATE TABLE lives (id INTEGER PRIMARY KEY AUTOINCREMENT,nickname TEXT NOT NULL UNIQUE, number INTEGER DEFAULT 10);
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

    conn.commit()
    conn.close()


for xml_file in Path(".").glob("*.xml"):
    # check if database sqlite file exists
    if not xml_file.with_suffix(".sqlite"):
        print(f"Database file {xml_file.stem} not found")
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
        return f(*args, **kwargs)

    return decorated_function


def course_exists(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not Path(kwargs["course"]).with_suffix(".sqlite").is_file():
            return "The course does not exists"
        return f(*args, **kwargs)

    return decorated_function


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
    lives = None
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])

    return render_template("home.html", course=course, lives=lives)


@app.route(f"{app.config["APPLICATION_ROOT"]}/topic_list/<course>", methods=["GET"])
@check_login
@course_exists
def topic_list(course: str):
    """
    display list of topics for selected course
    """
    lives = None
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])

    with get_db(course) as db:
        topics: list = [
            row["topic"]
            for row in db.execute("SELECT DISTINCT topic FROM questions").fetchall()
        ]
        scores = {topic: get_score(course, topic) for topic in topics}

    return render_template(
        "topic_list.html", course=course, topics=topics, scores=scores, lives=lives
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/recover_lives/<course>", methods=["GET"])
@check_login
@course_exists
def recover_lives(course: str):
    """
    display recover_lives
    """
    lives = None
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])

    return render_template("recover_lives.html", course=course, lives=lives)


@app.route(f"{app.config["APPLICATION_ROOT"]}/brush_up/<course>", methods=["GET"])
@check_login
@course_exists
def brush_up(course):
    """
    display ripasso
    """
    lives = None
    if "nickname" in session:
        lives = get_lives_number(course, session["nickname"])

    return render_template("brush_up.html", course=course, lives=lives)


def get_seed(nickname, topic):
    return int(hashlib.md5((nickname + topic).encode()).hexdigest(), 16)


@app.route(f"{app.config["APPLICATION_ROOT"]}/steps/<course>/<topic>", methods=["GET"])
@check_login
@course_exists
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
        course=course,
        topic=topic,
        lives=lives,
        n_steps=config["N_STEPS"],
        n_quiz_by_step=config["N_QUIZ_BY_STEP"],
        steps_active=steps_active,
    )


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/step/<course>/<topic>/<int:step>",
    methods=["GET"],
)
@check_login
@course_exists
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
    session["quiz_position"] = 0

    # return redirect(f"{app.config["APPLICATION_ROOT"]}/question/{}/{topic}/{step}/0")
    return redirect(url_for("question", course=course, topic=topic, step=step, idx=0))


'''
@app.route(f"{app.config["APPLICATION_ROOT"]}/quiz/<topic>", methods=["GET"])
@check_login
def create_quiz(topic: str):
    """
    create the quiz
    """

    with get_db(config["DATABASE_NAME"]) as db:
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

        df_results = pd.DataFrame(rows, columns=columns)

    session["quiz"] = quiz.get_quiz(
        topic, config["N_QUESTIONS"], df_results, get_lives_number(session["nickname"])
    )

    session["quiz_position"] = 0
    # show 1st question of the new quiz
    return redirect(f"{app.config["APPLICATION_ROOT"]}/question/{topic}/0")
'''


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
        cursor = db.execute(
            query, (topic, topic, session["nickname"] if nickname == "" else nickname)
        )
        # Fetch all rows
        score = cursor.fetchone()[0]
        if score is not None:
            return round(score, 3)
        else:
            return 0


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/question/<course>/<topic>/<int:step>/<int:idx>",
    methods=["GET"],
)
@check_login
@course_exists
def question(course: str, topic: str, step: int, idx: int):
    """
    show question idx
    """
    # check if quiz is finished
    if idx < len(session["quiz"]):
        # get question content
        with get_db(course) as db:
            question = json.loads(
                db.execute(
                    "SELECT content FROM questions WHERE id = ?",
                    (session["quiz"][idx],),
                ).fetchone()["content"]
            )
    else:
        # step/quiz finished

        with get_db(course) as db:
            row = db.execute(
                (
                    "SELECT number FROM steps WHERE nickname = ? AND topic = ? AND step_index = ?"
                ),
                (session["nickname"], topic, step),
            ).fetchone()
            if row is None:
                db.execute(
                    (
                        "INSERT INTO steps (nickname, topic, step_index, number) VALUES (?, ?, ?, ?)"
                    ),
                    (session["nickname"], topic, step, 1),
                )
                db.commit()

            else:
                db.execute(
                    (
                        "UPDATE steps SET number = number + 1 WHERE nickname = ? AND topic = ? AND step_index = ?"
                    ),
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

        return redirect(f"{app.config["APPLICATION_ROOT"]}/steps/{topic}")

    image_list = []
    for image in question.get("files", []):
        image_list.append(f"{app.config["APPLICATION_ROOT"]}/images/{image}")

    if question["type"] == "multichoice" or question["type"] == "truefalse":
        answers = random.sample(question["answers"], len(question["answers"]))
        placeholder = "Input a text"
        type_ = "text"
    elif question["type"] in ("shortanswer", "numerical"):
        answers = ""
        type_ = "number" if question["type"] == "numerical" else "text"
        placeholder = (
            "Input a number" if question["type"] == "numerical" else "Input a text"
        )

    return render_template(
        "question.html",
        question=question,
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
        lives=get_lives_number(
            course, session["nickname"] if "nickname" in session else ""
        ),
    )


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/check_answer/<course>/<topic>/<int:step>/<int:idx>/<path:user_answer>",
    methods=["GET"],
)
@app.route(
    f"{app.config["APPLICATION_ROOT"]}/check_answer/<course>/<topic>/<int:step>/<int:idx>",
    methods=["POST"],
)
@check_login
@course_exists
def check_answer(course: str, topic: str, step: int, idx: int, user_answer: str = ""):
    """
    check user answer and display feedback and score
    """

    def correct_answer():
        return "You selected the correct answer."

    def wrong_answer(correct_answer, answer_feedback):
        # feedback
        if answer_feedback:
            return (
                f"{answer_feedback}<br><br>The correct answer is:<br>{correct_answer}"
            )
        else:
            return f"The correct answer is:<br>{correct_answer}"

    # get question content
    with get_db(course) as db:
        question = json.loads(
            db.execute(
                "SELECT content FROM questions WHERE id = ?", (session["quiz"][idx],)
            ).fetchone()["content"]
        )

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
            answer_feedback = (
                answer["feedback"] if answer["feedback"] is not None else ""
            )

    feedback = {"questiontext": question["questiontext"]}

    # if user_answer.upper() == correct_answer_str.upper():
    if str_match(user_answer, correct_answer_str):
        feedback["result"] = correct_answer()
        feedback["correct"] = True

    else:
        # print(f"{answer_feedback=}")
        feedback["result"] = Markup(wrong_answer(correct_answer_str, answer_feedback))
        feedback["correct"] = False
        # remove a life
        with get_db(course) as db:
            db.execute(
                (
                    "UPDATE lives SET number = number - 1 WHERE number > 0 AND nickname = ? "
                ),
                (session["nickname"],),
            )
            db.commit()

        # check
        # if get_lives_number(session["nickname"] if "nickname" in session else "") == 0:

    # save result
    with get_db(course) as db:
        db.execute(
            (
                "INSERT INTO results (nickname, topic, question_type, question_name, good_answer) VALUES (?, ?, ?, ?, ?)"
            ),
            (
                session["nickname"],
                topic,
                question["type"],
                question["name"],
                feedback["correct"],
            ),
        )
        db.commit()

    return render_template(
        "feedback.html",
        course=course,
        feedback=feedback,
        user_answer=user_answer,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session["quiz"]),
        score=get_score(course, topic),
        lives=get_lives_number(
            course, session["nickname"] if "nickname" in session else ""
        ),
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/<course>/results", methods=["GET"])
@check_login
@course_exists
def results(course: str):
    with get_db(course) as db:
        cursor = db.execute("SELECT * FROM users")
        scores: dict = {}
        for user in cursor.fetchall():
            scores[user["nickname"]] = {}
            topics: list = [
                row["topic"]
                for row in db.execute("SELECT DISTINCT topic FROM questions").fetchall()
            ]
            for topic in topics:
                scores[user["nickname"]][topic] = get_score(
                    topic, nickname=user["nickname"]
                )

    return render_template("results.html", topics=topics, scores=scores)


@app.route(f"{app.config["APPLICATION_ROOT"]}/<course>/admin42", methods=["GET"])
@check_login
@course_exists
def admin(course: str):
    with get_db(course) as db:
        questions_number = db.execute(
            "SELECT COUNT(*) AS questions_number FROM questions"
        ).fetchone()["questions_number"]

        users_number = db.execute(
            "SELECT COUNT(*) AS users_number FROM users"
        ).fetchone()["users_number"]

        topics = db.execute(
            "SELECT topic,  type, count(*) AS n_questions FROM questions GROUP BY topic, type ORDER BY id"
        ).fetchall()

        """scores: dict = {}
        for user in cursor.fetchall():
            scores[user["nickname"]] = {}
            topics: list = [row["topic"] for row in db.execute("SELECT DISTINCT topic FROM questions").fetchall()]
            for topic in topics:
                scores[user["nickname"]][topic] = get_score(topic, nickname=user["nickname"])
        """

    if Path("data.txt").exists():
        with open("data.txt", "r") as f_in:
            data_content = f_in.read()

    return render_template(
        "admin.html",
        questions_number=questions_number,
        topics=topics,
        users_number=users_number,
        data_content=data_content,
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/login/<course>", methods=["GET", "POST"])
@course_exists
def login(course: str):
    if request.method == "GET":
        return render_template("login.html", course=course)
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
                flash("Incorrect login. Retry", "error")
                return redirect(url_for("login", course=course))

            else:
                session["nickname"] = form_data.get("nickname")
                session["course"] = course
                return redirect(url_for("home", course=course))


@app.route(
    f"{app.config["APPLICATION_ROOT"]}/<course>/new_nickname", methods=["GET", "POST"]
)
@course_exists
def new_nickname(course: str):
    """
    create a nickname
    """
    config = get_course_config(course)

    if request.method == "GET":
        return render_template("new_nickname.html")

    if request.method == "POST":
        form_data = request.form
        # Then, access form data with .get()
        nickname = form_data.get("nickname")
        password1 = form_data.get("password1")
        password2 = form_data.get("password2")

        if not password1 or not password2:
            flash("A password is missing", "error")
            return render_template("new_nickname.html")

        if password1 != password2:
            flash("Passwords are not the same", "error")
            return render_template("new_nickname.html")

        password_hash = hashlib.sha256(password1.encode()).hexdigest()

        with get_db(course) as db:
            cursor = db.execute(
                "SELECT count(*) AS n_users FROM users WHERE nickname = ?", (nickname,)
            )
            n_users = cursor.fetchone()

            if n_users[0]:
                flash("Nickname already taken", "error")
                return render_template("new_nickname.html")

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
                    Markup(
                        f'<div class="notification is-success">New nickname created with {config["INITIAL_LIFE_NUMBER"]} lives</div>'
                    ),
                    "",
                )
                return redirect(app.config["APPLICATION_ROOT"])

            except Exception:
                flash(
                    Markup(
                        '<div class="notification is-danger">Error creating the new nickname</div>'
                    ),
                    "error",
                )

                return redirect(app.config["APPLICATION_ROOT"])


@app.route(f"{app.config["APPLICATION_ROOT"]}/<course>/delete", methods=["GET", "POST"])
@check_login
def delete(course: str):
    with get_db(course) as db:
        db.execute("DELETE FROM users WHERE nickname = ?", (session["nickname"],))
        db.execute("DELETE FROM lives WHERE nickname = ?", (session["nickname"],))
        db.execute("DELETE FROM steps WHERE nickname = ?", (session["nickname"],))
        db.commit()

    del session["nickname"]
    return redirect(app.config["APPLICATION_ROOT"])


@app.route(f"{app.config["APPLICATION_ROOT"]}/logout", methods=["GET", "POST"])
@check_login
def logout():
    if "nickname" in session:
        del session["nickname"]
        del session["course"]
        if "quiz" in session:
            del session["quiz"]
            del session["position"]

    return redirect(app.config["APPLICATION_ROOT"])


if __name__ == "__main__":
    app.run(host="0.0.0.0")
