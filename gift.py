"""
convert gift questions file in python dictionary
"""

import pygiftparser
from pygiftparser import parser
from typing import List


def gift_to_dict(file_path: str, question_types: list):
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

    with open(file_path, "r") as f_in:
        content = f_in.read()

    g = parser.parse(content)

    questions: dict = {}

    # check categories
    topic_list: list = []
    for question in g.questions:
        if question.category.split("/") not in topic_list:
            topic_list.append(question.category.split("/"))

    # remove 2 first categories ("$course$/top/Default ..." ...)
    print(f"{topic_list=}")
    all_categories = remove_two_shortest(topic_list)
    print(all_categories)

    prefix_to_remove = find_common_prefix(all_categories)
    print(f"{prefix_to_remove=}")

    c = 0
    for question in g.questions:
        c += 1
        d: dict = {}

        topic: str = question.category.removeprefix(prefix_to_remove)

        d["name"] = question.name
        d["questiontext"] = question.text

        if isinstance(question.answer, pygiftparser.gift.TrueFalse):
            d["type"] = "truefalse"
        if isinstance(question.answer, pygiftparser.gift.Short):
            d["type"] = "shortanswer"
        if isinstance(question.answer, pygiftparser.gift.MultipleChoiceRadio):
            d["type"] = "multichoice"

        answers = []

        for answer in question.answer.options:
            answers.append(
                {
                    "text": answer.text,
                    "fraction": str(int(100 * answer.percentage)),
                    "feedback": answer.feedback,
                }
            )

        d["answers"] = list(answers)

        if topic not in questions:
            questions[topic] = {}
        if d["type"] not in questions[topic]:
            questions[topic][d["type"]] = {}

        questions[topic][d["type"]][d["name"]] = dict(d)

        print()
        print(questions[topic][d["type"]][d["name"]])

        print("-" * 20)

    # print(q)
    print(c)

    return questions


if __name__ == "__main__":
    import sys

    print(gift_to_dict(sys.argv[1], []))
