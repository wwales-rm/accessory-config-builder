from collections import defaultdict
import os
import sys
from enum import Enum
import struct

import common
import shared
from shared import AccType
from text_tables import parse_markdown_table, to_markdown_table

SWITCHES_PER_ACC_TYPE = {
    AccType.FEATURE: 1,
    AccType.UNCOUPLER: 1,
    AccType.TURNOUT_S: 1,
    AccType.TURNOUT_3: 3,
    AccType.TURNOUT_X: 1
}

LEDS_PER_ACCTYPE = {
    AccType.FEATURE: 0,
    AccType.UNCOUPLER: 1,
    AccType.TURNOUT_S: 2,
    AccType.TURNOUT_3: 3,
    AccType.TURNOUT_X: 4
}
    
SERVOS_PER_ACCTYPE = {
    AccType.FEATURE: 0,
    AccType.UNCOUPLER: 1,
    AccType.TURNOUT_S: 1,
    AccType.TURNOUT_3: 2,
    AccType.TURNOUT_X: 2
}

TURNOUT_SERVO_DEFAULT_POS = {'On': 900, 'Off': 400}
UNCOUPLER_SERVO_DEFAULT_POS = {'On': 1200, 'Off': 100}

SERVO_DEFAULT_POS_PER_ACCTYPE = {
    AccType.FEATURE: {'On': 0, 'Off': 0},   # Features don't use servos
    AccType.UNCOUPLER: UNCOUPLER_SERVO_DEFAULT_POS,
    AccType.TURNOUT_S: TURNOUT_SERVO_DEFAULT_POS,
    AccType.TURNOUT_3: TURNOUT_SERVO_DEFAULT_POS,
    AccType.TURNOUT_X: TURNOUT_SERVO_DEFAULT_POS
}

ACCESSORY_MODE_DEFAULTS = {
    AccType.FEATURE:   0,   # feature dependent action for mode 0
    AccType.UNCOUPLER: 0,   # retracted
    AccType.TURNOUT_S: 0,   # normal
    AccType.TURNOUT_3: 1,   # straight
    AccType.TURNOUT_X: 0    # normal
}

MAX_SWITCHES_PER_MODULE = 24
MAX_LEDS_PER_MODULE = 16
MAX_ACCS_ON_LAYOUT = 255

