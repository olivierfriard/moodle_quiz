import kivy
import random
import sys
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.core.window import Window
from pathlib import Path


def moodle_xml_to_dict_with_images(xml_file):
    """
    Convert a Moodle XML question file into a Python dictionary, organizing questions by categories and decoding images from base64.

    Args:
        xml_file (str): Path to the XML file.

    Returns:
        dict: A dictionary with categories as keys and lists of questions as values.
    """

    import xml.etree.ElementTree as ET
    import base64
    from collections import defaultdict

    def strip_html_tags(text):
        # This is a simple method to strip HTML tags
        import re

        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Dictionary to hold questions organized by category
    categories_dict = defaultdict(list)
    current_category = "Uncategorized"

    # Parse the XML tree
    for question in root.findall("question"):
        question_type = question.get("type")

        # Handle category change
        if question_type == "category":
            category_text = question.find("category/text").text
            current_category = category_text if category_text else current_category

        # Handle actual questions
        else:
            question_dict = {
                "type": question_type,
                "name": question.find("name/text").text if question.find("name/text") is not None else None,
                "questiontext": strip_html_tags(
                    question.find("questiontext/text").text if question.find("questiontext/text") is not None else None
                ),
                "answers": [],
                "feedback": {},
                "files": [],  # To store files related to the question
            }

            # Process feedback
            question_dict["feedback"]["correct"] = (
                question.find("correctfeedback/text").text if question.find("correctfeedback/text") is not None else None
            )
            question_dict["feedback"]["partiallycorrect"] = (
                question.find("partiallycorrectfeedback/text").text if question.find("partiallycorrectfeedback/text") is not None else None
            )
            question_dict["feedback"]["incorrect"] = (
                question.find("incorrectfeedback/text").text if question.find("incorrectfeedback/text") is not None else None
            )

            # Process answers
            for answer in question.findall("answer"):
                answer_dict = {
                    "fraction": answer.get("fraction"),
                    "text": strip_html_tags(answer.find("text").text if answer.find("text") is not None else None),
                    "feedback": answer.find("feedback/text").text if answer.find("feedback/text") is not None else None,
                }
                question_dict["answers"].append(answer_dict)

            # Process files (decode base64 encoded content)
            file_list = question.findall("questiontext/file")
            # print(f"{file_list=}")
            for file_ in file_list:
                # print(f"{file_.get("name")=}")
                # print(f"{file_.text=}")
                # print()

                # save base64 str into file
                with open(Path("files") / Path(file_.get("name")), "wb") as file:
                    file.write(base64.b64decode(file_.text))

                question_dict["files"].append(file_.get("name"))

            # Add the question to the respective category
            categories_dict[current_category].append(question_dict)

    return dict(categories_dict)


xml_file = sys.argv[1]
question_data = moodle_xml_to_dict_with_images(xml_file)
print(question_data)
print()

CATEGORY = "$course$/top/Default per ZooSist/KAHOOT/tree_thinking"

CATEGORY = "$course$/top/Default per ZooSist/KAHOOT"

CATEGORY = ""

# Set the window background color to a light color (RGB + Alpha)
Window.clearcolor = (1, 1, 1, 1)  # White background


class QuestionBox(BoxLayout):
    def __init__(self, question, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.question = question
        print(self.question)

        # check if images to display
        if self.question["files"]:
            # Load and display the PNG image
            img = Image(source=str(Path("files") / Path(self.question["files"][0])))
            self.add_widget(img)

        # Display the question with light theme colors
        self.question_label = Label(
            text=self.question["questiontext"],
            text_size=(int(Window.width * 0.9), None),
            valign="top",
            halign="center",
            size_hint_y=0.2,
            # height=100,
            color=(0, 0, 0, 1),  # Black text
            font_size="30sp",
        )
        self.add_widget(self.question_label)

        # Display the options with light theme buttons
        self.option_buttons = []
        for option in random.sample(self.question["answers"], len(self.question["answers"])):
            btn = Button(
                text=option["text"],
                text_size=(int(Window.width * 0.9), None),
                valign="top",
                halign="center",
                size_hint_y=0.1,
                # height=50,
                background_normal="",
                background_color=(0.9, 0.9, 0.9, 1),
                color=(0, 0, 0, 1),
                font_size="20sp",
            )  # Black text
            btn.bind(on_press=self.check_answer)
            self.option_buttons.append(btn)
            self.add_widget(btn)

    def strip_html_tags(self, text):
        # This is a simple method to strip HTML tags
        import re

        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    def check_answer(self, instance):
        # Check if the selected option is correct
        flag_OK = False
        correct_answer = ""
        for answer in self.question["answers"]:
            if answer["fraction"] == "100":
                correct_answer = answer["text"]
                if instance.text == answer["text"]:
                    self.show_popup("Correct!", "You selected the correct answer.")
                    flag_OK = True
                    break
        if not flag_OK:
            self.show_popup("Incorrect!", f"The correct answer is:\n\n{correct_answer}")

    def show_popup(self, title, message):
        """
        display the system answer
        """
        popup_content = BoxLayout(orientation="vertical")
        label = Label(
            text=message,
            text_size=(int(Window.width * 0.5), None),
            font_size="25sp",
            color=(0, 0, 0, 1),
        )  # Black text
        popup_content.add_widget(label)

        close_btn = Button(
            text="Close",
            font_size="20sp",
            size_hint=(1, 0.25),
            background_normal="",
            background_color=(0.9, 0.9, 0.9, 1),  # Light gray background
            color=(0, 0, 0, 1),
        )  # Black text
        popup_content.add_widget(close_btn)

        popup = Popup(
            title=title,
            content=popup_content,
            size_hint=(0.7, 0.5),
            title_color=(0, 0, 0, 1),  # Black title text
            background="",
            background_color=(1, 1, 1, 1),
        )  # White background
        close_btn.bind(on_press=popup.dismiss)
        popup.open()


class RandomQuestionApp(App):
    def build(self):
        self.root = BoxLayout(orientation="vertical")

        # Button to get a random question with light theme
        self.random_btn = Button(
            text="Show Random Question",
            size_hint_y=None,
            height=50,
            background_normal="",
            background_color=(0.8, 0.8, 0.8, 1),  # Light background
            color=(0, 0, 0, 1),
            font_size="30sp",
        )  # Black text
        self.random_btn.bind(on_press=self.show_random_question)
        self.root.add_widget(self.random_btn)

        # Placeholder for the question display
        self.question_box = None

        return self.root

    def show_random_question(self, instance):
        # Clear the current question if any
        if self.question_box:
            self.root.remove_widget(self.question_box)

        # Select a random question
        if CATEGORY:
            random_question = random.choice(question_data[CATEGORY])
        else:
            random_question = random.choice(
                [item for sublist in [[q for q in question_data[cat]] for cat in question_data] for item in sublist]
            )

        # Display the question
        self.question_box = QuestionBox(random_question)
        self.root.add_widget(self.question_box)


if __name__ == "__main__":
    RandomQuestionApp().run()
