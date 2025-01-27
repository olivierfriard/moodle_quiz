"""
convert questions from a moodle xml file to a dictionary

"""


def moodle_xml_to_dict_with_images(xml_file: str, question_types: list, image_files_path: str) -> dict:
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

    FILES_PATH = image_files_path

    def remove_two_shortest(strings):
        # written by chatGPT
        # Sort the list by length of strings
        sorted_strings = sorted(strings, key=len)
        # Remove the two shortest strings
        if len(sorted_strings) > 2:
            return [s for s in strings if s not in sorted_strings[:2]]
        return strings  # If there are fewer than 3 elements, return the original list

    def find_common_prefix(lista: List[list]) -> str:
        # written by chatGPT
        if not lista:
            return ""
        common_prefix: list = []
        for idx, element in enumerate(lista[0]):
            if len(set([x[idx] for x in lista])) == 1:
                common_prefix.append(element)
            else:
                return "/".join(common_prefix) + "/"

        return "/".join(common_prefix) + "/"

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
    all_categories: list = []
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            category_text = question.find("category/text").text
            if category_text not in all_categories:
                all_categories.append(category_text.split("/"))

    # remove 2 first categories ("$course$/top/Default ..." ...)
    all_categories = remove_two_shortest(all_categories)

    print(f"{all_categories=}")

    prefix_to_remove = find_common_prefix(all_categories)

    print(f"{prefix_to_remove=}")

    # Dictionary to hold questions organized by category
    categories_dict = defaultdict(list)
    current_category = "Uncategorized"
    current_id_number = 0

    main_categories = set()
    # parse all main categories
    for question in root.findall("question"):
        question_type = question.get("type")
        if question_type == "category":
            if len(question.find("category/text").text) < len(prefix_to_remove):
                continue
            category_text = question.find("category/text").text.removeprefix(prefix_to_remove)
            print(f"{category_text=}")
            # print(question.find("idnumber").text)
            id_number = 0
            if question.find("idnumber").text is not None:
                try:
                    id_number = float(question.find("idnumber").text)
                except Exception:
                    id_number = question.find("idnumber").text
            print(f"{len(category_text.split("/"))=}")
            print()

            main_cat = category_text.split("/")[0]

            try:
                position = int(main_cat.split(" ")[0])
            except Exception:
                position = 0

            main_categories.add((position, main_cat))
            # if len(category_text.split("/")) == 1:
            #    main_categories.add((id_number, category_text.split("/")[0]))

    print(f"{sorted(main_categories)=}")

    # Parse the XML tree
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            if len(question.find("category/text").text) < len(prefix_to_remove):
                continue

            category_text = question.find("category/text").text.removeprefix(prefix_to_remove)
            # print(f"{category_text=}")

            main_cat = category_text.split("/")[0]

            for idx, cat in main_categories:
                if main_cat == cat:
                    current_category = (idx, cat)
                    break
            else:
                # print("ERROR {main_cat} not found")
                continue

            # print(f"{current_category=}")

        # Handle actual questions
        else:
            # check if question type is allowed
            if question_type not in question_types:
                continue

            question_text = question.find("questiontext/text").text

            question_dict = {
                "type": question_type,
                "name": question.find("name/text").text if question.find("name/text") is not None else None,
                "questiontext": strip_html_tags(question_text if question_text is not None else None),
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
                strip_html_tags(question.find("generalfeedback/text").text) if question.find("generalfeedback/text") is not None else None
            )

            # Process feedback
            question_dict["feedback"]["correct"] = (
                strip_html_tags(question.find("correctfeedback/text").text) if question.find("correctfeedback/text") is not None else None
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
                    "text": strip_html_tags(answer.find("text").text) if answer.find("text") is not None else None,
                    "feedback": strip_html_tags(answer.find("feedback/text").text) if answer.find("feedback/text") is not None else None,
                }
                question_dict["answers"].append(answer_dict)

            # Process embedded files (decode base64 encoded content)
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

            # Add the question to the respective category
            if current_category[0:2] not in categories_dict:
                categories_dict[current_category[0:2]] = {}
            if question_dict["type"] not in categories_dict[current_category[0:2]]:
                categories_dict[current_category[0:2]][question_dict["type"]] = []
            # if current_category[2] not in categories_dict[current_category[0:2]]:
            #    categories_dict[current_category[0:2]][current_category[2]] = []
            categories_dict[current_category[0:2]][question_dict["type"]].append(question_dict)

    # sort dict categories by id_number
    categories_dict = dict(sorted(categories_dict.items()))

    # print()
    print(f"{categories_dict.keys()=}")

    # print([categories_dict[x] for x in categories_dict])

    # remove id_number
    categories_dict = {key[1]: value for key, value in categories_dict.items()}

    return dict(categories_dict)


if __name__ == "__main__":
    import sys

    moodle_xml_to_dict_with_images(sys.argv[1], ["multichoice", "truefalse", "shortanswer"], "tmp")