def generate_module_info(table_data: dict) -> list:

    LEVEL_TABLE_HEADING = 'Level'
    BASEBOARD_TABLE_HEADING = 'Baseboard'

    ACC_TABLE_HEADINGS_TO_ACC_TYPES = {
        'Single Turnouts': AccType.TURNOUT_S,
        '3 Way Turnouts': AccType.TURNOUT_3, 
        'Crossovers': AccType.TURNOUT_X, 
        'Uncouplers': AccType.UNCOUPLER,
        'Features': AccType.FEATURE
    }

    ACC_TABLE_HEADINGS = list(ACC_TABLE_HEADINGS_TO_ACC_TYPES.keys())

    TABLE_HEADINGS = [
        LEVEL_TABLE_HEADING,
        BASEBOARD_TABLE_HEADING
    ] + ACC_TABLE_HEADINGS

    TABLE_ROW_COUNT = shared.NUM_MODULES

    # --- STEP 1: TABLE VALIDATION ---
    
    # 1. Validate table headings
    if table_data.keys() != set(TABLE_HEADINGS):
        raise ValueError("Dictionary keys do not exactly match the specification.")

    # Validate that all columns have the required number of rows
    for key, value in table_data.items():
        if not isinstance(value, list):
            raise TypeError(f"Value for table heading '{key}' must be a list.")
        if len(value) != TABLE_ROW_COUNT:
            raise ValueError(f"Table must have {TABLE_ROW_COUNT} rows: Column '{key}' has {len(value)} rows.")

    # Track combinations to ensure (Level, Baseboard) uniqueness
    seen_combinations = set()

    # Loop through elements to validate specific constraints
    for i in range(TABLE_ROW_COUNT):

        # Validate level value
        level_val = str(table_data[LEVEL_TABLE_HEADING][i]).strip().lower()
        if level_val not in shared.LEVEL_VALUE_MAP.keys():
            level_options = "'" + "' or '".join(k.capitalize() for k in shared.LEVEL_VALUE_MAP.keys()) + "'"
            bad_level_val = level_val.capitalize()
            raise ValueError(f"Invalid {LEVEL_TABLE_HEADING} value at row {i}: '{bad_level_val}'. Must be {level_options}.")
        
        # Validate baseboard value
        baseboard_val = str(table_data[BASEBOARD_TABLE_HEADING][i]).strip().upper()
        if baseboard_val not in shared.BASEBOARD_VALUE_MAP.keys():
            baseboard_options = "'" + "', '".join(shared.BASEBOARD_VALUE_MAP.keys()) + "'"
            raise ValueError(
                f"Invalid {BASEBOARD_TABLE_HEADING} value at index {i}: '{baseboard_val}'. Must be one of {baseboard_options}."
            )
        
        # Check for unique (level, baseboard) pairs
        pair = (level_val, baseboard_val)
        if pair in seen_combinations:
            dup_level = table_data[LEVEL_TABLE_HEADING][i]
            dup_bb = table_data[BASEBOARD_TABLE_HEADING][i]
            raise ValueError(
                f"Duplicate (Level, Baseboard) combination found at index {i}: {dup_level}, {dup_bb}."
            )
        seen_combinations.add(pair)

        # Validate integer ranges for the accessory type values
        for key in ACC_TABLE_HEADINGS:
            val = table_data[key][i]
            if not isinstance(val, int) or isinstance(val, bool):  # isinstance(True, int) is True in Python
                raise TypeError(f"Row at index {i} in column '{key}' must be an integer.")
            if not (0 <= val <= 15):
                raise ValueError(f"Value {val} at row {i} in column '{key}' is out of range 0..15.")

    # --- STEP 2: TRANSFORMATION ---
    result = []
    
    for i in range(TABLE_ROW_COUNT):
        # Extract and normalize values for mapping
        lvl = str(table_data[LEVEL_TABLE_HEADING][i]).strip().lower()
        bsb = str(table_data[BASEBOARD_TABLE_HEADING][i]).strip().upper()
        
        # Calculate module value
        module_value = shared.encode_module_id(shared.LEVEL_VALUE_MAP[lvl], shared.BASEBOARD_VALUE_MAP[bsb])
        
        # Construct dictionary for table row i
        elem = dict()
        elem['module'] = module_value
        for acc_heading, acc_type in ACC_TABLE_HEADINGS_TO_ACC_TYPES.items():
            elem[acc_type] = table_data[acc_heading][i]
        result.append(elem)
        
    return result

