"""
module of moodle_quiz app

"""

import random
import pandas as pd
import numpy as np


def get_quiz_test(
    question_data: dict,
    topic: str,
    n_questions: int,
    results: pd.DataFrame,
    n_lives: int,
) -> list:
    """
    return a quiz (list of questions)

    Args:

        question_data (dict): all the question (extracted from moodle xml file)
        topic (str): topic requested
        n_questions (int): number of questions
        results (pd.DataFrame): results of user
        n_lives (int):  number of lives
    """

    print([question_data["Lezione 10 - Anellidi"]["shortanswer"]["1. Struttura caratteristica nei Sipunculidi - FILL IN THE BLANK"]])

    return [question_data["Lezione 10 - Anellidi"]["shortanswer"]["1. Struttura caratteristica nei Sipunculidi - FILL IN THE BLANK"]]

    # for image type debugging:
    # return [question_data["lezione 4 - Poriferi"]["shortanswer"]["Q1"]]

    questions_list: list = []
    # random extraction of n_questions (all question types) for topic
    for type_ in question_data[topic]:
        questions_list.extend([question for _, question in question_data[topic][type_].items()])

    return random.sample(questions_list, n_questions)


def get_quiz_recover(df_results: pd.DataFrame, recover_topics: list, n_questions_recover: int):
    # 50% domande estratte dal topic 'recover' (approssimato per difetto)
    n_questions_1 = n_questions_recover // 2

    lista_topic = df_results["topic"].unique().tolist()
    # limita la lista ai topics già in parte svolti
    ripasso_sel = []
    for i in np.arange(len(lista_topic)):
        df_filtered = df_results[df_results["topic"] == lista_topic[i]]
        id_domande = df_filtered[df_filtered["n_ok"] > 0]["question_id"].to_list()
        ripasso_sel.extend(id_domande)
    if len(id_domande) > n_questions_1:
        ripasso_sel = random.sample(ripasso_sel, n_questions_1)

    # 50% domande estratte dal topic 'recover' (approssimato per eccesso)
    n_questions_2 = n_questions_recover - n_questions_1
    # estrazione domande topic = recover
    id_recover = df_results[df_results["topic"].isin(recover_topics)]["question_id"].to_list()
    recover_sel = random.sample(id_recover, n_questions_2)
    questions_recover = recover_sel + ripasso_sel
    random.shuffle(questions_recover)

    print(questions_recover)

    return questions_recover


def crea_tappe(df_domande, topic, n_tappe, n_domande_x_quiz, seed):
    # Imposta un seed per garantire che la permutazione sia riproducibile
    # IDEA: Quando lo studente si logga per la prima volta, gli si potrebbe assegnare un array di N numeri, che saranno
    # utilizzati come seeds in differenti funzioni, se si vuole replicare la sequenza estratta

    # Filtra il DataFrame per ottenere solo le domande relative a "Capitolo 1"
    df_capitolo = df_domande[df_domande["topic"] == topic].reset_index(drop=True)

    # Conta il numero totale di domande nel capitolo filtrato
    ndomande = len(df_capitolo)
    print(f"{ndomande=}")

    # Permuta casualmente gli indici del DataFrame
    rng = np.random.default_rng(seed)

    shuffled_indices = rng.permutation(df_capitolo.index)
    # shuffled_indices = np.random.permutation(df_capitolo.index)

    # Calcola la dimensione approssimativa di ciascun sotto-DataFrame
    chunk_size = len(df_capitolo) // n_tappe
    resto = len(df_capitolo) % n_tappe

    if chunk_size < n_domande_x_quiz:
        n_domande_x_quiz = chunk_size
    df_tappe = []
    start = 0
    for i in range(n_tappe):
        end = start + chunk_size + (1 if i < resto else 0)
        df_tappa = df_capitolo.iloc[shuffled_indices[start:end]]
        df_tappe.append(df_tappa)
        start = end

    return df_tappe


def get_difficulty_tipo(tipo):
    difficulty_map = {"truefalse": 0.1, "multichoice": 0.25, "shortanswer": 0.4}
    return difficulty_map.get(tipo, 0)  # Ritorna 0 se il tipo non è nella mappa


def get_difficulty_old(score_tipo, ok, no):
    # assegna valore di difficoltà per ciascuna domanda
    # se la domanda non è mai stata presentata, il valore dipende dal tipo di domanda
    # altrimenti dal numero di risposte corrette ed errate già fornite
    with np.errstate(divide="ignore", invalid="ignore"):
        # score = np.where((no + ok) == 0, score_tipo, 0.5 * ((no - ok)/(no + ok) + 1))

        score = np.where((no + ok) == 0, score_tipo, no / (ok + no))
    return score


