import struct
import os
import sys
import common
from text_tables import parse_markdown_table, to_markdown_table

def encode_mode_string(mode_str: str) -> int:
    """Converts a 4-char string (e.g., '1011') into a 4-bit mask (Mode 0 = bit 0)."""
    if not isinstance(mode_str, str) or len(mode_str) != 4:
        return 0

    mask = 0
    for mode_idx, char in enumerate(mode_str):
        if char == '1':
            mask |= (1 << mode_idx)
    return mask

def export_switches_config_to_binary_matrix(switch_data: dict) -> None:
    """
    Writes a fixed-size 64-byte matrix.
    Structure: For each mode (0..3), for each baseboard (0..3), packs a
    32-bit unsigned integer mask where bit N represents if Switch ID N is enabled.
    """

    # Total data rows in the edited user dictionary
    num_records = len(switch_data["Baseboard"])
    
    with open(os.path.join(common.ROOT_DIR, common.SWITCH_CONFIG_FILE), "wb") as bin_file:

        file_size = 0

        # Loop 1: Mode index corresponds to the character column in the strings (0 to 3)
        for mode_idx in range(4):
            
            # Loop 2: Sequential baseboards across the physical layout (0 to 3)
            for target_bb in range(4):
                # Initialise an empty 32-bit bitfield mask for this Pico under this mode
                bb_switch_mask = 0
                
                # Scan the designer dictionary to isolate entries belonging to this specific baseboard
                for idx in range(num_records):
                    if switch_data["Baseboard"][idx] != target_bb:
                        continue
                    
                    # --- Process Rear Switch ---
                    rear_id = int(switch_data["Rear Switch ID"][idx])
                    rear_modes = str(switch_data["Rear Switch Modes"][idx])

                    # If this switch is marked active ('1') for the current mode, flag its Pin bit
                    if rear_modes[mode_idx] == '1':
                        bb_switch_mask |= (1 << rear_id)
                        
                    # --- Process Front Switch (if it exists) ---
                    front_id_val = switch_data["Front Switch ID"][idx]
                    front_modes = str(switch_data["Front Switch Modes"][idx])
                    
                    if front_id_val != "-":
                        front_id = int(front_id_val)
                        if front_modes[mode_idx] == '1':
                            bb_switch_mask |= (1 << front_id)
                
                # Pack the completed mask into a 4-byte unsigned int ('I')
                # Explicit little-endian '<I' can be used if you want to ensure Pico native match, 
                # but standard native 'I' matches standard ARM Cortex-M0+ expectations perfectly.
                packed_mask = struct.pack("<I", bb_switch_mask)
                bin_file.write(packed_mask)
                file_size += len(packed_mask)
                
    print(f"💾 Binary switch config data written to '{common.SWITCH_CONFIG_FILE}' ({file_size} bytes).")

def create_switches_config():

    # Read Markdown that describes the switch modes
    with open(os.path.join(common.ROOT_DIR, common.SWITCH_CONFIG_INPUT_FILE), "r", encoding="utf-8") as fd:
        switches_mode_markdown = fd.read()

    # Parse Markdown
    switches_mode_data = parse_markdown_table(
        switches_mode_markdown,
        column_types={"Rear Switch Modes": str, "Front Switch Modes": str}
    )

    # Generate required binary file
    export_switches_config_to_binary_matrix(switches_mode_data)

