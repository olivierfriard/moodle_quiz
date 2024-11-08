from pathlib import Path
import hashlib
import quiz
import sqlite3
import pandas as pd
import tomllib
import random
from markupsafe import Markup
from flask import Flask, render_template, session, redirect, request, g, flash, url_for
from functools import wraps
import moodle_xml


XML_FILE = "data.xml"


def get_quiz_config(xml_file: str):
    # check config file
    if Path(xml_file).with_suffix(".txt").is_file():
        with open(Path(xml_file).with_suffix(".txt"), "rb") as f:
            config = tomllib.load(f)
    else:
        config = {
            "N_QUESTIONS": 5,
            "QUESTION_TYPES": ["truefalse", "multichoice", "shortanswer", "numerical"],
            "DATABASE_NAME": "quiz.sqlite",
        }
    return config


def load_questions(xml_file: str, config: dict):
    # load questions from xml moodle file
    question_data1 = moodle_xml.moodle_xml_to_dict_with_images(xml_file, config["QUESTION_TYPES"], "duolinzoo/images")
    # re-organize the questions structure
    question_data: dict = {}
    for topic in question_data1:
        question_data[topic] = {}
        for category in question_data1[topic]:
            for question in question_data1[topic][category]:
                if question["type"] not in question_data[topic]:
                    question_data[topic][question["type"]] = {}

                question_data[topic][question["type"]][question["name"]] = question

    conn = sqlite3.connect(config["DATABASE_NAME"])
    cursor = conn.cursor()
    cursor.execute("DELETE FROM questions")

    conn.commit()
    for topic in question_data:
        for type_ in question_data[topic]:
            for question in question_data[topic][type_]:
                cursor.execute(
                    "INSERT INTO questions (topic, type, name) VALUES (?, ?, ?)",
                    (topic, type_, question),
                )
    conn.commit()
    conn.close()

    return question_data


app = Flask(__name__, static_folder="duolinzoo")
app.config.from_object("config")
app.config["DEBUG"] = True
# print(app.config)
app.secret_key = "votre_clé_secrète_sécurisée_ici"

config = get_quiz_config(XML_FILE)

question_data = load_questions(XML_FILE, config)

DATABASE = config["DATABASE_NAME"]


def check_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "nickname" not in session:
            flash("You must be logged to use Duolinzoo", "error")
            return redirect(url_for("home"))
        return f(*args, **kwargs)

    return decorated_function


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


@app.route(app.config["APPLICATION_ROOT"], methods=["GET"])
def home():
    return render_template("home.html")


@app.route(f"{app.config["APPLICATION_ROOT"]}/topic_list", methods=["GET"])
@check_login
def topic_list():
    return render_template("topic_list.html", topics=question_data.keys())


@app.route(f"{app.config["APPLICATION_ROOT"]}/quiz/<topic>", methods=["GET"])
@check_login
def create_quiz(topic):
    """
    create the quiz
    """
    db = get_db()
    # Execute the query
    query = """
SELECT 
    q.topic AS topic, 
    q.type AS type, 
    q.name AS question_name, 
    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
FROM questions q LEFT JOIN results r 
      ON q.topic=r.topic 
         AND q.type=r.category 
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

    # print(df_results.head())

    session["quiz"] = quiz.get_quiz(question_data, topic, config["N_QUESTIONS"], df_results, 1)
    # session["quiz"] = quiz.get_quiz(question_data, topic, config["N_QUESTIONS"], df_results)
    session["quiz_position"] = 0
    # show 1st question of the new quiz
    return redirect(f"{app.config["APPLICATION_ROOT"]}/question/{topic}/0")


def get_score(topic):
    db = get_db()
    query = """
SELECT AVG(percentage_ok) AS mean_percentage_ok 
FROM  (
SELECT 
    CAST(SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS FLOAT) / NULLIF((SELECT COUNT(*) FROM questions WHERE topic = ?), 0) AS percentage_ok
FROM 
    results 
WHERE 
    nickname = ?
GROUP BY 
    question_name
) AS subquery;

