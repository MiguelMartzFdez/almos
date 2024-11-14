######################################################.
#     This file stores generic functions     #
######################################################.

import os
import sys
import ast
import getopt
from pathlib import Path
from argument_parser import set_options, var_dict

def command_line_args():
    """
    Load default and user-defined arguments specified through command lines. Arrguments are loaded as a dictionary

    """

    # First, create dictionary with user-defined arguments
    kwargs = {}
    available_args = ["help"]
    bool_args = []
    int_args = ["number_of_new_points"]
    list_args = [
        "ignore_list",  
    ]
    float_args = [
        "factor_explore",
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
            print(f"o  Module v {aqme_version} is installed correctly!")
            sys.exit()
        else:
                # this converts the string parameters to lists
                if arg_name in bool_args:
                    value = True                    
                elif arg_name.lower() in list_args:
                    value = format_lists(value,arg_name)
                elif arg_name.lower() in int_args:
                    if value is not None:
                        value = int(value)
                    else:
                        value = None
                elif arg_name.lower() in float_args:
                    value = float(value)
                elif value == "None":
                    value = None
                elif value == "False":
                    value = False
                elif value == "True":
                    value = True

                kwargs[arg_name] = value

    # Second, load all the default variables as an "add_option" object
    args = load_variables(kwargs, "command")
    
    return args


def load_variables(kwargs, program_module, create_dat=True):
    """
    Load default and user-defined variables
    """

    # first, load default values and options manually added to the function
    self = set_options(kwargs)
 
    if aqme_module != "command":

        self.initial_dir = Path(os.getcwd())

        # get PATH for the files option
        self.files = get_files(self.files)

        if not isinstance(self.files, list):
            self.w_dir_main = os.path.dirname(self.files)
        elif len(self.files) != 0:
            self.w_dir_main = os.path.dirname(self.files[0])
        else:
            self.w_dir_main = os.getcwd()

        if (
            Path(f"{self.w_dir_main}").exists()
            and os.getcwd() not in f"{self.w_dir_main}"
        ):
            self.w_dir_main = Path(f"{os.getcwd()}/{self.w_dir_main}")
        else:
            self.w_dir_main = Path(self.w_dir_main)

        if self.isom_type is not None:
            if (
                Path(f"{self.isom_inputs}").exists()
                and os.getcwd() not in f"{self.isom_inputs}"
            ):
                self.isom_inputs = Path(f"{os.getcwd()}/{self.isom_inputs}")
            else:
                self.isom_inputs = Path(self.isom_inputs)

        error_setup = False

        if not self.w_dir_main.exists():
            txt_yaml += "\nx  The PATH specified as input or files might be invalid!"
            error_setup = True

        if error_setup:
            self.w_dir_main = Path(os.getcwd())
            
        # start a log file to track the AQME modules
        if create_dat:
            logger_1, logger_2 = "AQME", "data"
            if aqme_module == "qcorr":
                # detects cycle of analysis (0 represents the starting point)
                self.round_num, self.resume_qcorr = check_run(self.w_dir_main)
                logger_1 = "QCORR-run"
                logger_2 = f"{str(self.round_num)}"

            elif aqme_module == "csearch":
                logger_1 = "CSEARCH"

            elif aqme_module == "cmin":
                logger_1 = "CMIN"

            elif aqme_module == "qprep":
                logger_1 = "QPREP"

            elif aqme_module == "qdescp":
                logger_1 = "QDESCP"

            if txt_yaml not in [
                "",
                f"\no  Importing AQME parameters from {self.varfile}",
                "\nx  The specified yaml file containing parameters was not found! Make sure that the valid params file is in the folder where you are running the code.\n",
            ]:
                self.log = Logger(self.initial_dir / logger_1, logger_2, verbose=self.verbose)
                self.log.write(txt_yaml)
                error_setup = True

            if not error_setup:
                if not self.command_line:
                    self.log = Logger(self.initial_dir / logger_1, logger_2, verbose=self.verbose)
                else:
                    # prevents errors when using command lines and running to remote directories
                    path_command = Path(f"{os.getcwd()}")
                    self.log = Logger(path_command / logger_1, logger_2, verbose=self.verbose)

                self.log.write(f"AQME v {aqme_version} {time_run} \nCitation: {aqme_ref}\n")

                if self.command_line:
                    cmd_print = ''
                    cmd_args = sys.argv[1:]
                    for i,elem in enumerate(cmd_args):
                        if elem[0] in ['"',"'"]:
                            elem = elem[1:]
                        if elem[-1] in ['"',"'"]:
                            elem = elem[:-1]
                        if elem != '-h' and elem.split('--')[-1] not in var_dict:
                            # parse single elements of the list as strings (otherwise the commands cannot be reproduced)
                            if cmd_args[i-1] == '--qdescp_atoms':
                                elem = elem[1:-1]
                                elem = elem.replace(', ',',').replace(' ,',',')
                                new_elem = []
                                for smarts_strings in elem.split(','):
                                    new_elem.append(f'{smarts_strings}'.replace("'",''))
                                elem = f'{new_elem}'.replace(" ","")
                            if cmd_args[i-1].split('--')[-1] in var_dict: # check if the previous word is an arg
                                cmd_print += f'"{elem}'
                            if i == len(cmd_args)-1 or cmd_args[i+1].split('--')[-1] in var_dict: # check if the next word is an arg, or last word in command
                                cmd_print += f'"'
                        else:
                            cmd_print += f'{elem}'
                        if i != len(cmd_args)-1:
                            cmd_print += ' '

                    self.log.write(f"Command line used in AQME: python -m aqme {cmd_print}\n")

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
    A simple logger that writes messages to both a file and the console.

    """

    def __init__(self, filein, append, suffix="dat"):
        """
        Initializes the Logger by opening a log file.
        
        Parameters:
        ----------
        filein : str
            Base name of the log file.
        append : str
            String to append to the base name (e.g., "log").
        suffix : str, optional
            File extension (default is 'dat').
        """
        self.log = open(f"{filein}_{append}.{suffix}", "w")

    def write(self, message):
        """
        Writes a message to both the log file and the console.

        Parameters:
        ----------
        message : str
            Message to log and print.
            
        """
        self.log.write(f"{message}\n")
        print(f"{message}\n")

    def finalize(self):
        """
        Closes the log file.

        """
        self.log.close()