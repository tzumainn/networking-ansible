# This is a work around for neutron 16.x importing from mock
# when neutron 17 is tagged it will import from unittest properly
# at that point this can be deleted
from unittest.mock import *  # noqa
