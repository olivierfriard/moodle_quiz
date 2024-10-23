import kivy
import random
import sys
import quiz
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.core.window import Window
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from pathlib import Path


STEP_NUMBER = 4

STEP_NAME = "Tappa"

# question handled by app
QUESTION_TYPES = ["truefalse", "multichoice", "shortanswer", "numerical"]

BASE_CATEGORY = "Auto-apprendimento"


def moodle_xml_to_dict_with_images(xml_file: str, base_category: str) -> dict:
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
            category_text = question.find("category/text").text.removeprefix("$course$/top/")
            category_list = category_text.split("/")[1:]  # delele first category (with Default ...))
            if base_category in category_list:
                category_list.remove(base_category)

            category_tuple = tuple(category_list)

            # current_category = category_text if category_text else current_category
            current_category = category_tuple if category_tuple else current_category

        # Handle actual questions
        else:
            # check if question type is allowed
            if question_type not in QUESTION_TYPES:
                continue

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
                if not Path("files").is_dir():
                    Path("files").mkdir(parents=True, exist_ok=True)
                with open(Path("files") / Path(file_.get("name")), "wb") as file:
                    file.write(base64.b64decode(file_.text))

                question_dict["files"].append(file_.get("name"))

            if len(current_category) == 2:
                # Add the question to the respective category
                if current_category[0] not in categories_dict:
                    categories_dict[current_category[0]] = {}
                if current_category[1] not in categories_dict[current_category[0]]:
                    categories_dict[current_category[0]][current_category[1]] = []
                categories_dict[current_category[0]][current_category[1]].append(question_dict)

    return dict(categories_dict)


xml_file = "data.xml"
question_data = moodle_xml_to_dict_with_images(xml_file, BASE_CATEGORY)
print()
for topic in question_data.keys():
    print(topic)
    for subtopic in question_data[topic]:
        print(f"   {subtopic}: {len(question_data[topic][subtopic])} questions")
    print()
print()

CATEGORY = "$course$/top/Default per ZooSist/KAHOOT/tree_thinking"

CATEGORY = "$course$/top/Default per ZooSist/KAHOOT"

CATEGORY = ""

# Set the window background color to a light color (RGB + Alpha)
Window.clearcolor = (1, 1, 1, 1)  # White background


