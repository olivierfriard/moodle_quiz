from pathlib import Path
import hashlib
import re
import quiz
import aiosqlite
import sqlite3
import json
import pandas as pd
import tomllib
import random
from markupsafe import Markup
from quart import Quart, render_template, session, redirect, request, g, flash

import moodle_xml


xml_file = "data.xml"

# check config file
if Path(xml_file).with_suffix(".txt").is_file():
    with open(Path(xml_file).with_suffix(".txt"), "rb") as f:
        config = tomllib.load(f)

print(f"{config=}")

# load questions from xml moodle file
question_data1 = moodle_xml.moodle_xml_to_dict_with_images(xml_file, config["BASE_CATEGORY"], config["QUESTION_TYPES"])
# re-organize the questions structure
question_data = {}
for topic in question_data1:
    question_data[topic] = {}
    for category in question_data1[topic]:
        for question in question_data1[topic][category]:
            if question["type"] not in question_data[topic]:
                question_data[topic][question["type"]] = {}

            question_data[topic][question["type"]][question["name"]] = question

print()
for topic in question_data:
    print(topic)
    for category in question_data[topic]:
        print(f"   {category}: {len(question_data[topic][category])} questions")
    print()
print()


# check if file results.json exists
flag_results_file_present = False
results = {"questions": {}, "finished": {}}
if Path("results.json").is_file():
    try:
        with open("results.json", "r") as file_in:
            results = json.loads(file_in.read())
        print("Results loaded:")
        print(results)
        flag_results_file_present = True
    except Exception:
        print("Error loading the results.json file")

print(f"{results=}")


app = Quart(__name__)
app.config["DEBUG"] = True

app.secret_key = "votre_clé_secrète_sécurisée_ici"

DATABASE = "quiz.sqlite"


async def get_db():
    if "db" not in g:
        g.db = await aiosqlite.connect(DATABASE)
        g.db.row_factory = aiosqlite.Row
    return g.db


@app.route("/", methods=["GET"])
async def home():
    return await render_template("home.html")


@app.route("/topic_list", methods=["GET"])
async def topic_list():
    # print(question_data.keys())

    return await render_template("topic_list.html", topics=question_data.keys())


@app.route("/view_topic/<topic>", methods=["GET"])
async def view_topic(topic):
    step_list = []
    for i in range(1, config["STEP_NUMBER"] + 1):
        if i == 1:
            disabled = False
        else:
            disabled = i - 1 not in results["finished"].get(topic, [])

        step_list.append({"name": f"Step #{i}", "idx": i, "disabled": disabled})
    return await render_template("topic.html", topic=topic, step_list=step_list)


@app.route("/view_quiz/<topic>/<step>", methods=["GET"])
async def view_quiz(topic, step):
    # Write your SQL query

    # Connect to the SQLite database asynchronously
    async with aiosqlite.connect("quiz.sqlite") as db:
        # Execute the query
        query = """SELECT 
    topic, 
    category, 
    question_name, 
    SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
    SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
FROM 
    results
GROUP BY 
    topic, 
    category, 
    question_name;
"""
        async with db.execute(query) as cursor:
            # Fetch all rows
            rows = await cursor.fetchall()
            # Get column names from the cursor description
            columns = [description[0] for description in cursor.description]

    df = pd.DataFrame(rows, columns=columns)

    print(df)

    session["quiz"] = quiz.get_quiz(question_data, topic, step, config["N_STEP_QUESTIONS"], session["nickname"], df)
    session["quiz_position"] = 0
    return redirect(f"/question/{topic}/{step}/0")


@app.route("/question/<topic>/<int:step>/<int:idx>", methods=["GET"])
async def question(topic, step, idx):
    if idx < len(session["quiz"]):
        question = session["quiz"][idx]
    else:
        if topic not in results["finished"]:
            results["finished"][topic] = []
        if step not in results["finished"][topic]:
            results["finished"][topic].append(step)
        # save_results()

        return redirect(f"/view_topic/{topic}")

    if question["type"] == "multichoice" or question["type"] == "truefalse":
        answers = random.sample(question["answers"], len(question["answers"]))
        placeholder = "Input a text"
        type_ = "text"
    elif question["type"] in ("shortanswer", "numerical"):
        answers = ""
        type_ = "number"
        placeholder = "Input a number" if question["type"] == "numerical" else "Input a text"

    return await render_template(
        "question.html",
        question=question,
        answers=answers,
        type_=type_,
        placeholder=placeholder,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session["quiz"]),
    )


