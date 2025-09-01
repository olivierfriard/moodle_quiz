CREATE TABLE courses (
   id SERIAL PRIMARY KEY,
   name TEXT NOT NULL,
   question_types TEXT[],
   initial_life_number  INTEGER,
   topics_to_hide TEXT[],
   topic_question_number  INTEGER,
   steps TEXT[],
   step_quiz_number INTEGER,
   recover_topics TEXT[],
   recover_question_number INTEGER,
   brush_up_question_number INTEGER,
   brush_up_level_names TEXT[],
   brush_up_levels INTEGER[]
);

INSERT INTO courses (name, question_types, initial_life_number, topics_to_hide, topic_question_number, steps, step_quiz_number, recover_question_number, recover_topics, brush_up_question_number, brush_up_level_names, brush_up_levels) VALUES (
'Quizzoo',
'{"truefalse","multichoice", "shortanswer", "numerical"}',
5,
'{"Ripasso e recupero vite"}',
10,
'{"Esploratore", "Ricercatore", "Maestro"}',
4,
5,
'{"Ripasso e recupero vite"}',
10,
'{"Easy", "Hard", "Very hard"}',
'{1, 2, 4}'
);



CREATE TABLE questions (
    id SERIAL PRIMARY KEY,
    course TEXT,
    topic TEXT,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL
);


CREATE TABLE lives (
    id SERIAL PRIMARY KEY,
    course TEXT,
    nickname TEXT NOT NULL UNIQUE,
    number INTEGER DEFAULT 10
);

CREATE TABLE steps (
    id SERIAL PRIMARY KEY,
    course TEXT,
    nickname TEXT NOT NULL,
    topic TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    number INTEGER NOT NULL
);

CREATE TABLE bookmarks (
    id SERIAL PRIMARY KEY,
    course TEXT,
    nickname TEXT NOT NULL UNIQUE,
    question_id INTEGER NOT NULL
);

CREATE TABLE results (
    id SERIAL PRIMARY KEY,
    course TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    nickname TEXT NOT NULL,
    topic TEXT NOT NULL,
    question_type TEXT NOT NULL,
    question_name TEXT NOT NULL,
    good_answer BOOLEAN NOT NULL
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    nickname TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE INDEX idx_results_nickname ON results(nickname);
CREATE INDEX idx_results_topic ON results(topic);
CREATE INDEX idx_questions_topic ON questions(topic);

