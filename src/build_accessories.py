import sys
import os
import struct
from collections import defaultdict
import common
from text_tables import to_markdown_table, parse_markdown_table

def generate_accessory_info(raw_data: dict) -> list:
    """
    Transforms raw accessory description into information about the required
    accessories and their associated switches, LEDs and servos.
    """

    # Get baseboard IDs
    baseboard_ids = raw_data['Baseboard ID']
    
    # Filter out the ID key to isolate accessory types
    accessory_keys = [key for key in raw_data.keys() if key != 'Baseboard ID']
    
    # Map each baseboard ID to the data items at the same index
    transformed_data = {
        board_id: {key: raw_data[key][idx] for key in accessory_keys}
        for idx, board_id in enumerate(baseboard_ids)
    }

    all_accessories = []

    for b_id, counts in transformed_data.items():
        # Track accessory local IDs within this baseboard (indexed by type code)
        local_id_counters = {
            common.ACCESSORY_TYPE_FEATURE: 0, 
            common.ACCESSORY_TYPE_TURNOUT: 0, 
            common.ACCESSORY_TYPE_CROSSOVER: 0, 
            common.ACCESSORY_TYPE_UNCOUPLER: 0
        }
        
        # --- PRE-CALCULATIONS FOR SWITCH, LED and SERVO IDs ---
        # 1. Switches: High Level (HL) vs Low Level (LL) offset partitions
        hl_switch_total = sum(counts[f'HL {t}'] for t in common.ACCESSORY_TYPE_CODES.keys())
        ll_switch_total = sum(counts[f'LL {t}'] for t in common.ACCESSORY_TYPE_CODES.keys())
        
        hl_sw_ptr = 0
        ll_rear_sw_ptr = hl_switch_total
        ll_front_sw_ptr = hl_switch_total + ll_switch_total
        
        # 2. LEDs: Sum all high level LEDs to find the start pointer for low level
        hl_led_total = (counts['HL Turnouts'] * 2) + (counts['HL Crossovers'] * 4) + (counts['HL Uncouplers'] * 1)
        hl_led_ptr = 0
        ll_led_ptr = hl_led_total
        
        # 3. Servos: Sum all high level servos to find start pointer for low level
        hl_servo_total = (counts['HL Turnouts'] * 1) + (counts['HL Crossovers'] * 2) + (counts['HL Uncouplers'] * 1)
        hl_servo_ptr = 1  # IDs start at 1
        ll_servo_ptr = 1 + hl_servo_total

        # --- HARDWARE CONFIGURATION GENERATION LOOP ---
        for level in ['HL', 'LL']:
            # Maintain processing order context for index mappings
            for t_name, t_code in common.ACCESSORY_TYPE_CODES.items():
                qty = counts[f'{level} {t_name}']
                
                for _ in range(qty):
                    # Local ID Assignment
                    loc_id = local_id_counters[t_code]
                    local_id_counters[t_code] += 1
                    
                    # Global ID Generation (8-bit pack: BB Type Local)
                    global_id = common.encode_global_accessory_id(b_id, t_code, loc_id)
                    
                    # Switch Assignment Logic
                    if level == 'HL':
                        rear_switch = hl_sw_ptr
                        front_switch = None
                        hl_sw_ptr += 1
                    else:
                        rear_switch = ll_rear_sw_ptr
                        front_switch = ll_front_sw_ptr
                        ll_rear_sw_ptr += 1
                        ll_front_sw_ptr += 1
                        
                    # LED Array Assignment
                    leds = []
                    if t_name != 'Features':
                        # Determine current baseboard counter pointer
                        ptr = hl_led_ptr if level == 'HL' else ll_led_ptr
                        
                        if t_name == 'Turnouts':    leds, ptr = [ptr, ptr + 1], ptr + 2
                        elif t_name == 'Crossovers': leds, ptr = list(range(ptr, ptr + 4)), ptr + 4
                        elif t_name == 'Uncouplers': leds, ptr = [ptr], ptr + 1
                        
                        # Save the updated pointer state
                        if level == 'HL': hl_led_ptr = ptr
                        else: ll_led_ptr = ptr

                    # Servo ID Bit Assembly (8-bit pack: 0 BB Local)
                    servos = []
                    if t_name != 'Features':
                        s_ptr = hl_servo_ptr if level == 'HL' else ll_servo_ptr
                        
                        if t_name == 'Turnouts':    s_list, s_ptr = [s_ptr], s_ptr + 1
                        elif t_name == 'Crossovers': s_list, s_ptr = [s_ptr, s_ptr + 1], s_ptr + 2
                        elif t_name == 'Uncouplers': s_list, s_ptr = [s_ptr], s_ptr + 1
                        
                        # Encode baseboard context into bits 5 and 6
                        servos = [common.encode_servo_id(b_id, s_local) for s_local in s_list]
                        
                        # Save the updated pointer state
                        if level == 'HL': hl_servo_ptr = s_ptr
                        else: ll_servo_ptr = s_ptr
                            
                    # Construct and add finalized record
                    all_accessories.append({
                        'baseboard_id': b_id,
                        'level': 'Low' if level == 'LL' else 'High',
                        'local_id': loc_id,
                        'type': t_name,
                        'global_id': global_id,
                        'rear_switch_id': rear_switch,
                        'front_switch_id': front_switch,
                        'led_ids': leds,
                        'servo_ids': servos
                    })
                    
    return all_accessories

