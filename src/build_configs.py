import struct
import os
import sys
import common
import shared
import json
from shared import AccType
from text_tables import parse_markdown_table, to_markdown_table

def export_switches_config_to_binary_matrix(switch_data: dict[str,list]) -> None:
    """
    Writes a fixed-size 128-byte matrix.
    Structure: For each module (0..7) and for each mode (0..3), 32-bit unsigned
    integer mask where bit N represents if Switch ID N is enabled.
    """

    # Total data rows in the edited user dictionary
    num_switches = len(switch_data['Module'])
    
    with open(os.path.join(common.ROOT_DIR, common.SWITCH_CONFIG_FILE), "wb") as bin_file:

        file_size = 0

        # switch_data contains some redundant keys. We only require module, switch ID and mode data:
        # * module comes directly from 'Module' column
        # * switch ID needs to be parsed from 'Switch ID' column
        # * mode data needs to be parsed from 'Switch Modes' column
        # we get module from 'Module' column, parse switch ID from 'Switch ID' column 

        # Loop 1: Modules index corresponds to the layput modules
        for module_idx in range(shared.NUM_MODULES):
            
            # Loop 2: Mode index corresponds to the character column in the strings
            for mode_idx in range(shared.NUM_OPERATING_MODES):
                # Initialise an empty 32-bit bitfield mask for this Pico under this mode
                switch_mask = 0
                
                # Scan the template dictionary to isolate entries belonging to this specific module
                for idx in range(num_switches):
                    if int(switch_data['Module'][idx]) != module_idx:
                        continue

                    # Extract switch id number from full switch ID with format (ABC:9 or ABC:99)
                    _, sw_id_str = switch_data['Switch ID'][idx].split(':', 1)
                    sw_id = int(sw_id_str)

                    # Extract mode data
                    modes = switch_data['Switch Modes'][idx]
                    if modes[mode_idx] == '1':
                        switch_mask |= (1 << sw_id)

                # Pack the completed mask into a little endian uint32 ('<I')
                packed_mask = struct.pack("<I", switch_mask)
                bin_file.write(packed_mask)
                file_size += len(packed_mask)
                
    print(f"💾 Saved switch configuration data to '{common.SWITCH_CONFIG_FILE}' ({file_size} bytes).")

def create_switches_config():

    # Read Markdown that describes the switch modes
    with open(os.path.join(common.ROOT_DIR, common.SWITCH_CONFIG_INPUT_FILE), "r", encoding="utf-8") as fd:
        switches_mode_markdown = fd.read()

    # Parse Markdown into a dict[str, list] where key is table header and values are rows under the header
    switches_mode_data = parse_markdown_table(
        switches_mode_markdown,
        column_types={
            'Module': int,
            'Switch ID': str,
            'Switch Modes': str
        }
    )

    # Generate required binary file
    export_switches_config_to_binary_matrix(switches_mode_data)

def export_servos_config_to_binary(servo_data: dict) -> None:
    """
    Packs calibrated servo positions into a 7-byte binary structure.
    Header: 1-byte count of total layout servos.
    Records: 
      - Byte 0: Module ID (3 bit number) 
      - Byte 1: Local servo ID within module (4 bit number)
      - Bytes 2 & 3: Left Position (2 bytes)
      - Bytes 4 & 5: Right Position (2 bytes)
      - Byte 6: Reversed (single bit: 0x01 - reversed, 0x00 - normal)
    """

    # Servo config file contains some redundant table columns. Required columns are:
    # * 'Servo' - need to parse module and local servo ID from here to create global servo ID written to file
    # * 'Left Position' - left-most position of servo
    # * 'Right Position' - right-most position of servo
    # * 'Reversed' - whether servo is reversed:
    #     * if 'no' servo off is left position, on is right position;
    #     * if 'yes' servo off is right position, on is left position
    servo_ids = servo_data["Servo"]
    left_positions = servo_data["Left Position"]
    right_positions = servo_data["Right Position"]
    reversed_flags = servo_data['Reversed']    

    LEVEL_INITIALS_MAP = {k[0].upper(): v for k, v in shared.LEVEL_VALUE_MAP.items()}

    num_servos = len(servo_ids)

    with open(os.path.join(common.ROOT_DIR, common.SERVO_CONFIG_FILE), "wb") as bin_file:

        # Write file header: Total number of servo records
        header = struct.pack("<B", num_servos)
        bin_file.write(header)
        file_size = len(header)
        
        # Write individual records sequentially
        for idx in range(num_servos):
            global_servo_id = servo_ids[idx]
            left_pos = int(left_positions[idx])
            right_pos = int(right_positions[idx])
            reversed_flag = 0 if reversed_flags[idx].lower() == 'no' else 1

            # extract module and local servo ID from global servo ID. This has form 'XY:ddd', where:
            # * 'X' is the Baseboard ID - 'A'..'D', where 'A' is baseboard 0 through to 'D' for baseboard 3.
            # * 'Y' is the Level - 'L' for low level (0) or 'H' for high level (1)
            # * ':' is a separator
            # * 'ddd' is a sequence of one or more digits forming the local servo ID.
            code, servo_id_str = global_servo_id.split(':', 1)
            bb_code = code[0]
            level_code = code[1]
            servo_id = int(servo_id_str)
            bb = shared.BASEBOARD_VALUE_MAP[bb_code]
            level = LEVEL_INITIALS_MAP[level_code]
            module_id = shared.encode_module_id(level, bb)

            # Format data into a 7 byte record and write to file
            record_bytes = struct.pack(
                "<BBHHB",       # 7 bytes
                module_id,      # uint8: module containing servo
                servo_id,       # uint8: local servo ID
                left_pos,        # little endian uint16: calibrated servo left position
                right_pos,       # little endian uint16: calibrated servo right position
                reversed_flag   # uint8: whether servo operates in reverse
            )
            bin_file.write(record_bytes)
            file_size += len(record_bytes)
            
    print(f"💾 Saved servo configuration data to '{common.SERVO_CONFIG_FILE}' ({num_servos} items, {file_size} bytes)")

