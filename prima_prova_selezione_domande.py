import pandas as pd
import numpy as np

CAPITOLI = ["tree thinking", "protisti"]
TIPO_DOMANDE = ["MC", "FB", "TF"]

cod_domanda = []
cod_tipo = []
cod_capitolo = []




quiz_structure = {
    CAPITOLI[0]: {
        "MC": {
            "1": {"testo": ["?"]},
            "2": {"testo": ["?"]},
            "3": {"testo": ["?"]},
            "4": {"testo": ["?"]}},
        "FB":  {
            "1": {"testo": ["?"]},
            "2": {"testo": ["?"]},
            "3": {"testo": ["?"]},
            "4": {"testo": ["?"]}},
        "TF":  {
            "1": {"testo": ["?"]},
            "2":  {"testo": ["?"]},
            "3":  {"testo": ["?"]},
            "4":  {"testo": ["?"]}}},
    CAPITOLI[1]: {
        "MC": {
            "1": {"testo": ["?"]},
            "2": {"testo": ["?"]},
            "3": {"testo": ["?"]},
            "4": {"testo": ["?"]}},
        "FB":  {
            "1": {"testo": ["?"]},
            "2": {"testo": ["?"]},
            "3": {"testo": ["?"]},
            "4": {"testo": ["?"]}},
        "TF":  {
            "1": {"testo": ["?"]},
            "2":  {"testo": ["?"]},
            "3":  {"testo": ["?"]},
            "4":  {"testo": ["?"]}}}
        }
    
STUDENTI = {
        }

PESI = {
        "TAPPA1": [1, 0.5, 0.25],
        "TAPPA2": [1, 1, 0.5],
        "TAPPA3": [0.5, 1, 1],
        "TAPPA4": [0.25, 0.5, 1]
        }
PESI = pd.DataFrame(PESI)

STUDENTI = ["GIACOMO", "UMBERTO"]


for capitolo in CAPITOLI:
    for tipo in TIPO_DOMANDE:
        for n in np.arange(len(quiz_structure[capitolo][tipo])):
            cod_capitolo.append(capitolo)
            cod_tipo.append(tipo)
            cod_domanda.append(str(n+1))  

risultati = pd.DataFrame({"cod_capitolo": cod_capitolo, "cod_tipo": cod_tipo, "cod_domanda": cod_domanda})

risultati["GIACOMO_OK"] = np.round(np.random.uniform(0,3,24),0)
risultati["GIACOMO_NO"] = np.round(np.random.uniform(0,3,24),0)


capX = "tree thinking"
studente = "GIACOMO"
# valuto il livello di preparazione per quel capitolo

tipo = risultati[(risultati["cod_capitolo"] == capX)]["cod_tipo"]
risposte = risultati[(risultati["cod_capitolo"] == capX)]

risposteOK = np.array(risultati[(risultati["cod_capitolo"] == capX)][studente+"_OK"])
risposteNO = np.array(risultati[(risultati["cod_capitolo"] == capX)][studente+"_NO"])

if np.sum(risposteOK) >0 or np.sum(risposteNO) > 0:
    score = (np.sum(risposteOK) - np.sum(risposteNO))/(np.sum(risposteOK) + np.sum(risposteNO))
else:
    score = 0
    
# quantifico difficoltà relativa delle domande
p = np.zeros(np.size(risposteOK))
for nd in np.arange(np.size(p)):
    if tipo[nd] == "TF":
        diffic = .1
    elif tipo[nd] == "MC":
        diffic = .25
    else:
        diffic = .40
    if np.sum(risposteNO[nd]) > 0: 
        diffic += 0.5 * (risposteNO[nd] - risposteOK[nd])/(risposteOK[nd] + risposteNO[nd])     
        
    
    p[nd] = np.abs(np.random.uniform(diffic- 0.5, diffic + 0.5, 1) - score)

rank_p = np.argsort(p)
ndomande = 4
for i in np.arange(np.size(p)):
    if rank_p[i] < ndomande:
        domanda = quiz_structure[capX][risposte["cod_tipo"][i]][risposte["cod_domanda"][i]]["testo"]
        print(domanda)
    
