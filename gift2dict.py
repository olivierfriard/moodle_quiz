import re


def parse_gift_file_with_names_and_feedback(file_path):
    """
    Parses a GIFT format file, including question names and feedback, and stores the information in a dictionary.

    Args:
        file_path (str): The path to the GIFT file.

    Returns:
        list: A list of dictionaries with question details, including names and feedback.
    """
    questions = []

    with open(file_path, "r") as file:
        content = [x.strip() for x in file.readlines()]

    idx = 0
    open_question = False
    while True:
        if "::" in content[idx] and not open_question:
            open_question = True
        if content[idx] == "}" and open_question:
            open_question = False
            print("-" * 30)
        if open_question:
            print(content[idx])

        idx += 1

    """
    # Split the content into individual questions
    question_blocks = re.split(r"\n(?=\s*[^\n]*\{)", content)

    for block in question_blocks:
        print(block)
        print("-" * 20)

        input()

        question_dict = {}

        # Extract question name (::name::)
        name_match = re.match(r"::(.*?)::", block)
        if name_match:
            question_dict["name"] = name_match.group(1).strip()
            block = block[
                name_match.end() :
            ]  # Remove name part from block for further parsing

        # Extract question text
        question_match = re.match(r"(.*)\{", block, re.DOTALL)
        if question_match:
            question_text = question_match.group(1).strip()
            question_dict["question"] = question_text

        # Extract general feedback (#### General Feedback)
        general_feedback_match = re.search(r"####\s*(.*)", block)
        if general_feedback_match:
            question_dict["general_feedback"] = general_feedback_match.group(1).strip()

        # Check for True/False questions
        tf_match = re.search(r"\{\s*([TtFf])\s*(#.*?)?\}", block)
        if tf_match:
            question_dict["type"] = "true/false"
            question_dict["answer"] = (
                True if tf_match.group(1).lower() == "t" else False
            )
            if tf_match.group(2):
                question_dict["feedback"] = tf_match.group(2).strip("#").strip()

        # Check for Multiple Choice questions
        mc_match = re.search(r"\{\s*(.*?)\s*\}", block, re.DOTALL)
        if mc_match:
            choices = mc_match.group(1).splitlines()
            if "=" in choices[0] or "~" in choices[0]:  # MC format check
                question_dict["type"] = "multiple choice"
                question_dict["choices"] = []
                for choice in choices:
                    choice_text = re.match(r"([=~])(.*?)(#.*?)?$", choice)
                    if choice_text:
                        correctness = choice_text.group(1) == "="
                        answer = choice_text.group(2).strip()
                        feedback = (
                            choice_text.group(3).strip("#").strip()
                            if choice_text.group(3)
                            else None
                        )
                        question_dict["choices"].append(
                            {
                                "answer": answer,
                                "correct": correctness,
                                "feedback": feedback,
                            }
                        )

        # Check for Fill-in-the-Blank questions
        fb_match = re.search(r"\{\s*=(.*?)\s*(#.*?)?\}", block, re.DOTALL)
        if fb_match:
            question_dict["type"] = "fill-in-the-blank"
            question_dict["correct_answer"] = fb_match.group(1).strip()
            if fb_match.group(2):
                question_dict["feedback"] = fb_match.group(2).strip("#").strip()

        if question_dict:
            questions.append(question_dict)
    """
    return questions


q = parse_gift_file_with_names_and_feedback("courses/alimentazione.gift")

# print(q)
