"""
PCRGlobWB Calibration using CMA-ES
"""

import configparser
CALIBRATION_PARAMS = {
    'manningsN': {
        'ini_section': 'routingOptions',
        'ini_key': 'manningsN',
        'bounds': (0.01, 0.15),
        'initial': 0.04
    },
    'recessionCoeff': {
        'ini_section': 'groundwaterOptions',
        'ini_key': 'recessionCoeff',
        'bounds': (0.01, 0.5),
        'initial': 0.1
    },
    # Add more parameters here
}



def modify_ini_file(template_ini_path, output_ini_path, param_dict):
    """
    Modify INI file with new parameter values
    
    Args:
        template_ini_path: Path to template .ini file
        output_ini_path: Path to save modified .ini file
        param_dict: Dict of {param_name: value} to update
    """
    config = configparser.ConfigParser()
    config.optionxform = str  # Preserve case of keys
    config.read(template_ini_path)
    
    for param_name, value in param_dict.items():
        if param_name in CALIBRATION_PARAMS:
            section = CALIBRATION_PARAMS[param_name]['ini_section']
            key = CALIBRATION_PARAMS[param_name]['ini_key']
            
            # Ensure section exists
            if not config.has_section(section):
                config.add_section(section)
            
            config.set(section, key, str(value))
    
    with open(output_ini_path, 'w') as f:
        config.write(f)
    
    return output_ini_path