def validate_accessory_info(accessory_info: list) -> tuple:
    """
    Validates physical limits and protocol boundaries across all baseboards.
    Returns: (is_valid: bool, errors: list of str)
    """
    # Track physical resource footprints per baseboard
    switches_per_bb = defaultdict(set)
    leds_per_bb = defaultdict(set)
    servos_per_bb = defaultdict(set)
    acc_types_per_bb = defaultdict(lambda: defaultdict(set))
    all_servo_ids = set()
    
    errors = []

    # --- Profile Hardware Allocation ---
    for acc in accessory_info:
        bb = acc['baseboard_id']
        t_name = acc['type']
        loc_id = acc['local_id']
        
        # Track accessory count per type on this baseboard
        acc_types_per_bb[bb][t_name].add(loc_id)
        
        # Track unique switches wired to this baseboard
        if acc['rear_switch_id'] is not None:
            switches_per_bb[bb].add(acc['rear_switch_id'])
        if acc['front_switch_id'] is not None:
            switches_per_bb[bb].add(acc['front_switch_id'])
            
        # Track unique LEDs wired to this baseboard
        for led in acc['led_ids']:
            leds_per_bb[bb].add(led)
            
        # Track unique Servos assigned to this baseboard and layout wide
        for servo in acc['servo_ids']:
            servos_per_bb[bb].add(servo)
            all_servo_ids.add(servo)

    # --- Run Constraint Rules Evaluation ---
    active_baseboards = set(acc['baseboard_id'] for acc in accessory_info)
    
    for bb in active_baseboards:
        # Check 1: Switches per baseboard (max 24)
        sw_count = len(switches_per_bb[bb])
        if sw_count > 24:
            errors.append(f"Baseboard {bb}: Exceeds switch limit! Found {sw_count} (Max: 24)")
            
        # Check 2: LEDs per baseboard (max 24)
        led_count = len(leds_per_bb[bb])
        if led_count > 24:
            errors.append(f"Baseboard {bb}: Exceeds LED limit! Found {led_count} (Max: 24)")
            
        # Check 3: Servos per baseboard (max 31)
        servo_count = len(servos_per_bb[bb])
        if servo_count > 31:
            errors.append(f"Baseboard {bb}: Exceeds servo limit! Found {servo_count} (Max: 31)")
            
        # Check 4: Quantity of each individual accessory type (max 16)
        for t_name, instances in acc_types_per_bb[bb].items():
            qty = len(instances)
            if qty > 16:
                errors.append(f"Baseboard {bb}: Type '{t_name}' exceeds capacity! Found {qty} (Max: 16)")
                
    # Check 5: Protocol compliance for Waveshare SC09 servo global IDs (1..253)
    for s_id in all_servo_ids:
        if not (1 <= s_id <= 253):
            errors.append(f"Global Layout Error: Servo ID {s_id} is out of protocol range (Valid: 1..253)")

    # Check 6: Max 255 accessories on layout
    if len(accessory_info) > 255:
        errors.append(f"Global Layout Error: More than 255 accessories on layout")

    is_valid = len(errors) == 0
    return is_valid, errors