def create_servos_config():

    with open(os.path.join(common.ROOT_DIR, common.SERVO_CONFIG_INPUT_FILE), "r", encoding="utf-8") as fd:
        servos_mode_markdown = fd.read()

    # Parse Markdown
    servos_mode_data = parse_markdown_table(
        servos_mode_markdown,
        column_types={"Default State": str}
    )

    # Generate required binary file
    export_servos_config_to_binary(servos_mode_data)

def read_accessory_info_from_json() -> list[dict]:
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_TEMP_FILE), 'r') as json_file:
        acc_info = json.load(json_file)
    return acc_info

def read_accessory_mode_info_from_markdown() -> list[dict]:
    # Read Markdown that describes the feature modes
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_CONFIG_INPUT_FILE), "r", encoding="utf-8") as fd:
        accessories_mode_markdown = fd.read()
    # Parse Markdown
    accessories_mode_data = parse_markdown_table(
        accessories_mode_markdown,
        column_types={"Startup Modes": str}
    )
    return accessories_mode_data

def transform_accessory_mode_data(mode_data: list[dict]) -> dict[int, int]:
    # The following columns of the data table are required:
    # * 'Baseboard / Level' - value parsed to get the module containing the accessory
    # * 'Accessory' - value parsed to get the accessory type and local ID
    # * 'Startup Modes' - value parsed to get the startup mode data - valid values depend on accessory type
    module_strs = mode_data["Baseboard / Level"]
    acc_strs = mode_data["Accessory"]
    modes_strs = mode_data["Startup Modes"]

    num_accessories = len(module_strs)

    acc_short_name_map = {v: k for k, v in shared.ACCESSORY_SHORTNAMES.items()}
    mode_str_map = {'0': 0b00, '1': 0b01, '2': 0b10, '3': 0b11}

    result = {}

    # Write individual records sequentially
    for idx in range(num_accessories):

        # Parse module info: form 'X - YYY', where X is baseboard id ('A'..'D') and YYY is level (Low -> 0 or High -> 1)
        module_str = module_strs[idx]
        bb_id_str, level_id_str = module_str.split(' - ', 1)
        bb = shared.BASEBOARD_VALUE_MAP[bb_id_str.upper()]
        level = shared.LEVEL_VALUE_MAP[level_id_str.lower()]

        # Parse accessory info: form X:N, where X is code for feature and N is local accessory ID number
        acc_str = acc_strs[idx]
        acc_type_str, acc_id_str = acc_str.split(':', 1)
        acc_type = acc_short_name_map[acc_type_str]
        acc_id = int(acc_id_str)

        # -- Assemble global accessory ID
        module = shared.encode_module_id(level, bb)
        global_id = shared.encode_global_acc_id(module, acc_type, acc_id)

        # -- Parse mode data
        modes_str = modes_strs[idx]
        # -- Ensure characters in mode string are valid for type of current accessory
        mode_chars = [str(i) for i in range(0, shared.ACCESSORY_MODE_COUNTS[acc_type])]
        for char in modes_str:
            if char not in mode_chars:
                raise ValueError(f"Mode digit {char} out of range for accessory type {shared.ACCESSORY_SHORTNAMES[acc_type]}")
        # -- Assemble binary modes byte
        modes_mask = 0
        for mode_idx, char in enumerate(modes_str):
            if char not in mode_str_map.keys():
                raise ValueError(f"Invalid mode character {char}")
            modes_mask |= (mode_str_map[char] << 2 * mode_idx)

        result[global_id] = modes_mask

    return result