"""
    cursor = db.execute(query, (topic, session["nickname"]))
    # Fetch all rows
    return cursor.fetchone()[0]


@app.route(f"{app.config["APPLICATION_ROOT"]}/question/<topic>/<int:idx>", methods=["GET"])
@check_login
def question(topic, idx):
    if idx < len(session["quiz"]):
        question = session["quiz"][idx]
    else:
        return redirect(f"{app.config["APPLICATION_ROOT"]}/topic_list")

    # get score
    print(f"{get_score(topic)=}")

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
        placeholder = "Input a number" if question["type"] == "numerical" else "Input a text"

    return render_template(
        "question.html",
        question=question,
        image_list=image_list,
        answers=answers,
        type_=type_,
        placeholder=placeholder,
        topic=topic,
        idx=idx,
        total=len(session["quiz"]),
        score=get_score(topic),
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/check_answer/<topic>/<int:idx>/<path:user_answer>", methods=["GET"])
@app.route(f"{app.config["APPLICATION_ROOT"]}/check_answer/<topic>/<int:idx>", methods=["POST"])
@check_login
def check_answer(topic: str, idx: int, user_answer: str = ""):
    """
    check user answer and display feedback and score
    """

    def correct_answer():
        return "You selected the correct answer."

    def wrong_answer(correct_answer, answer_feedback):
        # feedback
        if answer_feedback:
            return f"{answer_feedback}<br><br>The correct answer is:<br>{correct_answer}"
        else:
            return f"The correct answer is:<br>{correct_answer}"

    question = session["quiz"][idx]

    if request.method == "GET":
        # get user answer
        if question["type"] in ("truefalse", "multichoice"):
            user_answer = user_answer
        else:
            print(f"Question type error: {question["type"]}")

    if request.method == "POST":
        # form_data = request.form
        user_answer = request.form.get("user_answer")

    print(f"{user_answer=} {type(user_answer)}")

    # get correct answer
    correct_answer_str: str = ""
    feedback: str = ""
    answer_feedback: str = ""
    for answer in question["answers"]:
        if answer["fraction"] == "100":
            correct_answer_str = answer["text"]
        print(f"{answer["text"]=}")
        if user_answer == answer["text"]:
            print("ok")
            answer_feedback = answer["feedback"] if answer["feedback"] is not None else ""

    print(answer_feedback)

    feedback = {"questiontext": session["quiz"][idx]["questiontext"]}
    if user_answer.upper() == correct_answer_str.upper():
        feedback["result"] = correct_answer()
        feedback["correct"] = True
    else:
        feedback["result"] = Markup(wrong_answer(correct_answer_str, answer_feedback))
        feedback["correct"] = False

    db = get_db()
    db.execute(
        ("INSERT INTO results (nickname, topic, category, question_name,good_answer) VALUES (?, ?, ?, ?, ?)"),
        (session["nickname"], topic, session["quiz"][idx]["type"], session["quiz"][idx]["name"], feedback["correct"]),
    )

    db.commit()

    return render_template(
        "feedback.html",
        feedback=feedback,
        user_answer=user_answer,
        topic=topic,
        idx=idx,
        total=len(session["quiz"]),
        score=get_score(topic),
    )


@app.route(f"{app.config["APPLICATION_ROOT"]}/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    if request.method == "POST":
        form_data = request.form
        password_hash = hashlib.sha256(form_data.get("password").encode()).hexdigest()
        db = get_db()
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
            return render_template("login.html")

        else:
            session["nickname"] = form_data.get("nickname")
            return redirect(app.config["APPLICATION_ROOT"])


@app.route(f"{app.config["APPLICATION_ROOT"]}/new_nickname", methods=["GET", "POST"])
def new_nickname():
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

        db = get_db()
        cursor = db.execute("SELECT count(*) AS n_users FROM users WHERE nickname = ?", (nickname,))
        n_users = cursor.fetchone()
        print(n_users[0])
        if n_users[0]:
            flash("Nickname already taken", "error")
            return render_template("new_nickname.html")

        try:
            db.execute("INSERT INTO users (nickname, password_hash) VALUES (?, ?)", (nickname, password_hash))

            db.commit()

            flash("New nickname created", "")
            return redirect(app.config["APPLICATION_ROOT"])

        except Exception:
            flash("Error creating the new nickname", "error")
            return redirect(app.config["APPLICATION_ROOT"])


@app.route(f"{app.config["APPLICATION_ROOT"]}/logout", methods=["GET", "POST"])
@check_login
def logout():
    if "nickname" in session:
        del session["nickname"]
    if "quiz" in session:
        del session["quiz"]

    return redirect(app.config["APPLICATION_ROOT"])


if __name__ == "__main__":
    app.run()
