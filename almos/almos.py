#!/usr/bin/env python

###########################################################################################.
###########################################################################################
###                                                                                     ###
###  ALMOS is a tool automates the process of:                                          ###
###  (CLUSTER)                                                                          ###
###  (AL)                                                                               ###                                                                                 
###  - Updating a machine learning model                                                ###                                                     
###  - Checking and validating input data for active learning                           ###
###  - Running model updates and generating predictions                                 ###
###  - Processing and selecting data points for new batches                             ###
###  - Checking for convergence and generating convergence plots                        ###
###                                                                                     ###
###########################################################################################
###                                                                                     ###
###  Authors: Miguel Martínez Fernández, Susana García Abellán,                         ###
###           Juan V. Alegre Requena                                                    ###
###                                                                                     ###
###                                                                                     ###
###                                                                                     ###
###  Please, report any bugs or suggestions to:                                         ###
###  miguel.martinez@csic.es                                                            ###
###                                                                                     ###
###########################################################################################
###########################################################################################


from almos.cluster import cluster
from almos.el import el
from almos.al import al
from almos.al_bayes import bo 
from almos.utils import command_line_args

def main():
    """
    Main function of ALMOS, acts as the starting point when the program is run through a terminal

    """
    # load user-defined arguments from command line
    args = command_line_args()
    args.command_line = True
    
    if not args.cluster and not args.el and not args.al and not args.bo:
        print('x  No module was specified in the command line! (i.e. --cluster for Clustering Execution). If you did specify a module, check that you are using quotation marks when using options (i.e. --csv_name "*.csv").\n')

    # Cluster
    if args.cluster:
        cluster(**vars(args))

    # Active Learning process
    if args.al:
        al(**vars(args))

    # Bayesian Optimization process
    if args.bo:
        bo(**vars(args))

if __name__ == "__main__":
    main()