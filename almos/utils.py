######################################################.
#         This file stores generic functions         #
######################################################.

import os
import sys
import ast
import getopt
from pathlib import Path
import time
from argument_parser import set_options, var_dict

robert_version = "1.2.2" 
aqme_version = "1.7.1"
almos_version = "0.1.0"
time_run = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
almos_ref = f"ALMOS v {almos_version}, Miguel Martínez Fernández, Susana P. García Abellán, Juan V. Alegre Requena. ALMOS: Active Learning Molecular Selection for Researchers and Educators."

def command_line_args():
    """
    Load default and user-defined arguments specified through command lines. Arrguments are loaded as a dictionary

    """

    # First, create dictionary with user-defined arguments
    kwargs = {}
    available_args = ["help"]
    bool_args = [
        "cluster",
        "al",
        "aqme_workflow",
        "auto_fill",
        "pca3d"
    ]
    int_args = [
        "n_points",
        "n_clusters",
        "seed_clustered"
    ]
    list_args = [
        "ignore"    
    ]
    float_args = [
        "factor_exp",
    ]

    for arg in var_dict:
        if arg in bool_args:
            available_args.append(f"{arg}")
        else:
            available_args.append(f"{arg} =")

    try:
        opts, _ = getopt.getopt(sys.argv[1:], "h", available_args)
    except getopt.GetoptError as err:
        print(err)
        sys.exit()

    for arg, value in opts:
        if arg.find("--") > -1:
            arg_name = arg.split("--")[1].strip()
        elif arg.find("-") > -1:
            arg_name = arg.split("-")[1].strip()

        if arg_name in ("h", "help"):
            print(f"o  ALMOS v {almos_version} is installed correctly! For more information, see the documentation in https://github.com/MiguelMartzFdez/almos")
            sys.exit()
        else:
                # this converts the string parameters to lists
                if arg_name in bool_args:
                    value = True                    
                elif arg_name.lower() in list_args:
                    value = format_lists(value)
                elif arg_name.lower() in int_args:
                    if value is not None:
                        value = int(value)
                elif arg_name.lower() in float_args:
                    value = float(value)
                elif value == "None":
                    value = None
                elif value == "False":
                    value = False
                elif value == "True":
                    value = True

                kwargs[arg_name] = value

    # Second, combine all the default variables with the user-defined ones saved in "kwargs".
    # This is done as an "add_option" object using the "set_options" function
    args = load_variables(kwargs, "command")
    
    return args


def load_variables(kwargs, almos_module, create_dat=True):
    """
    Load default and user-defined variables
    
    """

    # first, load default values and options manually added to the function
    self = set_options(kwargs)

    if almos_module != "command":

        # Define path and other variables
        self.initial_dir = Path(os.getcwd())
        error_setup = False
            
        # start a log file to track the ALMOS modules
        if create_dat:
            logger_1, logger_2 = "ALMOS", "data"

            if almos_module == "al":
                logger_1 = "AL"

            elif almos_module == "cluster":
                logger_1 = "CLUSTER"

            if not error_setup:
                if not self.command_line:
                    self.log = Logger(self.initial_dir / logger_1, logger_2, verbose=self.verbose)
                else:
                    # prevents errors when using command lines and running to remote directories
                    path_command = Path(f"{os.getcwd()}")
                    self.log = Logger(path_command / logger_1, logger_2, verbose=self.verbose)

                self.log.write(f"\nALMOS v {almos_version} {time_run} \nCitation: {almos_ref}\n")

                if self.command_line:
                    cmd_print = ''
                    cmd_args = sys.argv[1:]
                    for i,elem in enumerate(cmd_args):
                        if elem[0] in ['"',"'"]:
                            elem = elem[1:]
                        if elem[-1] in ['"',"'"]:
                            elem = elem[:-1]
                        if elem != '-h' and elem.split('--')[-1] not in var_dict:
                            if cmd_args[i-1].split('--')[-1] in var_dict: # check if the previous word is an arg
                                cmd_print += f'"{elem}'
                            if i == len(cmd_args)-1 or cmd_args[i+1].split('--')[-1] in var_dict: # check if the next word is an arg, or last word in command
                                cmd_print += f'"'
                        else:
                            cmd_print += f'{elem}'
                        if i != len(cmd_args)-1:
                            cmd_print += ' '

                    self.log.write(f"Command line used in ALMOS: python -m almos {cmd_print}\n")

            if error_setup:
                # this is added to avoid path problems in jupyter notebooks
                self.log.finalize()
                os.chdir(self.initial_dir)
                sys.exit()

    return self

def format_lists(value):
    '''
    Transforms strings into a list
    '''

    if not isinstance(value, list):
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            # this line fixes issues when using "[X]" or ["X"] instead of "['X']" when using lists
            value = value.replace('[',']').replace(',',']').replace("'",']').split(']')
            while('' in value):
                value.remove('')
    return value


class Logger:
    """
    Class that wraps a file object to abstract the logging.
    """

    # Class Logger to write output to a file
    def __init__(self, filein, append, suffix="dat", verbose=True):
        if verbose:
            self.log = open(f"{filein}_{append}.{suffix}", "w")
        else:
            self.log = ''

    def write(self, message):
        """
        Appends a newline character to the message and writes it into the file.

        Parameters
        ----------
        message : str
           Text to be written in the log file.
        """
        try:
            self.log.write(f"{message}\n")
        except AttributeError:
            pass
        print(f"{message}\n")

    def finalize(self):
        """
        Closes the file
        """
        try:
            self.log.close()
        except AttributeError:
            pass

# def check_dependencies(self):
#     # this is a dummy command just to warn the user if OpenBabel is not installed
#     try:
#         command_run_1 = ["obabel", "-H"]
#         subprocess.run(command_run_1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
#     except FileNotFoundError:
#         self.args.log.write(f"x  Open Babel is not installed! You can install the program with 'conda install -y -c conda-forge openbabel={obabel_version}'")
#         self.args.log.finalize()
#         sys.exit()

#     # this is a dummy import just to warn the user if RDKit is not installed
#     try: 
#         from rdkit.Chem import AllChem as Chem
#     except ModuleNotFoundError:
#         self.args.log.write("x  RDKit is not installed! You can install the program with 'pip install rdkit' or 'conda install -y -c conda-forge rdkit'")
#         self.args.log.finalize()
#         sys.exit()