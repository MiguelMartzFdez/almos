#!/usr/bin/env python

###########################################################################################.
###########################################################################################
###                                                                                     ###
###  Active Learning Program                                                            ###
###                                                                                     ###
###  This tool automates the process of:                                                ###
###  - Checking and validating input data for active learning                           ###
###  - Running model updates and generating predictions                                 ###
###  - Processing and selecting data points for new batches                             ###
###  - Checking for convergence and generating diagnostic plots                         ###
###                                                                                     ###
###########################################################################################
###                                                                                     ###
###  Authors: [Name(s)]                                                                 ###
###                                                                                     ###
###  Please, report any bugs or suggestions to:                                         ###
###  [ Emails Address]                                                                  ###
###                                                                                     ###
###########################################################################################
###########################################################################################


from al import al 
from argument_parser import var_dict 

def main():
    al(var_dict)  

if __name__ == "__main__":
    main()