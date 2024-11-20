#######################################################
#        This file contains the argument parser       #
#######################################################


var_dict = {
    "varfile": None,
    "verbose": True,
    "command_line": False,
    "csv_name": None,
    "n_clusters": None,
    "seed_clustered": 0,
    "descp_level": "interpret",
    "ignore": [],
    "cluster": False,
    "qdescp_atoms": None,
    "qdescp_solvent": None,
    "aqme_workflow": True,
    "name": '',
    "y": '',
    "auto_fill": True,
    "categorical": "onehot",
    "pca3d": False,
    "pca3d_csv": "batch_0/pca_b0.csv",
    "al": False,          
    'n_points': None,                  
    'factor_exp': 2/3,           
    'options_file': 'options.csv',
    'batch_column': 'batch',
    'tolerance': 'medium',
    'levels_tolerance': {  
        'tight': 0.01,
        'medium': 0.05,
        'wide': 0.10,
    }, 
}

# part for using the options in a script or jupyter notebook
class options_add:
    pass

def set_options(kwargs):
    """
    Combine default settings with user-provided arguments.

    This function merges the defaults from `var_dict` with the values in `kwargs`.
    User-provided arguments override defaults, and all options are returned as
    attributes of an object. Unrecognized arguments trigger a warning.

    Parameters:
    -----------
    kwargs : dict
        User-provided arguments to override default settings.

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