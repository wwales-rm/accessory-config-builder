from enum import Enum

NUM_OPERATING_MODES = 4

_NUM_BASEBOARDS = 4
_NUM_LEVELS = 2

NUM_MODULES = 8

MIN_SERVO_ID = 1
MAX_SERVO_ID = 253
MAX_SERVOS_PER_MODULE = MAX_SERVO_ID - MIN_SERVO_ID + 1

MAX_ACCESSORIES_PER_MODULE = 16

LOW_LEVEL_ID = 0
HIGH_LEVEL_ID = 1

LEVEL_VALUE_MAP = {'low': LOW_LEVEL_ID, 'high':HIGH_LEVEL_ID}
BASEBOARD_VALUE_MAP = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

LEVEL_NAMES_MAP = {v: k.capitalize() for k, v in LEVEL_VALUE_MAP.items()}
BASEBOARD_NAMES_MAP = {v: k.upper() for k, v in BASEBOARD_VALUE_MAP.items()}

class AccType(Enum):
    FEATURE = 0
    UNCOUPLER = 1
    TURNOUT_S = 2
    TURNOUT_3 = 3
    TURNOUT_X = 4

ACCESSORY_NAMES = {
    AccType.FEATURE:   'Feature',
    AccType.UNCOUPLER: 'Uncoupler',
    AccType.TURNOUT_S: 'Simple Turnout',
    AccType.TURNOUT_3: '3-way Turnout',
    AccType.TURNOUT_X: 'Crossover'
}

ACCESSORY_SHORTNAMES = {
    AccType.FEATURE:   'F',
    AccType.UNCOUPLER: 'U',
    AccType.TURNOUT_S: 'T',
    AccType.TURNOUT_3: '3',
    AccType.TURNOUT_X: 'X'
}

ACCESSORY_MODE_COUNTS = {
    AccType.FEATURE:   4,   # features may support up to four modes
    AccType.UNCOUPLER: 2,   # mode 0 -> retracted, mode 1 -> extended
    AccType.TURNOUT_S: 2,   # mode 0 -> normal, mode 1 -> reversed
    AccType.TURNOUT_3: 3,   # mode 0 -> left, mode 1 -> straight, mode 2 -> right
    AccType.TURNOUT_X: 2    # mode 0 -> normal, mode 1 -> reversed
}

def encode_global_acc_id(module: int, acc_type: AccType, local_id: int) -> int:
    # global ID is 16 bit unsigned integer encoded as follows:
    # bits 0..7: local accessory ID
    # bits 8..11: accessory type code
    # bits 12..15: module ID 
    return ((module & 0xF) << 12) | ((acc_type.value & 0xF) << 8) | local_id & 0xFF

def decode_global_acc_id(id: int) -> tuple[int, AccType, int]:
    module = (id >> 12) & 0xF               # bits 12..15
    acc_type = AccType((id >> 8) & 0xF)     # bits 8..11
    local_id = id & 0xFF                    # bits 0..7
    return (module, acc_type, local_id)

def encode_module_id(level: int, baseboard: int) -> int:
    # module ID is a 8 bit unsigned integer encoded and follows:
    # bits 0..1: baseboard ID (0 -> 'A', 1 -> 'B', 2 -> 'C', 3 -> 'D')
    # bit 3: level (0 -> low, 1 -> high)
    # bits 4..7: unused, set to 0
    return ((level & 0x1) << 2) | (baseboard & 0x3)

def decode_module_id(module: int) -> tuple[int, int]:
    level = (module >> 2) & 0x1     # bit 3
    baseboard = module & 0x3        # bits 0 and 1
    return (level, baseboard)