def export_servos_config_to_binary(servo_data: dict) -> None:
    """
    Packs servo positions and multi-mode default states into a 5-byte binary structure.
    Header: 1-byte count of total layout servos.
    Records: 
      - Byte 0: Servo ID (1 byte)
      - Bytes 1 & 2: Off Position (2 bytes)
      - Bytes 3 & 4: On Position (2 bytes)
    """
    servo_ids = servo_data["Servos"]
    off_positions = servo_data["Off Position"]
    on_positions = servo_data["On Position"]
    
    num_servos = len(servo_ids)

    with open(os.path.join(common.ROOT_DIR, common.SERVO_CONFIG_FILE), "wb") as bin_file:
        # Write file header: Total number of active records (1 byte)
        header = struct.pack("<B", num_servos)
        bin_file.write(header)
        file_size = len(header)
        
        # Write individual records sequentially
        for idx in range(num_servos):
            s_id = servo_ids[idx]
            off_pos = off_positions[idx]
            on_pos = on_positions[idx]
            
            # Format: B (1-byte ID), H (2-byte uint16), H (2-byte uint16) = 5 bytes
            record_bytes = struct.pack("<BHH", s_id, off_pos, on_pos)
            bin_file.write(record_bytes)
            file_size += len(record_bytes)
            
    print(f"💾 Binary servo config data written to '{common.SERVO_CONFIG_FILE}' ({num_servos} items, {file_size} bytes)")

