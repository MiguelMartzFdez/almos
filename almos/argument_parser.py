#######################################################
#        This file contains the argument parser       #
#######################################################


var_dict = {
    'csv_name': None,                
    'name_column': None,            
    'target_column': None,           
    'n_points': None,    
    'ignore_list': [],               
    'factor_explore': 2/3,           
    'options_file': 'options.csv',
    'batch_column': 'batch',
    'tolerance_level': 'medium',
    'tolerance_levels': {  
        'tight': 0.01,
        'medium': 0.05,
        'wide': 0.10,
    }, 
}

# part for using the options in a script or jupyter notebook
class options_add:
    pass

def set_options(kwargs):
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