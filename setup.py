################################
# These variables are overwritten by Zenoss when the ZenPack is exported
# or saved.  Do not modify them directly here.
# NB: PACKAGES is deprecated
NAME = "ZenPacks.zenoss.Microsoft.Windows"
VERSION = "2.5.4dev"
AUTHOR = "Zenoss"
LICENSE = ""
NAMESPACE_PACKAGES = ['ZenPacks', 'ZenPacks.zenoss', 'ZenPacks.zenoss.Microsoft']
PACKAGES = ['ZenPacks', 'ZenPacks.zenoss', 'ZenPacks.zenoss.Microsoft', 'ZenPacks.zenoss.Microsoft.Windows']
INSTALL_REQUIRES = ['ZenPacks.zenoss.PythonCollector>=1.4']
COMPAT_ZENOSS_VERS = ">=4.2"
PREV_ZENPACK_NAME = ""
# STOP_REPLACEMENTS
################################
# Zenoss will not overwrite any changes you make below here.

import os
import subprocess
import sys

from setuptools import setup, find_packages


if os.path.isfile('GNUmakefile'):
    make_target = None
    if 'bdist_egg' in sys.argv:
        make_target = 'egg-dependencies'
    elif 'develop' in sys.argv:
        make_target = 'develop-dependencies'

    if make_target:
        try:
            subprocess.check_output('make {}'.format(make_target), shell=True)
        except subprocess.CalledProcessError as e:
            print e.output
            raise

setup(
    # This ZenPack metadata should usually be edited with the Zenoss
    # ZenPack edit page.  Whenever the edit page is submitted it will
    # overwrite the values below (the ones it knows about) with new values.
    name=NAME,
    version=VERSION,
    author=AUTHOR,
    license=LICENSE,

    # This is the version spec which indicates what versions of Zenoss
    # this ZenPack is compatible with
    compatZenossVers=COMPAT_ZENOSS_VERS,

    # previousZenPackName is a facility for telling Zenoss that the name
    # of this ZenPack has changed.  If no ZenPack with the current name is
    # installed then a zenpack of this name if installed will be upgraded.
    prevZenPackName=PREV_ZENPACK_NAME,

    # Indicate to setuptools which namespace packages the zenpack
    # participates in
    namespace_packages=NAMESPACE_PACKAGES,

    # Tell setuptools what packages this zenpack provides.
    packages=find_packages(),

    # Tell setuptools to figure out for itself which files to include
    # in the binary egg when it is built.
    include_package_data=True,

    # Tell setuptools what non-python files should also be included
    # with the binary egg.
    #package_data = {}

    # Indicate dependencies on other python modules or ZenPacks.  This line
    # is modified by zenoss when the ZenPack edit page is submitted.  Zenoss
    # tries to put add/delete the names it manages at the beginning of this
    # list, so any manual additions should be added to the end.  Things will
    # go poorly if this line is broken into multiple lines or modified to
    # dramatically.
    install_requires=INSTALL_REQUIRES,

    # Every ZenPack egg must define exactly one zenoss.zenpacks entry point
    # of this form.
    entry_points={
        'zenoss.zenpacks': '%s = %s' % (NAME, NAME),
    },

    # All ZenPack eggs must be installed in unzipped form.
    zip_safe=False,
)