def create_servos_config():
    # Read Markdown that describes the switch modes
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
      - Byte 0: Global accessory ID
      - Byte 1: Default state bitmask for modes 0 to 3 (Bits 4-7 are 0)
    """

    bb_ids = accessories_data["Baseboard"]
    acc_types = accessories_data["Accessory Type"]
    acc_ids = accessories_data["Accessory ID"]
    modes = accessories_data["Startup Modes"]

    num_accessories = len(bb_ids)

    TYPE_NAME_TO_CODE = {v: k for k, v in common.ACCESSORY_TYPE_NAMES.items()}

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_CONFIG_FILE), "wb") as bin_file:
        # Write file header: Total number of active records (1 byte)
        header = struct.pack("<B", num_accessories)
        bin_file.write(header)
        file_size = len(header)
        
        # Write individual records sequentially
        for idx in range(num_accessories):
            type_code = TYPE_NAME_TO_CODE[acc_types[idx]]
            global_id = common.encode_global_accessory_id(bb_ids[idx], type_code, acc_ids[idx])

            # Convert the mode string (e.g., '0101') into a 4-bit integer mask
            state_mask = encode_mode_string(modes[idx])
            
            # Format: B (1-byte Global accessory ID), B (1-byte mode mask) = 2 bytes
            record_bytes = struct.pack("<BB", global_id, state_mask)
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

TYPE_NAME_TO_CODE = common.ACCESSORY_TYPE_CODES
TYPE_CODE_TO_NAME = {v: k for k, v in common.ACCESSORY_TYPE_CODES.items()}

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
        # Read the first byte to get the total number of records
        count_byte = bin_file.read(1)
        if not count_byte:
            raise FileFormatError("Malformed binary: File is empty and missing the record count byte.")
        total_records = struct.unpack("<B", count_byte)[0]

        # Read exactly the specified number of records
        for record_idx in range(total_records):
            header_bytes = bin_file.read(3)

            if len(header_bytes) < 3:
                raise FileFormatError(f"Malformed binary: Expected {total_records} records, but file ended abruptly at record {record_idx}.")

            global_id, rear_switch, front_switch_raw = struct.unpack("<BBB", header_bytes)
            front_switch = None if front_switch_raw == 0xFF else front_switch_raw

            # Extract encoded structural data from Global Accessory ID bits
            b_id, t_code, loc_id = common.decode_global_accessory_id(global_id)
            t_name = TYPE_CODE_TO_NAME[t_code]

            # Read variable length payloads based on type criteria
            leds = []
            servos = []

            if t_name == 'Turnouts':
                payload = bin_file.read(3)
                if len(payload) < 3:
                    raise FileFormatError(f"Malformed binary: Incomplete Turnout payload at record {record_idx}.")
                led1, led2, s_id = struct.unpack("<BBB", payload)
                leds = [led1, led2]
                servos = [s_id]

            elif t_name == 'Crossovers':
                payload = bin_file.read(6)
                if len(payload) < 6:
                    raise FileFormatError(f"Malformed binary: Incomplete Crossover payload at record {record_idx}.")
                led1, led2, led3, led4, s_id1, s_id2 = struct.unpack("<BBBBBB", payload)
                leds = [led1, led2, led3, led4]
                servos = [s_id1, s_id2]

            elif t_name == 'Uncouplers':
                payload = bin_file.read(2)
                if len(payload) < 2:
                    raise FileFormatError(f"Malformed binary: Incomplete Uncoupler payload at record {record_idx}.")
                led1, s_id = struct.unpack("<BB", payload)
                leds = [led1]
                servos = [s_id]

            elif t_name == 'Features':
                pass # Features contain no payload data

            configs.append({
                'baseboard_id': b_id,
                'level': 'HL' if rear_switch < 24 and front_switch is None else 'LL',  # Approximated baseline level flag
                'local_id': loc_id,
                'type': t_name,
                'global_id': global_id,
                'rear_switch_id': rear_switch,
                'front_switch_id': front_switch,
                'led_ids': leds,
                'servo_ids': servos
            })

    return configs

def reconstruct_switch_config_from_binary() -> dict:
    """Reads switch binary config file and converts the 64-byte matrix back into a 4x4 matrix dictionary structure."""

    matrix_dict = {mode: {} for mode in range(4)}

    with open(os.path.join(common.ROOT_DIR, common.SWITCH_CONFIG_FILE), "rb") as bin_file:
        for mode in range(4):
            for bb in range(4):
                packed_mask = bin_file.read(4)
                if len(packed_mask) < 4:
                    raise FileFormatError(f"Malformed binary: {common.SWITCH_CONFIG_FILE} must be exactly 64 bytes.")
                mask = struct.unpack("<I", packed_mask)[0]
                matrix_dict[mode][bb] = mask

    return matrix_dict

def reconstruct_servo_config_from_binary() -> dict:
    """Reads binary servo config file and populates the designers' columnar dictionary layout."""

    column_data = {
        "Servos": [], 
        "Off Position": [], 
        "On Position": [], 
        "Baseboard": []
    }

    with open(os.path.join(common.ROOT_DIR, common.SERVO_CONFIG_FILE), "rb") as bin_file:
        header = bin_file.read(1)
        if not header:
            return column_data
        num_servos = struct.unpack("<B", header)[0]

        for _ in range(num_servos):
            record_bytes = bin_file.read(5)
            if len(record_bytes) < 5:
                raise FileFormatError(f"Malformed binary: Incomplete 5-byte record found in {common.SERVO_CONFIG_FILE}.")

            s_id, off_pos, on_pos = struct.unpack("<BHH", record_bytes)

            # Reconstruct basic positional mapping metadata out of the Servo Global ID bits
            b_id, _ = common.decode_servo_id(s_id)

            column_data["Servos"].append(s_id)
            column_data["Off Position"].append(off_pos)
            column_data["On Position"].append(on_pos)
            column_data["Baseboard"].append(b_id)

    return column_data

