from selenium.webdriver.chrome.options import Options
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium import webdriver
from selenium.webdriver.common.by import By
import json
from typing import Callable, TypedDict, Protocol, Union
import logging
from selenium.webdriver.remote.remote_connection import LOGGER

LOGGER.setLevel(logging.WARNING)
import threading
import queue

from dirty.env import (
    SAMPLE_RATE_MS,
    THINKERCAD_URL,
    DEBUGGER_PORT,
)


class QueueProtocol(Protocol):
    def get(self):
        pass

    def put(self, obj, block: bool = True, timeout: Union[float, None] = None) -> None:
        pass

    def task_done(self) -> None:
        pass


class Sample(TypedDict):
    time: int
    ...


def open_simulation() -> WebDriver:
    # Specify the debugging address for the already opened Chrome browser
    debugger_address = f"localhost:{DEBUGGER_PORT}"

    # Set up ChromeOptions and connect to the existing browser
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", debugger_address)

    # Initialize the WebDriver with the existing Chrome instance
    driver = webdriver.Chrome(options=chrome_options)
    # Now, you can interact with the already opened Chrome browser
    print(f"Driver opens url={THINKERCAD_URL}")
    driver.get(THINKERCAD_URL)
    try:
        WebDriverWait(driver=driver, timeout=10).until(
            EC.presence_of_element_located((By.ID, "CODE_EDITOR_ID"))
        )
    except:
        print("Failed to load page in specified timeout due to indicator")
        driver.quit()
        exit(1)
    return driver


def is_code_panel_open(driver: WebDriver):
    code_panel = driver.find_element(by=By.CLASS_NAME, value="code_panel")
    code_panel_right_position = code_panel.value_of_css_property(property_name="right")
    return code_panel_right_position == "0px"


def open_code_editor(driver: WebDriver):
    is_open = is_code_panel_open(driver=driver)
    if not is_open:
        open_code_editor_button = driver.find_element(by=By.ID, value="CODE_EDITOR_ID")
        open_code_editor_button.click()
    while not is_open:
        driver.implicitly_wait(0.1)
        is_open = is_code_panel_open(driver=driver)


def open_serial_monitor(driver: WebDriver):
    open_code_editor(driver=driver)
    open_serial_monitor_button = driver.find_element(
        by=By.ID, value="SERIAL_MONITOR_ID"
    )
    open_serial_monitor_button.click()


def start_simulation(driver: WebDriver):
    start_simulation_button = driver.find_element(by=By.ID, value="SIMULATION_ID")
    start_simulation_button.click()


def sample_serial_monitor(
    driver: WebDriver,
    on_new_read: Callable[[list[Sample]], None],
    stop_event: threading.Event,
):
    # so basically serial monitor is bound to max line of 60
    # so reading all of it all the time and take last should be fine as long as
    # the service output in less frequent than the python read rate
    while not stop_event.is_set():
        serial_content = driver.find_element(
            by=By.CLASS_NAME, value="code_panel__serial__content__text"
        )
        text = serial_content.get_attribute("innerHTML")
        if text is None:
            print("serial monitor text is None")
            continue
        samples = extract_valid_samples(text)
        on_new_read(samples)
        driver.implicitly_wait(SAMPLE_RATE_MS / 1000)


def extract_valid_samples(data: str):
    samples: list[Sample] = []
    lines = data.split("\n")
    for line in lines:
        try:
            sample: Sample = json.loads(line)
            if not isinstance(sample, dict):
                continue
            if not "time" in sample:
                print(f"sample={sample} has no .time key, skipping...")
                continue
            samples.append(sample)
        except ValueError:
            # print(f'faled to load incomplete line={line}')
            # that's expected...
            pass
    return samples


def watch(
    driver: WebDriver,
    on_next_read: Callable[[Sample], None],
    stop_event: threading.Event,
):
    last_sample_time = -1

    def on_new_read(new_samples: list[Sample]):
        nonlocal last_sample_time
        delta_samples: list[Sample] = []
        if len(new_samples) == 0:
            return
        for sample in new_samples:
            if sample["time"] > last_sample_time:
                delta_samples.append(sample)

        last_sample_time = new_samples[-1]["time"]

        for sample in delta_samples:
            on_next_read(sample)

    sample_serial_monitor(driver=driver, on_new_read=on_new_read, stop_event=stop_event)


def speak_with_serial_monitor(
    driver: WebDriver, messages_queue: QueueProtocol, stop_event: threading.Event
):
    while not stop_event.is_set():
        driver.implicitly_wait(1)
        message = messages_queue.get()
        if message is None:
            print("message is none")
            continue
        serial_input = driver.find_element(
            by=By.CLASS_NAME, value="code_panel__serial__input"
        )
        if serial_input is None:
            print("cannot find serial input")
            continue
        serial_input.send_keys(message)
        serial_input.send_keys(Keys.ENTER)
        messages_queue.task_done()


class SerialMonitorInterface:
    __slots__ = (
        "driver",
        "messages_to_send_queue",
        "sender_thread",
        "watcher_thread",
        "stop_event",
    )

    def __init__(
        self,
        on_next_read: Callable[[Sample], None],
        messages_to_send_queue: QueueProtocol = queue.Queue(),  # type: ignore
    ):
        self.driver = open_simulation()
        self.messages_to_send_queue = messages_to_send_queue

        self.stop_event = threading.Event()

        self.sender_thread = threading.Thread(
            target=speak_with_serial_monitor,
            args=(
                self.driver,
                self.messages_to_send_queue,
                self.stop_event,
            ),
            daemon=True,
        )
        self.watcher_thread = threading.Thread(
            target=watch,
            args=(
                self.driver,
                on_next_read,
                self.stop_event,
            ),
            daemon=True,
        )

    def __destroy__(self):
        if self.driver is not None:
            self.driver.quit()
            self.driver = None
        if self.sender_thread.is_alive():
            self.stop_event.set()

    def _init_simulation(self):
        if self.driver is None:
            raise RuntimeError("Unexpected. driver is None")
        open_serial_monitor(driver=self.driver)
        start_simulation(driver=self.driver)
        self.driver.implicitly_wait(1)

    def send_message(self, message: str):
        self.messages_to_send_queue.put(message)

    def start(self):
        self._init_simulation()
        self.sender_thread.start()
        self.watcher_thread.start()
