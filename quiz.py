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

    # print(f"{p=}")
    # print("HELLO !!!!")
    # print(tipo)
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


def get_quiz_sc2(question_data: dict, topic: str, n_questions: int, results: pd.DataFrame, quiz_type: int) -> list:
    """
    return a quiz (list of questions)

    Args:

        question_data (dict): all the question (extracted from moodle xml file)
        topic (str): topic requested
        n_questions (int): number of questions
        results (pd.DataFrame): results of user
        quiz_type:  1 # Normal quiz
                    2 # Life retieval

    """

    ndomande = n_questions
    capX = topic
    risultati = results  # pd.DataFrame({"cod_capitolo": cod_capitolo, "cod_tipo": cod_tipo, "cod_domanda": cod_domanda})

    # valuto il livello di preparazione per quel capitolo
    tipo = risultati[(risultati["topic"] == capX)]["type"].reset_index(drop=True)
    risposte = risultati[(risultati["topic"] == capX)].reset_index(drop=True)

    risposteOK = np.array(risultati[(risultati["topic"] == capX)]["n_ok"])
    risposteNO = np.array(risultati[(risultati["topic"] == capX)]["n_no"])

    # print(f"{risposteNO=}")

    if np.sum(risposteOK) > 0 or np.sum(risposteNO) > 0:
        score = (np.sum(risposteOK) - np.sum(risposteNO)) / (np.sum(risposteOK) + np.sum(risposteNO))
    else:
        score = 0

    # quantifico difficoltà relativa delle domande
    p = np.zeros(np.size(risposteOK))

    # print(f"{p=}")
    # print("HELLO !!!!")
    # print(tipo)
    for nd in np.arange(np.size(p)):
        if np.sum(risposteNO[nd]) > 0:
            p[nd] = (risposteNO[nd] - risposteOK[nd]) / (risposteOK[nd] + risposteNO[nd])

    rank_p = np.argsort(p)
    print(f"rango domande: {rank_p}")
    print(f"score domande: {p}")
    questions_list: list = []
    for i in np.arange(np.size(p)):
        if rank_p[i] < ndomande:
            questions_list.append(question_data[capX][risposte["type"][i]][risposte["question_name"][i]])
            print("score_domande", p[i])
            print("rango= ", rank_p[i])
            # print(question_data[capX][risposte["type"][i]][risposte["question_name"][i]],rank_p[i])
    print(f"selected questions are: {questions_list}")
    return questions_list


def get_difficulty_tipo(tipo):
    difficulty_map = {"truefalse": 0.1, "multichoice": 0.25, "shortanswer": 0.4}
    return difficulty_map.get(tipo, 0)  # Ritorna 0 se il tipo non è nella mappa


def get_difficulty(score_tipo, ok, no):
    # assegna valore di difficoltà per ciascuna domanda
    # se la domanda non è mai stata presentata, il valore dipende dal tipo di domanda
    # altrimenti dal numero di risposte corrette ed errate già fornite
    with np.errstate(divide="ignore", invalid="ignore"):
        # score = np.where((no + ok) == 0, score_tipo, 0.5 * ((no - ok)/(no + ok) + 1))

        score = np.where((no + ok) == 0, 0, ok / (ok + no))
    return score


def get_random_select(score_medio_studente, score_domande):
    n_tot_domande = np.size(score_domande)
    rnd_walk = score_medio_studente + np.cumsum(np.random.normal(0, 0.05, (n_tot_domande, 100)), axis=0)
    t = 20 * np.ones(n_tot_domande)
    for i in np.arange(n_tot_domande):
        if score_medio_studente < score_domande[i]:
            tempo = np.where(rnd_walk[i, :] > score_domande[i])[0]
        else:
            tempo = np.where(rnd_walk[i, :] < score_domande[i])[0]
        if np.size(tempo) > 0:
            t[i] = np.min(tempo)

    rank_t = np.argsort(t)
    return rank_t, t


def get_quiz_sc3(question_data: dict, topic: str, n_questions: int, results: pd.DataFrame, quiz_type: int) -> list:
    """
    return a quiz (list of questions)

    Args:

        question_data (dict): all the question (extracted from moodle xml file)
        topic (str): topic requested
        n_questions (int): number of questions
        results (pd.DataFrame): results of user
        quiz_type:  1 # Normal quiz
                    2 # Life retieval

    """

    capX = topic
    risultati = results  # pd.DataFrame({"cod_capitolo": cod_capitolo, "cod_tipo": cod_tipo, "cod_domanda": cod_domanda})

    # valuto il livello di preparazione per quel capitolo
    tipologie_domande = list(risultati[(risultati["topic"] == capX)]["type"].reset_index(drop=True))

    # print(tipologie_domande)

    risposte = risultati[(risultati["topic"] == capX)].reset_index(drop=True)

    risposteOK = np.array(risultati[(risultati["topic"] == capX)]["n_ok"])
    risposteNO = np.array(risultati[(risultati["topic"] == capX)]["n_no"])

    score_tipo = np.vectorize(get_difficulty_tipo)(tipologie_domande)

    scores_domande = get_difficulty(score_tipo, risposteOK, risposteNO)

    scores_studente = get_difficulty(score_tipo, risposteOK, risposteNO)

    # score_medio_studente = np.sum(risposteOK - risposteNO)/np.sum(risposteNO + risposteOK)
    score_medio_studente = np.mean(scores_studente)

    # print(score_medio_studente)

    questions_score, t = get_random_select(score_medio_studente, scores_domande)

    # print(f"{questions_score=}")

    questions_list = []
    count = 0
    for i in questions_score:
        nome_domanda = risposte.iloc[i]["question_name"]
        print(nome_domanda)
        tipologia_domanda = risposte.iloc[i]["type"]
        print(nome_domanda, tipologia_domanda)
        questions_list.append(question_data[capX][tipologia_domanda][nome_domanda])
        # print("=" * 20)
        count += 1
        if count >= n_questions:
            break

    print()
    print(scores_studente, np.mean(scores_domande), np.mean(scores_domande[0:n_questions]))

    # print(questions_list)

    return questions_list


print("ci sonoooo")
get_quiz = get_quiz_sc3