def save_accessory_info_to_binary(accessory_info: list) -> None:
    """
    Packs layout accessory data into variable-length binary structures
    and writes them to a local binary configuration file.
    """
    count = len(accessory_info)
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_INFO_FILE), "wb") as bin_file:
        count_byte = struct.pack("<B", count)
        bin_file.write(count_byte)
        file_size = len(count_byte)
        for acc in accessory_info:
            # --- Common 3-Byte Header Execution ---
            global_id = acc['global_id']
            rear_switch = acc['rear_switch_id']
            
            # Map None to the 0xFF rogue/sentinel byte indicator
            front_switch = acc['front_switch_id'] if acc['front_switch_id'] is not None else 0xFF
            
            # Pack the 3 header bytes: B = unsigned char (1 byte)
            header_bytes = struct.pack("<BBB", global_id, rear_switch, front_switch)
            bin_file.write(header_bytes)
            file_size += len(header_bytes)
            
            # --- Variable Content Payload Mapping (by Type) ---
            t_name = acc['type']
            leds = acc['led_ids']
            servos = acc['servo_ids']
            
            if t_name == 'Turnouts':
                # Bytes 3 & 4: 2 LEDs | Byte 5: 1 Servo
                payload = struct.pack("<BBB", leds[0], leds[1], servos[0])
                bin_file.write(payload)
                file_size += len(payload)
                
            elif t_name == 'Crossovers':
                # Bytes 3-6: 4 LEDs | Bytes 7 & 8: 2 Servos
                payload = struct.pack("<BBBBBB", leds[0], leds[1], leds[2], leds[3], servos[0], servos[1])
                bin_file.write(payload)
                file_size += len(payload)
                
            elif t_name == 'Uncouplers':
                # Byte 3: 1 LED | Byte 4: 1 Servo
                payload = struct.pack("<BB", leds[0], servos[0])
                bin_file.write(payload)
                file_size += len(payload)
                
            elif t_name == 'Features':
                # No payload data to append
                continue
                
    print(f"💾 Binary accessory data saved in '{common.ACCESSORY_INFO_FILE}' ({count} items, {file_size} bytes)")

def generate_accessory_documentation(accessory_info: list) -> dict:
    """
    Combines accessory configurations into a human-readable columnar dictionary 
    describing all accessories, their physical switches, LEDs, and servos.
    Sorted by Baseboard, Accessory Type (Standard order), and Local Accessory ID.
    """
    # Sort order map to maintain standard layout type hierarchies
    type_sort_order = common.ACCESSORY_TYPE_CODES
    
    # Singular names for the display documentation as requested
    type_display_name = {
        'Features': 'Feature',
        'Turnouts': 'Turnout',
        'Crossovers': 'Crossover',
        'Uncouplers': 'Uncoupler'
    }
    
    # 1. Unpack, format, and organize rows for explicit multi-key sorting
    raw_rows = []
    for acc in accessory_info:
        global_id = f"`{acc['global_id']}`"
        bb = f"`{acc['baseboard_id']}`"
        acc_type = type_display_name[acc['type']]
        acc_id = f"`{acc['local_id']}`"
        rear_sw = f"`{acc['rear_switch_id']}`"
        led_str = "`" + "`, `".join(map(str, acc['led_ids'])) + "`" if acc['led_ids'] else "-"
        servo_str = "`" + "`, `".join(map(str, acc['servo_ids'])) + "`" if acc['servo_ids'] else "-"
        front_sw = f"`{acc['front_switch_id']}`" if acc['front_switch_id'] is not None else "-"
        level = 'Low' if acc['front_switch_id'] else 'High'
        
        raw_rows.append({
            'Global Accessory ID': global_id,
            'Baseboard': bb,
            'Accessory Type': acc_type,
            'Accessory ID': acc_id,
            'Level': level, 
            'Rear Switch': rear_sw,
            'Front Switch': front_sw,
            'LEDs': led_str,
            'Servos': servo_str,
        })
        
    # 2. Sort by global ID, stripped of leading and trailing back ticks
    raw_rows.sort(key=lambda x: (int(x['Global Accessory ID'][1 : -1])))
    
    # 3. Reassemble structured row arrays back into parallel column arrays
    column_data = {
        "Global Accessory ID": [],
        "Baseboard": [],
        "Accessory Type": [],
        "Accessory ID": [],
        "Level": [],
        "Rear Switch": [],
        "Front Switch": [],
        "LEDs": [],
        "Servos": []
    }
    
    for row in raw_rows:
        for key in column_data.keys():
            column_data[key].append(row[key])
            
    return column_data

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