def generate_accessory_info(module_data: list[dict]) -> dict[str, any]:

    # Get module IDs
    module_ids = [elem['module'] for elem in module_data]

    # Get keys for accessory types
    accessory_keys = [key for key in AccType]

    # Map each module ID to the data items at the same index
    transformed_data = {
        module_id: {key: module_data[idx][key] for key in accessory_keys}
        for idx, module_id in enumerate(module_ids)
    }

    accessory_info = []

    for module_id, acc_counts in transformed_data.items():

        level, _ = shared.decode_module_id(module_id)

        total_rear_switches = sum([acc_counts[a] * SWITCHES_PER_ACC_TYPE[a] for a in AccType])

        # Assign IDs in order of members of AccType Enum
        current_rear_switch_id = 0                      # switch IDs start from 0 at rear
        current_front_switch_id = total_rear_switches   # front switch IDs follow last switch ID
        current_led_id = 0                              # LED IDs start at 0
        current_servo_id = shared.MIN_SERVO_ID          

        # Track accessory local IDs within this module (indexed by type code)
        local_id_counters = {
            AccType.FEATURE: 0, 
            AccType.UNCOUPLER: 0,
            AccType.TURNOUT_S: 0, 
            AccType.TURNOUT_3: 0, 
            AccType.TURNOUT_X: 0, 
        }

        for acc in AccType:
            qty = acc_counts[acc]

            for _ in range(qty):

                local_id = local_id_counters[acc]
                local_id_counters[acc] += 1

                global_id = shared.encode_global_acc_id(module_id, acc, local_id)

                r_module_id, r_acc, r_local_id = shared.decode_global_acc_id(global_id)
                if module_id != r_module_id or acc != r_acc or local_id != r_local_id:
                    raise ValueError('Global ID encoding or decoding failed')

                rear_switches = list(range(current_rear_switch_id, current_rear_switch_id + SWITCHES_PER_ACC_TYPE[acc]))
                current_rear_switch_id += SWITCHES_PER_ACC_TYPE[acc]

                if level == shared.LOW_LEVEL_ID:
                    front_switches = list(range(current_front_switch_id, current_front_switch_id + SWITCHES_PER_ACC_TYPE[acc]))
                    current_front_switch_id += SWITCHES_PER_ACC_TYPE[acc]
                else: # level = shared.HIGH_LEVEL_ID
                    front_switches = []

                leds = list(range(current_led_id, current_led_id + LEDS_PER_ACCTYPE[acc]))
                current_led_id += LEDS_PER_ACCTYPE[acc]

                servos = list(range(current_servo_id, current_servo_id + SERVOS_PER_ACCTYPE[acc]))
                current_servo_id += SERVOS_PER_ACCTYPE[acc]

                accessory_info.append({
                    'global_id': global_id,
                    'rear_switches': rear_switches,
                    'front_switches': front_switches,
                    'leds': leds,
                    'servos': servos
                })

    return accessory_info

def validate_accessory_info(acc_info: list[dict[str,int | list[int]]]) -> None:

    # Track physical resource footprints per baseboard
    switches_per_module = defaultdict(set)
    leds_per_module = defaultdict(set)
    servos_per_module = defaultdict(set)
    accs_per_types_per_module = defaultdict(lambda: defaultdict(set))

    errors = []

    # --- Profile Hardware Allocation ---
    for acc in accessory_info:
        global_id = acc['global_id']
        module, acc_type, local_id = shared.decode_global_acc_id(global_id)
        
        # Track accessory count per type on this module
        accs_per_types_per_module[module][acc_type].add(local_id)
        
        # Track unique switches wired to this module
        if acc['rear_switches'] is not None:
            for switch_id in acc['rear_switches']:
                switches_per_module[module].add(switch_id)
        if acc['front_switches'] is not None:
            for switch_id in acc['front_switches']:
                switches_per_module[module].add(switch_id)
            
        # Track unique LEDs wired to this module
        for led in acc['leds']:
            leds_per_module[module].add(led)
            
        # Track unique Servos assigned to this module
        for servo in acc['servos']:
            servos_per_module[module].add(servo)

    # --- Run Constraint Rules Evaluation ---

    global_ids = [modules['global_id'] for modules in accessory_info]

    def module_from_global_id(global_id: int) -> int:
        module, _, _ = shared.decode_global_acc_id(global_id)
        return module
    
    active_modules = set(module_from_global_id(gid) for gid in global_ids)
    
    for m in active_modules:

        # Check 1: Switches per module
        sw_count = len(switches_per_module[m])
        if sw_count > MAX_SWITCHES_PER_MODULE:
            errors.append(f"Module {m}: Exceeds switch limit! Found {sw_count} (Max: {MAX_SWITCHES_PER_MODULE})")
            
        # Check 2: LEDs per module
        led_count = len(leds_per_module[m])
        if led_count > MAX_LEDS_PER_MODULE:
            errors.append(f"Module {m}: Exceeds LED limit! Found {led_count} (Max: {MAX_LEDS_PER_MODULE})")
            
        # Check 3: Servos per module
        servo_count = len(servos_per_module[m])
        if servo_count > shared.MAX_SERVOS_PER_MODULE:
            errors.append(f"Module {m}: Exceeds servo limit! Found {servo_count} (Max: {shared.MAX_SERVOS_PER_MODULE})")
            
        # Check 4: Quantity of each individual accessory type
        for acc_type, instances in accs_per_types_per_module[m].items():
            qty = len(instances)
            if qty > shared.MAX_ACCESSORIES_PER_MODULE:
                errors.append(f"Baseboard {m}: Type '{shared.ACCESSORY_NAMES[acc_type]}' exceeds capacity! Found {qty} (Max: {shared.MAX_ACCESSORIES_PER_MODULE})")
                
    # Check 5: Max accessories on layout
    if len(accessory_info) > MAX_ACCS_ON_LAYOUT:
        errors.append(f"Global Layout Error: {len(accessory_info)} accessories on layout exceeds maximum of {MAX_ACCS_ON_LAYOUT}")

    is_valid = len(errors) == 0
    return is_valid, errors

