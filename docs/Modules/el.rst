.. el-modules-start

Data curation
-------------

Overview of the CURATE module
+++++++++++++++++++++++++++++

.. |curate_fig| image:: images/CURATE.jpg
   :width: 800

.. centered:: |curate_fig|

Input required
++++++++++++++

This module uses a CSV containing the initial database.

Automated protocols
+++++++++++++++++++

*  Filters off correlated descriptors (with R\ :sup:`2` higher than 0.7).
*  Filters off variables with very low correlation to the target values (noise, with R\ :sup:`2` lower than 0.001). (Disabled by default)
*  Filters off duplicates.
*  Converts categorical descriptors into one-hot or numerical descriptors.
*  At the end of the curation process, the program uses scikit-learn’s RFECV with repeated K-fold cross-validation to select the most relevant descriptors. The selection can average importances across multiple models (e.g., RF, GB, ADAB) and ensures that the number of descriptors is reduced to one third of the datapoints.

Technical information
+++++++++++++++++++++

The CURATE module offers features to improve data quality. These include the removal of correlated variables, noise, and duplicated entries. These options are activated by default to reduce the complexity of the resulting predictors, 
and users can set specific thresholds for the correlation and noise filters using the "thres_x" and "thres_y" parameters. Additionally, the module facilitates the conversion of categorical data, transforming columns containing categorical variables into 
numerical or one-hot encoding values. For example, consider a variable that represents four types of carbon atoms (e.g., primary, secondary, tertiary, quaternary). This variable can be converted using the "categorical" command, offering the following options:

*	“Numbers”: It assigns numerical values (e.g., 1, 2, 3, 4) to describe the different C atom types.
*	“Onehot”: It creates a separate descriptor for each C atom type using 0s and 1s to indicate their presence.

Example
+++++++

An example is available in **Examples/Use of individual modules**.

.. el-modules-end