def export_accessory_info_to_binary(accessory_info: list, accessories_mode_data: list) -> None:
    """
    Packs layout accessory data into variable-length binary structures
    and writes them to a local binary configuration file.
    """

    def add_list_to_data(data: list[int], l: list[int]) -> list[int]:
        return data + [len(l)] + l

    transformed_mode_data = transform_accessory_mode_data(accessories_mode_data)

    count = len(accessory_info)

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_FILE), "wb") as bin_file:

        count_byte = struct.pack("<B", count)
        bin_file.write(count_byte)
        file_size = len(count_byte)

        for acc in accessory_info:

            # --- Fixed data: global ID & mode mask ---
            global_id = acc['global_id']
            mode_mask = transformed_mode_data[global_id]
            bin_file.write(struct.pack("<HB", global_id, mode_mask))
            file_size += 3

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
                
    print(f"💾 Saved accessory data to '{common.ACCESSORY_INFO_FILE}' ({count} items, {file_size} bytes)")

MODE_HEADINGS = [
    'Club Mode (normal)', 
    'Club Mode (split)', 
    'Exhib Mode (normal)', 
    'Exhib Mode (split)'
]

class FileFormatError(Exception):
    pass

def decode_mode_mask_to_string(mask: int) -> str:
    """Converts a 4-bit integer mask back into a 4-character mode string (e.g., 5 -> '1010')."""
    return "".join('1' if (mask & (1 << idx)) else '0' for idx in range(4))

def reconstruct_accessories_from_binary() -> list:
    """Reads the binary accessory info file and reconstructs the structured list of accessory configuration dictionaries."""

    configs = []

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_FILE), "rb") as bin_file:

        def read_list() -> list[int]:
            result = []
            list_size_byte = bin_file.read(1)
            list_size, = struct.unpack("<B", list_size_byte)
            for _ in range(list_size):
                list_item_byte = bin_file.read(1)
                list_item, = struct.unpack("<B", list_item_byte)
                result.append(list_item)
            return result

        # Read the first byte to get the total number of records
        count_byte = bin_file.read(1)
        if not count_byte:
            raise FileFormatError("Malformed binary: File is empty and missing the record count byte.")
        total_records = struct.unpack("<B", count_byte)[0]

        # Read exactly the specified number of records
        for record_idx in range(total_records):
            # read fixed header: global accessory ID, mode bitmask and total accessory data size
            header_bytes = bin_file.read(4)

            if len(header_bytes) < 4:
                raise FileFormatError(f"Malformed binary: Expected {total_records} records, but file ended abruptly at record {record_idx}.")

            global_id, mode_mask, acc_data_size = struct.unpack("<HBB", header_bytes)
            module, acc_type, local_id = shared.decode_global_acc_id(global_id)
            level, bb = shared.decode_module_id(module)

            data_size_count = 0

            # read rear switches list
            rear_switches = read_list()
            data_size_count += (1 + len(rear_switches))

            # read font switches list
            front_switches = read_list()
            data_size_count += (1 + len(front_switches))

            # read leds list
            leds = read_list()
            data_size_count += (1 + len(leds))

            # read servos list
            servos = read_list()
            data_size_count += (1 + len(servos))

            if acc_data_size != data_size_count:
                raise FileFormatError(f"Malformed binary: Expected {acc_data_size} bytes for accessory {global_id} but got {data_size_count}")

            configs.append({
                'global_id': global_id,
                'module': module,
                'baseboard_id': bb,
                'level': level,
                'local_id': local_id,
                'acc_type': acc_type,
                'rear_switches': rear_switches,
                'front_switches': front_switches,
                'leds': leds,
                'servos': servos,
                'mode_mask': mode_mask
            })

    return configs

