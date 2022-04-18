#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Roon Controller © Autolog 2019-2022
#

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

number = -1

show_constants = False


def constant_id(constant_label) -> int:  # Auto increment constant id
    global number
    if show_constants and number == -1:
        indigo.server.log("Roon Controller Plugin internal Constant Name mapping ...")
    number += 1
    if show_constants:
        # indigo.server.log(f"{number}: {constant_label}", isError=True)
        indigo.server.log(f"{number}: {constant_label}")
    return number


# plugin Zone Maps and Output Maps

ZONE_MAP_ALPHAS = list()
for minor_letter in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
    for major_letter in [' ', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']:
        ZONE_MAP_ALPHAS.append('{}{}'.format(major_letter, minor_letter))

ZONE_MAP_ALPHAS.sort()

OUTPUT_MAP_NUMBERS = list()
for major_number in [' ', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
    for minor_number in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
        OUTPUT_MAP_NUMBERS.append('{}{}'.format(major_number, minor_number))

OUTPUT_MAP_NUMBERS.sort()
OUTPUT_MAP_NUMBERS.pop(0)  # Remove first entry = '0'

# Log Levels
LOG_LEVEL_NOT_SET = 0
LOG_LEVEL_DETAILED_DEBUGGING = 5
LOG_LEVEL_DEBUGGING = 10
LOG_LEVEL_INFO = 20
LOG_LEVEL_WARNING = 30
LOG_LEVEL_ERROR = 40
LOG_LEVEL_CRITICAL = 50

LOG_LEVEL_TRANSLATION = {}
LOG_LEVEL_TRANSLATION[LOG_LEVEL_NOT_SET] = "Not Set"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_DETAILED_DEBUGGING] = "Detailed debugging"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_DEBUGGING] = "Debugging"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_INFO] = "Info"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_WARNING] = "Warning"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_ERROR] = "Error"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_CRITICAL] = "Critical"

