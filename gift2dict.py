"""
{"type": "truefalse",
"name": "verofalso1",
"questiontext": "1 + 2 = 3",
"generalfeedback": "feedback generaleblabla",
"answers": [{"fraction": "100", "text": "true",
                   "feedback": "Hai risposto bene"},
            {"fraction": "0", "text": "false",
                 "feedback": "Risposta sbagliata"}],
"feedback": {"correct": null, "partiallycorrect": null, "incorrect": null},
"files": []}

"""

import pygiftparser
from pygiftparser import parser


def gift_to_dict(file_path: str):
    with open(file_path, "r") as f_in:
        content = f_in.read()

    g = parser.parse(content)

    questions = {}

    for question in g.questions:
        d = {}

        topic = question.category

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

        print(d)

        if topic not in questions:
            questions[topic] = {}
        if d["type"] not in questions[topic]:
            questions[topic][d["type"]] = {}

        questions[topic][d["type"]][d["name"]] = dict(d)

        print()
        print(questions[topic][d["type"]][d["name"]])

        print("-" * 20)

    # print(q)
    return questions


import sys

print(gift_to_dict(sys.argv[1]))
