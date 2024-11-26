 #!/usr/bin/env python

###############################################.
#          __main__ file for the code         #
###############################################.

from __future__ import absolute_import

import sys
from almos import almos

# If we are running from a wheel, add the wheel to sys.path
# This allows the usage python pip-*.whl/pip install pip-*.whl

if __package__ != 'almos':
    print('ALMOS is not installed! Use: pip install almos (anywhere, using a terminal) or python setup.py install (from the downloaded /almos/almos folder).')

if __name__ == '__main__':
    almos.main()
    sys.exit()