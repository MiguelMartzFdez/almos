"""
Parameters
----------

General
+++++++

   input : str, default = '' 
      Current file extension: .csv or .sdf (i.e. example.csv).
      Only is possible use a SDF file if using AQME (--aqme).
      If the descriptors are to be obtained through AQME from a CSV file two columns are required: 'code_name' with the names and 'SMILES' for the SMILES string. 
      If the CSV already contains descriptors, it must contain at least 3, and the variable --name must be defined.
      For both cases, there cannot be any column named 'batch' in the CSV file.
   n_clusters : int, default = None 
      Number of clusters for the clustered. If not defined by the user, it is calculated using the Elbow Method.  
   seed_clustered : int, default = 0
      Random seed used during KMeans (in k_means function).
   descp_level : str, default = 'interpret'
      Type of descriptor to be used in the ALMOS workflow. Options are 'interpret', 'denovo' or 'full'. 
   ignore : list, default = []
      List containing the columns of the input CSV file that will be ignored during the clustered process
      (i.e. ['code_name','SMILES']). The descriptors will be included in the clustered CSV file. The y value
      is automatically ignored.
   aqme : bool, default = False
      Enables the aqme workflow to generate descriptors.
   name : str, default = ''
      It is mandatory to define it if the clustering is to be done with the descriptors already defined by the user.
      If the descriptors are to be generated with the program (using AQME) 'name' is not defined.
   y : str, default = ''
      Name of the column containing the response variable in the input CSV file (i.e. 'yield').         
   auto_fill: bool, default = True
      If the CSV contains empty spaces (less than 30 % of NaN per column), KNNImputer is applied, using the K-nearest neighbors method 
      to estimate and fill missing values based on the closest values to each point in the dataset.
      If auto_fill is False, the KNNImputer is not applied (if there are still empty spaces the program finish).            
   categorical: str, default = 'onehot'
      It can be used when the user provide their descriptors.
      Mode to convert data from columns with categorical variables. As an example, a variable containing 4 types of C atoms 
      (i.e. primary, secondary, tertiary, quaternary) will be converted into categorical variables. Options: 
        1. 'onehot' (for one-hot encoding, ROBERT will create a descriptor for each type of C atom using 0s and 1s to indicate whether the C type is present)
        2. 'numbers' (to describe the C atoms with numbers: 1, 2, 3, 4).
   aqme_keywords: str, default = ''
       It can be used to use specific functions from aqme. The entire argument must be in quotation marks, as in the example.
       (i.e., --aqme_keywords "--qdescp_atoms [1,2]") 
   varfile : str, default=None
      Option to parse the variables using a yaml file (specify the filename, i.e. varfile=FILE.yaml).  
   nprocs: int, default=8
      Number of processors used in AQME for the clustered

"""
######################################################.
#        This file stores the cluster class          #
#          used to generate the batch 0              #
######################################################.

import sys
import os, glob
from pathlib import Path
import subprocess
import shutil
import pandas as pd
import numpy as np
from rdkit import Chem
from sklearn.cluster import KMeans
import plotly.express as px
from pca import pca
from sklearn.preprocessing import StandardScaler
from sklearn.impute import KNNImputer
import time
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import seaborn as sb
os.environ.setdefault("MPLBACKEND", "Agg") # avoid unwanted information on the terminal, it tells Matplotlib to use a backend that does not depend on Qt
# os.environ["QT_QPA_PLATFORM"] = "xcb"  # Force Qt to use X11 backend to avoid Wayland plugin error, not compatible with Windows
from kneed import KneeLocator




from almos.utils import (
    load_variables,
    check_dependencies
)

