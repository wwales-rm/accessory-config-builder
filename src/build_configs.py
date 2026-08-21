import struct
import os
import sys
import common
import shared
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
                
    print(f"💾 Binary switch config data written to '{common.SWITCH_CONFIG_FILE}' ({file_size} bytes).")

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
    Packs calibrated servo positions into a 6-byte binary structure.
    Header: 1-byte count of total layout servos.
    Records: 
      - Byte 0: Module ID (3 bit number) 
      - Byte 1: Local servo ID within module (4 bit number)
      - Bytes 2 & 3: Off Position (2 bytes)
      - Bytes 4 & 5: On Position (2 bytes)
    """

    # Servo config file contains some redundant table columns. Required columns are:
    # * 'Servo' - need to parse module and local servo ID from here to create global servo ID written to file
    # * 'Off Position' - position of servo when off
    # * 'On Position' - position of servo when on
    servo_ids = servo_data["Servo"]
    off_positions = servo_data["Off Position"]
    on_positions = servo_data["On Position"]

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
            off_pos = off_positions[idx]
            on_pos = on_positions[idx]

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
            
            # Format data into a 6 byte record and write to file
            record_bytes = struct.pack(
                "<BBHH",        # 6 bytes
                module_id,      # uint8: module containing servo
                servo_id,       # uint8: local servo ID
                off_pos,        # little endian uint16: calibrated servo off position
                on_pos          # little endian uint16: calibrated servo off position
            )
            bin_file.write(record_bytes)
            file_size += len(record_bytes)
            
    print(f"💾 Binary servo config data written to '{common.SERVO_CONFIG_FILE}' ({num_servos} items, {file_size} bytes)")

    # Read Markdown that describes the switch modes
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

def export_accessories_config_to_binary(accessories_data: dict) -> None:
    """
    Packs accessories start up states and into a 2-byte binary structure.
    Header: 1-byte count of total number of accessories on layout.
    Records: 
      - Bytes 0 & 1: Unsigned 16 bit integer containing global accessory ID
      - Byte 2: Bitmask for modes 0 to 3: mode N is encoded in bits 2N+1 & 2N
    """

    # The following columns of the data table are required:
    # * 'Baseboard / Level' - value parsed to get the module containing the accessory
    # * 'Accessory' - value parsed to get the accessory type and local ID
    # * 'Startup Modes' - value parsed to get the startup mode data - valid values depend on accessory type
    module_strs = accessories_data["Baseboard / Level"]
    acc_strs = accessories_data["Accessory"]
    modes_strs = accessories_data["Startup Modes"]

    num_accessories = len(module_strs)

    acc_short_name_map = {v: k for k, v in shared.ACCESSORY_SHORTNAMES.items()}
    mode_str_map = {'0': 0b00, '1': 0b01, '2': 0b10, '3': 0b11}

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_CONFIG_FILE), "wb") as bin_file:
        # Write file header: Total number of active records (1 byte)
        header = struct.pack("<B", num_accessories)
        bin_file.write(header)
        file_size = len(header)
        
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

            # Parse mode data
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

            # -- Assemble global accessory ID
            module = shared.encode_module_id(level, bb)
            global_id = shared.encode_global_acc_id(module, acc_type, acc_id)

            # Write data record: Format: H (2-byte Global accessory ID), B (1-byte mode mask) = 2 bytes
            record_bytes = struct.pack("<HB", global_id, modes_mask)
            bin_file.write(record_bytes)
            file_size += len(record_bytes)

    print(f"💾 Binary accessory config data written to '{common.ACCESSORY_CONFIG_FILE}' ({num_accessories} items, {file_size} bytes)")

def create_accessories_config():
    # Read Markdown that describes the feature modes
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_CONFIG_INPUT_FILE), "r", encoding="utf-8") as fd:
        features_mode_markdown = fd.read()
    # Parse Markdown
    accessories_mode_data = parse_markdown_table(
        features_mode_markdown,
        column_types={"Startup Modes": str}
    )
    # Generate required binary file
    export_accessories_config_to_binary(accessories_mode_data)

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
            # read fixed header: global accessory ID and total accessory data size
            header_bytes = bin_file.read(3)

            if len(header_bytes) < 3:
                raise FileFormatError(f"Malformed binary: Expected {total_records} records, but file ended abruptly at record {record_idx}.")

            global_id, acc_data_size = struct.unpack("<HB", header_bytes)
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
                'servos': servos
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
        "off_pos": [], 
        "on_pos": [], 
    }

    with open(os.path.join(common.ROOT_DIR, common.SERVO_CONFIG_FILE), "rb") as bin_file:

        header = bin_file.read(1)
        if not header:
            return column_data
        num_servos = struct.unpack("<B", header)[0]

        RECORD_SIZE = 6

        for _ in range(num_servos):
            
            record_bytes = bin_file.read(RECORD_SIZE)
            if len(record_bytes) < RECORD_SIZE:
                raise FileFormatError(f"Malformed binary: Incomplete {RECORD_SIZE}-byte record found in {common.SERVO_CONFIG_FILE}.")

            module_id, local_servo_id, off_pos, on_pos = struct.unpack("<BBHH", record_bytes)

            column_data["module_id"].append(module_id)
            column_data["local_servo_id"].append(local_servo_id)
            column_data["off_pos"].append(off_pos)
            column_data["on_pos"].append(on_pos)

    return column_data

def reconstruct_accessory_config_from_binary() -> dict:
    """Reads binary accessories config file and populates the designers' columnar dictionary layout."""
    
    column_data = {
        "global_id": [], 
        "module_id": [],
        "acc_type": [],
        "acc_local_id": [],
        "startup_modes": []
    }
    RECORD_SIZE = 3

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_CONFIG_FILE), "rb") as bin_file:

        header = bin_file.read(1)
        if not header:
            return column_data
        num_features = struct.unpack("<B", header)[0]

        for _ in range(num_features):
            record_bytes = bin_file.read(RECORD_SIZE)
            if len(record_bytes) < RECORD_SIZE:
                raise FileFormatError(f"Malformed binary: Incomplete {RECORD_SIZE}-byte record found in {common.FEATURE_CONFIG_FILE}.")

            global_id, startup_modes = struct.unpack("<HB", record_bytes)

            # Extract baseboard and local feature ID information from global_id byte
            module_id, acc_type, acc_local_id = shared.decode_global_acc_id(global_id)


            column_data["global_id"].append(global_id)
            column_data["module_id"].append(module_id)
            column_data["acc_type"].append(acc_type)
            column_data["acc_local_id"].append(acc_local_id)
            column_data["startup_modes"].append(startup_modes)

    return column_data