def reconstruct_accessory_config_from_binary() -> dict:
    """Reads binary accessories config file and populates the designers' columnar dictionary layout."""
    
    column_data = {
        "Global ID": [], "Baseboard": [], "Accessory Type": [], "Accessory ID": [], "Startup Modes": []
    }
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_CONFIG_FILE), "rb") as bin_file:
        header = bin_file.read(1)
        if not header:
            return column_data
        num_features = struct.unpack("<B", header)[0]

        for _ in range(num_features):
            record_bytes = bin_file.read(2)
            if len(record_bytes) < 2:
                raise FileFormatError(f"Malformed binary: Incomplete 2-byte record found in {common.FEATURE_CONFIG_FILE}.")

            global_id, state_mask = struct.unpack("<BB", record_bytes)

            # Extract baseboard and local feature ID information from global_id byte
            baseboard_id, accessory_type, local_feature_id = common.decode_global_accessory_id(global_id)

            column_data["Global ID"].append(global_id)
            column_data["Baseboard"].append(baseboard_id)
            column_data["Accessory Type"].append(accessory_type)
            column_data["Accessory ID"].append(local_feature_id)
            column_data["Startup Modes"].append(decode_mode_mask_to_string(state_mask))

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
    # Compile actual registered hardware pins found inside binary accessory info definitions
    layout_servos_set = set()
    layout_switches_per_bb = {bb: set() for bb in range(4)}
    layout_accessories_set = set()

    for acc in layout_configs:
        bb = acc['baseboard_id']
        if acc['rear_switch_id'] is not None:
            layout_switches_per_bb[bb].add(acc['rear_switch_id'])
        if acc['front_switch_id'] is not None:
            layout_switches_per_bb[bb].add(acc['front_switch_id'])
        for s_id in acc['servo_ids']:
            layout_servos_set.add(s_id)
        global_accessory_id = acc["global_id"]
        layout_accessories_set.add(global_accessory_id)

    # Cross-Check A: Cross-reference switches matrix definitions with layout structure boundaries
    for mode in range(4):
        for bb in range(4):
            matrix_mask = switch_matrix[mode][bb]

            # Ensure bits are never enabled for non-existent physical switches
            for pin_id in range(32):
                if (matrix_mask & (1 << pin_id)) and (pin_id not in layout_switches_per_bb[bb]):
                    errors.append(f"Constraint Violation: {common.SWITCH_CONFIG_FILE} (Mode {mode}, Baseboard {bb}) enables Switch ID {pin_id}, but this switch does not exist in {common.ACCESSORY_INFO_FILE}.")

    # Cross-Check B: Check if every servo listed in accessory info file exists in servos config file
    binary_servos_set = set(servo_data["Servos"])
    missing_servos = layout_servos_set - binary_servos_set
    if missing_servos:
        errors.append(f"Constraint Violation: Servos {missing_servos} defined in {common.ACCESSORY_INFO_FILE} are missing inside {common.SERVO_CONFIG_FILE} mapping parameters.")

    # Cross-Check C: Validate protocol physical restrictions (1..253 range boundary check)
    for s_id in binary_servos_set:
        if not (1 <= s_id <= 253):
            errors.append(f"Protocol Boundary Error: Servo ID {s_id} is out of safe hardware ranges (1..253).")

    # Cross-Check D: Check every accessory on the layout exists in the accessory config binary file
    # for acc in layout_configs:
    try:
        global_accessory_ids_set = {
            common.encode_global_accessory_id(baseboard_id, acc_type, acc_id)
            for baseboard_id, acc_type, acc_id in zip(
                accessory_data["Baseboard"],
                accessory_data["Accessory Type"],
                accessory_data["Accessory ID"],
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
        'Baseboard',
        'Switch ID',
        'Location',
        'Accessory',
    ]

    switch_info = make_table_cols(switch_headings, MODE_HEADINGS)

    switch_to_acc = {}
    for acc in accessories_data:
        rear_sw = acc['rear_switch_id']
        front_sw = acc['front_switch_id']
        bb = acc['baseboard_id']
        # rear switch
        switch_to_acc.update({(bb, rear_sw): (acc, 'Rear')})
        # front switch if any
        if front_sw is not None:
            switch_to_acc.update({(bb, front_sw): (acc, 'Front')})

    # sort switch_to_acc on the key tuple
    # uses default sorting for tuples, equivalent to
    # switch_to_acc = dict(sorted(switch_to_acc.items(), key=lambda item: item[0]))
    switch_to_acc = dict(sorted(switch_to_acc.items()))

    for bb, sw in switch_to_acc:
        (acc, pos) = switch_to_acc[(bb, sw)]
        acc_gid = acc["global_id"]
        _, acc_type, acc_id = common.decode_global_accessory_id(acc_gid)
        level = 'Low' if acc["level"] == "LL" else "High"
        location = f"{level} / {pos}"
        acc_code = f"`{common.ACCESSORY_TYPE_SHORT_NAMES[acc_type]}:{acc_id}`"

        switch_info["Baseboard"].append(f"`{bb}`")
        switch_info["Switch ID"].append(f"`{sw}`")
        switch_info["Location"].append(location)
        switch_info["Accessory"].append(acc_code)
        for mode in range(4):
            mode_bits = switch_data[mode][bb]
            mode_bit = (mode_bits >> sw) & 1
            mode_str = '■' if mode_bit else '○'
            switch_info[MODE_HEADINGS[mode]].append(mode_str)

    # Create Markdown
    markdown = "# Switch Information\n\n"
    markdown += "The following table provides information about each switch on the layout.\n\n"
    markdown += "* _Baseboard_ is the ID of the baseboard containing the switch.\n"
    markdown += "* _Switch ID_ is the ID of the switch within its baseboard.\n"
    markdown += "* _Location_ describes the position of the switch on the layout.\n"
    markdown += "* _Accessory_ is the code of the accessory that the switch operates.\n"
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
        'Servo ID',
        'Off Position',
        'On Position',
        'Baseboard',
        'Accessory',
        'Level'
    ]

    columns = make_table_cols(servo_headings)

    # Build a lookup table: Servo ID -> Global ID for use in next for loop
    servo_to_accessory = {}
    for accessory in accessories_data:
        for servo_id in accessory.get("servo_ids", []):
            servo_to_accessory[servo_id] = accessory

    for idx in range(len(servo_data['Servos'])):
        s_id = servo_data['Servos'][idx]
        # Get accessory assoicated with servo
        acc = servo_to_accessory.get(s_id, None)
        if acc is None:
            raise ValueError(f"Malformed data: Servo {s_id} not found in accessory data")

        # Calculate accessory type, local id, level, baseboard, on and off positions
        acc_gid = acc['global_id']
        _, acc_type, acc_id = common.decode_global_accessory_id(acc_gid)
        level = 'High' if acc['front_switch_id'] is None else 'Low'
        pos_off = servo_data['Off Position'][idx]
        pos_on = servo_data['On Position'][idx]
        bb = servo_data['Baseboard'][idx]

        # Add columns
        columns['Servo ID'].append(f"`{s_id}`")
        columns['Off Position'].append(f"`{pos_off}`")
        columns['On Position'].append(f"`{pos_on}`")
        columns['Baseboard'].append(f"`{bb}`")
        columns['Accessory'].append(f"`{common.ACCESSORY_TYPE_SHORT_NAMES[acc_type]}:{acc_id}`")
        columns['Level'].append(level)

    # Generate markdown
    markdown = "# Servo Information\n\n"
    markdown += "The following table provides information about each servo on the layout.\n\n"
    markdown += "* _Servo ID_ is the ID of the servo. This is unique across the layout.\n"
    markdown += "* _Off Position_ is the calibrated `off` or default position of the servo.\n";
    markdown += "* _On Position_ is the calibrated `on` or non-default position of the servo.\n";
    markdown += "* _Baseboard_ is the ID of the baseboard containing the servo.\n"
    markdown += "* _Accessory_ is the code of the accessory that controls the servo within the baseboard.\n"
    markdown += "* _Level_ indicates whether the servo is on the high or low level of the layout.\n\n"
    markdown += generate_markdown_table(columns)
    markdown += "\n\nFor different accessory types the `off` and `on` positions of servos have slightly different meanings:\n\n"
    markdown += "* Turnouts & Crossovers - the servo moves a turnout: `off` is the turnout's `normal` position; `on` is the `reverse` position.\n"
    markdown += "* Uncouplers - the servo raises and lowers the uncoupler magnet: `off` is the `lowered` position; `on` is the `raised` position.\n"

    # Save required data
    save_markdown(markdown, common.SERVO_DOCS_FILE)
    print(f"💾 Saved servo configuration documentation to '{common.SERVO_DOCS_FILE}'")

