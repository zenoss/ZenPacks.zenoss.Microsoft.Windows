##############################################################################
#
# Copyright (C) Zenoss, Inc. 2012, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

from Products.Zuul.form import schema
from Products.Zuul.interfaces.component import IComponentInfo

from Products.Zuul.utils import ZuulMessageFactory as _t


class IWinComponentInfo(IComponentInfo):
    title = schema.TextLine(title=_t(u'Title'), readonly=True)


class IWinServiceInfo(IWinComponentInfo):
    servicename = schema.TextLine(title=_t(u'Service Name'), readonly=True)
    caption = schema.TextLine(title=_t(u'Caption'), readonly=True)
    description = schema.TextLine(title=_t(u'Description'), readonly=True)
    startmode = schema.TextLine(title=_t(u'Start Mode'), readonly=True)
    account = schema.TextLine(title=_t(u'Account'), readonly=True)
    state = schema.TextLine(title=_t(u'Current State'), readonly=True)


class IWinProcInfo(IWinComponentInfo):
    caption = schema.TextLine(title=_t(u'Caption'), readonly=True)
    numbercore = schema.TextLine(title=_t(u'Number of Core'), readonly=True)
    status = schema.TextLine(title=_t(u'Status'), readonly=True)
    architecture = schema.TextLine(title=_t(u'Architecture'), readonly=True)
    clockspeed = schema.TextLine(title=_t(u'Clock Speed'), readonly=True)
