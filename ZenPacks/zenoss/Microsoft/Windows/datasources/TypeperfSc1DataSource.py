##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
A datasource that uses WinRS to run typeperf -sc1.

See Products.ZenModel.ZenPack._getClassesByPath() to understand how this class
gets discovered as a datasource type in Zenoss.
"""

from ..monitor import \
    SingleCounterDataSource, TYPEPERFSC1_SOURCETYPE, ZENPACKID


class TypeperfSc1DataSource(SingleCounterDataSource):
    """
    Datasource used to capture datapoints from winrs typeperf -sc1.
    """

    sourcetypes = (TYPEPERFSC1_SOURCETYPE,)
    sourcetype = sourcetypes[0]
    plugin_classname = ZENPACKID + '.monitor.TypeperfSc1Plugin'