def save_accessory_info_documentation(accessory_info: list) -> None:

    doc_info = generate_accessory_documentation(accessory_info)

    markdown = "# Accessory Details\n\n"
    markdown += "The following table describes all the layout's accessories.\n\n"
    markdown += "* _Global Accessory ID_ identifies the accessory uniquely within the whole layout.\n"
    markdown += "* _Baseboard_ is the number of the baseboard that contains the accessory.\n"
    markdown += "* _Accessory Type_ specifies the type of the accessory.\n"
    markdown += "* _Accessory ID_ is the local identifier of the accessory, unique only within its baseboard and type.\n"
    markdown += "* _Level_ specifies whether the accessory is located on the high or low level of the layout.\n"
    markdown += "* _Rear Switch_ is the ID of the switch that operates the accessory from the rear of the baseboard.\n"
    markdown += "* _Front Switch_ is the ID of the switch that operates the accessory from the front of the baseboard, if any.\n"
    markdown += "* _LEDs_ is a list of LEDs that are controlled by the accessory, if any.\n"
    markdown += "* _Servos_ is a list of Servos that are controlled by the accessory, if any.\n\n"
    markdown += to_markdown_table(doc_info, max_widths=uniform_table_padding(doc_info, 99))
    markdown += "\n\nNote that switch and LED IDs are unique within their host baseboard, but not unique across the layout.\n"

    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_DOCS_FILE), "w", encoding="utf-8") as fd:
        fd.write(markdown)
    print(f"💾 Accessory documentation saved in '{common.ACCESSORY_DOCS_FILE}'")

def generate_led_documentation(accessory_info: list) -> dict:
    """
    Combines LED configurations into a human-readable columnar dictionary.
    """

    # 1. Unpack, format, and organize rows for explicit multi-key sorting
    raw_data = []
    for acc in accessory_info:
        bb = acc['baseboard_id']
        acc_type_code = common.ACCESSORY_TYPE_CODES[acc['type']]
        acc_type = common.ACCESSORY_TYPE_SHORT_NAMES[acc_type_code]
        acc_id = acc['local_id']
        leds = acc['led_ids']

        for led in leds:
            raw_data.append({
                'Baseboard': bb,
                'LED': led,
                'Accessory Type': acc_type,
                'Accessory ID': acc_id
            })
        
        
    # 2. Apply explicit sorting rules: Baseboard first, then LED
    raw_data.sort(key = lambda x: (x['Baseboard'], x['LED']))

    column_data = {'Baseboard': [], 'LED': [], 'Accessory': []}
    for row in raw_data:
        column_data['Baseboard'].append(f"`{row['Baseboard']}`")
        column_data['LED'].append(f"`{row['LED']}`")
        column_data['Accessory'].append(f"`{row['Accessory Type']}:{row['Accessory ID']}`")

    return column_data

def save_led_info_documentation(accessory_info: list) -> None:
    table_cols = generate_led_documentation(accessory_info)
    markdown = "# LED Information\n\n"
    markdown += "The following table provides information about the layouts LEDs.\n\n"
    markdown += "* _Baseboard_ specifies the baseboard containing the LED.\n"
    markdown += "* _LED_ ID of the LED.\n"
    markdown += "* _Accessory_ code describing the accessory that controls the LED.\n\n"
    markdown += to_markdown_table(table_cols, max_widths=uniform_table_padding(table_cols, 99))
    markdown += "\n\n"
    markdown += "LED IDs are unique within the baseboard to which they belong, but are not unique within the layout."
    with open(os.path.join(common.ROOT_DIR, common.LED_DOCS_FILE), "w", encoding="utf-8") as fd:
        fd.write(markdown)
    print(f"💾 LED documentation saved in '{common.LED_DOCS_FILE}'")