def reconstruct_switch_config_from_binary() -> dict:
    """Reads switch binary config file and converts the 64-byte matrix back into a 4x4 matrix dictionary structure."""

    matrix_dict = {module: {} for module in range(shared.NUM_MODULES)}

    with open(os.path.join(common.ROOT_DIR, common.SWITCH_CONFIG_FILE), "rb") as bin_file:
        for module in range(shared.NUM_MODULES):
            for op_mode in range(shared.NUM_OPERATING_MODES):
                packed_mask = bin_file.read(4)
                if len(packed_mask) < 4:    
                    raise FileFormatError(f"Malformed binary: {common.SWITCH_CONFIG_FILE} must be exactly 64 bytes.")
                mask = struct.unpack("<I", packed_mask)[0]
                matrix_dict[module][op_mode] = mask

    return matrix_dict

def reconstruct_servo_config_from_binary() -> dict:
    """Reads binary servo config file and populates the designers' columnar dictionary layout."""

    column_data = {
        "module_id": [],
        "local_servo_id": [], 
        "left_pos": [], 
        "right_pos": [], 
        "reversed": [],
    }

    with open(os.path.join(common.ROOT_DIR, common.SERVO_CONFIG_FILE), "rb") as bin_file:

        header = bin_file.read(1)
        if not header:
            return column_data
        num_servos = struct.unpack("<B", header)[0]

        RECORD_SIZE = 7

        for _ in range(num_servos):
            
            record_bytes = bin_file.read(RECORD_SIZE)
            if len(record_bytes) < RECORD_SIZE:
                raise FileFormatError(f"Malformed binary: Incomplete {RECORD_SIZE}-byte record found in {common.SERVO_CONFIG_FILE}.")

            module_id, local_servo_id, left_pos, right_pos, reversed = struct.unpack("<BBHHB", record_bytes)

            column_data["module_id"].append(module_id)
            column_data["local_servo_id"].append(local_servo_id)
            column_data["left_pos"].append(left_pos)
            column_data["right_pos"].append(right_pos)
            column_data["reversed"].append(reversed)

    return column_data

def validate_binary_files() -> tuple:
    """
    Validates cross-file relationships and checks binary limits.
    Returns: (is_valid: bool, errors: list of str)
    """
    errors = []

    # Parse and extract reconstructed parameters from all 3 files
    try:
        layout_configs = reconstruct_accessories_from_binary()
        switch_matrix = reconstruct_switch_config_from_binary()
        servo_data = reconstruct_servo_config_from_binary()
    except (FileNotFoundError) as err:
        return False, [f"Validation aborted due to file not found error: {err}"]
    except (FileFormatError) as err:
        return False, [f"Validation aborted due to invalid binary file format: {err}"]
    except (ValueError) as err:
        return False, [f"{err}"]

    # --- CROSS FILE CHECKS ---
    # Check numbers of defined accessory items fall within design requirements
    layout_servos_per_module = {module: set() for module in range(shared.NUM_MODULES)}
    layout_switches_per_module = {module: set() for module in range(shared.NUM_MODULES)}
    layout_accessories_set = set()

    for acc in layout_configs:
        global_id = acc['global_id']
        module = acc['module']
        bb = acc['baseboard_id']
        level = acc['level']
        acc_type = acc['acc_type']
        rear_switches = acc['rear_switches']
        front_switches = acc['front_switches']
        leds = acc['leds']
        servos = acc['servos']
        mode_mask = acc['mode_mask']

        layout_switches_per_module[module].update(rear_switches)
        layout_switches_per_module[module].update(front_switches)
        for s_id in servos:
            layout_servos_per_module[module].add(s_id)
        layout_accessories_set.add(global_id)

        # Validate that start-up states for each mode are valid for accessory
        for mode_idx in range(shared.NUM_OPERATING_MODES):
            state = (mode_mask >> 2 * mode_idx) & 0b11
            valid_states = list(range(shared.ACCESSORY_MODE_COUNTS[acc_type]))
            if state not in valid_states:
                errors.append(f"Accessory {global_id} has invalid state {state} for operating mode {mode_idx}")

    # Cross-reference switches matrix definitions with accessories configuration

    for module in range(shared.NUM_MODULES):
        for op_mode in range(shared.NUM_OPERATING_MODES):

            matrix_mask = switch_matrix[module][op_mode]

            # Ensure bits are never enabled for non-existent physical switches
            for pin_id in range(32):    # 32 is size of uint32
                if (matrix_mask & (1 << pin_id)) and (pin_id not in layout_switches_per_module[module]):
                    errors.append(f"Constraint Violation: {common.SWITCH_CONFIG_FILE} (Module {module}, Mode {op_mode}) enables Switch ID {pin_id}, but this switch does not exist in {common.ACCESSORY_INFO_FILE}.")

    # Check if every servo listed in accessory info file exists in servos config file

    servo_config_servos_per_module = {module: set() for module in range(shared.NUM_MODULES)}
    servo_data_len = len(servo_data['module_id'])
    for idx in range(servo_data_len):
        module_id = servo_data['module_id'][idx]
        local_servo_id = servo_data['local_servo_id'][idx]
        servo_config_servos_per_module[module_id].add(local_servo_id)
    for module in range(shared.NUM_MODULES):
        missing_servos = layout_servos_per_module[module] - servo_config_servos_per_module[module]
        if missing_servos:
            errors.append(f"Constraint Violation: Servos {missing_servos} defined for module {module} in {common.ACCESSORY_INFO_FILE} are missing inside {common.SERVO_CONFIG_FILE}.")

    # Check if every servo has left position < right position and positions in range
    for idx in range(servo_data_len):
        left_pos = int(servo_data['left_pos'][idx])
        right_pos = int(servo_data['right_pos'][idx])
        module_id = servo_data['module_id'][idx]
        local_servo_id = servo_data['local_servo_id'][idx]
        if left_pos >= right_pos:
            errors.append(f"Constraint Violation: Servo {local_servo_id} in module {module_id} has left position ({left_pos} >= right position ({right_pos}) in {common.SERVO_CONFIG_FILE})")
        if not left_pos in shared.SERVO_RANGES['left']:
            errors.append(f"Constraint Violation: Servo {local_servo_id} in module {module_id} has left position {left_pos} out of range")
        if not right_pos in shared.SERVO_RANGES['right']:
            errors.append(f"Constraint Violation: Servo {local_servo_id} in module {module_id} has right position {right_pos} out of range")

    # Check if every local servo has an id in [1..15]
    for local_servo_id in servo_data['local_servo_id']:
        if not shared.MIN_SERVO_ID <= local_servo_id <= shared.MAX_SERVO_ID:
            errors.append(f"Constraint Violation: Servo ID {s_id} is out of permittted range ({shared.MIN_SERVO_ID}..{shared.MAX_SERVO_ID}).")

    is_valid = len(errors) == 0
    return is_valid, errors