def save_accessory_info_to_binary(accessory_info: list) -> None:
    """
    Packs layout accessory data into variable-length binary structures
    and writes them to a local binary configuration file.
    """

    def add_list_to_data(data: list[int], l: list[int]) -> list[int]:
        return data + [len(l)] + l

    count = len(accessory_info)

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_FILE), "wb") as bin_file:

        count_byte = struct.pack("<B", count)
        bin_file.write(count_byte)
        file_size = len(count_byte)
        for acc in accessory_info:

            # --- Accessory global ID ---
            global_id = acc['global_id']
            bin_file.write(struct.pack("<H", global_id))
            file_size += 2

            data = []

            # --- Rear switch IDs
            rear_switches = acc['rear_switches'] if acc['rear_switches'] is not None else []
            data = add_list_to_data(data, rear_switches)

            # --- Front switch IDs
            front_switches = acc['front_switches'] if acc['front_switches'] is not None else []
            data = add_list_to_data(data, front_switches)

            # --- LED IDs
            leds = acc['leds'] if acc['leds'] is not None else []
            data = add_list_to_data(data, leds)

            # --- Servos
            servos = acc['servos'] if acc['servos'] is not None else []
            data = add_list_to_data(data, servos)

            # --- write the total length of data, followed by data for this accessory
            assert len(data) < 256, "Accessory data length exceeds byte limit"
            bin_file.write(struct.pack("<B", len(data)))
            for d in data:
                bin_file.write(struct.pack("<B", d))
            file_size += 1 + len(data)
                
    print(f"💾 Binary accessory data saved in '{common.ACCESSORY_INFO_FILE}' ({count} items, {file_size} bytes)")

def uniform_table_padding(columns: dict, padding: int = 99) -> dict[str,int]:
    widths = {}   
    for col in columns:
        widths.update({col: padding})
    return widths

def save_markdown_table(table_cols: dict[str,int], filename: str) -> None:
    # generate table widths to ensure each cell in a column has same width
    table_widths = uniform_table_padding(table_cols, 99)   
    markdown = to_markdown_table(table_cols, max_widths=table_widths) + "\n"
    with open(os.path.join(common.ROOT_DIR, filename), "w", encoding="utf-8") as fd:
        fd.write(markdown)

def generate_accessory_table(accessory_info: list) -> dict:
    """
    Combines accessory configurations into a human-readable columnar dictionary 
    describing all accessories, their physical switches, LEDs, and servos.
    Sorted by Baseboard, Accessory Type (Standard order), and Local Accessory ID.
    """

    # 1. Unpack, format, and organize rows for explicit multi-key sorting
    raw_rows = []
    for acc in accessory_info:
        global_id = acc['global_id']
        module, acc_type, local_id = shared.decode_global_acc_id(global_id)
        level, bb = shared.decode_module_id(module)
        rear_sw = "`" + "`,`".join(map(str, acc['rear_switches'])) + "`" if acc['rear_switches'] else "-"
        front_sw = "`" + "`,`".join(map(str, acc['front_switches'])) + "`" if acc['front_switches'] else "-"
        led_str = "`" + "`,`".join(map(str, acc['leds'])) + "`" if acc['leds'] else "-"
        servo_str = "`" + "`,`".join(map(str, acc['servos'])) + "`" if acc['servos'] else "-"
        global_id_str = f"`{global_id}`"
        global_code_str = f"`{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0]}{shared.ACCESSORY_SHORTNAMES[acc_type]}:{local_id}`"
        local_id_str = f"`{local_id}`"
        module_str = f"`{module}` ({shared.LEVEL_NAMES_MAP[level]} level, baseboard {shared.BASEBOARD_NAMES_MAP[bb]})"

        raw_rows.append({
            '_global_id': global_id,
            'Global ID': global_id_str,
            'Global Code': global_code_str,
            'Module': module_str,
            'Accessory Type': shared.ACCESSORY_NAMES[acc_type],
            'Accessory ID': local_id_str,
            'Rear Switches': rear_sw,
            'Front Switches': front_sw,
            'LEDs': led_str,
            'Servos': servo_str,
        })
        
    # 2. Sort by global ID string, stripped of leading and trailing back ticks
    raw_rows.sort(key=lambda x: (int(x['_global_id'])))
    
    # 3. Reassemble structured row arrays back into parallel column arrays
    column_data = {
        'Global ID': [],
        'Global Code': [],
        'Module': [],
        'Accessory Type': [],
        'Accessory ID': [],
        'Rear Switches': [],
        'Front Switches': [],
        'LEDs': [],
        'Servos': [],
    }
    
    for row in raw_rows:
        for key in column_data.keys():
            column_data[key].append(row[key])
            
    return column_data