@app.route("/check_answer/<topic>/<step>/<int:idx>/<user_answer>", methods=["GET"])
@app.route("/check_answer/<topic>/<step>/<int:idx>", methods=["POST"])
async def check_answer(topic, step, idx, user_answer: str = ""):
    def correct_answer():
        if question["name"] not in results["questions"]:
            results["questions"][question["name"]] = []
        results["questions"][question["name"]].append(1)
        return "You selected the correct answer."

    def wrong_answer(correct_answer, answer_feedback):
        if question["name"] not in results["questions"]:
            results["questions"][question["name"]] = []
        results["questions"][question["name"]].append(0)
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
        # First, await request.form
        form_data = await request.form
        # Then, access form data with .get()
        user_answer = form_data.get("user_answer")

    print(f"{user_answer=} {type(user_answer)}")

    # get correct answer
    correct_answer_str: str = ""
    feedback: str = ""
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

    db = await get_db()
    await db.execute(
        ("INSERT INTO results (nickname, topic, category, question_name,good_answer) VALUES (?, ?, ?, ?, ?)"),
        (session["nickname"], topic, session["quiz"][idx]["type"], session["quiz"][idx]["name"], feedback["correct"]),
    )

    await db.commit()

    # answers = random.sample(question["answers"], len(question["answers"]))

    return await render_template(
        "feedback.html",
        feedback=feedback,
        user_answer=user_answer,
        topic=topic,
        step=step,
        idx=idx,
        total=len(session["quiz"]),
    )


@app.route("/login", methods=["GET", "POST"])
async def login():
    if request.method == "GET":
        return await render_template("login.html")
    if request.method == "POST":
        form_data = await request.form
        password_hash = hashlib.sha256(form_data.get("password").encode()).hexdigest()
        db = await get_db()
        cursor = await db.execute(
            "SELECT count(*) AS n_users FROM users WHERE nickname = ? AND password_hash = ?",
            (
                form_data.get("nickname"),
                password_hash,
            ),
        )
        n_users = await cursor.fetchone()
        if not n_users[0]:
            await flash("Incorrect login. Retry", "error")
            return await render_template("login.html")

        else:
            session["nickname"] = form_data.get("nickname")
            return redirect("/")


@app.route("/new_nickname", methods=["GET", "POST"])
async def new_nickname():
    if request.method == "GET":
        return await render_template("new_nickname.html")

    if request.method == "POST":
        # First, await request.form
        form_data = await request.form
        # Then, access form data with .get()
        nickname = form_data.get("nickname")
        password1 = form_data.get("password1")
        password2 = form_data.get("password2")

        if not password1 or not password2:
            await flash("A password is missing", "error")
            return await render_template("new_nickname.html")

        if password1 != password2:
            await flash("Passwords are not the same", "error")
            return await render_template("new_nickname.html")

        password_hash = hashlib.sha256(password1.encode()).hexdigest()

        db = await get_db()
        cursor = await db.execute("SELECT count(*) AS n_users FROM users WHERE nickname = ?", (nickname,))
        n_users = await cursor.fetchone()
        print(n_users[0])
        if n_users[0]:
            flash("Nickname already taken", "error")
            return await render_template("new_nickname.html")

        try:
            await db.execute(
                "INSERT INTO users (nickname, password_hash) VALUES (?, ?)",
                (nickname, password_hash),
            )
            await db.commit()

            await flash("New nickname created", "")
            return redirect("/")

        except aiosqlite.IntegrityError:
            await flash("Error creating the new nickname", "error")
            return redirect("/")


if __name__ == "__main__":
    app.run()
