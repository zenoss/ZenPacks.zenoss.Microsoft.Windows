##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016-2017, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from . import schema
from Products import Zuul
from zenoss.protocols.protobufs.zep_pb2 import (
    STATUS_NEW, STATUS_ACKNOWLEDGED,
    SEVERITY_CLEAR, SEVERITY_CRITICAL, SEVERITY_ERROR,
    SEVERITY_INFO, SEVERITY_WARNING
)


class WinSQLDatabase(schema.WinSQLDatabase):
    """
    Base class for WinSQLDatabase classes.

    """

    def getDBStatus(self):
        """Return database state"""
        status = 'Unknown'
        if not self.monitored():
            return status
        instance = getattr(self, 'winsqlinstance', None)
        if instance and instance().getStatus():
            return status

        zep = Zuul.getFacade("zep", self.dmd)
        try:
            event_filter = zep.createEventFilter(
                tags=[self.getUUID()],
                status=[STATUS_NEW, STATUS_ACKNOWLEDGED],
                severity=[SEVERITY_CLEAR, SEVERITY_CRITICAL, SEVERITY_ERROR,
                          SEVERITY_INFO, SEVERITY_WARNING],
                event_class=filter(None, ['/Status/*']))

            status = 'Normal'
            summaries = zep.getEventSummariesGenerator(filter=event_filter)
            for summary in summaries:
                try:
                    occurrence = summary['occurrence'][0]
                except Exception:
                    continue
                else:
                    for detail in occurrence.get('details', []):
                        if detail.get('name', '') == 'dbstatus':
                            status = detail.get('value', ['Unknown'])[0]
        except Exception:
            pass

        return status

    def monitored(self):
        instance = getattr(self, 'winsqlinstance', None)
        if instance and not instance().monitored():
            return False
        return self.monitor
