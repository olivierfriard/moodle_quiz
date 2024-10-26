from pathlib import Path
import re
import quiz
import json
import tomllib
import random
from markupsafe import Markup
from quart import Quart, render_template, session, redirect,request

import moodle_xml



xml_file = "data.xml"

# check config file
if Path(xml_file).with_suffix(".txt").is_file():
    with open(Path(xml_file).with_suffix(".txt"), "rb") as f:
        config = tomllib.load(f)

print(f"{config=}")

# load questions from xml moodle file
question_data = moodle_xml.moodle_xml_to_dict_with_images(xml_file, config["BASE_CATEGORY"], config["QUESTION_TYPES"])
print()
for topic in question_data.keys():
    print(topic)
    for subtopic in question_data[topic]:
        print(f"   {subtopic}: {len(question_data[topic][subtopic])} questions")
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
    session["quiz"] = quiz.get_quiz(question_data, topic, step, config["N_STEP_QUESTIONS"], results)
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
        placeholder = 'Input a text'
        type_='text'
    elif question["type"] in ("shortanswer", "numerical"):
        answers =''
        type_='number'
        placeholder = 'Input a number' if question["type"] =="numerical" else "Input a text"


    return await render_template(
        "question.html", question=question, answers=answers,
        type_=type_,
        placeholder=placeholder,
        topic=topic, step=step, idx=idx, total=len(session["quiz"])
    )

@app.route("/check_answer/<topic>/<step>/<int:idx>/<user_answer>", methods=["GET"])
@app.route("/check_answer/<topic>/<step>/<int:idx>", methods=["POST"])
async def check_answer(topic, step, idx, user_answer:str=""):
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

    if request.method == 'GET':

        # get user answer
        if question["type"] in ("truefalse", "multichoice"):
            user_answer = user_answer
        else:
            print(f"Question type error: {question["type"]}")


    if request.method == 'POST':
        # First, await request.form
        form_data = await request.form
        # Then, access form data with .get()
        user_answer = form_data.get('user_answer')

    print(f"{user_answer=} {type(user_answer)}")

    # get correct answer
    correct_answer_str: str = ""
    feedback: str = ""
    for answer in question["answers"]:
        if answer["fraction"] == "100":
            correct_answer_str = answer["text"]
        print(f"{answer["text"]=}")
        if user_answer == answer["text"]:
            print('ok')
            answer_feedback = answer["feedback"] if answer["feedback"] is not None else ""

    print(answer_feedback)

    feedback = {"questiontext": session["quiz"][idx]["questiontext"]}
    if user_answer.upper() == correct_answer_str.upper():
        feedback["result"] = correct_answer()
        feedback["correct"] = True
    else:
        feedback["result"] = Markup(wrong_answer(correct_answer_str, answer_feedback))
        feedback["correct"] = False

    # answers = random.sample(question["answers"], len(question["answers"]))

    return await render_template(
        "feedback.html", feedback=feedback, user_answer=user_answer, topic=topic, step=step, idx=idx, total=len(session["quiz"])
    )


if __name__ == "__main__":
    app.run()
