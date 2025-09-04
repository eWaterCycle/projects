def classify_discharge_status(discharge_values):
    statuses = []
    consecutive_low_days = 0

    for value in discharge_values:
        if value < 500:
            consecutive_low_days += 1
            if 1 <= consecutive_low_days <= 3:
                status = "caution"
            elif 4 <= consecutive_low_days <= 7:
                status = "risk"
            else:
                status = "critical"
        else:
            consecutive_low_days = 0
            status = "normal"
        statuses.append(status)

    return statuses

def get_segments_final_color_safe(x, y, threshold=500):
    segments = []
    colors = []
    low_flow_counter = 0
    tracking_low_flow = False

    for i in range(len(x) - 1):
        xi = [x[i], x[i + 1]]
        yi = [y[i], y[i + 1]]

        if y[i] < threshold:
            if not tracking_low_flow:
                low_flow_counter = 1
                tracking_low_flow = True
            else:
                low_flow_counter += 1
        elif tracking_low_flow and y[i + 1] < threshold:
            low_flow_counter += 1
        else:
            tracking_low_flow = False
            low_flow_counter = 0

        # kleur alléén als beide punten onder threshold zijn
        if y[i] < threshold and y[i + 1] < threshold:
            if 1 <= low_flow_counter <= 3:
                color = 'yellow'
            elif 4 <= low_flow_counter <= 7:
                color = 'orange'
            else:
                color = 'red'
        else:
            color = 'black'

        segments.append((xi, yi))
        colors.append(color)

    return segments, colors

def droughts(df, basin_name, q_crit=500):
    """
    Identify drought events as contiguous runs of days with status != "normal".
    Status on each day is assigned by classify_discharge_status().
    An event's status is the worst status seen during that run.
    """
    # 1) get a pandas Series of statuses
    statuses = classify_discharge_status(df.values)
    
    events = []
    drought_id = 1
    idx = 0
    n = len(df)
    
    # helper to rank statuses
    rank = {"caution": 1, "risk": 2, "critical": 3}
    
    while idx < n:
        if statuses[idx] != "normal":
            start_date = df.index[idx]
            worst = rank[statuses[idx]]
            duration = 0
            
            
            while idx < n and statuses[idx] != "normal":
                worst = max(worst, rank[statuses[idx]])
                duration += 1
                idx += 1
            
            # map back from rank to status string
            for s, r in rank.items():
                if r == worst:
                    event_status = s
                    break
            
            events.append({
                "Drought Number": drought_id,
                "Start Date": start_date,
                "Duration (days)": duration,
                "Status": event_status,
                "Basin": basin_name
            })
            drought_id += 1
        else:
            idx += 1
    
    # if none found, return a neutral row
    if not events:
        events.append({
            "Drought Number": 0,
            "Start Date": None,
            "Duration (days)": 0,
            "Status": None,
            "Basin": basin_name
        })
    
    return pd.DataFrame(events)

def export_functions_from_notebook(ipynb_path, py_path):
    # Load the notebook
    with open(ipynb_path, 'r', encoding='utf-8') as f:
        nb = nbformat.read(f, as_version=4)

    function_lines = []
    recording = False

    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        lines = cell.source.split('\n')
        for line in lines:
            if line.strip().startswith("def "):
                recording = True
            if recording:
                function_lines.append(line)
        # Add blank lines between functions
        if recording:
            function_lines.append("")  # one empty line
            recording = False

    # Write to .py file
    with open(py_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(function_lines))

    print(f"Exported functions to: {py_path}")

# Example usage
export_functions_from_notebook("CriticalDaysLowFlow.ipynb", "critical_days_module.py")
