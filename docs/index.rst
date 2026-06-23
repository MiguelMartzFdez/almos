.. |almos_banner| image:: ../almos/icons/almos_logo.png

|almos_banner|

.. include:: README.rst
   :start-after: badges-start
   :end-before: badges-end

.. _github: https://github.com/MiguelMartzFdez/almos

.. include:: README.rst
   :start-after: checkboxes-start
   :end-before: checkboxes-end

================
Welcome to ALMOS
================

.. include:: README.rst
   :start-after: introduction-start
   :end-before: introduction-end

Quick Start
-----------

If you are new to ALMOS, the shortest route is usually:

1. Install the conda environment from ``almos.yaml``.
2. Use ``cluster`` to generate or evaluate ``batch = 0``.
3. Use ``al`` to run the next active learning cycle.
4. Use ``easyalmos`` if you prefer the GUI.

Typical commands:

.. code-block:: shell

   curl -L -o almos.yaml https://raw.githubusercontent.com/MiguelMartzFdez/almos/master/install/almos.yaml
   conda env create -f almos.yaml
   conda activate almos
   cluster --input EXAMPLE.csv --name Name
   al --csv_name A_b0.csv --name Name --y target --n_exps 10

Start here:

* [Install ALMOS](Install/installation.html)
* [Use CLUSTER](Modules/cluster.html)
* [Use Active Learning](Modules/al.html)
* [Launch easyALMOS](Install/gui.html)


.. toctree::
   :maxdepth: 1
   :caption: Installation and interface

   Install/installation
   Install/note
   Install/gui

.. toctree::
   :maxdepth: 1
   :caption: How does ALMOS work?
   
   Modules/cluster
   Modules/al


.. include:: README.rst
   :start-after: reference-start
   :end-before: reference-end


.. .. toctree::
..    :maxdepth: 2
..    :caption: Examples

..    Examples/full_workflow/full_workflow
..    Examples/full_workflow/full_workflow_test
..    Examples/full_workflow/smiles_workflow
..    Examples/full_workflow/smiles_vaskas
..    Examples/modules/modules

.. .. toctree:: 
..    :maxdepth: 1
..    :caption: Video Tutorials

..    Videos/video_tutorials

.. toctree:: 
   :maxdepth: 1
   :caption: Technical Details

   Technical/defaults
   Technical/requirements
   Technical/tests
   Technical/development

.. toctree:: 
   :caption: API Reference
   :maxdepth: 1

   API/API_Reference.rst

.. toctree::
   :maxdepth: 2
   :caption: Misc

   Misc/abbreviations
   Misc/versions
   Misc/license
   Misc/help
