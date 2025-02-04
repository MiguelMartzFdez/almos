######################################################.
#         This file stores generic functions         #
######################################################.

import os
import sys
import ast
import getopt
from pathlib import Path
import time
import subprocess
from almos.argument_parser import set_options, var_dict
from almos.al_utils import check_missing_outputs

almos_version = "0.0.0"
time_run = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
almos_ref = f"ALMOS v {almos_version}, Miguel Martínez Fernández, Susana García Abellán, Juan V. Alegre Requena. ALMOS: Active Learning Molecular Selection for Researchers and Educators."

def command_line_args():
    """     
    Parse and process command-line arguments.

    This function reads and processes arguments provided via the command line. 
    It validates the arguments against a predefined set of valid options, converts 
    them to their expected data types, and combines them with default values. 
    The final configuration is returned as an object in args using the set_options function.

    Returns:
    --------
    args : object
        An object containing all configuration options, including default values 
        and user-provided overrides.

    """
    # First, create dictionary with user-defined arguments
    kwargs = {}
    available_args = ["help"]
    bool_args = [
        "cluster",
        "al",
        "aqme_workflow",
        "reverse",
        "intelex",
    ]
    int_args = [
        "n_clusters",
        "seed_clustered"
    ]
    int_double_args = [
        "n_points",
    ]
    list_args = [
        "ignore",
        "qdescp_atoms",   
    ]
    float_args = [
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
                elif arg_name.lower() in int_double_args:
                     if ":" in value and len(value.split(":")) == 2: 
                        value = tuple(map(int, value.split(":")))
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
    args = load_variables(kwargs, "command")
    
    return args


def load_variables(kwargs, almos_module, create_dat=True):
    """    
    Combine user-defined arguments with default variables and set up the environment.

    This function merges default values from 'var_dict' with user-provided arguments 
    using 'set_options'. It also initializes additional variables, such as the 
    working directory, sets up the logger and print command line used for depending on the module.

    Parameters:
    -----------
    kwargs : dict
        Dictionary of user-provided arguments to override default values.

    Returns:
    --------
    self : object
        An object containing all configuration options and additional setup attributes.
    
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

                # check if outputs are missing and load, needed here for update "command line" with inputs.
                if almos_module == "al":
                    self = check_missing_outputs(self)

                self.log.write(f"\nALMOS v {almos_version} {time_run} \nCitation: {almos_ref}\n")

                if self.command_line:
                    cmd_print = ''
                    cmd_args = sys.argv[1:]
                    if self.extra_cmd != '':
                        for arg in self.extra_cmd.split():
                            cmd_args.append(arg)
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

def check_dependencies(self, module):
    """
    Checks if the required Python packages are installed for the specified module.

    For module "al":
    - Requires 'robert' on all platforms.
    - Requires 'scikit-learn-intelex' on Windows and Linux; optional on macOS (with a warning message).

    Parameters:
    -----------
    module : str
        The name of the module for which dependencies are being checked.
    """
    if module == "al":

        # Check for glib, gtk3, pango, and mscorefonts
        required_packages = ["glib", "gtk3", "pango", "mscorefonts"]
        missing_packages = []

        # Use conda list to verify package installation
        result = subprocess.run(
            ["conda", "list"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True
        )
        installed_packages = result.stdout

        # Check for each required package
        for package in required_packages:
            if package not in installed_packages:
                missing_packages.append(package)

        # Log missing packages and exit if necessary
        if missing_packages:
            self.args.log.write(
                f"\nx WARNING! The following required packages are missing: {', '.join(missing_packages)}"
                "\nYou can install them with the command: 'conda install -y -c conda-forge glib gtk3 pango mscorefonts'."
            )
            self.args.log.finalize()
            sys.exit()

        # Check for 'scikit-learn-intelex'
        if not self.args.intelex:
            try:
                import sklearnex  
            except ImportError:
                self.args.log.write(
                    "\nx WARNING! The required package 'scikit-learn-intelex' is not installed! Install it with 'pip install scikit-learn-intelex'."
                    "\nNote that 'scikit-learn-intelex' is required unless '--intelex' is set in the command line. Exiting.")
                self.args.log.finalize()
                sys.exit()
        else:
            self.args.log.write(
                "\no Running without 'scikit-learn-intelex' as requested.\n"
            )