def get_difficulty(score_tipo, ok, no):
    # assegna valore di difficoltà per ciascuna domanda
    # se la domanda non è mai stata presentata, il valore dipende dal tipo di domanda

    # altrimenti dalla media tra tipo e numero di risposte corrette ed errate già fornite
    tot_risposte = no + ok
    # print(tot_risposte)
    score = np.zeros(len(tot_risposte))
    for i in np.arange(np.size(score_tipo)):
        if tot_risposte[i] > 0:
            diff = no[i] / tot_risposte[i]
            score[i] = tot_risposte[i] * diff / (tot_risposte[i] + 1) + score_tipo[i] / (tot_risposte[i] + 1)
        else:
            score[i] = score_tipo[i]
    return score


def get_score_studente(ok, no):
    # domande già sottoposte
    ntot_domande = np.size(ok)

    print(f"{ntot_domande=}")

    domande_con_risposta = np.where(ok + no > 0)

    print(f"{domande_con_risposta=}")

    print(f"{ok[domande_con_risposta]=}")

    print(f"{no[domande_con_risposta]=}")

    print(f"{ok[domande_con_risposta] + no[domande_con_risposta]=}")

    print(f"{ok[domande_con_risposta] / (ok[domande_con_risposta] + no[domande_con_risposta])=}")

    somma_scores = np.sum(ok[domande_con_risposta] / (ok[domande_con_risposta] + no[domande_con_risposta]))
    # somma_scores = np.sum(ok[domande_con_risposta]) / sum(ok[domande_con_risposta] + no[domande_con_risposta])

    print(f"{somma_scores=}")

    score_studente = somma_scores / ntot_domande
    return score_studente


def get_random_select(score_medio_studente, score_domande, f_rnd, f_studente_score):
    n_tot_domande = np.size(score_domande)
    rnd_walk = score_medio_studente * f_studente_score + np.cumsum(np.random.normal(0, f_rnd, (n_tot_domande, 1000)), axis=1)
    t = 1000 * np.ones(n_tot_domande)

    for i in np.arange(n_tot_domande):
        if score_medio_studente < score_domande[i]:
            tempo = np.where(rnd_walk[i, :] > score_domande[i])[0]

        else:
            tempo = np.where(rnd_walk[i, :] < score_domande[i])[0]

        if np.size(tempo) > 0:
            t[i] = np.min(tempo) + np.random.normal(1, 0.1, 1)

    rank_t = np.argsort(t)
    return rank_t, t


def get_quiz_sc3(topic: str, n_questions: int, results: pd.DataFrame, n_lives: int) -> list:
    """
    return a quiz (list of questions)

    Args:

        topic (str): topic requested
        n_questions (int): number of questions
        results (pd.DataFrame): results of user
        n_lives (int):  number of lives

    """

    capX = topic
    risultati = results  # pd.DataFrame({"cod_capitolo": cod_capitolo, "cod_tipo": cod_tipo, "cod_domanda": cod_domanda})

    # valuto il livello di preparazione per quel capitolo
    tipologie_domande = list(risultati[(risultati["topic"] == capX)]["type"].reset_index(drop=True))

    # print(tipologie_domande)

    risposte = risultati[(risultati["topic"] == capX)].reset_index(drop=True)

    risposteOK = np.array(risultati[(risultati["topic"] == capX)]["n_ok"])
    risposteNO = np.array(risultati[(risultati["topic"] == capX)]["n_no"])

    # print(np.nanmean(risposteNO / (risposteOK + risposteNO)))

    score_tipo = np.vectorize(get_difficulty_tipo)(tipologie_domande)

    scores_domande = get_difficulty(score_tipo, risposteOK, risposteNO)

    print(f"{risposteOK=}")
    print(f"{risposteNO=}")

    score_medio_studente = get_score_studente(risposteOK, risposteNO)

    print(f"{score_medio_studente=}")

    questions_score, t = get_random_select(score_medio_studente, scores_domande, f_rnd, f_student_score)

    print(f"{questions_score=}")

    question_id_list = []
    count = 0
    for i in questions_score:
        nome_domanda = risposte.iloc[i]["question_name"]

        print(f"{nome_domanda=}")

        question_id = risposte.iloc[i]["question_id"]

        # print(f"{question_id=}")

        # tipologia_domanda = risposte.iloc[i]["type"]

        # questions_list.append(question_data[capX][tipologia_domanda][nome_domanda])

        question_id_list.append(int(question_id))

        count += 1
        if count >= n_questions:
            break

    return question_id_list


f_rnd = 0.15  # deviazione standard della normale usata nel random walk
f_student_score = 1.1  # fattore di moltiplicazione dello score dello studente. se maggiore di 1 le domande selezionate
# hanno un livello di difficoltà superiore allo score medio dello studente
# (e.g livello medio di difficoltà = f_studente_score * studente_score)

get_quiz = get_quiz_sc3