def save_accessory_info_documentation(accessory_info: list) -> None:

    doc_info = generate_accessory_table(accessory_info)

    bb_names = list(shared.BASEBOARD_NAMES_MAP.values())

    markdown = "# Accessory Details\n\n"
    markdown += "The following table describes all the layout's accessories.\n\n"
    markdown += "* _Global ID_ identifies the accessory uniquely within the whole layout.\n"
    markdown += "* _Global Code_ human readable version of _Global ID_. It can be decoded as follows:\n"
    markdown += f"    * 1st character: baseboard ID (`{bb_names[0]}`..`{bb_names[-1]}`)\n"
    markdown += f"    * 2nd character: level ({'; '.join([f"`{i[0].upper()}` - {i.capitalize()}" for i in shared.LEVEL_VALUE_MAP.keys() ])})\n"
    markdown += f"    * 3rd character: accessory type ({'; '.join([f"`{shared.ACCESSORY_SHORTNAMES[a].upper()}` - {shared.ACCESSORY_NAMES[a].capitalize()}" for a in AccType])})\n"
    markdown += "    * Separator (`:`)\n"
    markdown += f"    * digit(s): the id (`0`..`{shared.MAX_ACCESSORIES_PER_MODULE - 1}`) of the accessory within its baseboard, level and type\n"
    markdown += "* _Module_ identifies the module that contains the accessory.\n"
    markdown += "* _Accessory Type_ specifies the type of the accessory.\n"
    markdown += "* _Accessory ID_ is the local identifier of the accessory, unique only within its baseboard and type.\n"
    markdown += "* _Rear Switches_ is a list of the IDs of the switches that operates the accessory from the rear of the baseboard.\n"
    markdown += "* _Front Switches_ is a list of the IDs of the switches that operates the accessory from the front of the baseboard, if any.\n"
    markdown += "* _LEDs_ is a list of LEDs that are controlled by the accessory, if any.\n"
    markdown += "* _Servos_ is a list of Servos that are controlled by the accessory, if any.\n\n"
    markdown += to_markdown_table(doc_info, max_widths=uniform_table_padding(doc_info, 99))
    markdown += "\n\nNote that switch, LED and servo IDs are unique within their host module, but not unique across the layout.\n"

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_DOCS_FILE), "w", encoding="utf-8") as fd:
        fd.write(markdown)
    print(f"💾 Accessory documentation saved in '{common.ACCESSORY_DOCS_FILE}'")

