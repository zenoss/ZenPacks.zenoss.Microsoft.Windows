##############################################################################
#
# Copyright (C) Zenoss, Inc. 2015, all rights reserved.
#
# This content is made available according to terms specified in
# License.zenoss under the directory where your Zenoss product is installed.
#
##############################################################################

import os
import pickle


class StringAttributeObject(dict):
    def __setattr__(self, k, v):
        self.__setitem__(k, v)

    def __getattr__(self, k):
        return self.get(k, str(k))


def load_pickle(self, filename):
    with open(os.path.join(
            os.path.dirname(__file__),
            'data',
            self.__class__.__name__,
            filename), 'rb') as f:
        return pickle.load(f)