import quiz
import sqlite3
import pandas as pd
import numpy as np
import hashlib


def get_db(database_name):
    db = sqlite3.connect(database_name)
    db.row_factory = sqlite3.Row
    return db


NICKNAME = "sergio"
TOPIC = "5 - Cnidari"
N_TAPPE = 3

with get_db("quiz.sqlite") as db:
    # Execute the query
    query = """
            SELECT 
                q.id AS question_id,
                q.topic AS topic, 
                q.type AS type, 
                q.name AS question_name, 
                SUM(CASE WHEN good_answer = 1 THEN 1 ELSE 0 END) AS n_ok,
                SUM(CASE WHEN good_answer = 0 THEN 1 ELSE 0 END) AS n_no
            FROM questions q LEFT JOIN results r 
                ON q.topic=r.topic 
                    AND q.type=r.question_type 
                    AND q.name=r.question_name
                    AND nickname = ?
            GROUP BY 
                q.topic, 
                q.type, 
                q.name
            """

    cursor = db.execute(query, (NICKNAME,))
    # Fetch all rows
    rows = cursor.fetchall()
    # Get column names from the cursor description
    columns = [description[0] for description in cursor.description]

    df_results = pd.DataFrame(rows, columns=columns)

print(df_results.columns)

seed = hash_obj = int(hashlib.md5((NICKNAME + TOPIC).encode()).hexdigest(), 16)

df_tappe = quiz.crea_tappe(df_results, TOPIC, N_TAPPE, 10, seed)

print(df_tappe[0])