class Question(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def display_question(self):
        self.clear_widgets()
        print("display question")
        # get question from quiz
        if App.get_running_app().quiz_position < len(App.get_running_app().quiz):
            self.question = App.get_running_app().quiz[App.get_running_app().quiz_position]
        else:
            print("quiz finished")

        print(f"{self.question=}")

        layout = BoxLayout(orientation="vertical", spacing=10)

        # check if images to display
        if self.question["files"]:
            # Load and display the PNG image
            img = Image(source=str(Path("files") / Path(self.question["files"][0])))
            layout.add_widget(img)

        # Display the options with light theme buttons
        if self.question["type"] == "multichoice" or self.question["type"] == "truefalse":
            # Display the question
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
            layout.add_widget(self.question_label)

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
                layout.add_widget(btn)

            self.add_widget(layout)

        elif self.question["type"] in ("shortanswer", "numerical"):
            # Display the question
            self.question_label = Label(
                text=self.question["questiontext"],
                text_size=(int(Window.width * 0.9), None),
                valign="top",
                halign="center",
                size_hint_y=0.5,
                # height=100,
                color=(0, 0, 0, 1),  # Black text
                font_size="30sp",
            )
            layout.add_widget(self.question_label)

            self.input_box = TextInput(
                hint_text="Enter something here",
                multiline=False,
                size_hint_y=0.4,
                font_size="30sp",
            )
            layout.add_widget(self.input_box)
            submit_button = Button(
                text="Submit",
                size_hint_y=0.1,
                font_size="20sp",
                background_normal="",
                background_color=(0, 0, 0.9, 1),
            )
            submit_button.bind(on_press=self.check_answer)
            layout.add_widget(submit_button)

            self.add_widget(layout)

        else:
            print(f"Question type error: {self.question["type"]}")

    def strip_html_tags(self, text):
        # This is a simple method to strip HTML tags
        import re

        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    def check_answer(self, instance):
        # Check if the selected option is correct

        correct_answer: str = ""
        for answer in self.question["answers"]:
            if answer["fraction"] == "100":
                correct_answer = answer["text"]
                break
        text_output = [App.get_running_app().quiz[App.get_running_app().quiz_position]["questiontext"] + "\n\n"]
        if self.question["type"] in ("truefalse", "multichoice"):
            if instance.text == correct_answer:
                text_output.append("You selected the correct answer.")
            else:
                text_output.append(f"The correct answer is:\n\n{correct_answer}")

        elif self.question["type"] in ("shortanswer", "numerical"):
            if self.input_box.text.strip().upper() == correct_answer.strip().upper():
                text_output.append("You selected the correct answer.")
            else:
                text_output.append(f"The correct answer is:\n\n{correct_answer}")
        else:
            print(f"Question type error: {self.question["type"]}")

        self.manager.get_screen("feedback").display(text_output)
        self.manager.current = "feedback"

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


class Feedback(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def display(self, str):
        self.clear_widgets()

        layout = BoxLayout(orientation="vertical")
        # Label
        label = Label(text=str, color="#000000", font_size="30sp", text_size=(int(Window.width * 0.9), None), size_hint_y=0.8)
        layout.add_widget(label)

        btn = Button(
            text="Next" if App.get_running_app().quiz_position < len(App.get_running_app().quiz) - 1 else "Quiz finished",
            size_hint_y=0.2,
        )
        btn.bind(on_release=self.next)
        layout.add_widget(btn)

        self.add_widget(layout)

    def next(self, instance):
        """
        show next question
        """
        App.get_running_app().quiz_position += 1
        if App.get_running_app().quiz_position < len(App.get_running_app().quiz):
            self.manager.get_screen("question").display_question()
            self.manager.current = "question"
        else:
            self.manager.get_screen("choose_subtopic").show_subtopic()
            self.manager.current = "choose_subtopic"


class Home(Screen):
    """
    app home page
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical")
        start_button = Button(text="Start", font_size="50sp")
        start_button.bind(on_press=self.start_button_pressed)
        layout.add_widget(start_button)
        self.add_widget(layout)

    def start_button_pressed(self, instance):
        # Switch to another screen when the button is pressed
        self.manager.current = "choose_topic"


class ChooseTopic(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        scrollwidget_layout = ScrollView(size_hint=(1, None), size=(Window.width, Window.height))
        main_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        main_layout.bind(minimum_height=main_layout.setter("height"))

        for topic in question_data:
            print(topic)
            btn = Button(text=topic, size_hint_y=None, on_release=lambda btn: self.choose_subtopic(btn.text))
            main_layout.add_widget(btn)

        scrollwidget_layout.add_widget(main_layout)

        self.add_widget(scrollwidget_layout)

    def choose_subtopic(self, topic):
        App.get_running_app().current_topic = topic
        self.manager.get_screen("choose_subtopic").show_subtopic()
        self.manager.current = "choose_subtopic"


class ChooseSubTopic(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def show_subtopic(self):
        scrollwidget_layout = ScrollView(size_hint=(1, None), size=(Window.width, Window.height))
        main_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        main_layout.bind(minimum_height=main_layout.setter("height"))

        for i in range(1, STEP_NUMBER + 1):
            btn = Button(text=f"{STEP_NAME } {i}", size_hint_y=None, on_release=lambda btn: self.start_subtopic(btn.text))
            main_layout.add_widget(btn)

        scrollwidget_layout.add_widget(main_layout)

        self.add_widget(scrollwidget_layout)

    def start_subtopic(self, subtopic):
        # Passa alla schermata del percorso
        App.get_running_app().current_subtopic = subtopic

        print(App.get_running_app().current_topic)
        print(App.get_running_app().current_subtopic)

        App.get_running_app().quiz = quiz.get_quiz(
            question_data, App.get_running_app().current_topic, App.get_running_app().current_subtopic
        )
        App.get_running_app().quiz_position = 0

        self.manager.get_screen("question").display_question()
        self.manager.current = "question"

        # self.manager.get_screen("subtopic").get_quiz()
        # self.manager.current = "subtopic"


class QuizApp(App):
    current_topic: str = ""
    current_subtopic: str = ""
    quiz: list = []
    quiz_position: int = 0

    def build(self):
        sm = ScreenManager()
        sm.add_widget(Home(name="home"))
        sm.add_widget(ChooseTopic(name="choose_topic"))
        sm.add_widget(ChooseSubTopic(name="choose_subtopic"))
        sm.add_widget(Question(name="question"))
        sm.add_widget(Feedback(name="feedback"))
        return sm


if __name__ == "__main__":
    QuizApp().run()