def validate_binary_files() -> tuple:
    """
    Validates cross-file relationships and checks binary limits.
    Returns: (is_valid: bool, errors: list of str)
    """
    errors = []

    # 1. Parse and extract reconstructed parameters from all 3 files
    try:
        layout_configs = reconstruct_accessories_from_binary()
        switch_matrix = reconstruct_switch_config_from_binary()
        servo_data = reconstruct_servo_config_from_binary()
        accessory_data = reconstruct_accessory_config_from_binary()
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

        layout_switches_per_module[module].update(rear_switches)
        layout_switches_per_module[module].update(front_switches)
        for s_id in servos:
            layout_servos_per_module[module].add(s_id)
        layout_accessories_set.add(global_id)

    # Cross-Check A: Cross-reference switches matrix definitions with accessories configuration

    for module in range(shared.NUM_MODULES):
        for op_mode in range(shared.NUM_OPERATING_MODES):

            matrix_mask = switch_matrix[module][op_mode]

            # Ensure bits are never enabled for non-existent physical switches
            for pin_id in range(32):    # 32 is size of uint32
                if (matrix_mask & (1 << pin_id)) and (pin_id not in layout_switches_per_module[module]):
                    errors.append(f"Constraint Violation: {common.SWITCH_CONFIG_FILE} (Module {module}, Mode {op_mode}) enables Switch ID {pin_id}, but this switch does not exist in {common.ACCESSORY_INFO_FILE}.")

    # Cross-Check B: Check if every servo listed in accessory info file exists in servos config file

    servo_config_servos_per_module = {module: set() for module in range(shared.NUM_MODULES)}
    servo_data_len = len(servo_data['module_id'])
    for idx in range(servo_data_len):
        module_id = servo_data['module_id'][idx]
        local_servo_id = servo_data['local_servo_id'][idx]
        servo_config_servos_per_module[module_id].add(local_servo_id)
    for module in range(shared.NUM_MODULES):
        missing_servos = layout_servos_per_module[module] - servo_config_servos_per_module[module]
        if missing_servos:
            errors.append(f"Constraint Violation: Servos {missing_servos} defined for module {module}  in {common.ACCESSORY_INFO_FILE} are missing inside {common.SERVO_CONFIG_FILE}.")

    # Cross-Check C: Check if every local servo has an id in [1..15]
    for local_servo_id in servo_data['local_servo_id']:
        if not shared.MIN_SERVO_ID <= local_servo_id <= shared.MAX_SERVO_ID:
            errors.append(f"Constraint Violation: Servo ID {s_id} is out of permittted range ({shared.MIN_SERVO_ID}..{shared.MAX_SERVO_ID}).")

    # Cross-Check D: Check every accessory on the layout exists in the accessory config binary file
    try:
        global_accessory_ids_set = {
            shared.encode_global_acc_id(module_id, acc_type, acc_id)
            for module_id, acc_type, acc_id in zip(
                accessory_data["module_id"],
                accessory_data["acc_type"],
                accessory_data["acc_local_id"],
                strict=True
            )
        }
    except ValueError:
        errors.append("Malformed accessory config data: value lists are not the same length")
    else:
        missing_accs = layout_accessories_set - global_accessory_ids_set
        if missing_accs:
            errors.append(f"Constraint violation: Accessories {missing_accs} defined in {common.ACCESSORY_INFO_FILE}, have not been configured in {common.ACCESSORY_CONFIG_FILE}")

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
        # acc_gid = acc["global_id"]
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
        'Off Position',
        'On Position',
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
        off_pos = servo_data['off_pos'][idx]
        on_pos = servo_data['on_pos'][idx]
        
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
        columns['Off Position'].append(f"`{off_pos}`")
        columns['On Position'].append(f"`{on_pos}`")
        columns['Accessory'].append(f"`{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0].upper()}{shared.ACCESSORY_SHORTNAMES[acc_type]}:{acc_lid}`")
 
    # Generate markdown
    bb_names = list(shared.BASEBOARD_NAMES_MAP.values())
    markdown = "# Servo Information\n\n"
    markdown += "The following table provides information about each servo on the layout.\n\n"
    markdown += "* _Module_ is the number of the layout module containing both the servo and its controlling accessory.\n"
    markdown += "* _Servo_ is the ID of the servo. This is unique within the level and baseboard.\n"
    markdown += "* _Off Position_ is the calibrated `off` or default position of the servo.\n"
    markdown += "* _On Position_ is the calibrated `on` or non-default position of the servo.\n"
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
    markdown += f"    * digit(s): the id (`0`..`{shared.MAX_ACCESSORIES_PER_MODULE - 1}`) of the accessory within its baseboard, level and type\n"

    # Save required data
    save_markdown(markdown, common.SERVO_DOCS_FILE)
    print(f"💾 Saved servo configuration documentation to '{common.SERVO_DOCS_FILE}'")