def create_switch_mode_dict(accessory_info: list) -> dict:
    """
    Creates a dict[str, list] of all layout switches with default mode strings.
    Rear switches default to '1111' (always on).
    Front switches default to '1010' (modes 0 and 2 only) or '-' if missing.
    """
    column_data = {
        "Baseboard": [],
        "Accessory Type": [],
        "Accessory ID": [],
        "Level": [],
        "Rear Switch ID": [],
        "Rear Switch Modes": [],
        "Front Switch ID": [],
        "Front Switch Modes": []
    }
    
    for acc in accessory_info:
        column_data["Baseboard"].append(acc['baseboard_id'])
        column_data["Accessory Type"].append(acc['type'])
        column_data["Accessory ID"].append(acc['local_id'])
        column_data["Rear Switch ID"].append(acc['rear_switch_id'])
        column_data["Rear Switch Modes"].append("1111")
        
        if acc['front_switch_id'] is not None:
            column_data["Front Switch ID"].append(acc['front_switch_id'])
            column_data["Front Switch Modes"].append("1010")
            column_data["Level"].append("Low")
        else:
            column_data["Front Switch ID"].append("-")
            column_data["Front Switch Modes"].append("-")
            column_data["Level"].append("High")
            
    return column_data

def save_switch_config_template_file(accessory_info: list) -> None:

    table_cols = create_switch_mode_dict(accessory_info)
    save_markdown_table(table_cols, common.SWITCH_CONFIG_TPLT_FILE)
    save_dir_name, save_file_name = os.path.split(common.SWITCH_CONFIG_INPUT_FILE)
    print(f"💾 Draft switch configuration template saved in '{common.SWITCH_CONFIG_TPLT_FILE}'")
    print(f"   TODO:")
    print(f"      ✅ Open '{common.SWITCH_CONFIG_TPLT_FILE}' in a text editor")
    print(f"      ✅ Edit switch availability for each operating mode")
    print(f"      ✅ Save the edited file as '{save_file_name}' in the '{save_dir_name}' directory")

def create_servo_calibration_dict(accessory_info: list) -> dict:
    """
    Creates a dict[str, list] of all servos with type-specific position defaults
    and a startup default state string ('0000') supporting 4 distinct layout modes.
    Sorted by 'Servos' ID, then by 'Accessory ID'.
    """

    defaults = {
        common.ACCESSORY_TYPE_TURNOUT: {'On': 900, 'Off': 400},
        common.ACCESSORY_TYPE_CROSSOVER: {'On': 900, 'Off': 400},
        common.ACCESSORY_TYPE_UNCOUPLER: {'On': 1200, 'Off': 100}
    }
    
    raw_rows = []
    for acc in accessory_info:

        acc_type = common.ACCESSORY_TYPE_CODES[acc['type']]

        if acc_type == common.ACCESSORY_TYPE_FEATURE or not acc.get('servo_ids'):
            continue

        for s_id in acc['servo_ids']:
            raw_rows.append({
                'Servos': s_id,
                'Off Position': defaults[acc_type]['Off'],
                'On Position': defaults[acc_type]['On'],
                'Baseboard': acc['baseboard_id'],
                'Level': acc['level'],
                'Accessory Type': common.ACCESSORY_TYPE_NAMES[acc_type],
                'Accessory ID': acc['local_id']
            })
            
    raw_rows.sort(key=lambda x: (x['Servos'], x['Accessory ID']))
    
    column_data = {
        "Servos": [], 
        "Off Position": [], 
        "On Position": [],
        "Baseboard": [], 
        "Level": [], 
        "Accessory Type": [], 
        "Accessory ID": []
    }
    
    for row in raw_rows:
        for key in column_data.keys():
            column_data[key].append(row[key])
            
    return column_data

