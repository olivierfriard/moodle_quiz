"""
module of moodle_quiz app

"""

import random


def get_quiz(question_data: dict, topic: str, step: str, n_questions: int, results: dict) -> list:
    """
    return a quiz (list of questions)

    Args:

        question_data (dict): all the question (extracted from moodle xml file)
        topic (str): topic requested
        step (str): step requested
        n_questions (int): number of questions
        results (dict): results of user

    """

    # for numerical type debugging:
    # return [question_data["lezione 3 - multicellularità"]["03-FI"][1]]

    questions_list: list = []

    # random extraction of n_questions (all question types) for topic
    for question_type in question_data[topic]:
        questions_list.extend(question_data[topic][question_type])

    return random.sample(questions_list, n_questions)