def generate_led_table(accessory_info: list) -> dict:
    """
    Combines LED configurations into a human-readable columnar dictionary.
    """

    # 1. Unpack, format, and organize rows for explicit multi-key sorting
    raw_data = []
    for acc in accessory_info:
        g_id = acc['global_id']
        module, acc_type, l_id = shared.decode_global_acc_id(g_id)
        level, bb = shared.decode_module_id(module)
        acc_str = f"`{shared.ACCESSORY_SHORTNAMES[acc_type]}:{l_id}`"
        module_str = f"`{module}` ({shared.LEVEL_NAMES_MAP[level]} level, baseboard {shared.BASEBOARD_NAMES_MAP[bb]})"

        for led in acc['leds']:
            raw_data.append({
                '_module': module,
                '_led': led,
                'Module': module_str,
                'LED': f"`{led}`",
                'Accessory': acc_str, 
            })
                
    # 2. Apply explicit sorting rules: Baseboard first, then LED
    raw_data.sort(key = lambda x: (x['_module'], x['LED']))

    column_data = {'Module': [], 'LED': [], 'Accessory': []}

    for row in raw_data:
        for key in column_data.keys():
            column_data[key].append(row[key])

    return column_data

def save_led_info_documentation(accessory_info: list) -> None:
    table_cols = generate_led_table(accessory_info)

    markdown = "# LED Information\n\n"
    markdown += "The following table provides information about the layouts LEDs.\n\n"
    markdown += "* _Module_ identifies the module that contains the accessory.\n"
    markdown += "* _LED_ the ID of the LED within its module.\n"
    markdown += "* _Accessory_ the accessory that controls the LED. The character before the colon is the accessory type code and the digit(s) after the colon are the accessory ID, unique with the module and type. Type codes are as follows:\n"
    markdown += "".join([f"    * `{shared.ACCESSORY_SHORTNAMES[acc]}` - {shared.ACCESSORY_NAMES[acc]}\n" for acc in AccType])
    markdown += "\n"
    markdown += to_markdown_table(table_cols, max_widths=uniform_table_padding(table_cols, 99))
    markdown += "\n\n"
    markdown += "LED IDs are unique within the module (i.e. level and baseboard) to which they belong, but are not unique within the layout.\n"

    with open(os.path.join(common.ROOT_DIR, common.LED_DOCS_FILE), "w", encoding="utf-8") as fd:
        fd.write(markdown)
    print(f"💾 LED documentation saved in '{common.LED_DOCS_FILE}'")

def create_accessory_mode_table(accessory_info: list) -> dict:
    """
    Creates a dict[str, list] of all layout accessories with default startup
    state strings. All accessories default to `0000`
    """

    column_data = {
        "Module (Level/Baseboard)": [],
        "Accessory": [],
        "Startup Modes": [],
        "Valid Startup Modes": []
    }

    raw_data = []

    for acc in accessory_info:

        g_id = acc['global_id']
        module, acc_type, l_id = shared.decode_global_acc_id(g_id)
        level, bb = shared.decode_module_id(module)

        bl = f"{shared.BASEBOARD_NAMES_MAP[bb]} - {shared.LEVEL_NAMES_MAP[level]}"
        acc_id = f"{shared.ACCESSORY_SHORTNAMES[acc_type]}:{l_id}"
        num_modes = shared.ACCESSORY_MODE_COUNTS[acc_type]
        valid_modes = f"0..{num_modes-1}"
        def_modes = str(ACCESSORY_MODE_DEFAULTS[acc_type]) * shared.NUM_OPERATING_MODES

        raw_data.append({
            '_level': level,
            '_bb': bb,
            '_acc_type': acc_type,
            '_l_id': l_id,
            'Baseboard / Level': bl,
            'Accessory': acc_id,
            'Startup Modes': def_modes,
            'Valid Startup Modes': valid_modes
        })

    raw_data.sort(
        key = lambda x: (
            int(x['_bb']), 
            int(x['_level']), 
            int(x['_acc_type'].value), 
            int(x['_l_id'])
        )
    )

    column_data = {
        "Baseboard / Level": [],
        "Accessory": [],
        "Startup Modes": [],
        "Valid Startup Modes": []
    }
    for row in raw_data:
        for key in column_data.keys():
            column_data[key].append(row[key])

    return column_data