def save_servo_config_template_file(accessory_info: list) -> None:

    table_cols = create_servo_calibration_dict(accessory_info)
    save_markdown_table(table_cols, common.SERVO_CONFIG_TPLT_FILE)
    save_dir_name, save_file_name = os.path.split(common.SERVO_CONFIG_INPUT_FILE)
    print(f"💾 Draft servo configuration table saved in '{common.SERVO_CONFIG_TPLT_FILE}'")
    print(f"   TODO:")
    print(f"      ✅ Open '{common.SERVO_CONFIG_TPLT_FILE}' in a text editor")
    print(f"      ✅ Edit servo calibration information")
    print(f"      ✅ Save the edited file as '{save_file_name}' in the '{save_dir_name}' directory")

def create_accessory_mode_dict(accessory_info: list) -> dict:
    """
    Creates a dict[str, list] of all layout accessories with default startup
    state strings. All accessories default to `0000`
    """

    column_data = {
        "Baseboard": [],
        "Level": [],
        "Accessory Type": [],
        "Accessory ID": [],
        "Startup Modes": [],
    }

    for acc in accessory_info:
        bb = acc['baseboard_id']
        level = acc['level']
        acc_type_code = common.ACCESSORY_TYPE_CODES[acc['type']]
        acc_type_name = common.ACCESSORY_TYPE_NAMES[acc_type_code]
        acc_id = acc['local_id']

        column_data['Baseboard'].append(bb)
        column_data['Level'].append(level)
        column_data['Accessory Type'].append(acc_type_name)
        column_data['Accessory ID'].append(acc_id)
        column_data['Startup Modes'].append("0000")

    return column_data

def save_accessory_config_template_file(accessory_info: list) -> None:
    table_cols = create_accessory_mode_dict(accessory_info)
    save_markdown_table(table_cols, common.ACCESSORY_CONFIG_TPLT_FILE)
    save_dir_name, save_file_name = os.path.split(common.ACCESSORY_CONFIG_INPUT_FILE)
    print(f"💾 Draft accessory configuration table saved in '{common.ACCESSORY_CONFIG_TPLT_FILE}'")
    print(f"   TODO:")
    print(f"      ✅ Open '{common.ACCESSORY_CONFIG_TPLT_FILE}' in a text editor")
    print(f"      ✅ Edit accessory startup state for each operating mode")
    print(f"      ✅ Save the edited file as '{save_file_name}' in the '{save_dir_name}' directory")
    pass

# ------------------------------------------------------------------------------


if __name__ == "__main__":

    # Ensure output directories exist
    os.makedirs(os.path.join(common.ROOT_DIR, common.DOCS_DIR), exist_ok=True)
    os.makedirs(os.path.join(common.ROOT_DIR, common.BIN_DIR), exist_ok=True)
    os.makedirs(os.path.join(common.ROOT_DIR, common.TEMPLATES_DIR), exist_ok=True)

    # Read and process layout definition information

    # -- read Markdown file content
    with open(os.path.join(common.ROOT_DIR, common.ACCESSORY_DEFINITION_FILE), "r", encoding="utf-8") as fd:
        layout_definition_markdown = fd.read()
    
    # -- parse Markdown table
    layout_definition_data = parse_markdown_table(layout_definition_markdown)

    # -- generate accessory information   
    accessory_info = generate_accessory_info(layout_definition_data)

    # Validate accessory info

    is_valid, validation_errors = validate_accessory_info(accessory_info)

    if is_valid:
        print("✔️ Validation Passed: The layout design respects all electrical and hardware limits")
    else:
        print("❌ Validation Failed: Fix the following configuration issues:")
        for err in validation_errors:
            print(f"  - {err}")
        sys.exit(1)

    # Write accessory data

    # -- write binary
    save_accessory_info_to_binary(accessory_info)
    
    # -- write accessory documentation as Markdown table
    save_accessory_info_documentation(accessory_info)

    # -- write LED documentation as Markdown table
    save_led_info_documentation(accessory_info)

    # Write configuration template files

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
