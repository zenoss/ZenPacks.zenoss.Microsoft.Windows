##
# Copyright (c) 2006-2008 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from setuptools import setup, Extension
import subprocess
import sys

long_description = """
This Python package is a high-level wrapper for Kerberos (GSSAPI) operations.
The goal is to avoid having to build a module that wraps the entire Kerberos.framework,
and instead offer a limited set of functions that do what is needed for client/server
Kerberos authentication based on <http://www.ietf.org/rfc/rfc4559.txt>.

"""

# Backport from Python 2.7 in case we're in 2.6.
def check_output(*popenargs, **kwargs):
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        raise subprocess.CalledProcessError(retcode, cmd, output=output)
    return output

def check_krb5_version():
    krb5_vers = check_output(["krb5-config", "--version"], universal_newlines=True).split()
    if len(krb5_vers) == 4:
        if int(krb5_vers[3].split('.')[1]) >= 10:
            return r'-DGSSAPI_EXT'

extra_link_args = check_output(
    ["krb5-config", "--libs", "gssapi"],
    universal_newlines=True
).split()

extra_compile_args = check_output(
    ["krb5-config", "--cflags", "gssapi"],
    universal_newlines=True
).split()

krb5_ver = check_krb5_version()
if krb5_ver:
    extra_compile_args.append(krb5_ver)

setup (
    name = "pykerberos",
    version = "1.1.6",
    description = "High-level interface to Kerberos",
    long_description=long_description,
    license="ASL 2.0",
    classifiers = [
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Systems Administration :: Authentication/Directory"
        ],
    ext_modules = [
        Extension(
            "kerberos",
            extra_link_args = extra_link_args,
            extra_compile_args = extra_compile_args,
            sources = [
                "src/kerberos.c",
                "src/kerberosbasic.c",
                "src/kerberosgss.c",
                "src/kerberospw.c",
                "src/base64.c"
            ],
        ),
    ],
)