def uniform_table_padding(columns: dict, padding: int = 99) -> dict[str,int]:
    widths = {}   
    for col in columns:
        widths.update({col: padding})
    return widths

def save_markdown(markdown: str, filename: str) -> None:
    with open(os.path.join(common.ROOT_DIR, filename), "w", encoding="utf-8") as fd:
        fd.write(markdown)

def generate_markdown_table(table_cols: dict[str,list]) -> str:
    # generate table widths to ensure each cell in a column has same width
    table_widths = uniform_table_padding(table_cols, 99)   
    return to_markdown_table(table_cols, max_widths=table_widths)

def save_markdown_table(table_cols: dict[str,list], filename: str) -> None:
    markdown = generate_markdown_table(table_cols)
    with open(os.path.join(common.ROOT_DIR, filename), "w", encoding="utf-8") as fd:
        fd.write(markdown)

def make_table_cols(*headings: str | list[str]) -> dict[str, list]:
    result = {}
    for item in headings:
        if isinstance(item, list):
            for elem in item:
                result.update({elem: []})
        elif isinstance(item, str):
            result.update({item: []})
    return result

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
        mode_mask = acc["mode_mask"]
        mode_state = [None] * shared.NUM_OPERATING_MODES
        for mode_num in range(shared.NUM_OPERATING_MODES):
            mode = (mode_mask >> 2 * mode_num) & 0b11
            mode_state[mode_num] = f"`{mode}`"
            # column_data[MODE_HEADINGS[mode_num]].append(mode_str)
        mode_str = ",".join(mode_state)

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
            'Startup State': mode_str
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
        'Startup State': []
    }
    
    for row in raw_rows:
        for key in column_data.keys():
            column_data[key].append(row[key])
            
    return column_data

def save_accessory_docs(accessory_info: list) -> None:

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
    markdown += "* _Servos_ is a list of Servos that are controlled by the accessory, if any.\n"
    op_modes = '; '.join(f"{i} - {MODE_HEADINGS[i]}" for i in range(shared.NUM_OPERATING_MODES))
    markdown += f"* _Startup State_ is a list of comma separated the start-up states of the accessory in each of the four operating modes, from 0 to {shared.NUM_OPERATING_MODES - 1}. Operating modes are:\n"
    markdown += '\n'.join(f"    * {i} - {MODE_HEADINGS[i]}" for i in range(shared.NUM_OPERATING_MODES))
    markdown += "\n\n"
    markdown += to_markdown_table(doc_info, max_widths=uniform_table_padding(doc_info, 99))
    markdown += "\n\nNote that switch, LED and servo IDs are unique within their host module, but not unique across the layout.\n"

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_DOCS_FILE), "w", encoding="utf-8") as fd:
        fd.write(markdown)
    print(f"💾 Saved accessory documentation to '{common.ACCESSORY_DOCS_FILE}'")

