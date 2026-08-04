import csv
import io
from enum import Enum, auto

def _coerce_type(val: str, expected_type: type | None) -> any:
    """Helper to convert string value into a specified Python primitive type."""
    val = val.strip()
    if not expected_type:
        return val
    if expected_type in (int, float):
        # Strip surrounding quotes if someone quoted a number
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1].strip()
        return expected_type(val)
    if expected_type == str:
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        return val
    return expected_type(val)

def _process_cell(val: str, col_name: str, types: dict[str, type], defaults: dict[str, any]) -> any:
    """Cleans a cell value, inferring/coercing types and applying column-specific defaults."""
    val = val.strip()
    expected_type = types.get(col_name)
    
    # Check if cell is blank
    if val == "":
        return defaults.get(col_name, None)
        
    # Coerce to enforced type if defined
    if expected_type:
        try:
            return _coerce_type(val, expected_type)
        except (ValueError, TypeError):
            # Fallback to default value if data type coercion fails
            return defaults.get(col_name, None)
            
    # Dynamic type discovery if no strict column type is specified
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val

class InvalidRowStrategy(Enum):
    """
    Specifies how invalid table row lengths are to be handled
    
    * `RAISE` - raise an exception
    * `SKIP` - skip ignore the error and continue
    * `PAD` - pad the row out with empty values
    * `TRUNCATE` - truncate excess cells
    """
    RAISE = auto()
    SKIP = auto()
    PAD = auto()
    TRUNCATE = auto()

def parse_markdown_table(
    md_text: str, 
    invalid_row_strategy: InvalidRowStrategy = InvalidRowStrategy.RAISE, 
    column_types: dict[str, type] | None = None,
    column_defaults: dict[str, any] | None = None
) -> dict[str, list[any]]:
    """
    Parses a Markdown table string into a dictionary of typed columns with default fallbacks.

    * `text`: text containing Markdown table.
    * `invalid_row_strategy`: how to process invalid rows within table.
    * `column_types`: specifies the data type of each column, where the column title is the dictionary key.
    * `column_defaults`: default values used for empty cells in a column, where column title is the dictionary key.
    """
    types = column_types or {}
    defaults = column_defaults or {}
    
    lines = [line.strip() for line in md_text.strip().split('\n') if line.strip()]
    if not lines:
        return {}
    
    raw_rows = [[cell.strip() for cell in line.split('|')[1:-1]] for line in lines]
    if not raw_rows:
        return {}
        
    # Headers are kept as raw strings to map back to configurations safely
    headers = [cell.strip().strip('"').strip("'") for cell in raw_rows[0]]
    result = {h: [] for h in headers}
    
    start_idx = 1
    if len(raw_rows) > 1 and all(set(cell).issubset({'-', ':', ' '}) for cell in raw_rows[1] if cell):
        start_idx = 2
        
    for row_num, row in enumerate(raw_rows[start_idx:], start=start_idx + 1):
        if len(row) != len(headers):
            if invalid_row_strategy == InvalidRowStrategy.RAISE:
                raise ValueError(f"Row {row_num} length mismatch: got {len(row)}, expected {len(headers)}.")
            elif invalid_row_strategy == InvalidRowStrategy.SKIP:
                continue
            elif invalid_row_strategy == InvalidRowStrategy.PAD:
                row = row + [""] * (len(headers) - len(row))
            elif invalid_row_strategy == InvalidRowStrategy.TRUNCATE:
                row = row[:len(headers)]
                
        for i, cell in enumerate(row):
            col_name = headers[i]
            processed_val = _process_cell(cell, col_name, types, defaults)
            result[col_name].append(processed_val)
            
    return result

def parse_delimited_table(
    text: str, 
    invalid_row_strategy: InvalidRowStrategy = InvalidRowStrategy.RAISE, 
    column_types: dict[str, type] | None = None,
    column_defaults: dict[str, any] | None = None
) -> dict[str, list[any]]:
    """
    Parses a CSV/TSV string using auto-detection, type enforcement, and column defaults.

    * `text`: text containing delimited table.
    * `invalid_row_strategy`: how to process invalid rows within table.
    * `column_types`: specifies the data type of each column, where the column title is the dictionary key.
    * `column_defaults`: default values used for empty cells in a column, where column title is the dictionary key.
    """
    types = column_types or {}
    defaults = column_defaults or {}
    
    cleaned_text = text.strip()
    if not cleaned_text:
        return {}
        
    f = io.StringIO(cleaned_text)
    try:
        dialect = csv.Sniffer().sniff(cleaned_text[:1024], delimiters=[',', '\t', ';'])
    except csv.Error:
        dialect = 'excel'
        
    reader = csv.reader(f, dialect)
    try:
        headers = [h.strip().strip('"').strip("'") for h in next(reader)]
    except StopIteration:
        return {}
        
    result = {h: [] for h in headers}
    
    for row_num, row in enumerate(reader, start=2):
        if not row or (len(row) == 1 and row[0].strip() == ""):
            continue
            
        if len(row) != len(headers):
            if invalid_row_strategy == InvalidRowStrategy.RAISE:
                raise ValueError(f"Row {row_num} length mismatch: got {len(row)}, expected {len(headers)}.")
            elif invalid_row_strategy == InvalidRowStrategy.SKIP:
                continue
            elif invalid_row_strategy == InvalidRowStrategy.PAD:
                row = row + [""] * (len(headers) - len(row))
            elif invalid_row_strategy == InvalidRowStrategy.TRUNCATE:
                row = row[:len(headers)]
                
        for i, cell in enumerate(row):
            col_name = headers[i]
            processed_val = _process_cell(cell, col_name, types, defaults)
            result[col_name].append(processed_val)
            
    return result

