##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################
from . import schema
from utils import get_rrd_path


class WinIIS(schema.WinIIS):
    '''
    Model class for WinIIS.
    '''
    # preserve the old style path
    rrdPath = get_rrd_path
