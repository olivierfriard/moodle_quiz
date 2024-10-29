def moodle_xml_to_dict_with_images(xml_file: str, question_types: list) -> dict:
    """
    Convert a Moodle XML question file into a Python dictionary, organizing questions by categories and decoding images from base64.

    Args:
        xml_file (str): Path to the XML file.

    Returns:
        dict: A dictionary with categories as keys and lists of questions as values.
    """

    import re
    from pathlib import Path
    import xml.etree.ElementTree as ET
    import base64
    from collections import defaultdict

    from typing import List

    FILES_PATH = "duolinzoo/images"

    def trova_prefisso_comune(lista: List[str]) -> str:
        if not lista:
            return ""

        # Trova il prefisso comune più lungo
        prefisso_comune = lista[0]
        for stringa in lista[1:]:
            while not stringa.startswith(prefisso_comune):
                prefisso_comune = prefisso_comune[:-1]
                if not prefisso_comune:
                    return ""

        return prefisso_comune

    def strip_html_tags(text):
        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # check categories
    all_categories = []
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            category_text = question.find("category/text").text
            if category_text not in all_categories:
                all_categories.append(category_text)

    prefix_to_remove = trova_prefisso_comune(all_categories)

    print(f"{prefix_to_remove=}")

    # Dictionary to hold questions organized by category
    categories_dict = defaultdict(list)
    current_category = "Uncategorized"

    # Parse the XML tree
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            category_text = question.find("category/text").text.removeprefix(prefix_to_remove)
            category_list = category_text.split("/")
            # if base_category in category_list:
            #    category_list.remove(base_category)

            category_tuple = tuple(category_list)

            current_category = category_tuple if category_tuple else current_category

        # Handle actual questions
        else:
            # check if question type is allowed
            if question_type not in question_types:
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
                if not Path(FILES_PATH).is_dir():
                    Path(FILES_PATH).mkdir(parents=True, exist_ok=True)
                with open(Path(FILES_PATH) / Path(file_.get("name")), "wb") as file_out:
                    file_out.write(base64.b64decode(file_.text))

                question_dict["files"].append(file_.get("name"))

            if len(current_category) == 2:
                # Add the question to the respective category
                if current_category[0] not in categories_dict:
                    categories_dict[current_category[0]] = {}
                if current_category[1] not in categories_dict[current_category[0]]:
                    categories_dict[current_category[0]][current_category[1]] = []
                categories_dict[current_category[0]][current_category[1]].append(question_dict)

    return dict(categories_dict)