def save_switch_config_docs(switch_data: list, accessories_data: list) -> None:

    switch_headings = [
        'Level',
        'Baseboard',
        'Switch ID',
        'Side',
        'Accessory',
    ]

    LOC_REAR = 0
    LOC_FRONT = 1

    LOCATION_MAP = {LOC_REAR: 'Rear', LOC_FRONT: 'Front'}

    switch_info = make_table_cols(switch_headings, MODE_HEADINGS)
    switch_to_acc = {}
    for acc in accessories_data:
        module = acc['module']
        gid = acc['global_id']
        rear_switches = acc['rear_switches']
        front_switches = acc['front_switches']
        for rear_sw in rear_switches:
            switch_to_acc.update({(module, rear_sw): (gid, LOC_REAR) })    
        for front_sw in front_switches:
            switch_to_acc.update({(module, front_sw): (gid, LOC_FRONT)})

    # sort switch_to_acc on the key tuple
    # uses default sorting for tuples, equivalent to
    # switch_to_acc = dict(sorted(switch_to_acc.items(), key=lambda item: item[0]))
    switch_to_acc = dict(sorted(switch_to_acc.items()))

    for module, sw in switch_to_acc:
        (acc_gid, pos) = switch_to_acc[(module, sw)]
        _, acc_type, acc_id = shared.decode_global_acc_id(acc_gid)
        level, bb = shared.decode_module_id(module)
        acc_code = f"`{shared.ACCESSORY_SHORTNAMES[acc_type]}:{acc_id}`"

        switch_info['Level'].append(shared.LEVEL_NAMES_MAP[level])
        switch_info["Baseboard"].append(f"`{shared.BASEBOARD_NAMES_MAP[bb]}`")
        switch_info["Switch ID"].append(f"`{sw}`")
        switch_info["Side"].append(LOCATION_MAP[pos])
        switch_info["Accessory"].append(acc_code)
        for mode in range(shared.NUM_OPERATING_MODES):
            mode_bits = switch_data[module][mode]
            mode_bit = (mode_bits >> sw) & 1
            mode_str = '■' if mode_bit else '○'
            switch_info[MODE_HEADINGS[mode]].append(mode_str)

    # Create Markdown
    markdown = "# Switch Information\n\n"
    markdown += "The following table provides information about each switch on the layout.\n\n"
    markdown += "* _Level_ is the level containing the switch.\n"
    markdown += "* _Baseboard_ is the baseboard containing the switch.\n"
    markdown += "* _Switch ID_ is the ID of the switch within its level and baseboard.\n"
    markdown += "* _Side_ describes which side of the baseboard the switch is on.\n"
    markdown += "* _Accessory_ is the code of the accessory that the switch operates. The character before the colon is the accessory type code and the digit(s) after the colon are the accessory ID, unique with the level, baseboard and type. Type codes are as follows:\n"
    markdown += "".join([f"    * `{shared.ACCESSORY_SHORTNAMES[acc]}` - {shared.ACCESSORY_NAMES[acc]}\n" for acc in AccType])
    markdown += "\n"
    markdown += "* The final columns show whether the switch is enabled or disabled in each of the four operating modes.\n\n"
    markdown += generate_markdown_table(switch_info)
    markdown += "\n\nKey:\n"
    markdown += "\n* ■ = switch enabled"
    markdown += "\n* ○ = switch disabled\n"
    # Save required data
    save_markdown(markdown, common.SWITCH_DOCS_FILE)
    print(f"💾 Saved switch configuration documentation to '{common.SWITCH_DOCS_FILE}'")