class cluster:
    """
    Class containing all the functions from the CLUSTER module 
    """

    def __init__(self, **kwargs):

        start_time_overall = time.time()

        # load default and user-specified variables
        self.args = load_variables(kwargs, "cluster")
        self.vars = {}

        # check whether dependencies are installed
        if self.args.aqme:
            _ = check_dependencies(self, "cluster_aqme")       
        
        # detect errors and update variables before the CLUSTER run
        self, df_csv_name, file_name = self.checking_cluster()
        
        # prepare the CSV file
        self, descp_file, df_csv_name, csv = self.set_up_cluster(df_csv_name, file_name)
        
        # generate the descriptors if the user needs it
        if self.args.aqme:
            self, descp_file = self.run_aqme(csv, descp_file)
        
        # prepare the CSV for the clustered
        self, filled_array, descp_file = self.clean_up_cluster(descp_file, csv, file_name)
        
        # define n_clusters, if the user do not define it, with the Elbow Method  
        if self.args.n_clusters == None:
            _ = self.elbow_method_nclusters(filled_array)
        
        # cluster execution    
        self, pc_total_val, pc1_var, pc2_var, pc3_var, df_pca = self.cluster_workflow(filled_array, descp_file, csv, file_name)
        
        # provide and save the representation of the PCA in 3D
        _ = self.pca_control(df_pca, pc_total_val, pc1_var, pc2_var, pc3_var)
        
        elapsed_time = round(time.time() - start_time_overall, 2)
        self.args.log.write(f"\nTime cluster: {elapsed_time} seconds\n")
        self.args.log.finalize()
        
        shutil.move('CLUSTER_data.dat', 'batch_0/CLUSTER_data.dat') # move the DAT file to the subfolder of batch_0
    
    def checking_cluster(self):
        '''
        Detects errors and updates variables before the CLUSTER run
        '''
        # check that the CSV or SDF name has been defined
        if self.args.input == None:
            self.args.log.write(f"\nx WARNING. Please, specify your CSV file required, e.g. --input example.csv (or SDF file if using AQME workflow)")
            self.args.log.finalize()
            sys.exit(9)  
        
        file_name = self.args.input.split("/")
        file_name = file_name[-1]
                      
        # check for existence of input file
        if os.path.exists(self.args.input) == False: 
            self.args.log.write(f"\nx WARNING. The input provided ({file_name}) does not exist! Please specify this name correctly")
            self.args.log.finalize()
            sys.exit(10)

        # check that the number of clusters has been defined
        if self.args.n_clusters == None:
            self.args.log.write(f"\nx WARNING. The number of clusters is not specified (e.g. --n_clusters 20), it will be automatically calculated using the Elbow Method")
            # self.args.log.finalize()
            # sys.exit(11)
        else:
            self.args.log.write(f"\nx WARNING. The cluster module is performing without using the Elbow Method. If you want to generate the optical number of clusters remove '--n_clusters n' of your script")
           
        # if 'name' is not defined and program is not going through AQME workflow, notify and exit the program 
        if self.args.name == '' and self.args.aqme == False:
            self.args.log.write(f"\nx WARNING. Please, specify the name column of your CSV file, e.g. --name nitriles")
            self.args.log.finalize()
            sys.exit(13)    
            
        # if 'name' is defined and --aqme == True, exit the program 
        if self.args.name !='':
            if self.args.aqme:
                self.args.log.write(f"\nx WARNING. Only is possible define --name if not using AQME. If you use AQME named that column as 'code_name'")
                self.args.log.finalize()
                sys.exit(16)   

        # check that if the input is a SDF file, --aqme == True
        check_input = file_name.split(".")
        check_input = check_input[-1]
        if check_input == 'sdf' and self.args.aqme == False:
            self.args.log.write(f"\nx WARNING. Only is possible use a SDF file if using AQME (--aqme)")
            self.args.log.finalize()
            sys.exit(14)
        
        # convert the SDF file into a dataframe (df_csv_name) with code_name and SMILES columns
        if check_input == 'sdf' and self.args.aqme == True:
            if self.args.ignore != []:
                self.args.log.write(f"\nx WARNING. Only is possible define --ignore if using CSV file")
                self.args.log.finalize()
                sys.exit(15)                
                
            sdf_file = Chem.SDMolSupplier(self.args.input) # load the SDF file                              
            column_name =  [] # empty list for compound names
            column_smile = [] # empty list for the smiles
            for mol in sdf_file:
                if mol is not None:
                    for prop in mol.GetPropNames():
                        if "name" in prop.lower(): # search for "name" anywhere in the property name
                            name_column_sdf = prop
                            break # exit when find the first match
                if name_column_sdf:
                    break
            for mol in sdf_file:
                if mol is not None:
                    try:
                        column_name.append(mol.GetProp(name_column_sdf))   # there could be an empty space
                    except KeyError:                                       # with this, if it finds an empty name, it continues
                        continue
                    column_smile.append(Chem.MolToSmiles(mol))
            self.args.log.write(f'\no Analyzing SDF file')        
            df_csv_name = pd.DataFrame({
                'code_name': column_name,
                'SMILES': column_smile,
            })
            
            # rename the file_name variable from SDF to a CSV file and save it
            file_name = file_name.replace('sdf','csv')
            df_csv_name.to_csv(file_name, index=False)
            self.args.log.write(f'\no CSV file named {df_csv_name} has been created')  

 
        # read the csv_name in a DataFrame
        if check_input == 'csv':
        
            df_csv_name = pd.read_csv(self.args.input)
        
            # check that elements of ignore are in the CSV
            elements = []
            for element in self.args.ignore:
                if element not in df_csv_name.columns:
                    elements.append(element)
            if elements != []:
                string_ignore = "[" + ",".join(str(x) for x in self.args.ignore) + "]" # Convert list to string with commas without spaces
                self.args.log.write(f"\nx WARNING. Some columns ({elements}), named in --ignore {string_ignore}, do not exist in the input provided ({file_name}). Please, specify the list ignore correctly")
                self.args.log.finalize()
                sys.exit(5)

            # check that there is no column named 'batch'
            for col in df_csv_name.columns:
                if 'batch' in col:
                    self.args.log.write(f"\nx WARNING. The input provided ({file_name}) already contains a 'batch' column")
                    self.args.log.finalize()
                    sys.exit(1)
                    
            # if "y" has been defined and is in the csv_name, it is added to the ignore list
            if self.args.y != "":
                if self.args.y not in df_csv_name.columns:
                    self.args.log.write(f"\nx WARNING. The input provided ({file_name}) does not contain the column idicated as: --y {self.args.y}")
                    self.args.log.finalize()
                    sys.exit(3)                    
                if self.args.y not in self.args.ignore:
                    self.args.ignore.append(self.args.y) 
                      
        # check for duplicates, if any
        if df_csv_name.duplicated().any(): # True if any
            duplicate_rows = df_csv_name[df_csv_name.duplicated(keep=False)]
            self.args.log.write(f"\nx WARNING. The input provided ({file_name}) has duplicate rows, only the first one has been kept. The duplicate rows are: \n{duplicate_rows}")

            df_csv_name = df_csv_name.drop_duplicates() # This keep the first duplicate                        
            
        # if 'name' is defined but not in the CSV, notify and exit the program 
        if self.args.name !='':           
            if self.args.name not in df_csv_name.columns:
                self.args.log.write(f"\nx WARNING. The input provided ({file_name}) does not contain the column idicated as: --name {self.args.name}")
                self.args.log.finalize()
                sys.exit(4)
                
            # if 'name' is defined and not in ignore list, add it 
            if self.args.name not in self.args.ignore:
                self.args.ignore.append(self.args.name)
                
            # if 'name' is defined check for duplicates in column 'name'
            if df_csv_name[self.args.name].duplicated().any(): # True if any
                duplicate_names = df_csv_name[df_csv_name.duplicated(subset=[self.args.name], keep=False)]    
                self.args.log.write(f"\nx WARNING. The input provided ({file_name}) has the next duplicates in the column ({self.args.name}) with different values for the other columns of descriptors: \n{duplicate_names} \nCheck the input provided")
                self.args.log.finalize()    
                sys.exit(8) 
                  
        
        return self, df_csv_name, file_name

    def fix_cols_names(self, df):
        '''
        Set code_name and SMILES using the right format
        Function to unify the names
        '''
        
        for col in df.columns:
            if col.lower() == 'smiles':
                df = df.rename(columns={col: 'SMILES'})
            if col.lower() == 'code_name':
                df = df.rename(columns={col: 'code_name'})
        return df
    
    def auto_fill_knn(self, df):
        '''
        KNNImputer uses the K-nearest neighbors method to estimate and fill missing values based on the closest values to each point in the dataset
        Function to impute (or fill) null-values in a dataset
        '''

        imputer = KNNImputer(n_neighbors = 5, weights = 'uniform')
        df = imputer.fit_transform(df)
        return df

    def categorical_transform(self, df):
        '''
        Function to categorical transform from ROBERT. It can apply to the df without the columns of ignore list
        Converts all columns with strings into categorical values (one hot encoding by default, can be set to numerical 1,2,3... with categorical = 'numbers').
        Troubleshooting! For one-hot encoding, don't use variable names that are also column headers!
        i.e. DESCRIPTOR "C_atom" contain C2 as a value, but C2 is already a header of a different column in the database.
        Same applies for multiple columns containing the same variable names.
        '''
        
        txt_categor = f'\no Analyzing categorical variables'

        categorical_vars, new_categor_desc = [],[]
        for column in df.columns:
            if column not in self.args.ignore and column != self.args.y:
                if(df[column].dtype == 'object'):
                    categorical_vars.append(column)
                    
                    if self.args.categorical.lower() == 'numbers':
                        df[column] = df[column].astype('category') # converts the columns to a category
                        df[column] = df[column].cat.codes # .cat.codes returns the column values ​​as numeric codes, and stores them back into the column
                    else:
                        # each category in the column becomes a binary column
                        categor_descs = pd.get_dummies(df[column]) # converts the 'object' column in  binary columns
                        df = df.drop(column, axis=1) # delete the original column
                        df = pd.concat([df, categor_descs], axis=1) # combine both df horizontally
                        for desc in categor_descs: 
                            new_categor_desc.append(desc)

        if len(categorical_vars) == 0:
            txt_categor += f'\n   - No categorical variables were found'
        else:
            txt_categor += f'\n   A total of {len(categorical_vars)} categorical variables were converted using the {self.args.categorical} mode in the categorical option:'
            if self.args.categorical.lower() == 'numbers':
                txt_categor += '\n'.join(f'   - {var}' for var in categorical_vars)
            else:
                txt_categor += f'\n   Initial descriptors:\n'
                txt_categor += '\n'.join(f'   - {var}' for var in categorical_vars)
                txt_categor += f'\n   Generated descriptors:\n'
                txt_categor += '\n'.join(f'   - {var}' for var in new_categor_desc)

        self.args.log.write(f'{txt_categor}')

        return df

    def set_up_cluster(self, df_csv_name, file_name):
        '''
        Prepare the CSV file
        '''
        
        # add a new column named batch, empty for now
        df_csv_name['batch'] = ''
        # add the column 'batch' to ignore list
        self.args.ignore.append('batch') 
        # create the folders batch_0, if there is not
        os.makedirs('batch_0') if not os.path.exists('batch_0') else None
         
        
        # if aqme = True, check the CSV has to contain the columns 'SMILES' and 'code_name'
        # with the funcition fix_cols_names unify the names of the columns to 'SMILES' and 'code_name' 
        if self.args.aqme:
            if 'code_name' not in self.fix_cols_names(df_csv_name).columns or 'SMILES' not in self.fix_cols_names(df_csv_name).columns:
                self.args.log.write(f"\nx WARNING. The input provided ({file_name}) must contain a column called 'SMILES' and another called 'code_name' to generate the descriptors with aqme")
                self.args.log.finalize()
                sys.exit(2)
            # create the folder aqme, if there are not
            os.makedirs('aqme') if not os.path.exists('aqme') else None
        
        # FOR BOTH WORKFLOWS                
        # modify the df with the correct names ('SMILES' and 'code_name') if they are
        df_csv_name = self.fix_cols_names(df_csv_name)
        # add the columns 'SMILES' and 'code_name' to ignore list if they are
        for col in df_csv_name.columns:
            if col == 'SMILES':
                if 'SMILES' not in self.args.ignore:
                    self.args.ignore.append('SMILES')
                # prepare the new csv with canonical smiles and delete columns with invalid smiles
                invalid_smiles = []
                df_csv_name['SMILES'] = df_csv_name['SMILES'].apply(lambda x: Chem.MolToSmiles(Chem.MolFromSmiles(x)) if Chem.MolFromSmiles(x) else invalid_smiles.append(x) or None)    
                if invalid_smiles:
                    # if the flow goes through AQME, remove the invalid smiles and report it
                    if self.args.aqme:
                        self.args.log.write(f"\nx  WARNING. These invalid smiles from ({file_name}) have been removed:\n {invalid_smiles}")
                        df_csv_name = df_csv_name.dropna (subset = ['SMILES'])
                    # if the flow DOESN'T go through AQME, only report it
                    else:
                        self.args.log.write(f"\nx  WARNING. There are invalid smiles in ({file_name}):\n {invalid_smiles}")

                # check for duplicates in column 'SMILES', if any
                if df_csv_name['SMILES'].duplicated().any(): # True if any
                    duplicate_smiles = df_csv_name[df_csv_name.duplicated(subset=['SMILES'], keep=False)]    

                    # if the flow goes through AQME, remove the duplicated smiles and report it
                    if self.args.aqme:                    
                        self.args.log.write(f"\nx WARNING. The input provided ({file_name}) has duplicate canonicalized SMILES, only the first one has been kept. The duplicate SMILES are: \n{duplicate_smiles}")
                        
                        df_csv_name = df_csv_name.drop_duplicates(subset=['SMILES']) # This keep the first duplicate

                    # if the flow DOESN'T go through AQME, only report it
                    else:
                        self.args.log.write(f"\nx WARNING. The input provided ({file_name}) has duplicate canonicalized SMILES. The duplicate SMILES are: \n{duplicate_smiles}")
                                                  
            if col == 'code_name':
                if 'code_name' not in self.args.ignore:
                    self.args.ignore.append('code_name')

        # create a new CSV file with the modifications in the subfolder 'batch_0', if the file exists, replaces it
        csv = file_name.rsplit('.', 1) # because the name of the file could have more dots
        df_csv_name.to_csv(f'{csv[0]}_b0.csv', index=False, header=True)

        # first, CSV file is generated in the same folder. After aqme run (if it's the case) the CSV file will be moved to folder batch_0
        # this is to solve the use of aqme with Windows          
        descp_file = f'{csv[0]}_b0.csv'  
                      
        return self, descp_file, df_csv_name, csv   
       
    def run_aqme(self, csv, descp_file):
        '''
        Generate the descriptors if the user needs it
        '''

        workdir   = Path.cwd()                          
        dest_csearch  = workdir / "CSEARCH" 
        dest_qdescp  = workdir / "QDESCP" 

        cmd_csearch = ["python", "-m", "aqme", "--csearch", "--input", descp_file, "--destination", dest_csearch, "--program", "rdkit"]        
        cmd_qdescp = ["python", "-m", "aqme", "--qdescp", "--files", "/CSEARCH/*.sdf", "--csv_name", descp_file, "--destination", dest_qdescp, "--charge", "None", "--mult", "None"]

        
        # cmd_qdescp = ["python", "-m", "aqme", "--qdescp", "--input", descp_file] # using this command gave an error in pytest with Circle CI. 
        # Despite running this single command, it split the command into:
        # i) Command line used in AQME: python -m aqme --csearch --program "rdkit" --input "test_cluster2_b0.csv" --sample "5" --destination "/root/project/CSEARCH" --nprocs "8" --auto_sample "low"
        # ii) Command line used in AQME: python -m aqme --qdescp --input "test_cluster2_b0.csv"
        # and the second one didn't complete (it couldn't find some JSON file).
        # However, running the tests from the terminal (same version of aqme) did work.
        
        if self.args.nprocs != 8:  # it is 8 by default
            cmd_csearch += ["--nprocs", f"{self.args.nprocs}"]
            cmd_qdescp += ["--nprocs", f"{self.args.nprocs}"]
        
        if self.args.aqme_keywords != '':
            cmd_aqme = self.args.aqme_keywords.split()
            for word in cmd_aqme:
                word = word.replace('"','').replace("'","")                
                cmd_qdescp.append(word) 
                 
        # running both modules of aqme       
        exit_error = subprocess.run(cmd_csearch)        
        exit_error = subprocess.run(cmd_qdescp)
    
        # converts the commands to a string, for printing later          
        string_cmd_csearch = ''
        for cmd in cmd_csearch:
            string_cmd_csearch += f'{cmd} ' # adding blank space between words
            
        string_cmd = ''
        for cmd in cmd_qdescp:
            string_cmd += f'{cmd} ' # adding blank space between words
        
        # to check in cluster.dat the command line that it sends to aqme, which sometimes does not match the one that aqme launches later  
        self.args.log.write(f"\no Command line used in AQME: {string_cmd_csearch} ")        
        self.args.log.write(f"\no Command line used in AQME: {string_cmd} ")
        
        # if exit_error.returncode != 0:
        #     self.args.log.write(f'''\nx WARNING. --aqme_keywords not defined properly. Please, check if the quotation marks have been included, e.g. --aqme_keywords "--qdescp_atoms [1,2] --qdescp_solvent acetonitrile" ''')
        #     self.args.log.finalize()
        #     sys.exit()
            
        files_to_aqme = [f'AQME-ROBERT_denovo_{csv[0]}_b0.csv', 
                        f'AQME-ROBERT_interpret_{csv[0]}_b0.csv', 
                        f'AQME-ROBERT_full_{csv[0]}_b0.csv', 
                        'QDESCP_data.dat', 
                        'CSEARCH_data.dat',
                        'CSEARCH',
                        'QDESCP']
        folders = ['CSEARCH', 'QDESCP']
        
        # move files to aqme subfolder
        for file in files_to_aqme:
            destination = f'aqme/{file}'
            if os.path.exists(destination):       # if file exists in destination
                if file in folders:                  # if it is a folder, remove it
                    shutil.rmtree(destination)
                else:                                # if it is a file, remove it
                    os.remove(destination)
        
            if os.path.exists(file):                 # move the file
                shutil.move(file, destination)
                
        # check subprocess.run(cmd_qdescp), if there is an error, it is probably due to --aqme_keywords
        if not os.path.exists(f'aqme/AQME-ROBERT_denovo_{csv[0]}_b0.csv'):
            self.args.log.write(f'''\nx WARNING. --aqme_keywords not defined properly. Please, check if the quotation marks have been included, e.g. --aqme_keywords "--qdescp_atoms [1,2]". If that is not the problem, check the input of aqme.''')
            self.args.log.finalize()
            sys.exit(12)  
            
        # after running the code, the variable descp_file is updated with the chosen file with the descriptors
        descp_file = f'aqme/AQME-ROBERT_{self.args.descp_level}_{csv[0]}_b0.csv' 
        
        return self, descp_file
    
    def clean_up_cluster(self, descp_file, csv, file_name):
        '''
        Prepare the CSV (descp_file) of both paths for the clustered
        '''
        # move CSV file with batch_0 column to batch_0 subfolder
        shutil.move(f'{csv[0]}_b0.csv',f'batch_0/{csv[0]}_b0.csv')
        
        # putting the new correct location of the variable 
        if self.args.aqme == False:
            descp_file = f'batch_0/{csv[0]}_b0.csv'      
                            
        # read created csv with information, diferent for each aqme workflow
        descp_df = pd.read_csv(descp_file)  
                
        # delete columns from ignore list
        descp_df_drop = descp_df.drop(self.args.ignore, axis = 1) 
        
        # remove columns with less than 70% of the data
        col_to_drop = []
        for col in descp_df_drop.columns:
            if descp_df_drop[col].isna().mean() > 0.3:
                self.args.log.write(f"\nx WARNING. The column ({col}) in the input provided ({file_name}) has less than 70% of the data, so it has been deleted")
                col_to_drop.append(col)
        if col_to_drop != []:
            descp_df_drop = descp_df_drop.drop(col_to_drop, axis = 1)     
            
        # convert the df to int or float with the categorical_transform function
        descp_df_drop = self.categorical_transform(descp_df_drop)
        

        # if the csv has less than three columns corresponding to descriptors, exit the program
        if len(descp_df_drop.columns) < 3:
            self.args.log.write(f"\nx WARNING. The input provided ({file_name}) must contain at least three columns of descriptors")
            self.args.log.finalize()
            sys.exit(7)
            
        # check that there are no NaNs in descp_df and apply the auto_fill_knn function
        if descp_df_drop.isnull().any().any() == True:
            if self.args.aqme == False:
                if self.args.auto_fill: # auto_fill: True by default
                    self.args.log.write(f"\nx WARNING. The input provided ({file_name}) has empty spaces in the descriptor columns. These will be filled with the auto_fill_knn function. You can see the generated values in the file {descp_file}. If you don't want them to be auto-completed, set --auto_fill False, in this case, if empty spaces are found, they will not be auto-completed and the program will end.")   
                else: # auto_fill : False
                    self.args.log.write(f"\nx WARNING. The input provided ({file_name}) has empty spaces in the descriptor columns. If you want them to be auto-completed, set --auto_fill True, and these will be filled with the auto_fill_knn function.")
                    self.args.log.finalize()
                    sys.exit(6)       
            filled_array = self.auto_fill_knn(descp_df_drop)
            # rebuild descp_df_drop from NumPy array (filled_array)
            descp_df_drop = pd.DataFrame(filled_array, columns = descp_df_drop.columns, index = descp_df_drop.index)
            # update descp_df values
            descp_df.update(descp_df_drop)
        filled_array = descp_df_drop   
        # overwrite the CSV file (descp_file) in the subfolder 'batch_0', with the auto_fill_knn
        descp_df.to_csv(f'batch_0/{csv[0]}_b0.csv', index=False, header=True)
        descp_file = f'batch_0/{csv[0]}_b0.csv'# update the variable for the clustered
        
        return self, filled_array, descp_file
      
    def k_means(self, X_scaled,seed_clustered,n_clusters):

        '''
        Returns the data points that will be used as molecules to test to generate experimental data (k-means clustering)

        '''
        # n clusters with all the cores, of those clusters you keep 1 point (1 core) closest to each cluster, 
        # because what we are looking for is the most heterogeneous data possible

        # user insert the number of clusters 
        X_scaled_array = np.asarray(X_scaled)
        closest_points_cluster = []

        # runs the k-neighbours algorithm and keeps the closest point to the center of each cluster
        kmeans = KMeans(n_clusters,random_state=seed_clustered)
        kmeans.fit(X_scaled_array)

        centers = kmeans.cluster_centers_
        for i in range(n_clusters): # for each cluster lets find his closest point
            results_cluster = 1000000 # introduce a high distance value so when evaluating the first point, it gets replaced easily
            for k in range(len(X_scaled_array[:, 0])): #we evalue each point from array
                if k not in closest_points_cluster:
                    # calculate the Euclidean distance in n-dimensions
                    points_sum = 0
                    for l in range(len(X_scaled_array[0])): # if the Euclidean distance is less that the actual number, it gets replaced
                        points_sum += (X_scaled_array[:, l][k]-centers[:, l][i])**2 # with that loop we obtained the closest point for that cluster
                    if np.sqrt(points_sum) < results_cluster:                       # and we repeat with each cluster
                        results_cluster = np.sqrt(points_sum)
                        closest_point_cluster = k
            
            closest_points_cluster.append(closest_point_cluster)
        closest_points_cluster.sort()

        return closest_points_cluster,kmeans,X_scaled_array
      
    def elbow_method_nclusters(self, filled_array):
        ''' 
        define optimal n_clusters, if the user do not define it, with the Elbow Method   
        ''' 
                       
        # prepare array for kmeans
        # standardize the data before k-means-based data splitting
        scaler = StandardScaler()

        X_scaled= scaler.fit_transform(filled_array)
        
        # knowing the number of rows of filled_array, determinate the interval between the values of n_clusters
        rows_filled_array = len(filled_array)
      
        if rows_filled_array < 50:
            interval = 1
            coverage = 0.5
            
        elif 50 <= rows_filled_array < 100:
            interval = 2
            coverage = 0.4
            
        elif 100 <= rows_filled_array < 250:
            interval = 5
            coverage = 0.3
            
        elif 250 <= rows_filled_array < 1000:
            interval = 10
            coverage = 0.2
            
        elif 1000 <= rows_filled_array < 5000:
            interval = 10
            coverage = 0.1
            
        elif 5000 <= rows_filled_array < 10000:
            interval = 10
            coverage = 0.02
            
        elif 10000 <= rows_filled_array:
            interval = 10
            coverage = 0.01

        stop = int(rows_filled_array*coverage)
        
        # defining a limit value for the number of clusters
        if stop > 300:
            stop = 300
           
        # cluster execution for each n_clusters (k)
        self.args.log.write(f'\no Defining optimal n_clusters using the Elbow Method')  
                  
        k_list, wcss_list = [], [] # creating empty list for the number of clusters and the WCSS (within-cluster sum of squares)
        
        for i in range(interval, stop + 1, interval):  # i starts in 1/2/5/10 and covers up to the number of rows * chosen coverage (stop), step = interval
            k = i
            self.args.log.write(f'\no Evaluating {k} clusters')
            points,kmeans,X_scaled_array = self.k_means(X_scaled,self.args.seed_clustered,k)           
            k_list.append(k)
            # Within-Cluster Sum of Squares, the total of the squared distances between data points and their cluster center 
            wcss_list.append(kmeans.inertia_)
            
        # creating a df with the values of the plot and saving it in a csv ()
        dict_elbow = {
            "n_clusters (k)" : k_list,
            "WCSS" : wcss_list
        }
        df_elbow = pd.DataFrame(dict_elbow)
            
        # generate a plot of the relationship between the number of clusters (x) and the WCSS (y)
        plt.plot(k_list,wcss_list, marker='o', linestyle='-', color='#1f77b4')
        #sb.scatterplot(s = 20, marker='o', linestyle='-', color = 'b',  alpha = 1, edgecolor = 'black')
        sb.scatterplot(x = k_list, y = wcss_list, s = 20, marker='o', color = 'b',  alpha = 1, edgecolor = 'black')
        plt.title('Elbow Method for Optimal n_clusters (k)', fontsize=11)      # Chart title
        plt.xlabel('Number of Clusters (k)', fontsize=9)                       # X-axis label
        plt.ylabel('WCSS', fontsize=9)                                         # Y-axis label
        
        # set x-axis ticks every interval units, until rows_filled_array (number of rows)
        plt.xticks(np.arange(0, stop + 1, interval), fontsize=8)
        plt.yticks(fontsize=8)
        plt.ylim(bottom=0)
        plt.xlim(left=0)
        
        # save the plot as a PNG file in the 'batch_0' folder
        plt.savefig('batch_0/elbow_plot.png', dpi=300, bbox_inches='tight')
        self.args.log.write(f'\no The file elbow_plot.png, which shows the relationship between the number of clusters (x) and the WCSS (y), has been generated in the folder batch_0')
        
        # evaluate the optimal number of n_clusters using kneew
        k_optimal = KneeLocator(k_list, wcss_list, curve="convex", direction="decreasing")
        self.args.n_clusters = k_optimal.elbow

        if self.args.n_clusters == None:
            self.args.log.write(f'''\nx WARNING. Optimal n_cluster could not be defined, because the curve doesn't have a clear "elbow" shape (the WCSS drops smoothly without inflection) or because the data is noisy or very linear''')
            self.args.log.write(f'''\no SUGGESTION. You can open de graph generated in batch_0, select n_clusters manually, and run ALMOS again including n_cluster selected (e.g. -n_clusters n)''')
            
            self.args.log.finalize()
            sys.exit(11)    

        self.args.log.write(f'\no Optimal n_clusters has been defined as {self.args.n_clusters}')

        # add dashed vertical line in k_optimal
        ymax = df_elbow.loc[df_elbow['n_clusters (k)'] == self.args.n_clusters, 'WCSS'].values[0]
        plt.vlines(x=self.args.n_clusters, ymin = -5, ymax=ymax, colors='dimgray', linestyles='dashed', linewidth=1, zorder=1)
        # plt.axvline(x=self.args.n_clusters, ymax=ymax, color='dimgray', linestyle='dashed', linewidth=1, zorder=1)
        
        # modify title to include optimal k value
        plt.title(f'Elbow Method for Optimal n_clusters (k found at {self.args.n_clusters})', fontsize=11)

        # overwrites the graph with some variation (vertical line and optimal number of clusters)
        plt.savefig('batch_0/elbow_plot.png', dpi=300, bbox_inches='tight')

          
    def cluster_workflow(self, filled_array, descp_file, csv, file_name):
        ''' 
        cluster execution   
        '''
                
        # prepare array for kmeans
        # standardize the data before k-neighbours-based data splitting
        scaler = StandardScaler()

        X_scaled= scaler.fit_transform(filled_array)

        # saved points = n cores for index code, we can find them in descp_df with iloc
        points,kmeans,X_scaled_array = self.k_means(X_scaled,self.args.seed_clustered,self.args.n_clusters)

        # creating a list (batch_0) with the name of the molecules for the batch 0
        descp_df = pd.read_csv(descp_file) # this is because in the previous descp_df the names of the molecules have been removed
        if self.args.aqme:
            self.args.name = 'code_name'
        batch_0 = descp_df.iloc[points][self.args.name].tolist()
        self.args.log.write(f'\no The molecules selected for the batch 0 of the CLUSTER module are: {batch_0}')        

        # creating a CSV file with the options for the next module of Active Learning
        # create an ignore list without name or target value (y)
        ignore_al = [i for i in self.args.ignore if i != self.args.y and i != self.args.name]
        
        options = {'y': self.args.y,
                       'csv_name': file_name,
                       'ignore': [ignore_al],
                       'name': self.args.name
        } 
        options_csv = pd.DataFrame.from_dict(options)
        options_csv.to_csv('options.csv', index=False, header=True)
                
        self.args.log.write(f'\no A CSV file with the selected options for clustering has been created as options.csv')  
        
        # creating a .dat document with the name of the molecules for the batch 0 in the subfolder 'batch_0'    
        path_batch_0 = os.path.join('batch_0', 'batch_0.dat')
        with open (path_batch_0, 'w') as doc_batch_0:
            doc_batch_0.writelines(line + '\n' for line in batch_0) # to write each element of the list (code_names) in a new line
            
        # on the df created for the batch_0 subfolder, add 0 to the molecules obtained from the initial clustering, for the aqme = False it's the unique csv generated, for the aqme = True the descriptors are not included
        descp_df.loc[points, 'batch'] = 0
        # overwriting the csv 
        descp_df.to_csv(f'batch_0/{csv[0]}_b0.csv', index=False, header=True)
        self.args.log.write(f"\no The CSV file with the descriptors and the result of the clustered has been save as batch_0/{csv[0]}_b0.csv")
        self.args.log.write(f"\no For the clustering, the following columns of the CSV file batch_0/{csv[0]}_b0.csv have been ignore:\n {self.args.ignore}")


        # PCA model
        pcaModel = pca(normalize=True,n_components=3)
        X_pca = pcaModel.fit_transform(X_scaled_array)

        # with PC1,PC2 and PC3 we explain n% var of data
        pca_var_cum = pcaModel.results['explained_var']
        self.args.log.write(f"\n {pca_var_cum}")

        pc1_var = round(pca_var_cum[0]*100, 1)
        pc2_var = round((pca_var_cum[1]*100 - pc1_var), 1)
        pc3_var = round((pca_var_cum[2]*100-pc1_var-pc2_var), 1)
        pc_total_val = round(pc1_var + pc2_var + pc3_var, 1)

        # print the explained variability
        if pc_total_val >= 70:
            self.args.log.write(f"\no GOOD. {pc_total_val} % explained variability. (PC1 {pc1_var} %, PC2 {pc2_var} %, PC3 {pc3_var} %)")
        else:
            self.args.log.write(f"\nx POOR. {pc_total_val} % explained variability might not be high enough. (PC1 {pc1_var} %, PC2 {pc2_var} %, PC3 {pc3_var} %)")
            
        # copy df, we add column with cluster for each molecule and additionally we map with symbol our points choosed
        df_pca = descp_df.copy()
        df_pca['Cluster'] = kmeans.labels_.astype(int)
        df_pca['Point selected'] = 0
        df_pca.loc[points, 'Point selected'] = 1

        # df prepared with PC and cluster labels for each molecule
        pcaModel.results['PC']
        df_pca = pcaModel.results['PC'].join([df_pca['Cluster'], df_pca['Point selected']]) 
        
        # build and save a results DataFrame with SMILES, code_name, Cluster and PCs
        if self.args.aqme:
            results_df = descp_df[['SMILES', 'code_name']].copy()
        else:
            results_df = descp_df[[self.args.name]].copy()
        results_df['Cluster'] = kmeans.labels_.astype(int)
        results_df['Point selected'] = 0
        results_df.loc[points, 'Point selected'] = 1
        results_df[['PC1','PC2','PC3']] = pcaModel.results['PC'][['PC1','PC2','PC3']]
        results_df.to_csv('batch_0/clustering_results.csv', index=False)
        self.args.log.write("\no Complete clustering results (with cluster number, selected and unselected molecules, and PC coordinates) save as batch_0/clustering_results.csv")
        
        return self, pc_total_val, pc1_var, pc2_var, pc3_var, df_pca
      
    def pca_control(self,df_pca, pc_total_val, pc1_var, pc2_var, pc3_var):
        '''
        provide and save the representation of the PCA in 3D
        '''        
        
        # prepare 2 dataframes for not selected and selected, we want to put dif sizes and we need 2 grap and then combine them
        df_unselected = df_pca[df_pca['Point selected'] == 0]
        df_selected = df_pca[df_pca['Point selected'] == 1]

        # scatter of biplot for cluster
        # grap selected
        fig_selected = px.scatter_3d(df_selected, x='PC1', y='PC2', z='PC3', color='Cluster', symbol='Point selected', symbol_sequence=['circle'])
        fig_selected.update_traces(marker=dict(size=7))  

        # grap no selected
        fig_unselected = px.scatter_3d(df_unselected, x='PC1', y='PC2', z='PC3', color='Cluster', symbol='Point selected', symbol_sequence=['cross'])
        fig_unselected.update_traces(marker=dict(size=3)) 

        # combine grap for selected and not selected
        fig = fig_selected.add_traces(fig_unselected.data)
        fig = go.Figure(fig) 

        # defining the text for the legend
        if pc_total_val >= 70:
            text_legend = f"\n GOOD. {pc_total_val} % explained variability: PC1 {pc1_var} %, PC2 {pc2_var} %, PC3 {pc3_var} %"
        else:
            text_legend = f"\n POOR. {pc_total_val} % explained variability might not be high enough: PC1 {pc1_var} %, PC2 {pc2_var} %, PC3 {pc3_var} %"

        fig.update_layout(
            legend = dict(yanchor = 'top',xanchor = 'left'),
            legend1 = dict(yanchor = 'top',xanchor = 'right'))
        fig.add_annotation(text = text_legend, 
                        xref = 'paper', yref = 'paper', 
                        x = 0.5, y = -0.1, showarrow = False)
        
        fig.write_html('batch_0/pca_3d.html') 

        self.args.log.write(f"\no The 3D representation of the PCA has been save as batch_0/pca_3d.html")