def save_accessory_config_docs(accessory_data: dict[str, list]) -> None:

    column_headings = ["Accessory"]
    column_data = make_table_cols(column_headings, MODE_HEADINGS)

    for idx in range(len(accessory_data['global_id'])):

        global_id = accessory_data['global_id'][idx]
        module, acc_type, local_id = shared.decode_global_acc_id(global_id)
        level, bb = shared.decode_module_id(module)

        column_data['Accessory'].append(
            f"`{shared.BASEBOARD_NAMES_MAP[bb]}{shared.LEVEL_NAMES_MAP[level][0].upper()}{shared.ACCESSORY_SHORTNAMES[acc_type]}:{local_id}`"
        )

        mode_mask = accessory_data["startup_modes"][idx]
        for mode_num in range(shared.NUM_OPERATING_MODES):
            mode = (mode_mask >> 2 * mode_num) & 0b11
            mode_str = f"`{mode}`"
            column_data[MODE_HEADINGS[mode_num]].append(mode_str)

    markdown = "# Accessory Start-up States\n\n"
    markdown += "The following table displays information about each accessory's start-up state for each operating mode.\n\n"
    markdown += "* _Accessory_ identifies the accessory uniquely across the whole layout.\n"
    markdown += "* The last four columns shows the state of the accessory at start-up for each of the operating modes.\n\n"
    markdown += generate_markdown_table(column_data)
    bb_names = list(shared.BASEBOARD_NAMES_MAP.values())
    markdown += "\n\nKey:\n\n"
    markdown += "* Accessory IDs have the format `WXY:Z`, where:\n\n"
    markdown += f"    * 1st character: baseboard ID (`{bb_names[0]}`..`{bb_names[-1]}`)\n"
    markdown += f"    * 2nd character: level ({'; '.join([f"`{i[0].upper()}` - {i.capitalize()}" for i in shared.LEVEL_VALUE_MAP.keys() ])})\n"
    markdown += f"    * 3rd character: accessory type ({'; '.join([f"`{shared.ACCESSORY_SHORTNAMES[a].upper()}` - {shared.ACCESSORY_NAMES[a].capitalize()}" for a in AccType])})\n"
    markdown += "    * 4th character: separator (always `:`)\n"
    markdown += f"    * digit(s): the id (`0`..`{shared.MAX_ACCESSORIES_PER_MODULE - 1}`) of the accessory within its baseboard, level and type\n\n"
    markdown += "* Each type of accessory has a different number of valid start-up states, as follows:\n\n"
    markdown += "".join([f"    * {shared.ACCESSORY_NAMES[acc]} - `0`..`{shared.ACCESSORY_MODE_COUNTS[acc] - 1}`\n" for acc in AccType])
    markdown += "\n"
    markdown += "    See the layout description document for information about the different states.\n"

    save_markdown(markdown, common.ACCESSORY_CONFIG_DOCS_FILE)

    print(f"💾 Saved accessory configuration documentation to '{common.ACCESSORY_CONFIG_DOCS_FILE}'")

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

    if not os.path.exists(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_FILE)):
        print(f"❌ Run '{common.BUILD_ACCESSORY_SCRIPT}' first")
        sys.exit(1)

    # --- BUILD CONFIGS ---

    create_accessories_config()
    create_switches_config()
    create_servos_config()

    # # --- VALIDATE ---

    # Validate binary files
    is_valid, validation_errors = validate_binary_files()

    if is_valid:
        print("✔️ All binary files validated successfully")

        # Extract hardware info from binary files
        recovered_accessories = reconstruct_accessories_from_binary()
        recovered_switch_config = reconstruct_switch_config_from_binary()
        recovered_servo_config = reconstruct_servo_config_from_binary()
        recovered_accessory_config = reconstruct_accessory_config_from_binary()

        # Generate hardware documentation
        save_switch_config_docs(recovered_switch_config, recovered_accessories)
        save_servo_config_docs(recovered_servo_config, recovered_accessories)
        save_accessory_config_docs(recovered_accessory_config)
        save_summary_docs(recovered_accessories)

        # Display hardware summary
        print(f"\nSummary of layout hardware:\n\n{generate_summary_docs_table(recovered_accessories)}\n")

        # Display instructions
        print(f"\n✅ NEXT STEPS:")
        print(f"   Copy all files from the '{common.BIN_DIR}' directory to every layout microcontroller:")
        print(f"      * '{os.path.basename(common.ACCESSORY_INFO_FILE)}'")
        print(f"      * '{os.path.basename(common.ACCESSORY_CONFIG_FILE)}'")
        print(f"      * '{os.path.basename(common.SWITCH_CONFIG_FILE)}'")
        print(f"      * '{os.path.basename(common.SERVO_CONFIG_FILE)}'")

    else:
        print("❌ Binary validation failed:")
        for error in validation_errors:
            print(f"  - {error}")
