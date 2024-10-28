import pandas as pd
import numpy as np

"""
CAPITOLI = ["tree thinking", "protisti"]
TIPO_DOMANDE = ["MC", "FB", "TF"]

cod_domanda = []
cod_tipo = []
cod_capitolo = []


quiz_structure = {
    CAPITOLI[0]: {
        "MC": {"1": {"testo": ["?"]}, "2": {"testo": ["?"]}, "3": {"testo": ["?"]}, "4": {"testo": ["?"]}},
        "FB": {"1": {"testo": ["?"]}, "2": {"testo": ["?"]}, "3": {"testo": ["?"]}, "4": {"testo": ["?"]}},
        "TF": {"1": {"testo": ["?"]}, "2": {"testo": ["?"]}, "3": {"testo": ["?"]}, "4": {"testo": ["?"]}},
    },
    CAPITOLI[1]: {
        "MC": {"1": {"testo": ["?"]}, "2": {"testo": ["?"]}, "3": {"testo": ["?"]}, "4": {"testo": ["?"]}},
        "FB": {"1": {"testo": ["?"]}, "2": {"testo": ["?"]}, "3": {"testo": ["?"]}, "4": {"testo": ["?"]}},
        "TF": {"1": {"testo": ["?"]}, "2": {"testo": ["?"]}, "3": {"testo": ["?"]}, "4": {"testo": ["?"]}},
    },
}


for capitolo in CAPITOLI:
    for tipo in TIPO_DOMANDE:
        for n in np.arange(len(quiz_structure[capitolo][tipo])):
            cod_capitolo.append(capitolo)
            cod_tipo.append(tipo)
            cod_domanda.append(str(n + 1))

print(f"{cod_capitolo=}")
print(f"{cod_tipo=}")
print(f"{cod_domanda=}")
"""


def get_quiz(question_data: dict, topic: str, step: str, n_questions: int, nickname: str, results: pd.DataFrame) -> list:
    ndomande = n_questions
    capX = topic
    risultati = results  # pd.DataFrame({"cod_capitolo": cod_capitolo, "cod_tipo": cod_tipo, "cod_domanda": cod_domanda})

    # risultati["GIACOMO_OK"] = np.round(np.random.uniform(0, 3, 24), 0)
    # risultati["GIACOMO_NO"] = np.round(np.random.uniform(0, 3, 24), 0)

    # valuto il livello di preparazione per quel capitolo
    tipo = risultati[(risultati["topic"] == capX)]["type"]
    risposte = risultati[(risultati["topic"] == capX)]

    risposteOK = np.array(risultati[(risultati["topic"] == capX)]["n_ok"])
    risposteNO = np.array(risultati[(risultati["topic"] == capX)]["n_no"])

    if np.sum(risposteOK) > 0 or np.sum(risposteNO) > 0:
        score = (np.sum(risposteOK) - np.sum(risposteNO)) / (np.sum(risposteOK) + np.sum(risposteNO))
    else:
        score = 0

    # quantifico difficoltà relativa delle domande
    p = np.zeros(np.size(risposteOK))
    for nd in np.arange(np.size(p)):
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
            print(capX)
            print(risposte["type"][i])
            print(risposte["question_name"][i])
            questions_list.append(question_data[capX][risposte["type"][i]][risposte["question_name"][i]])
            print()

    return questions_list