def save_servo_config_docs(servo_data: list, accessories_data: list) -> None:

    servo_headings = [
        'Module',
        'Servo',
        'Left Position',
        'Right Position',
        'Reversed',
        'Accessory',
    ]

    columns = make_table_cols(servo_headings)

    # Build a lookup table mapping (module, servo_id) to controlling accessory
    servo_to_accessory = {}
    for accessory in accessories_data:
        servo_ids = accessory['servos']
        module = accessory['module']
        for servo_id in servo_ids:
            # servo IDs are unique within their module, so a tuple (module, servo_id) 
            # is needed to uniquely identify a servo within the layout
            servo_to_accessory[(module, servo_id)] = accessory

    for idx in range(len(servo_data['local_servo_id'])):
        local_servo_id = servo_data['local_servo_id'][idx]
        module_id = servo_data['module_id'][idx]
        left_pos = servo_data['left_pos'][idx]
        right_pos = servo_data['right_pos'][idx]
        reversed = servo_data['reversed'][idx]
        
        # Get accessory assoicated with servo
        acc = servo_to_accessory.get((module_id, local_servo_id), None)
        if acc is None:
            raise ValueError(f"Malformed data: Servo {local_servo_id} not found in accessory data")

        # Calculate accessory type, local id, level, baseboard, on and off positions
        acc_gid = acc['global_id']
        _, acc_type, acc_lid = shared.decode_global_acc_id(acc_gid)
        level, bb = shared.decode_module_id(module_id)

        # Add columns
        columns['Module'].append(f"`{module_id}`")
        columns['Servo'].append(f"`{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0].upper()}:{local_servo_id}`")
        columns['Left Position'].append(f"`{left_pos}`")
        columns['Right Position'].append(f"`{right_pos}`")
        columns['Reversed'].append('Yes' if reversed else 'No')
        columns['Accessory'].append(f"`{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0].upper()}{shared.ACCESSORY_SHORTNAMES[acc_type]}:{acc_lid}`")
 
    # Generate markdown
    bb_names = list(shared.BASEBOARD_NAMES_MAP.values())
    markdown = "# Servo Information\n\n"
    markdown += "The following table provides information about each servo on the layout.\n\n"
    markdown += "* _Module_ is the number of the layout module containing both the servo and its controlling accessory.\n"
    markdown += "* _Servo_ is the ID of the servo. This is unique within the level and baseboard.\n"
    markdown += "* _Left Position_ is the calibrated `left` position of the servo.\n"
    markdown += "* _Right Position_ is the calibrated `right` position of the servo.\n"
    markdown += "* _Reversed_ is a flag denotes whether the `normal` position of the servo is _Left Position_ or _Right Position_ or vice versa. When _Reversed_ is false then the `normal` position is _Left Position_ and when _Reversed_ is true then the `normal` position is _Right Position_.\n"
    markdown += "* _Accessory_ is ID of the accessory that controls the servo within. This is unique within the layout.\n\n"
    markdown += generate_markdown_table(columns)
    markdown += "\n\nKey to servo and accessory IDs:\n\n"
    markdown += "* Servo IDs have the format: `XY:Z`, where:\n\n"
    markdown += f"    * 1st character: baseboard ID (`{bb_names[0]}`..`{bb_names[-1]}`)\n"
    markdown += f"    * 2nd character: level ({'; '.join([f"`{i[0].upper()}` - {i.capitalize()}" for i in shared.LEVEL_VALUE_MAP.keys() ])})\n"
    markdown += "    * 3rd character: separator (always `:`)\n"
    markdown += f"    * digit(s): the id (`{shared.MIN_SERVO_ID}`..`{shared.MAX_SERVO_ID}`) of the servo within its baseboard and level\n\n"
    markdown += "* Accessory IDs have the format `WXY:Z`, where:\n\n"
    markdown += f"    * 1st character: baseboard ID (`{bb_names[0]}`..`{bb_names[-1]}`)\n"
    markdown += f"    * 2nd character: level ({'; '.join([f"`{i[0].upper()}` - {i.capitalize()}" for i in shared.LEVEL_VALUE_MAP.keys() ])})\n"
    markdown += f"    * 3rd character: accessory type ({'; '.join([f"`{shared.ACCESSORY_SHORTNAMES[a].upper()}` - {shared.ACCESSORY_NAMES[a].capitalize()}" for a in AccType])})\n"
    markdown += "    * 4th character: separator (always `:`)\n"
    markdown += f"    * digit(s): the id (`0`..`{shared.MAX_ACCESSORIES_PER_MODULE - 1}`) of the accessory within its baseboard, level and type\n\n"
    markdown += "* _Reversed_ has the following function:\n\n"
    markdown += "    * When false ('No') the servo's `normal` position is _Left Position_ and its `turned` position is _Right Position_.\n"
    markdown += "    * When true ('Yes') the servo's `normal` position is _Right Position_ and its `turned` position is _Left Position_.\n"

    # Save required data
    save_markdown(markdown, common.SERVO_DOCS_FILE)
    print(f"💾 Saved servo configuration documentation to '{common.SERVO_DOCS_FILE}'")

