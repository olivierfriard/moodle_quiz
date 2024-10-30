"""
module of moodle_quiz app

"""

import random
import pandas as pd
import numpy as np


def get_quiz_test(question_data: dict, topic: str, n_questions: int, results: pd.DataFrame) -> list:
    """
    return a quiz (list of questions)

    Args:

        question_data (dict): all the question (extracted from moodle xml file)
        topic (str): topic requested
        n_questions (int): number of questions
        results (dict): results of user

    """

    # for numerical type debugging:
    # return [question_data["lezione 3 - multicellularità"]["03-FI"][1]]

    # for image type debugging:
    # return [question_data["lezione 4 - Poriferi"]["shortanswer"]["Q1"]]

    questions_list: list = []
    # random extraction of n_questions (all question types) for topic
    for type_ in question_data[topic]:
        questions_list.extend([question for _, question in question_data[topic][type_].items()])

    return random.sample(questions_list, n_questions)


def get_quiz_sc(question_data: dict, topic: str, n_questions: int, results: pd.DataFrame) -> list:
    """
    return a quiz (list of questions)

    Args:

        question_data (dict): all the question (extracted from moodle xml file)
        topic (str): topic requested
        n_questions (int): number of questions
        results (pd.DataFrame): results of user

    """

    ndomande = n_questions
    capX = topic
    risultati = results  # pd.DataFrame({"cod_capitolo": cod_capitolo, "cod_tipo": cod_tipo, "cod_domanda": cod_domanda})

    # valuto il livello di preparazione per quel capitolo
    tipo = risultati[(risultati["topic"] == capX)]["type"].reset_index(drop=True)
    risposte = risultati[(risultati["topic"] == capX)].reset_index(drop=True)

    risposteOK = np.array(risultati[(risultati["topic"] == capX)]["n_ok"])
    risposteNO = np.array(risultati[(risultati["topic"] == capX)]["n_no"])

    print(f"{risposteNO=}")

    if np.sum(risposteOK) > 0 or np.sum(risposteNO) > 0:
        score = (np.sum(risposteOK) - np.sum(risposteNO)) / (np.sum(risposteOK) + np.sum(risposteNO))
    else:
        score = 0

    # quantifico difficoltà relativa delle domande
    p = np.zeros(np.size(risposteOK))

    print(f"{p=}")
    print("HELLO")
    print(tipo)
    for nd in np.arange(np.size(p)):
        # print(f"{nd=}")
        if tipo[nd] == "truefalse":
            diffic = 0.1
        elif tipo[nd] == "multichoice":
            diffic = 0.25
        else:  # shortanswer or numerical
            diffic = 0.40
        if np.sum(risposteNO[nd]) > 0:
            diffic += 0.5 * (risposteNO[nd] - risposteOK[nd]) / (risposteOK[nd] + risposteNO[nd])

        p[nd] = np.abs(np.random.uniform(diffic - 0.5, diffic + 0.5, 1) - score)

    rank_p = np.argsort(p)

    questions_list: list = []
    for i in np.arange(np.size(p)):
        if rank_p[i] < ndomande:
            # print(capX)
            # print(risposte["type"][i])
            # print(risposte["question_name"][i])
            questions_list.append(question_data[capX][risposte["type"][i]][risposte["question_name"][i]])
            # print()

    print(f"selected questions are: {questions_list}")
    return questions_list


get_quiz = get_quiz_sc