# plugin Constants
API = constant_id("API")
API_VERSION = constant_id("API_VERSION")
ARTIST_IMAGE_KEYS = constant_id("ARTIST_IMAGE_KEYS")
ARTIST_IMAGE_KEYS_COUNT = constant_id("ARTIST_IMAGE_KEYS_COUNT")
AUTO_CREATE_DEVICES = constant_id("AUTO_CREATE_DEVICES")
AUTO_RADIO = constant_id("AUTO_RADIO")
AVAILABLE_OUTPUT_NUMBERS = constant_id("AVAILABLE_OUTPUT_NUMBERS")
AVAILABLE_ZONE_ALPHAS = constant_id("AVAILABLE_ZONE_ALPHAS")
CAN_GROUP_WITH_OUTPUT_IDS = constant_id("CAN_GROUP_WITH_OUTPUT_IDS")
CAN_GROUP_WITH_OUTPUT_IDS_COUNT = constant_id("CAN_GROUP_WITH_OUTPUT_IDS_COUNT")
CONFIG = constant_id("CONFIG")
CONTROL_KEY = constant_id("CONTROL_KEY")
DEBUG = constant_id("DEBUG")
DEVICES_TO_ROON_CONTROLLER_TABLE = constant_id("DEVICES_TO_ROON_CONTROLLER_TABLE")
DEVICE_STARTED = constant_id("DEVICE_STARTED")
DISPLAY_NAME = constant_id("DISPLAY_NAME")
DISPLAY_TRACK_PLAYING = constant_id("DISPLAY_TRACK_PLAYING")
DYNAMIC_GROUPED_ZONES_RENAME = constant_id("DYNAMIC_GROUPED_ZONES_RENAME")
EXTENSION_INFO = constant_id("EXTENSION_INFO")
IMAGE_KEY = constant_id("IMAGE_KEY")
INDIGO_DEVICE_BEING_DELETED = constant_id("INDIGO_DEVICE_BEING_DELETED")
INDIGO_DEV_ID = constant_id("INDIGO_DEV_ID")
INDIGO_SERVER_ADDRESS = constant_id("INDIGO_SERVER_ADDRESS")
IS_NEXT_ALLOWED = constant_id("IS_NEXT_ALLOWED")
IS_PAUSE_ALLOWED = constant_id("IS_PAUSE_ALLOWED")
IS_PLAY_ALLOWED = constant_id("IS_PLAY_ALLOWED")
IS_PREVIOUS_ALLOWED = constant_id("IS_PREVIOUS_ALLOWED")
IS_SEEK_ALLOWED = constant_id("IS_SEEK_ALLOWED")
LENGTH = constant_id("LENGTH")
LINE_1 = constant_id("LINE_1")
LINE_2 = constant_id("LINE_2")
LINE_3 = constant_id("LINE_3")
LOOP = constant_id("LOOP")
MAP_OUTPUT = constant_id("MAP_OUTPUT")
MAP_ZONE = constant_id("MAP_ZONE")
NOW_PLAYING = constant_id("NOW_PLAYING")
ONE_LINE = constant_id("ONE_LINE")
OUTPUTS = constant_id("OUTPUTS")
OUTPUTS_COUNT = constant_id("OUTPUTS_COUNT")
OUTPUT_ID = constant_id("OUTPUT_ID")
OUTPUT_ID_TO_DEV_ID = constant_id("OUTPUT_ID_TO_DEV_ID")
PATH = constant_id("PATH")
PLUGIN_DISPLAY_NAME = constant_id("PLUGIN_DISPLAY_NAME")
PLUGIN_ID = constant_id("PLUGIN_ID")
PLUGIN_INFO = constant_id("PLUGIN_INFO")
PLUGIN_PREFS_FOLDER = constant_id("PLUGIN_PREFS_FOLDER")
PLUGIN_VERSION = constant_id("PLUGIN_VERSION")
PRINT_OUTPUT = constant_id("PRINT_OUTPUT")
PRINT_OUTPUTS_SUMMARY = constant_id("PRINT_OUTPUTS_SUMMARY")
PRINT_ZONE = constant_id("PRINT_ZONE")
PRINT_ZONES_SUMMARY = constant_id("PRINT_ZONES_SUMMARY")
QUEUE_ITEMS_REMAINING = constant_id("QUEUE_ITEMS_REMAINING")
QUEUE_TIME_REMAINING = constant_id("QUEUE_TIME_REMAINING")
REMAINING = constant_id("REMAINING")
ROON = constant_id("ROON")
ROON_CORE_IP_ADDRESS = constant_id("ROON_CORE_IP_ADDRESS")
ROON_CORE_PORT = constant_id("ROON_CORE_PORT")
ROON_DEVICE_FOLDER_ID = constant_id("ROON_DEVICE_FOLDER_ID")
ROON_DEVICE_FOLDER_NAME = constant_id("ROON_DEVICE_FOLDER_NAME")
ROON_OUTPUT_ID = constant_id("ROON_OUTPUT_ID")
ROON_VARIABLE_FOLDER_ID = constant_id("ROON_VARIABLE_FOLDER_ID")
ROON_VARIABLE_FOLDER_NAME = constant_id("ROON_VARIABLE_FOLDER_NAME")
SEEK_POSITION = constant_id("SEEK_POSITION")
SETTINGS = constant_id("SETTINGS")
SHUFFLE = constant_id("SHUFFLE")
SOURCE_CONTROLS = constant_id("SOURCE_CONTROLS")
SOURCE_CONTROLS_COUNT = constant_id("SOURCE_CONTROLS_COUNT")
STATE = constant_id("STATE")
STATUS = constant_id("STATUS")
SUPPORTS_STANDBY = constant_id("SUPPORTS_STANDBY")
THREE_LINE = constant_id("THREE_LINE")
TOKEN = constant_id("TOKEN")
TOKEN_FILE = constant_id("TOKEN_FILE")
TWO_LINE = constant_id("TWO_LINE")
VOLUME = constant_id("VOLUME")
VOLUME_HARD_LIMIT_MAX = constant_id("VOLUME_HARD_LIMIT_MAX")
VOLUME_HARD_LIMIT_MIN = constant_id("VOLUME_HARD_LIMIT_MIN")
VOLUME_IS_MUTED = constant_id("VOLUME_IS_MUTED")
VOLUME_MAX = constant_id("VOLUME_MAX")
VOLUME_MIN = constant_id("VOLUME_MIN")
VOLUME_SOFT_LIMIT = constant_id("VOLUME_SOFT_LIMIT")
VOLUME_STEP = constant_id("VOLUME_STEP")
VOLUME_TYPE = constant_id("VOLUME_TYPE")
VOLUME_VALUE = constant_id("VOLUME_VALUE")
ZONES = constant_id("ZONES")
ZONE_ID = constant_id("ZONE_ID")
ZONE_UNIQUE_IDENTITY_KEY = constant_id("ZONE_UNIQUE_IDENTITY_KEY")
ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID = constant_id("ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID")
ZONE_UNIQUE_IDENTITY_KEY_TO_ZONE_ID = constant_id("ZONE_UNIQUE_IDENTITY_KEY_TO_ZONE_ID")

# Image Types
ARTIST = 0
ALBUM = 1

# QUEUE Priorities
QUEUE_PRIORITY_STOP_THREAD = 0
QUEUE_PRIORITY_INIT_DISCOVERY = 50
QUEUE_PRIORITY_WAVEFORM = 100
QUEUE_PRIORITY_COMMAND_HIGH = 200
QUEUE_PRIORITY_COMMAND_MEDIUM = 300
QUEUE_PRIORITY_STATUS_HIGH = 400
QUEUE_PRIORITY_STATUS_MEDIUM = 500
QUEUE_PRIORITY_DISCOVERY = 600
QUEUE_PRIORITY_POLLING = 700
QUEUE_PRIORITY_LOW = 800
