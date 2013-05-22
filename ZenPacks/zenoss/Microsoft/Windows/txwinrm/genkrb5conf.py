##############################################################################
#
# Copyright (C) Zenoss, Inc. 2013, all rights reserved.
#
# This content is made available according to terms specified in the LICENSE
# file at the top-level directory of this package.
#
##############################################################################

import sys
import socket
import uuid
from argparse import ArgumentParser

TEMPLATE = """
[logging]
 default = FILE:/var/log/krb5libs.log
 kdc = FILE:/var/log/krb5kdc.log
 admin_server = FILE:/var/log/kadmind.log

[libdefaults]
 default_realm = {realm}
 dns_lookup_realm = false
 dns_lookup_kdc = false
 ticket_lifetime = 24h
 renew_lifetime = 7d
 forwardable = true

[realms]
 {realm} = {{
  kdc = {domain_controller_ip}
  admin_server = {domain_controller_ip}
 }}

[domain_realm]
 .{domain} = {realm}
 {domain} = {realm}
"""


def _parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        "domain",
        help="The name of the Windows domain")
    parser.add_argument(
        "domain_controller_ip",
        help="The IP address of the Domain Controller")
    parser.add_argument(
        "--output", "-o",
        default="/etc/krb5.conf",
        help="Path to the krb5.conf file")
    return parser.parse_args()


def main():
    args = _parse_args()
    try:
        socket.inet_aton(args.domain_controller_ip)
    except socket.error:
        print >>sys.stderr, "ERROR: {0} is not a valid IP address".format(
            args.domain_controller_ip)
    existing_content = None
    try:
        with open(args.output) as f:
            existing_content = f.read()
    except IOError:
        pass
    if existing_content is not None:
        backup_file = '{0}-genkrb5conf-{1}'.format(args.output, uuid.uuid4())
        with open(backup_file, 'w') as f:
            f.write(existing_content)
    with open(args.output, 'w') as f:
        f.write(TEMPLATE.format(
            domain=args.domain.lower(),
            realm=args.domain.upper(),
            domain_controller_ip=args.domain_controller_ip))


if __name__ == '__main__':
    main()
