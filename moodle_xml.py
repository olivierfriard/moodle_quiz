"""
convert questions from a moodle xml file to a dictionary

"""

import re
from pathlib import Path
import xml.etree.ElementTree as ET
import base64
from collections import defaultdict
import logging

from typing import List


def moodle_xml_to_dict_with_images(
    xml_file: str, question_types: list, image_files_path: str
) -> dict:
    """
    Convert a Moodle XML question file into a Python dictionary, organizing questions by categories and decoding images from base64.

    Args:
        xml_file (str): Path to the XML file.

    Returns:
        dict: A dictionary with categories as keys and lists of questions as values.
    """

    FILES_PATH = image_files_path

    def strip_html_tags(text: str) -> str:
        """
        remove HTML tags if text is string else retursn empty string
        """
        if text is None:
            return ""
        text = text.translate({10: 20, 13: 20})
        # &nbsp;
        text = text.replace("&nbsp;", " ")

        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # check categories
    unique_categories: list = []
    max_element_len: int = 0
    elements: dict = {}
    for question in root.findall("question"):
        question_type = question.get("type")

        if question_type == "category":
            category_text = question.find("category/text").text
            category_elements = category_text.split("/")
            max_element_len = max(max_element_len, len(category_elements))
            for idx, element in enumerate(category_elements):
                if idx not in elements:
                    elements[idx] = set()
                elements[idx].add(element)

            if category_elements not in unique_categories:
                unique_categories.append(category_elements)

    logging.debug(f"{elements=}")
    logging.debug(f"{max_element_len=}")

    print(elements)
    print(max_element_len)

    start: int | None = None
    for idx in range(max_element_len):
        if len(elements[idx]) > 1:
            start = idx
            break
    logging.debug(f"starting element: {start}")

    unique_categories = elements[start]
    logging.debug(f"{unique_categories=}")

    # Dictionary to hold questions organized by category
    categories_dict = defaultdict(list)
    current_category = "Uncategorized"

    question_names: dict = {}
    errors: list = []
    # Parse the XML tree
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            category_text = question.find("category/text").text
            category_elements = category_text.split("/")
            if len(category_elements) < start + 1:
                continue

            current_category = category_elements[start]
            if current_category not in question_names:
                question_names[current_category] = []

        # Handle actual questions
        else:
            # check if question type is allowed
            if question_type not in question_types:
                continue

            question_name = (
                question.find("name/text").text
                if question.find("name/text") is not None
                else None
            )
            # if question name already used in topic change it
            while question_name in question_names[current_category]:
                question_name += "_"

            question_text = question.find("questiontext/text").text

            question_names[current_category].append(question_name)

            question_dict = {
                "type": question_type,
                "name": question_name,
                "questiontext": strip_html_tags(
                    question_text if question_text is not None else None
                ),
                "generalfeedback": "",
                "answers": [],
                "feedback": {},
                "files": [],  # To store files related to the question
            }

            # check if external image(s)
            if question_text is not None and '<img src="http' in question_text:
                img_tag_pattern = r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>'
                img_sources = re.findall(img_tag_pattern, question_text)
                for img_source in img_sources:
                    question_dict["files"].append(img_source)

            # general feedback
            question_dict["generalfeedback"] = (
                strip_html_tags(question.find("generalfeedback/text").text)
                if question.find("generalfeedback/text") is not None
                else None
            )

            # Process feedback
            question_dict["feedback"]["correct"] = (
                strip_html_tags(question.find("correctfeedback/text").text)
                if question.find("correctfeedback/text") is not None
                else None
            )
            question_dict["feedback"]["partiallycorrect"] = (
                strip_html_tags(question.find("partiallycorrectfeedback/text").text)
                if question.find("partiallycorrectfeedback/text") is not None
                else None
            )
            question_dict["feedback"]["incorrect"] = (
                strip_html_tags(question.find("incorrectfeedback/text").text)
                if question.find("incorrectfeedback/text") is not None
                else None
            )

            # Process answers
            for answer in question.findall("answer"):
                answer_dict = {
                    "fraction": answer.get("fraction"),
                    "text": strip_html_tags(answer.find("text").text)
                    if answer.find("text") is not None
                    else None,
                    "feedback": strip_html_tags(answer.find("feedback/text").text)
                    if answer.find("feedback/text") is not None
                    else None,
                }
                question_dict["answers"].append(answer_dict)

            # Process embedded files (decode base64 encoded content)
            file_list = question.findall("questiontext/file")
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

            # Add the question to the respective category
            if current_category not in categories_dict:
                categories_dict[current_category] = []
            categories_dict[current_category].append(question_dict)

    # sort categories
    categories_dict = dict(sorted(categories_dict.items()))

    logging.debug(f"{categories_dict.keys()=}")

    if errors:
        return {"error": errors}

    return dict(categories_dict)


if __name__ == "__main__":
    import sys

    questions = moodle_xml_to_dict_with_images(
        sys.argv[1], ["multichoice", "truefalse", "shortanswer"], "tmp"
    )

    if "error" in questions:
        for row in questions["error"]:
            print(row)

    for category in questions:
        print(category, len(questions[category]))
    print("total number of questions", sum([len(questions[x]) for x in questions]))