def save_accessory_config_docs(feature_data: dict[str, list]) -> None:

    column_headings = ["Baseboard", "Accessory"]
    column_data = make_table_cols(column_headings, MODE_HEADINGS)

    for idx in range(len(feature_data['Baseboard'])):
        bb = feature_data["Baseboard"][idx]
        acc_type = common.ACCESSORY_TYPE_SHORT_NAMES[feature_data["Accessory Type"][idx]]
        acc_id = feature_data["Accessory ID"][idx]
        column_data['Baseboard'].append(f"`{bb}`")
        column_data['Accessory'].append(f"`{acc_type}:{acc_id}`")
        modes = feature_data["Startup Modes"][idx]
        for mode in range(4):
            triggered = modes[mode] == "1"
            mode_str = '■' if triggered else '○'
            column_data[MODE_HEADINGS[mode]].append(mode_str)

    markdown = "# Accessory Start-up States\n\n"
    markdown += "The following table displays information about each accessory's start-up state for each operating mode.\n\n"
    markdown += "* _Baseboard_ is the ID of the baseboard containing the accessory.\n"
    markdown += "* _Accessory_ is the type and ID of the accessory within its baseboard.\n"
    markdown += "* The last four columns shows the state of the accessory at start-up for each of the operating modes.\n\n"
    markdown += generate_markdown_table(column_data)
    markdown += "\n\nKey:\n\n"
    markdown += "* ■ = accessory set to non-default state at start-up\n"
    markdown += "* ○ = feature remains in default state at start-up\n\n"
    markdown += "'Default' and 'non-default' start-up states different interpretations for different types of devices:\n\n"
    markdown += "* Turnouts and Crossovers: default state is `normal`, non-default state is `reversed`.\n"
    markdown += "* Uncouplers: default state is `lowered`, non-default state is `raised`.\n"
    markdown += "* Features: default state is `not-triggered`, non-default state is `triggered`.\n"

    save_markdown(markdown, common.ACCESSORY_CONFIG_DOCS_FILE)
    print(f"💾 Saved accessory configuration documentation to '{common.ACCESSORY_CONFIG_DOCS_FILE}'")