# --- Exporter Functions ---

class TextAlignment(Enum):
    """
    Types of text alignment

    * `LEFT` - left aligned text
    * `CENTRE` - centred text
    * `RIGHT` - right aligned text
    """
    LEFT = auto()
    RIGHT = auto()
    CENTRE = auto()

def to_markdown_table(
    data: dict[str, list[any]], 
    max_widths: dict[str, int | None] | None = None,
    alignment: dict[str, TextAlignment | None] | None = None
) -> str:
    """
    Converts the internal dictionary format back into a cleanly aligned Markdown table string.
    
    * `data`:         The dictionary whose data is to formatted as a Markdown table.
    * `max_widths`:   A dictionary mapping column names to an integer threshold (or None).
                      Values longer than this threshold are ignored *only* when calculating table widths.
                      - If max_widths is None, padding is completely disabled for all columns.
                      - If a specific column key maps to None, padding is disabled for that column.
    * `alignment`:    Specifies how text is to be aligned within a table. If alignment is None then
                      the default text alignment is used.

    """
    if not data:
        return ""
        
    headers = list(data.keys())
    num_rows = len(data[headers[0]])
    
    # Pre-render all cell values into their string representations
    rendered_rows = []
    for r in range(num_rows):
        row_cells = {}
        for h in headers:
            val = data[h][r]
            row_cells[h] = "" if val is None else str(val)
        rendered_rows.append(row_cells)
        
    # Calculate column widths based on your configuration parameters
    col_widths = {}
    for h in headers:
        # Configuration case 1: Entire parameter is None -> Disable padding
        if max_widths is None:
            col_widths[h] = None
            continue
            
        # Configuration case 2: Specific column is None -> Disable padding
        limit = max_widths.get(h, None)
        if h in max_widths and limit is None:
            col_widths[h] = None
            continue
            
        # Collect candidate lengths (always include header length as a baseline)
        lengths = [len(h)]
        for row in rendered_rows:
            cell_str = row[h]
            # Filter out entries longer than the specified threshold if a limit exists
            if limit is not None and len(cell_str) > limit:
                continue
            lengths.append(len(cell_str))
            
        # Column width is maximum of qualifying row lengths
        col_widths[h] = max(lengths)

    def format_cell(text: str, col_name: str) -> str:
        """Helper to left-align string values inside computed column spans."""
        width = col_widths[col_name]
        if width is None:
            return text
        # Pads text with spaces to match the target column width
        return text.ljust(width)

    output = []
    
    # 1. Header row
    header_line = "| " + " | ".join(format_cell(h, h) for h in headers) + " |"
    output.append(header_line)

    # 2. Separator row
    parts = []
    for h in headers:
        # Safely extract the enum member
        align = alignment.get(h) if alignment else None
        
        # Identity comparison using 'is' or 'in' with enum members
        left_char = ':' if align in (TextAlignment.LEFT, TextAlignment.CENTRE) else '-'
        right_char = ':' if align in (TextAlignment.RIGHT, TextAlignment.CENTRE) else '-'
        
        width = col_widths[h] if col_widths[h] is not None else 3
        parts.append(f"{left_char}{'-' * width}{right_char}")

    separator_line = f"|{'|'.join(parts)}|"
    
    output.append(separator_line)
    
    # 3. Data rows
    for row in rendered_rows:
        row_line = "| " + " | ".join(format_cell(row[h], h) for h in headers) + " |"
        output.append(row_line)
        
    return "\n".join(output)

class TextTableType(Enum):
    """
    Enumeration of supported delimited table types

    * `CSV` - Comma separated values
    * `TSV` - Tab separated values
    """
    CSV = auto()
    TSV = auto()

def to_delimited_table(data: dict[str, list[any]], table_type: TextTableType = TextTableType.CSV) -> str:
    """
    Converts the internal dictionary format into a CSV or TSV string

    * `data`:         The dictionary whose data is to formatted as a Markdown table.
    * `delim_type`:   Speficies the type of delimiter used to separate fields.
    """
    if not data:
        return ""
    
    delimiter = ',' if table_type == TextTableType.CSV else "\t"
    headers = list(data.keys())
    num_rows = len(data[headers[0]])
    
    f = io.StringIO()
    writer = csv.writer(f, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
    
    writer.writerow(headers)
    for r in range(num_rows):
        row_cells = []
        for h in headers:
            val = data[h][r]
            row_cells.append("" if val is None else val)
        writer.writerow(row_cells)
        
    return f.getvalue().strip()
