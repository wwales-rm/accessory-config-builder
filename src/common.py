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

BUILD_ACCESSORY_SCRIPT = r'build_accessories.py'
BUILD_CONFIG_SCRIPT = r'build_configs.py'

ACCESSORY_TYPE_FEATURE = 0
ACCESSORY_TYPE_TURNOUT = 1
ACCESSORY_TYPE_CROSSOVER = 2
ACCESSORY_TYPE_UNCOUPLER = 3

ACCESSORY_TYPE_CODES = {
    'Features': ACCESSORY_TYPE_FEATURE,
    'Turnouts': ACCESSORY_TYPE_TURNOUT, 
    'Crossovers': ACCESSORY_TYPE_CROSSOVER, 
    'Uncouplers': ACCESSORY_TYPE_UNCOUPLER
}

ACCESSORY_TYPE_NAMES = {
    ACCESSORY_TYPE_FEATURE: 'Feature',
    ACCESSORY_TYPE_TURNOUT: 'Turnout',
    ACCESSORY_TYPE_CROSSOVER: 'Crossover',
    ACCESSORY_TYPE_UNCOUPLER: 'Uncoupler'
}

ACCESSORY_TYPE_SHORT_NAMES = {
    ACCESSORY_TYPE_FEATURE: 'F',
    ACCESSORY_TYPE_TURNOUT: 'T',
    ACCESSORY_TYPE_CROSSOVER: 'C',
    ACCESSORY_TYPE_UNCOUPLER: 'U'
}

def encode_global_accessory_id(baseboard_id: int, accessory_type: int, local_accessory_id: int) -> int:
    # baseboard_id is in range 0..3
    # accessory_type is in range 0..3
    # local_accessory_id is in range 0..15
    return ((baseboard_id & 3) << 6) | ((accessory_type & 3) << 4) | (local_accessory_id & 15)

def decode_global_accessory_id(global_id: int) -> tuple:
    baseboard_id = (global_id >> 6 ) & 3       # range 0..3
    accessory_type = (global_id  >> 4) & 3     # range 0..3
    local_accessory_id = global_id & 15        # range 0..15
    return baseboard_id, accessory_type, local_accessory_id

def global_accessory_id_has_type(global_id: int, wanted_type: int) -> bool:
    _, acc_type, _ = decode_global_accessory_id(global_id)
    return True if acc_type == wanted_type else False

def encode_servo_id(baseboard_id: int, local_servo_id: int) -> int:
    # baseboard_id is in range 0..3
    # local_servo_id is in range 0..31
    return ((baseboard_id & 3) << 5) | (local_servo_id & 31)

def decode_servo_id(servo_id: int) -> tuple:
    baseboard_id = (servo_id >> 5) & 3      # range 0..3
    local_servo_id = servo_id & 31          # range 0..31
    return baseboard_id, local_servo_id
