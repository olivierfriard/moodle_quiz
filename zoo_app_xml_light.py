import sys
import random
import json
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

N_STEP_QUESTIONS_ = 5

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

# check if file results.json exists

flag_file_present = False
results = {"questions": {}, "finished": {}}
if Path("results.json").is_file():
    try:
        with open("results.json", "r") as file_in:
            results = json.loads(file_in.read())
        flag_file_present = True
    except Exception:
        print("Error loading the results.json file")


# Set the window background color to a light color (RGB + Alpha)
Window.clearcolor = (1, 1, 1, 1)  # White background


class Question(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def menu(self):
        nav_menu = BoxLayout(orientation="horizontal", size_hint_y=0.1)

        # Create buttons for the bottom navigation menu
        home_btn = Button(
            text="Home",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        home_btn.bind(on_release=lambda x: setattr(self.manager, "current", "home"))
        nav_menu.add_widget(home_btn)

        about_btn = Button(
            text="Steps",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        about_btn.bind(on_release=lambda x: setattr(self.manager, "current", "choose_subtopic"))
        nav_menu.add_widget(about_btn)

        btn = Button(
            text="Topics",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        btn.bind(on_release=lambda x: setattr(self.manager, "current", "choose_topic"))
        nav_menu.add_widget(btn)

        return nav_menu

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
                    text=option["text"] if self.question["type"] == "multichoice" else option["text"].upper(),
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

        else:
            print(f"Question type error: {self.question["type"]}")
            return

        layout.add_widget(self.menu())

        self.add_widget(layout)

    def strip_html_tags(self, text):
        # This is a simple method to strip HTML tags
        import re

        clean = re.compile("<.*?>")
        return re.sub(clean, "", text)

    def check_answer(self, instance):
        # Check if the selected option is correct

        def correct_answer():
            if self.question["name"] not in results["questions"]:
                results["questions"][self.question["name"]] = []
            results["questions"][self.question["name"]].append(1)
            return "You selected the correct answer."

        def wrong_answer(correct_answer, feedback):
            if self.question["name"] not in results["questions"]:
                results["questions"][self.question["name"]] = []
            results["questions"][self.question["name"]].append(0)
            # feedback
            if feedback:
                return f"{feedback}\n\nThe correct answer is:\n\n{correct_answer}"
            else:
                return f"The correct answer is:\n\n{correct_answer}"

        # get user answer
        if self.question["type"] in ("truefalse", "multichoice"):
            user_answer = instance.text
        elif self.question["type"] in ("shortanswer", "numerical"):
            user_answer = self.input_box.text.strip()
        else:
            print(f"Question type error: {self.question["type"]}")

        # get correct answer
        correct_answer_str: str = ""
        feedback: str = ""
        for answer in self.question["answers"]:
            if answer["fraction"] == "100":
                correct_answer_str = answer["text"]
            if user_answer == answer["text"]:
                feedback = answer["feedback"] if answer["feedback"] is not None else ""

        text_output = [App.get_running_app().quiz[App.get_running_app().quiz_position]["questiontext"] + "\n\n"]
        if user_answer.upper() == correct_answer_str.upper():
            text_output.append(correct_answer())
        else:
            text_output.append(wrong_answer(correct_answer_str, feedback))

        self.manager.get_screen("feedback").display("\n".join(text_output))
        self.manager.current = "feedback"

    '''
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
    '''


class Feedback(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def display(self, str):
        print(results)
        self.clear_widgets()

        layout = BoxLayout(orientation="vertical")
        # Label
        label = Label(text=str, color="#000000", font_size="30sp", text_size=(int(Window.width * 0.9), None), size_hint_y=0.8)
        layout.add_widget(label)

        nav_menu = BoxLayout(orientation="horizontal", size_hint_y=None)

        home_btn = Button(
            text="Home",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        home_btn.bind(on_release=lambda x: setattr(self.manager, "current", "home"))
        nav_menu.add_widget(home_btn)

        btn = Button(
            text="Next" if App.get_running_app().quiz_position < len(App.get_running_app().quiz) - 1 else "Quiz finished",
            font_size="30sp",
            background_normal="",
            background_color=(0, 0, 0.9, 1),
        )
        btn.bind(on_release=self.next)
        nav_menu.add_widget(btn)

        layout.add_widget(nav_menu)

        self.add_widget(layout)

    def next(self, instance):
        """
        show next question
        """
        App.get_running_app().quiz_position += 1
        if App.get_running_app().quiz_position < len(App.get_running_app().quiz):
            self.manager.get_screen("question").display_question()
            self.manager.current = "question"
        else:  # quiz finished
            if App.get_running_app().current_topic not in results["finished"]:
                results["finished"][App.get_running_app().current_topic] = []
            results["finished"][App.get_running_app().current_topic].append(
                int(App.get_running_app().current_subtopic.removeprefix("Step "))
            )
            self.manager.get_screen("choose_subtopic").show_subtopic()
            self.manager.current = "choose_subtopic"


class Home(Screen):
    """
    app home page
    """

    def confirm_quit(self, instance):
        # Create a confirmation popup
        layout = BoxLayout(orientation="vertical")
        message = Label(text="Are you sure you want to quit?")
        layout.add_widget(message)

        button_layout = BoxLayout(orientation="horizontal", size_hint=(1, 0.3))

        yes_button = Button(text="Yes")
        yes_button.bind(on_press=self.quit_app)
        button_layout.add_widget(yes_button)

        no_button = Button(text="No")
        no_button.bind(on_press=self.close_popup)
        button_layout.add_widget(no_button)

        layout.add_widget(button_layout)

        self.popup = Popup(title="Confirm Quit", content=layout, size_hint=(0.6, 0.4), auto_dismiss=False)
        self.popup.open()

    def quit_app(self, instance):
        self.popup.dismiss()  # Close the popup

        # save results.json
        try:
            with open("results.json", "w") as file_out:
                file_out.write(json.dumps(results))
        except Exception:
            print("Error saving the results.json file")

        sys.exit()  # Quit the app

    def close_popup(self, instance):
        self.popup.dismiss()  # Just close the popup

    def menu(self):
        nav_menu = BoxLayout(orientation="horizontal", size_hint_y=None)

        # Create buttons for the bottom navigation menu
        settings_btn = Button(text="Start", font_size="30sp")
        settings_btn.bind(on_release=lambda x: setattr(self.manager, "current", "choose_topic"))
        nav_menu.add_widget(settings_btn)

        about_btn = Button(text="About", font_size="30sp")
        about_btn.bind(on_release=lambda x: setattr(self.manager, "current", "about"))
        nav_menu.add_widget(about_btn)

        quit_btn = Button(text="Quit", font_size="30sp")
        quit_btn.bind(on_release=self.confirm_quit)
        nav_menu.add_widget(quit_btn)

        return nav_menu

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation="vertical")
        # Label
        label = Label(text="Hi!", color="#000000", font_size="30sp", text_size=(int(Window.width * 0.9), None), size_hint_y=0.8)
        layout.add_widget(label)

        layout.add_widget(self.menu())

        self.add_widget(layout)

    def start_button_pressed(self, instance):
        # Switch to another screen when the button is pressed
        self.manager.current = "choose_topic"


class ChooseTopic(Screen):
    def menu(self):
        nav_menu = BoxLayout(orientation="horizontal", size_hint_y=None)

        # Create buttons for the bottom navigation menu
        home_btn = Button(
            text="Home",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        home_btn.bind(on_release=lambda x: setattr(self.manager, "current", "home"))
        nav_menu.add_widget(home_btn)

        return nav_menu

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        scrollwidget_layout = ScrollView(size_hint=(1, None), size=(Window.width, Window.height))

        main_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)

        main_layout.bind(minimum_height=main_layout.setter("height"))

        # Add the menu to the main layout
        main_layout.add_widget(self.menu())

        for topic in question_data:
            btn = Button(text=topic, size_hint_y=None, font_size="30sp", on_release=lambda btn: self.choose_subtopic(btn.text))
            main_layout.add_widget(btn)

        scrollwidget_layout.add_widget(main_layout)

        self.add_widget(scrollwidget_layout)

    def choose_subtopic(self, topic):
        App.get_running_app().current_topic = topic
        self.manager.get_screen("choose_subtopic").show_subtopic()
        self.manager.current = "choose_subtopic"


class ChooseSubTopic(Screen):
    def menu(self):
        nav_menu = BoxLayout(orientation="horizontal", size_hint_y=None)

        # Create buttons for the bottom navigation menu
        home_btn = Button(
            text="Home",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        home_btn.bind(on_release=lambda x: setattr(self.manager, "current", "home"))
        nav_menu.add_widget(home_btn)

        settings_btn = Button(
            text="Topics",
            font_size="20sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        settings_btn.bind(on_release=lambda x: setattr(self.manager, "current", "choose_topic"))
        nav_menu.add_widget(settings_btn)

        return nav_menu

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def show_subtopic(self):
        self.clear_widgets()
        scrollwidget_layout = ScrollView(size_hint=(1, None), size=(Window.width, Window.height))
        main_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        main_layout.bind(minimum_height=main_layout.setter("height"))

        # Add the menu to the main layout
        main_layout.add_widget(self.menu())

        main_layout.add_widget(
            Label(
                text=App.get_running_app().current_topic,
                color="#000000",
                size_hint_y=None,
                font_size="30sp",
                text_size=(int(Window.width * 0.9), None),
            )
        )

        for i in range(1, STEP_NUMBER + 1):
            if i == 1:
                disabled = False
            else:
                disabled = i - 1 not in results["finished"].get(App.get_running_app().current_topic, [])

            btn = Button(
                text=f"Step {i}",
                size_hint_y=None,
                font_size="30sp",
                disabled=disabled,
                on_release=lambda btn: self.start_subtopic(btn.text),
            )
            main_layout.add_widget(btn)

        scrollwidget_layout.add_widget(main_layout)

        self.add_widget(scrollwidget_layout)

    def start_subtopic(self, subtopic):
        App.get_running_app().current_subtopic = subtopic

        App.get_running_app().quiz = quiz.get_quiz(
            question_data, App.get_running_app().current_topic, App.get_running_app().current_subtopic, N_STEP_QUESTIONS_, results
        )
        App.get_running_app().quiz_position = 0

        # results["finished"][App.get_running_app().current_topic] = []

        self.manager.get_screen("question").display_question()
        self.manager.current = "question"


class About(Screen):
    def menu(self):
        nav_menu = BoxLayout(orientation="horizontal", size_hint_y=None)

        # Create buttons for the bottom navigation menu
        home_btn = Button(
            text="Home",
            font_size="30sp",
            color="#ffffff",
            background_normal="",
            background_color=(0, 0, 0, 1),
        )
        home_btn.bind(on_release=lambda x: setattr(self.manager, "current", "home"))
        nav_menu.add_widget(home_btn)

        return nav_menu

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = BoxLayout(orientation="vertical")
        # Label
        label = Label(text="About...", color="#000000", font_size="30sp", text_size=(int(Window.width * 0.9), None), size_hint_y=0.8)
        layout.add_widget(label)

        layout.add_widget(self.menu())

        self.add_widget(layout)


class QuizApp(App):
    current_topic: str = ""
    current_subtopic: str = ""
    quiz: list = []
    quiz_position: int = 0

    def build(self):
        sm = ScreenManager()
        sm.add_widget(Home(name="home"))
        sm.add_widget(About(name="about"))
        sm.add_widget(ChooseTopic(name="choose_topic"))
        sm.add_widget(ChooseSubTopic(name="choose_subtopic"))
        sm.add_widget(Question(name="question"))
        sm.add_widget(Feedback(name="feedback"))
        return sm


if __name__ == "__main__":
    QuizApp().run()
