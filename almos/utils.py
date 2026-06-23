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
import shutil
from almos.package_versions import ALMOS_VERSION, AQME_VERSION, OBABEL_VERSION
from almos.argument_parser import (
    AL_OPTION_ALIASES,
    BOOL_ARGS,
    FLOAT_ARGS,
    INT_ARGS,
    LIST_ARGS,
    NEGATED_BOOL_ALIASES,
    set_options,
    var_dict,
)
from almos.al_utils import check_missing_outputs

obabel_version = OBABEL_VERSION
aqme_version = AQME_VERSION
almos_version = ALMOS_VERSION
time_run = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
almos_ref = f"ALMOS v {almos_version}, Miguel Martínez Fernández, Susana García Abellán, Juan V. Alegre Requena. ALMOS: Active Learning Molecular Selection for Researchers and Educators."


def format_cli_help():
    """
    Return a compact, user-facing help message for the main ALMOS entrypoint.
    """

    return f"""ALMOS v{almos_version}
Active Learning Molecular Selection

Usage
  almos help
  cluster --input EXAMPLE.csv --name Name
  al --csv_name A_b0.csv --name Name --y target --n_exps 10
  easyalmos

Main commands
  cluster      Build or evaluate a representative batch_0 selection
  al           Run an active learning cycle
  easyalmos    Launch the graphical interface

Common examples
  cluster --input EXAMPLE.csv --name Name --n_points 40
  cluster --input EXAMPLE.csv --name Name --evaluate
  al --csv_name A_b0.csv --name Name --y target --n_exps 10
  al --csv_name A_b0.csv --name Name --y target --n_exps 10 --mode model
  al --csv_name A_b0.csv --name Name --y target --n_exps 10 --mode hit --objective max --alpha 0.5

Documentation
  ReadTheDocs: https://almos.readthedocs.io/en/latest/
  GitHub:      https://github.com/MiguelMartzFdez/almos
"""

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
    raw_args = sys.argv[1:]
    module_aliases = {
        "cluster": "--cluster",
        "clustering": "--cluster",
        "al": "--al",
        "active-learning": "--al",
        "active_learning": "--al",
    }
    executable_aliases = {
        "cluster": "--cluster",
        "almos-cluster": "--cluster",
        "al": "--al",
        "almos-al": "--al",
    }
    if raw_args and raw_args[0].lower() in module_aliases:
        raw_args = [module_aliases[raw_args[0].lower()]] + raw_args[1:]
    elif raw_args and raw_args[0].lower() == "help":
        if len(raw_args) > 1 and raw_args[1].lower() in module_aliases:
            raw_args = [module_aliases[raw_args[1].lower()], "--help"] + raw_args[2:]
        else:
            raw_args = ["--help"] + raw_args[1:]
    elif os.path.basename(sys.argv[0]).lower() in executable_aliases:
        raw_args = [executable_aliases[os.path.basename(sys.argv[0]).lower()]] + raw_args
    normalized_command_line_args = list(raw_args)
    is_al_command = any(arg == "--al" for arg in raw_args)
    normalized_raw_args = []
    for arg in raw_args:
        if arg == "--mode" and is_al_command:
            normalized_raw_args.append("--al_mode")
            continue
        if arg.startswith("--"):
            normalized_raw_args.append(f"--{AL_OPTION_ALIASES.get(arg[2:], arg[2:])}")
            continue
        normalized_raw_args.append(arg)
    raw_args = normalized_raw_args

    available_args = ["help"]
    bool_args = BOOL_ARGS
    int_args = INT_ARGS
    int_double_args = [

    ]
    list_args = LIST_ARGS
    float_args = FLOAT_ARGS

    for arg in var_dict:
        if arg in bool_args:
            available_args.append(f"{arg}")
        else:
            available_args.append(f"{arg} =")
    for alias in NEGATED_BOOL_ALIASES:
        available_args.append(f"{alias}")

    try:
        opts, _ = getopt.getopt(raw_args, "h", available_args)
    except getopt.GetoptError as err:
        print(err)
        sys.exit()

    for arg, value in opts:
        if arg.find("--") > -1:
            arg_name = arg.split("--")[1].strip()
        elif arg.find("-") > -1:
            arg_name = arg.split("-")[1].strip()
        if arg_name in NEGATED_BOOL_ALIASES:
            canonical_arg_name = NEGATED_BOOL_ALIASES[arg_name]
            value = False
        else:
            canonical_arg_name = arg_name

        if arg_name in ("h", "help"):
            print(format_cli_help())
            sys.exit()
        else:
                try:
                    # this converts the string parameters to lists
                    if arg_name in NEGATED_BOOL_ALIASES:
                        pass
                    elif canonical_arg_name in bool_args:
                        value = True
                    elif canonical_arg_name.lower() in list_args:
                        value = format_lists(value)
                    elif canonical_arg_name.lower() in int_args:
                        if value is not None:
                            value = int(value)
                    elif canonical_arg_name.lower() in int_double_args:
                         if ":" in value and len(value.split(":")) == 2: 
                            value = tuple(map(int, value.split(":")))
                    elif canonical_arg_name.lower() in float_args:
                        value = float(value)
                    elif value == "None":
                        value = None
                    elif value == "False":
                        value = False
                    elif value == "True":
                        value = True
                except (SyntaxError, ValueError, TypeError):
                    print(
                        f"Warning! Option '{arg_name}' received an invalid value ({value}). "
                        "The default value will be used instead."
                    )
                    continue

                kwargs[canonical_arg_name] = value

    # Second, combine all the default variables with the user-defined ones saved in "kwargs".
    args = load_variables(kwargs, "command")
    args._normalized_command_line_args = normalized_command_line_args
    
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
    internal_option_names = {"_normalized_command_line_args"}
    internal_options = {
        key: value for key, value in kwargs.items() if key in internal_option_names
    }
    user_options = {
        key: value for key, value in kwargs.items() if key not in internal_option_names
    }
    if "alfa" in user_options and "alpha" not in user_options:
        user_options["alpha"] = user_options["alfa"]
    if almos_module == "al" and "mode" in user_options and "al_mode" not in user_options:
        user_options["al_mode"] = user_options["mode"]
    self = set_options(user_options)
    for key, value in internal_options.items():
        setattr(self, key, value)
    
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
                    cmd_args = list(
                        getattr(self, "_normalized_command_line_args", sys.argv[1:])
                    )
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
            # these lines fix issues when there are blank spaces, in front or behind
            # value = [ele[1:] for ele in value if ele[0] == ' ']
            # value = [ele[:-1] for ele in value if ele[-1] == ' ']
            # this not work, because the problem is another thing
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
            self.log = open(f"{filein}_{append}.{suffix}", "w", encoding="utf-8")
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
        try:
            print(f"{message}\n")
        except UnicodeEncodeError:
            console_encoding = sys.stdout.encoding or "utf-8"
            safe_message = str(message).encode(
                console_encoding,
                errors="replace",
            ).decode(
                console_encoding,
                errors="replace",
            )
            print(f"{safe_message}\n")

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

    For module "cluster":
     Only required for the aqme workflow.
      - Requires 'obabel', version: "3.1.1"
      - Requires 'aqme', version: "1.7.2"

    For module "al":
    - Requires the system packages used by ROBERT/WeasyPrint on all platforms.

    Parameters:
    -----------
    module : str
        The name of the module for which dependencies are being checked.
    """
    if module == "cluster_aqme":
        # this is a dummy command just to warn the user if OpenBabel is not installed
        try:
            command_run_1 = ["obabel", "-H"]
            subprocess.run(command_run_1, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            self.args.log.write(f"x  Open Babel is not installed! You can install the program with 'conda install -y -c conda-forge openbabel={obabel_version}'")
            self.args.log.finalize()
            sys.exit()
            
        # this is a dummy command just to warn the user if AQME is not installed       
        try:
            command_run_2 = ["python","-m","aqme", "-h"]
            result = subprocess.run(command_run_2,capture_output=True, text=True, check=True)
            
        except subprocess.CalledProcessError:
            self.args.log.write(f"x  AQME is not installed! You can install the program with 'pip install aqme=={aqme_version}'")
            self.args.log.finalize()
            sys.exit()

    if module == "al":
        required_packages = ["glib", "gtk3", "pango", "mscorefonts"]
        missing_packages = []
        installed_package_names = []
        using_conda = False
        conda_cmd = "conda.bat" if os.name == "nt" else "conda"

        # --- Check conda or pip ---
        if shutil.which(conda_cmd):
            try:
                result = subprocess.run(
                    [conda_cmd, "list"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    shell=(os.name == "nt")
                )
                lines = result.stdout.strip().splitlines()
                installed_package_names = [
                    line.split()[0].lower()
                    for line in lines
                    if line and not line.startswith("#")
                ]
                using_conda = True
            except Exception as e:
                self.args.log.write(f"\nERROR: Failed to run 'conda list': {str(e)}")
                self.args.log.finalize()
                sys.exit()

        elif shutil.which("pip"):
            result = subprocess.run(
                ["pip", "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True
            )
            lines = result.stdout.strip().splitlines()[2:]  # Skip headers
            installed_package_names = [line.split()[0].lower() for line in lines]

        else:
            self.args.log.write("\nERROR! Neither 'conda' nor 'pip' found in PATH. Cannot verify package installation.")
            self.args.log.finalize()
            sys.exit()

        # --- Check each required package ---
        for package in required_packages:
            found = any(package.lower() in name for name in installed_package_names)
            if not found:
                missing_packages.append(package)

        # --- Warn and exit if any missing ---
        if missing_packages:
            self.args.log.write(f"\nWARNING! The following required packages are missing: {', '.join(missing_packages)}")
            if using_conda:
                self.args.log.write("\nYou can install them with: conda install -y -c conda-forge " + ' '.join(missing_packages))
            else:
                self.args.log.write("\nTry installing equivalents via pip or conda-forge.")
            self.args.log.finalize()
            sys.exit()

