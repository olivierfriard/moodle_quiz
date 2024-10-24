from pathlib import Path
import re
import tomllib
from quart import Quart, jsonify, request, render_template


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


app = Quart(__name__)


@app.route("/", methods=["GET"])
async def home():
    return await render_template("home.html")


@app.route("/topic_list", methods=["GET"])
async def topic_list():
    return await render_template("topic_list.html")


# Route pour créer une nouvelle ressource via une requête POST
@app.route("/data", methods=["POST"])
async def create_data():
    body = await request.get_json()
    if "name" not in body:
        return jsonify({"error": "Nom requis"}), 400

    new_item = {"name": body["name"], "description": body.get("description", "Pas de description fournie.")}
    return jsonify(new_item), 201


if __name__ == "__main__":
    app.run()
