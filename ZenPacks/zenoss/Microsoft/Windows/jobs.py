##############################################################################
#
# Copyright (C) Zenoss, Inc. 2016, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

"""
Zenpack's jobs.
"""

from Products.Jobber.jobs import Job


class ReindexWinServices(Job):

    """Job for reindexing affected Windows services components when related
    datasource was updated.
    """

    @classmethod
    def getJobType(cls):
        return "Reindex Windows services"

    @classmethod
    def getJobDescription(cls, *args, **kwargs):
        return "Reindex Windows services linked to {uid} template".format(**kwargs)

    def _run(self, uid, **kwargs):
        template = self.dmd.unrestrictedTraverse(uid)

        for service in template.getAffectedServices():
            service.index_object()
