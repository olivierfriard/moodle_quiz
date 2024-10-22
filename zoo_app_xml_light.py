import kivy
import random
import sys
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


# question handled by app
QUESTION_TYPES = ["truefalse", "multichoice", "shortanswer", "numerical"]


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
            category_text = question.find("category/text").text.removeprefix("$course$/top/")
            category_tuple = tuple(category_text.split("/")[1:])  # delele first catogory (with Default ...))

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

            # Add the question to the respective category
            categories_dict[current_category].append(question_dict)

    return dict(categories_dict)


xml_file = "data.xml"
question_data = moodle_xml_to_dict_with_images(xml_file)
print()
for category in question_data.keys():
    print(f"{category}: {len(question_data[category])}")
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
        print()

        # check if images to display
        if self.question["files"]:
            # Load and display the PNG image
            img = Image(source=str(Path("files") / Path(self.question["files"][0])))
            self.add_widget(img)

        # Display the options with light theme buttons
        if question["type"] == "multichoice" or question["type"] == "truefalse":
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
            self.add_widget(self.question_label)

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

        elif question["type"] in ("shortanswer", "numerical"):
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
            self.add_widget(self.question_label)

            self.input_box = TextInput(
                hint_text="Enter something here",
                multiline=False,
                size_hint_y=0.4,
                font_size="30sp",
            )
            self.add_widget(self.input_box)
            submit_button = Button(
                text="Submit",
                size_hint_y=0.1,
                font_size="20sp",
                background_normal="",
                background_color=(0, 0, 0.9, 1),
            )
            submit_button.bind(on_press=self.check_answer)
            self.add_widget(submit_button)

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

        if self.question["type"] in ("truefalse", "multichoice"):
            if instance.text == correct_answer:
                self.show_popup("Correct!", "You selected the correct answer.")
            else:
                self.show_popup("Incorrect!", f"The correct answer is:\n\n{correct_answer}")

        elif self.question["type"] == "shortanswer":
            if self.input_box.text.strip().upper() == correct_answer.strip().upper():
                self.show_popup("Correct!", "You selected the correct answer.")
            else:
                self.show_popup("Incorrect!", f"The correct answer is:\n\n{correct_answer}")
        else:
            print(f"Question type error: {self.question["type"]}")

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
        while True:
            if CATEGORY:
                random_question = random.choice(question_data[CATEGORY])
            else:
                random_question = random.choice(
                    [item for sublist in [[q for q in question_data[cat]] for cat in question_data] for item in sublist]
                )
            if random_question["type"] in QUESTION_TYPES:
                break

        # Display the question
        self.question_box = QuestionBox(random_question)
        self.root.add_widget(self.question_box)


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

        # layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        # title_label = Label(text="Scegli un argomento", font_size="20sp", size_hint=(1, 0.2))
        # layout.add_widget(title_label)

        # grid_layout = GridLayout(cols=1, rows=len(question_data), spacing=10, size_hint=(1, 0.8))
        for topic in question_data:
            print(topic)
            btn = Button(text=" / ".join(topic), size_hint_y=None, on_release=lambda btn: self.choose_subtopic(btn.text))
            main_layout.add_widget(btn)

        # layout.add_widget(grid_layout)
        # self.add_widget(layout)

        scrollwidget_layout.add_widget(main_layout)

        self.add_widget(scrollwidget_layout)

    def choose_subtopic(self, topic):
        # Passa alla schermata del percorso
        self.manager.get_screen("choose_subtopic").set_topic(topic)
        self.manager.current = "choose_subtopic"


class ChooseSubTopic(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        scrollwidget_layout = ScrollView(size_hint=(1, None), size=(Window.width, Window.height))
        main_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        main_layout.bind(minimum_height=main_layout.setter("height"))

        # layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        # title_label = Label(text="Scegli un argomento", font_size="20sp", size_hint=(1, 0.2))
        # layout.add_widget(title_label)

        # grid_layout = GridLayout(cols=1, rows=len(question_data), spacing=10, size_hint=(1, 0.8))
        for topic in question_data:
            if 
            print(topic)
            btn = Button(text=" / ".join(topic), size_hint_y=None, on_release=lambda btn: self.start_subtopic(btn.text))
            main_layout.add_widget(btn)

        # layout.add_widget(grid_layout)
        # self.add_widget(layout)

        scrollwidget_layout.add_widget(main_layout)

        self.add_widget(scrollwidget_layout)

    def set_topic(self, topic):
        """Imposta l'argomento selezionato"""
        self.topic = topic

    def start_subtopic(self, topic):
        # Passa alla schermata del percorso
        self.manager.get_screen("topic").set_topic(topic)
        self.manager.current = "topic"


'''class Topic(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.topic = None
        self.tappa = 0
        self.max_tappe = 5  # Numero di tappe
        self.layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        self.tappa_label = Label(text="Tappa 1", font_size="20sp", size_hint=(1, 0.2))
        self.layout.add_widget(self.tappa_label)
        self.start_button = Button(text="Inizia tappa", size_hint=(1, 0.2), on_release=self.start_tappa)
        self.layout.add_widget(self.start_button)
        self.add_widget(self.layout)

    def set_topic(self, topic):
        """Imposta l'argomento selezionato"""
        self.topic = topic
        self.tappa = 1
        self.tappa_label.text = f"Tappa {self.tappa}"
'''


class QuizApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(Home(name="home"))
        sm.add_widget(ChooseTopic(name="choose_topic"))
        sm.add_widget(ChooseSubTopic(name="choose_subtopic"))
        # sm.add_widget(Topic(name="topic"))
        return sm


if __name__ == "__main__":
    QuizApp().run()
