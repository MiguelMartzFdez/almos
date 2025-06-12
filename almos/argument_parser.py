#######################################################
#        This file contains the argument parser       #
#######################################################


var_dict = {
    "varfile": None,
    "extra_cmd": '',
    "verbose": True,
    "command_line": False,
    "csv_name": None,
    "input": None,
    "n_clusters": None,
    "n_exps": 1,
    "batch_number": None,
    "seed_clustered": 0,
    "descp_level": "interpret",
    "ignore": [],
    "cluster": False,
    "aqme_keywords": '',
    "aqme": False,
    "name": '',
    "y": '',
    "auto_fill": True,
    "categorical": "onehot",
    "el": False,          
    'explore_rt': 1,
    "el": False,
    "explore_rt": 1,
    "al": False,
    "bo": False,          
    'n_points': None,                  
    'options_file': 'options.csv',
    'batch_column': 'batch',
    'tolerance': 'medium',
    'levels_tolerance': {  
        'tight': 0.01,
        'medium': 0.05,
        'wide': 0.10,
    },
    'nprocs': 8,
    "robert_keywords" : '',
    "reverse" : False,
    "intelex" : False
}

# part for using the options in a script or jupyter notebook
class options_add:
    pass

def set_options(kwargs):
    """
    Combine default settings with user-provided arguments.

    This function merges the defaults from 'var_dict' with the values in 'kwargs'.
    User-provided arguments override defaults, and all options are returned as
    attributes of an object. Unrecognized arguments trigger a warning.

    Parameters:
    -----------
    kwargs : dict
        User-provided arguments to override default settings.
        From 'command_line_args()' function.

    Returns:
    --------
    options : options_add
        Object containing all configuration options as attributes.
    
    """
    # set default options and options provided
    options = options_add()
    
    # dictionary containing default values for options
    for key in var_dict:
        vars(options)[key] = var_dict[key]
    for key in kwargs:
        if key in var_dict:
            vars(options)[key] = kwargs[key]
        elif key.lower() in var_dict:
            vars(options)[key.lower()] = kwargs[key.lower()]
        else:
            print("Warning! Option: [", key,":",kwargs[key],"] provided but no option exists, try the online documentation to see available options for each module.",)

    return options