import os

ROOT_DIR = r'..'

DATA_DIR = r'data'

BUILD_DIR = r'_build'

DOCS_DIR = os.path.join(BUILD_DIR, r'docs')
BIN_DIR = os.path.join(BUILD_DIR, r'bin')
TEMPLATES_DIR = os.path.join(BUILD_DIR, r'templates')

ACCESSORY_DEFINITION_FILE = os.path.join(DATA_DIR, r'accessory_definition.md')
ACCESSORY_DOCS_FILE = os.path.join(DOCS_DIR, r'accessory_docs.md')
ACCESSORY_INFO_FILE = os.path.join(BIN_DIR, r'accessories.bin')

ACCESSORY_CONFIG_INPUT_FILE = os.path.join(DATA_DIR, r'accessory_config.md')
ACCESSORY_CONFIG_TPLT_FILE = os.path.join(TEMPLATES_DIR, r'accessory_config_template.md')
ACCESSORY_CONFIG_FILE = os.path.join(BIN_DIR, r'accessory_config.bin')
ACCESSORY_CONFIG_DOCS_FILE = os.path.join(DOCS_DIR, r'accessory_config_docs.md')

SWITCH_CONFIG_INPUT_FILE = os.path.join(DATA_DIR, r'switch_config.md')
SWITCH_CONFIG_TPLT_FILE = os.path.join(TEMPLATES_DIR, r'switch_config_template.md')
SWITCH_CONFIG_FILE = os.path.join(BIN_DIR, r'switch_config.bin')
SWITCH_DOCS_FILE = os.path.join(DOCS_DIR, r'switch_config_docs.md')

SERVO_CONFIG_INPUT_FILE = os.path.join(DATA_DIR, r'servo_config.md')
SERVO_CONFIG_TPLT_FILE = os.path.join(TEMPLATES_DIR, r'servo_config_template.md')
SERVO_CONFIG_FILE = os.path.join(BIN_DIR, r'servo_config.bin')
SERVO_DOCS_FILE = os.path.join(DOCS_DIR, r'servo_config_docs.md')

LED_DOCS_FILE = os.path.join(DOCS_DIR, r'led_docs.md')

SUMMARY_DOCS_FILE = os.path.join(DOCS_DIR, r'summary_docs.md')

BUILD_ACCESSORY_SCRIPT = r'build_accessories.py'
BUILD_CONFIG_SCRIPT = r'build_configs.py'