if __name__ == "__main__":

    if not os.path.exists(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_FILE)):
        print(f"❌ Run '{common.BUILD_ACCESSORY_SCRIPT}' first")
        sys.exit(1)

    # --- BUILD CONFIGS ---

    create_accessories_config()
    create_switches_config()
    create_servos_config()

    # --- VALIDATE ---

    # 1. Execute system binary validation sweeps
    is_valid, validation_errors = validate_binary_files()

    if is_valid:
        print("✔️ All binary files validated successfully")

        # 2. Extract layout content to generate structural system reference sheets
        recovered_accessories = reconstruct_accessories_from_binary()
        recovered_switch_config = reconstruct_switch_config_from_binary()
        recovered_servo_config = reconstruct_servo_config_from_binary()
        recovered_accessory_config = reconstruct_accessory_config_from_binary()

        print(f"\n* Total number of accessories: {len(recovered_accessories)}")
        total_layout_switches = sum(
            1 + (item["front_switch_id"] is not None)
            for item in recovered_accessories
        )
        print(f"* Total number of switches: {total_layout_switches}")
        num_leds = sum(
            len(rec.get("led_ids", []))
            for rec in recovered_accessories
        )
        print(f"* Total number of LEDs: {num_leds}")
        print(f"* Total number of servos: {len(recovered_servo_config['Servos'])}")

        print()

        save_switch_config_docs(recovered_switch_config, recovered_accessories)
        save_servo_config_docs(recovered_servo_config, recovered_accessories)
        save_accessory_config_docs(recovered_accessory_config)

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
