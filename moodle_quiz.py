from pathlib import Path
import re
import quiz
import json
import tomllib
import random
from markupsafe import Markup
from quart import Quart, render_template, session, redirect


def moodle_xml_to_dict_with_images(xml_file: str, base_category: str) -> dict:
    """
    Convert a Moodle XML question file into a Python dictionary, organizing questions by categories and decoding images from base64.

    Args:
        xml_file (str): Path to the XML file.

    Returns:
        dict: A dictionary with categories as keys and lists of questions as values.
    """

    import xml.etree.ElementTree as ET
    import base64
    from collections import defaultdict

    def strip_html_tags(text):
        # This is a simple method to strip HTML tags

        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Dictionary to hold questions organized by category
    categories_dict = defaultdict(list)
    current_category = "Uncategorized"

    # Parse the XML tree
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            category_text = question.find("category/text").text.removeprefix("$course$/top/")
            category_list = category_text.split("/")[1:]  # delele first category (with Default ...))
            if base_category in category_list:
                category_list.remove(base_category)

            category_tuple = tuple(category_list)

            # current_category = category_text if category_text else current_category
            current_category = category_tuple if category_tuple else current_category

        # Handle actual questions
        else:
            # check if question type is allowed
            if question_type not in config["QUESTION_TYPES"]:
                continue

            question_dict = {
                "type": question_type,
                "name": question.find("name/text").text if question.find("name/text") is not None else None,
                "questiontext": strip_html_tags(
                    question.find("questiontext/text").text if question.find("questiontext/text") is not None else None
                ),
                "answers": [],
                "feedback": {},
                "files": [],  # To store files related to the question
            }

            # Process feedback
            question_dict["feedback"]["correct"] = (
                question.find("correctfeedback/text").text if question.find("correctfeedback/text") is not None else None
            )
            question_dict["feedback"]["partiallycorrect"] = (
                question.find("partiallycorrectfeedback/text").text if question.find("partiallycorrectfeedback/text") is not None else None
            )
            question_dict["feedback"]["incorrect"] = (
                question.find("incorrectfeedback/text").text if question.find("incorrectfeedback/text") is not None else None
            )

            # Process answers
            for answer in question.findall("answer"):
                answer_dict = {
                    "fraction": answer.get("fraction"),
                    "text": strip_html_tags(answer.find("text").text if answer.find("text") is not None else None),
                    "feedback": answer.find("feedback/text").text if answer.find("feedback/text") is not None else None,
                }
                question_dict["answers"].append(answer_dict)

            # Process files (decode base64 encoded content)
            file_list = question.findall("questiontext/file")
            # print(f"{file_list=}")
            for file_ in file_list:
                # print(f"{file_.get("name")=}")
                # print(f"{file_.text=}")
                # print()

                # save base64 str into file
                if not Path("files").is_dir():
                    Path("files").mkdir(parents=True, exist_ok=True)
                with open(Path("files") / Path(file_.get("name")), "wb") as file:
                    file.write(base64.b64decode(file_.text))

                question_dict["files"].append(file_.get("name"))

            if len(current_category) == 2:
                # Add the question to the respective category
                if current_category[0] not in categories_dict:
                    categories_dict[current_category[0]] = {}
                if current_category[1] not in categories_dict[current_category[0]]:
                    categories_dict[current_category[0]][current_category[1]] = []
                categories_dict[current_category[0]][current_category[1]].append(question_dict)

    return dict(categories_dict)


xml_file = "data.xml"

# check config file
if Path(xml_file).with_suffix(".txt").is_file():
    with open(Path(xml_file).with_suffix(".txt"), "rb") as f:
        config = tomllib.load(f)

print(f"{config=}")

# load questions from xml moodle file
question_data = moodle_xml_to_dict_with_images(xml_file, config["BASE_CATEGORY"])
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

    answers = random.sample(question["answers"], len(question["answers"]))

    return await render_template(
        "question.html", question=question, answers=answers, topic=topic, step=step, idx=idx, total=len(session["quiz"])
    )


@app.route("/check_answer/<topic>/<step>/<int:idx>/<user_answer>", methods=["GET"])
async def check_answer(topic, step, idx, user_answer):
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

    # get user answer
    if question["type"] in ("truefalse", "multichoice"):
        user_answer = user_answer
    elif question["type"] in ("shortanswer", "numerical"):
        user_answer = "xx"
    else:
        print(f"Question type error: {question["type"]}")

    # get correct answer
    correct_answer_str: str = ""
    feedback: str = ""
    for answer in question["answers"]:
        if answer["fraction"] == "100":
            correct_answer_str = answer["text"]
        if user_answer == answer["text"]:
            answer_feedback = answer["feedback"] if answer["feedback"] is not None else ""

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
