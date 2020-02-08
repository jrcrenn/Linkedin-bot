"""Entrypoint for the LinkedinBot project."""
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.remote_connection import LOGGER
from string import Template

import traceback
import logging
import typing
import datetime
import selenium
import time
import os
import json
import sys
import random

LOGGER.setLevel(logging.WARNING)

def add_profile_to(profile: dict, profiles_file: str):
    logging.info("Added {}, {} to {}".format(profile["name"], profile["occupation"], profiles_file))
    data = []
    if os.path.exists(profiles_file) and os.path.isfile(profiles_file):
        with open(profiles_file, "r") as file:
            data = json.loads(file.read())
    data.append(profile)
    with open(profiles_file, "w") as file:
        file.write(json.dumps(data))

def pop_profile_from(profiles_file: str) -> dict:
    if os.path.exists(profiles_file) and os.path.isfile(profiles_file):
        with open(profiles_file, "r") as file:
            data = json.loads(file.read())
        if not len(data):
            return None
        value = data.pop(0)
        with open(profiles_file, "w") as file:
            file.write(json.dumps(data))
        return value
    return None

def scroll_profile(driver, config: dict):
    last_height = driver.execute_script("return window.scrollY")
    while True:
        driver.execute_script("window.scrollTo(0, window.scrollY + 5);")
        new_height = driver.execute_script("return window.scrollY")
        if new_height == last_height:
            break
        last_height = new_height
    driver.execute_script("window.scrollTo(0, 0);")

def login(driver, config: dict):
    driver.get("https://www.linkedin.com/")
    element = driver.find_element(By.XPATH, '//a[@data-tracking-control-name="guest_homepage-basic_nav-header-signin"]')
    login_href = element.get_attribute("href")
    driver.get(login_href)
    time.sleep(2)
    element = driver.find_element_by_name("session_key")
    element.send_keys(config["session_key"])
    element = driver.find_element_by_name("session_password")
    element.send_keys(config["session_password"])
    element = driver.find_element(By.XPATH, '//button[@type="submit"]')
    element.click()
    time.sleep(2)
    # cookies = driver.get_cookies()
    # with open("config/cookies.txt", "w") as file:
    #     file.write(json.dumps(cookies))


def go_to_home(driver, config: dict):
    logging.info("Logging in...")
    # driver.get("https://www.linkedin.com/")
    # if os.path.exists("config/cookies.txt") and os.path.isfile("config/cookies.txt"):
    #     logging.debug("Cookies detected, pushing them.")
    #     with open("config/cookies.txt", "r") as file:
    #         cookies = json.loads(file.read())
    #     for cookie in cookies:
    #         driver.add_cookie(cookie)
    driver.get("https://www.linkedin.com/")
    time.sleep(2)
    if "Log In" in driver.title or "s’identifier" in driver.title:
        logging.debug("Logging in with email and password")
        driver.delete_all_cookies()
        login(driver, config)


def enqueue_relationships(driver, config: dict):
    driver.get("https://www.linkedin.com/mynetwork/")
    profiles = driver.find_elements_by_class_name("discover-entity-type-card")
    for profile in profiles:
        try:
            occupation = profile.find_element_by_class_name("discover-person-card__occupation").text
            name = profile.find_element_by_class_name("discover-person-card__name").text
            link = profile.find_element_by_class_name("discover-entity-type-card__link").get_attribute("href")
            add_profile_to({
                "occupation": occupation,
                "name": name,
                "link": link
            }, config["data_files"]["enqueued"])
        except:
            logging.warning("An error happened parsing a person card, probably a company.")
            logging.debug(traceback.format_exc())

def add_relationships(driver, config: dict):
    passed = []
    profile = pop_profile_from(config["data_files"]["enqueued"])
    while profile != None and profile not in passed:
        driver.get(profile["link"])
        time.sleep(2)
        if len(driver.find_elements_by_css_selector("button.pv-s-profile-actions--connect.artdeco-button--disabled")):
            logging.info("{} is already waiting for approval...".format(profile["name"]))
            profile = pop_profile_from(config["data_files"]["enqueued"])
            continue
        if not len(driver.find_elements_by_class_name("pv-s-profile-actions--connect")):
            logging.info("{} is already in the added list...".format(profile["name"]))
            profile = pop_profile_from(config["data_files"]["enqueued"])
            continue
        scroll_profile(driver, config)
        time.sleep(2)
        try:
            element = driver.find_element_by_class_name("pv-s-profile-actions__overflow-toggle").click()
            element = driver.find_element_by_class_name("pv-s-profile-actions--connect").click()
            element = driver.find_element_by_css_selector("button.mr1.artdeco-button.artdeco-button--muted.artdeco-button--3.artdeco-button--secondary.ember-view").click()
            element = driver.find_element_by_name("message")
            text = Template(config["message"]).substitute(name=profile["name"].split(" ")[0])
            if len(text) > 300:
                logging.debug("The name was too long for the message: {}".format(profile["name"]))
                continue
            element.send_keys(text)
            element = driver.find_element_by_css_selector("button.ml1.artdeco-button.artdeco-button--3.artdeco-button--primary.ember-view").click()
            add_profile_to(profile, config["data_files"]["added"])
        except:
            logging.warning("An error happened connecting to {}, {}".format(profile["name"], profile["occupation"]))
            logging.warning(traceback.format_exc())
            add_profile_to(profile, config["data_files"]["enqueued"])
        time.sleep(3)
        passed.append(profile)
        profile = pop_profile_from(config["data_files"]["enqueued"])


def main_loop(driver, config):
    try:
        while True:
            date = datetime.datetime.now()
            is_day_okay = sum(list(map(lambda x: date.weekday() >= x["start"] and date.weekday() <= x["end"], config["working_days"])))
            is_hour_okay = sum(list(map(lambda x: date.hour >= x["start"] and date.hour < x["end"], config["working_hours"])))
            if is_hour_okay and is_day_okay:
                enqueue_relationships(driver, config)
                add_relationships(driver, config)
            wait_time = config["wait_time"] + random.randrange(0, config["wait_time_variance"])
            logging.info("Waiting {} seconds before next batch".format(wait_time))
            time.sleep(wait_time)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    if os.path.exists("config/config.json") and os.path.isfile("config/config.json"):
        with open("config/config.json", "r") as file:
            config = json.loads(file.read())
    else:
        print("The config.json file was not found.", file=sys.stderr)
        sys.exit(1)
    logging.basicConfig(
        filename='output.log',
        format="[%(asctime)s][%(levelname)s]: %(message)s",
        datefmt='%m/%d/%Y-%H:%M:%S',
        level=getattr(logging, config["log_level"])
    )
    for filename in ["added", "removed", "enqueued"]:
        foldername = config["data_files"][filename].split("/")[0]
        if not os.path.exists(foldername):
            logging.debug("Creating {} folder.".format(foldername))
            os.mkdir(foldername)
    firefox_options = webdriver.ChromeOptions()
    firefox_options.add_argument('--no-sandbox')
    if config["headless"]:
        logging.debug("Launching webdriver in headless mode.")
        firefox_options.add_argument('--headless')
    driver = webdriver.Chrome(options=firefox_options)
    logging.info("Starting bot.")
    go_to_home(driver, config)
    main_loop(driver, config)
    logging.info("Stopping bot.")
    driver.close()