def generate_summary_docs_table(accessory_data: dict[str, list]) -> str:

    def summarize_module_elements(data: list, target_keys: list) -> tuple[dict, list[dict]]:
        """
        Sums the lengths of lists stored under specified keys, grouped by module (0-7).
        
        Args:
            data: List of dictionaries containing a 'module' key and target lists.
            target_keys: List of string keys whose list lengths should be summed.
            
        Returns:
            A tuple containing:
            1. A single dictionary mapping module numbers to total counts.
            2. A list of single-key dictionaries mapping module numbers to total counts.
        """
        # Pre-populate all modules from 0 to 7 with 0
        combined_dict = {module: 0 for module in range(8)}
        
        for item in data:
            module = item.get("module")
            
            # Skip if the module key is missing or out of range (0 to 7)
            if module is None or not (0 <= module <= 7):
                continue
                
            # Sum lengths of all requested lists for this module
            for key in target_keys:
                element_list = item.get(key)
                if isinstance(element_list, list):
                    combined_dict[module] += len(element_list)

        return combined_dict

    total_switches_per_module = summarize_module_elements(accessory_data, ['rear_switches', 'front_switches'])
    total_switches = sum(list(total_switches_per_module.values()))

    total_leds_per_module = summarize_module_elements(accessory_data, ['leds'])
    total_leds = sum(list(total_leds_per_module.values()))

    total_servos_per_module = summarize_module_elements(accessory_data, ['servos'])
    total_servos = sum(list(total_servos_per_module.values()))

    total_accs_per_module = {module: 0 for module in range(8)}
    for acc_item in accessory_data:
        total_accs_per_module[acc_item['module']] += 1
    total_accs = sum(list(total_accs_per_module.values()))

    data = {
        'Module': list(range(shared.NUM_MODULES)) + ['Layout Total'],
        'Accessories': list(total_accs_per_module.values()) + [total_accs],
        'Switches': list(total_switches_per_module.values()) + [total_switches],
        'LEDs': list(total_leds_per_module.values()) + [total_leds],
        'Servos': list(total_servos_per_module.values()) + [total_servos]
    } 

    return generate_markdown_table(data)

def save_summary_docs(accessory_data: dict[str, list]) -> None:

    table = generate_summary_docs_table(accessory_data)

    markdown =  "# Hardware Summary\n\n"
    markdown += "The following table displays the total numbers of different types of hardware per module, and for the whole layout.\n\n"
    markdown += table
    save_markdown(markdown, common.SUMMARY_DOCS_FILE)

    print(f"💾 Saved summary documentation to '{common.SUMMARY_DOCS_FILE}'")

if __name__ == "__main__":

    if not os.path.exists(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_TEMP_FILE)):
        print(f"❌ Run '{common.BUILD_ACCESSORY_SCRIPT}' first")
        sys.exit(1)

    # --- BUILD CONFIGS ---

    acc_info = read_accessory_info_from_json()
    acc_mode_info = read_accessory_mode_info_from_markdown()

    export_accessory_info_to_binary(acc_info, acc_mode_info)
    create_switches_config()
    create_servos_config()

    # Validate binary files
    is_valid, validation_errors = validate_binary_files()

    if is_valid:
        print("✔️ All binary files validated successfully")

        # Extract hardware info from binary files
        recovered_accessories = reconstruct_accessories_from_binary()
        recovered_switch_config = reconstruct_switch_config_from_binary()
        recovered_servo_config = reconstruct_servo_config_from_binary()

        # Generate hardware documentation
        save_accessory_docs(recovered_accessories)
        save_switch_config_docs(recovered_switch_config, recovered_accessories)
        save_servo_config_docs(recovered_servo_config, recovered_accessories)
        save_summary_docs(recovered_accessories)

        # Display hardware summary
        print(f"\nSummary of layout hardware:\n\n{generate_summary_docs_table(recovered_accessories)}\n")

        # Display instructions
        print(f"\n✅ NEXT STEPS:")
        print(f"   Copy all files from the '{common.BIN_DIR}' directory to every layout microcontroller:")
        print(f"      * '{os.path.basename(common.ACCESSORY_INFO_FILE)}'")
        print(f"      * '{os.path.basename(common.SWITCH_CONFIG_FILE)}'")
        print(f"      * '{os.path.basename(common.SERVO_CONFIG_FILE)}'")

    else:
        print("❌ Binary validation failed:")
        for error in validation_errors:
            print(f"  - {error}")