def save_accessory_config_template_file(accessory_info: list) -> None:
    table_cols = create_accessory_mode_table(accessory_info)
    save_markdown_table(table_cols, common.ACCESSORY_CONFIG_TPLT_FILE)
    save_dir_name, save_file_name = os.path.split(common.ACCESSORY_CONFIG_INPUT_FILE)
    print(f"💾 Draft accessory configuration table saved in '{common.ACCESSORY_CONFIG_TPLT_FILE}'")
    print(f"   TODO:")
    print(f"      ✅ Open '{common.ACCESSORY_CONFIG_TPLT_FILE}' in a text editor")
    print(f"      ✅ Edit accessory startup state for each operating mode")
    print(f"      ✅ Save the edited file as '{save_file_name}' in the '{save_dir_name}' directory")
    pass

def create_switch_mode_table(accessory_info: list) -> dict:
    """
    Creates a dictionary representing a table of all switches with default mode strings.
    Rear switches default to '1111' (always on).
    Front switches default to '1010' (modes 0 and 2 only) or '-' if missing.
    """

    raw_data = []

    SW_POS_REAR = 0
    SW_POS_FRONT = 1

    SW_KEY_NAMES = {SW_POS_REAR: 'rear_switches', SW_POS_FRONT: 'front_switches'}
    SW_POS_NAMES = {SW_POS_REAR: 'Rear', SW_POS_FRONT: 'Front'}
    SW_POS_MODES = {
        SW_POS_REAR: '1' * shared.NUM_OPERATING_MODES, 
        SW_POS_FRONT: '10' * (shared.NUM_OPERATING_MODES // 2)
    }
    
    for acc in accessory_info:
        module, acc_type, l_id = shared.decode_global_acc_id(acc['global_id'])
        level, bb = shared.decode_module_id(module)

        for sw_pos in [SW_POS_REAR, SW_POS_FRONT]:
            sw_list = acc[SW_KEY_NAMES[sw_pos]]

            for sw_id in sw_list:
                raw_data.append({
                    "_level": level,
                    "_bb": bb,
                    "_sw_id": sw_id,
                    "Module": module,
                    "Baseboard / Level": f"{shared.BASEBOARD_NAMES_MAP[bb]} - {shared.LEVEL_NAMES_MAP[level]}",
                    "Accessory": f"{shared.ACCESSORY_SHORTNAMES[acc_type]}:{l_id}",
                    "Switch Position": SW_POS_NAMES[sw_pos],
                    "Switch ID": f"{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0]}{SW_POS_NAMES[sw_pos][0]}:{sw_id}",
                    "Switch Modes": SW_POS_MODES[sw_pos]
                })

    raw_data.sort(key = lambda x: (int(x['_bb']), int(x['_level']), int(x['_sw_id'])))

    column_data = {
        "Module": [],
        "Baseboard / Level": [],
        "Accessory": [],
        "Switch Position": [],
        "Switch ID": [],
        "Switch Modes": [],
    }
    for row in raw_data:
        for key in column_data.keys():
            column_data[key].append(row[key])

    return column_data

def save_switch_config_template_file(accessory_info: list) -> None:

    table_cols = create_switch_mode_table(accessory_info)
    save_markdown_table(table_cols, common.SWITCH_CONFIG_TPLT_FILE)
    save_dir_name, save_file_name = os.path.split(common.SWITCH_CONFIG_INPUT_FILE)
    print(f"💾 Draft switch configuration template saved in '{common.SWITCH_CONFIG_TPLT_FILE}'")
    print(f"   TODO:")
    print(f"      ✅ Open '{common.SWITCH_CONFIG_TPLT_FILE}' in a text editor")
    print(f"      ✅ Edit switch availability for each operating mode")
    print(f"      ✅ Save the edited file as '{save_file_name}' in the '{save_dir_name}' directory")

def create_servo_calibration_table(accessory_info: list[dict]) -> dict[str, list]:
    """
    Creates a dictionary representing a table of all servos with type-specific
    default on and off positions.
    """

    raw_rows = []
    for acc in accessory_info:

        g_id = acc['global_id']
        module, acc_type, l_id = shared.decode_global_acc_id(g_id)
        level, bb = shared.decode_module_id(module)
        bl = f"{shared.BASEBOARD_NAMES_MAP[bb]} - {shared.LEVEL_NAMES_MAP[level]}"

        servo_ids = acc['servos']

        for s_id in servo_ids:
            # key names beginning with with "_" are for sorting only - not included in table data
            raw_rows.append({
                '_level': level,
                '_bb': bb,
                '_servo': s_id,
                # 'Baseboard / Level': bl,
                'Servo': f"{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0]}:{s_id}",
                'Off Position': SERVO_DEFAULT_POS_PER_ACCTYPE[acc_type]['Off'],
                'On Position': SERVO_DEFAULT_POS_PER_ACCTYPE[acc_type]['On'],
                'Accessory': f"{shared.ACCESSORY_SHORTNAMES[acc_type]}:{l_id}",
                # 'Accessory Type': shared.ACCESSORY_NAMES[acc_type],
                # 'Accessory ID': l_id
            })
            
    raw_rows.sort(
        key=lambda x: (
            int(x['_bb']),
            int(x['_level']),
            int(x['_servo'])
        )
    )
    
    column_data = {
        # 'Baseboard / Level': [],
        "Servo": [], 
        "Off Position": [], 
        "On Position": [],
        # "Accessory Type": [], 
        # "Accessory ID": [],
        "Accessory": []
    }
    
    for row in raw_rows:
        for key in column_data.keys():
            column_data[key].append(row[key])
            
    return column_data

def save_servo_config_template_file(accessory_info: list) -> None:

    table_cols = create_servo_calibration_table(accessory_info)
    save_markdown_table(table_cols, common.SERVO_CONFIG_TPLT_FILE)
    save_dir_name, save_file_name = os.path.split(common.SERVO_CONFIG_INPUT_FILE)
    print(f"💾 Draft servo configuration table saved in '{common.SERVO_CONFIG_TPLT_FILE}'")
    print(f"   TODO:")
    print(f"      ✅ Open '{common.SERVO_CONFIG_TPLT_FILE}' in a text editor")
    print(f"      ✅ Edit servo calibration information")
    print(f"      ✅ Save the edited file as '{save_file_name}' in the '{save_dir_name}' directory")

# ------------------------------------------------------------------------------


if __name__ == "__main__":

    # Ensure output directories exist
    
    os.makedirs(os.path.join(common.ROOT_DIR, common.DOCS_DIR), exist_ok=True)
    os.makedirs(os.path.join(common.ROOT_DIR, common.BIN_DIR), exist_ok=True)
    os.makedirs(os.path.join(common.ROOT_DIR, common.TEMPLATES_DIR), exist_ok=True)

    # Create accessory information from accessory description file

    # -- read Markdown file content
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_DEFINITION_FILE), "r", encoding="utf-8") as fd:
        layout_definition_markdown = fd.read()
    
    # -- parse Markdown table
    table_data = parse_markdown_table(layout_definition_markdown)

    # -- transform markdown table data into a list of dictionaries that define each module
    module_info = generate_module_info(table_data)

    # -- transform module definition data into a list of dictionaries that define each accessory
    accessory_info = generate_accessory_info(module_info)

    # Validate accessory information

    is_valid, errors = validate_accessory_info(accessory_info)

    if is_valid:
        print("✔️ Validation Passed: The layout design respects all electrical and hardware limits")
    else:
        print("❌ Validation Failed: Fix the following configuration issues:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    # Write binary accessory info file
    
    save_accessory_info_to_binary(accessory_info)

    # Write documentation files as Markdown
 
    # -- write accessory documentation
    save_accessory_info_documentation(accessory_info)

    # -- write LED documentation
    save_led_info_documentation(accessory_info)

    # Write configuration template files as Markdown tables

    # -- write accessory config template
    save_accessory_config_template_file(accessory_info)

    # -- write switch config template
    save_switch_config_template_file(accessory_info)

    # -- write servo config template
    save_servo_config_template_file(accessory_info)

    # Write instructions for next steps

    print("\n✅ NEXT STEPS:")
    print("   When all configuration tables have been edited and saved")
    print(f"   run the '{common.BUILD_CONFIG_SCRIPT}' Python program to generate")
    print("   binary config files and documentation.")
