#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
import subprocess
import re
import json
import pyjq
from pprint import pprint
from urllib.parse import urlparse

def nagios_exit(message, code):
    print(message)
    sys.exit(code)

severities = {
        'OK': 1,
        'INFO': 2,
        'LOW': 3,
        'MEDIUM': 4,
        'HIGH': 5,
        'CRITICAL': 6
        }
try:
    parser = argparse.ArgumentParser(description='Check output of testssl.sh')
    parser.add_argument('--uri', help='host|host:port|URL|URL:port.'
            'Port 443 is default, URL can only contain HTTPS protocol', required=True)
    parser.add_argument('--testssl', help='Path to the testssl.sh script', required=True)
    parser.add_argument('--critical', help='Findings of this severity level trigger a CRITICAL',
            choices=severities.keys(), default='CRITICAL')
    parser.add_argument('--warning', help='Findings of this severity level trigger a WARNING', 
            choices=severities.keys(), default='HIGH')
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if severities[args.critical] < severities[args.warning]:
        parser.error('The severity level to raise a WARNING must be less that the level to raise a CRITICAL')

    if urlparse(args.uri).scheme != 'https':
        parser.error('The scheme of the URI must be \'https\'')

    uri = args.uri
    testssl = args.testssl
    critical = args.critical
    warning = args.warning


    # start with clean slate
    ok_msg = []
    warn_msg = []
    crit_msg = []

    # Create temp file
    fd, temp_path = tempfile.mkstemp()

    # Set command and arguments
    subproc_args = [
        testssl,
        '--jsonfile-pretty',
        temp_path,
        uri
        ]

    # Inject this script's extra command line arguments before the 'uri' part of the testssl.sh command
    for extra in args.args:
        subproc_args.insert(3, extra)

    # Run it
    proc = subprocess.run(subproc_args, stdout=subprocess.PIPE)
    # pprint(proc.returncode)
    # pprint(proc)

    # temp_path = os.path.expanduser("~/careers.deloitte.ca_p443-20200325-1434.json")
    # temp_path = os.path.expanduser("~/www.geant.org_p443-20200325-1857.json")
    with open(temp_path) as f:
        json = json.load(f)
    os.close(fd)
    os.remove(temp_path)

    r = pyjq.all('.scanResult[] | .[]? []?', json)

    # Add integer severity level
    for item in r:
        item['severity_int'] = severities[item['severity']]


    def get_severity_count_aggregated(severity_int):
        return len([f for f in r if f['severity_int'] >= severity_int])

    def get_severity_items_aggregated(severity_int):
        _results = sorted([f for f in r if f['severity_int'] >= severity_int], key = lambda i: i['severity_int'], reverse=True)
        return list(map(lambda x: x['severity'] +  ": " + x['id'] + " (" + x['finding'] + ")", _results))

    # FIXME loop over these?
    if get_severity_count_aggregated(severities[critical]) > 0:
        crit_msg.append("{0} issues found for {1} with severity {2} or higher: {3}".format(
            get_severity_count_aggregated(severities[critical]),
            uri,
            critical,
            ', '.join(get_severity_items_aggregated(severities[critical])),

            ))
    if get_severity_count_aggregated(severities[warning]) > 0:
        warn_msg.append("{0} issues found for {1} with severity {2} or higher: {3}".format(
            get_severity_count_aggregated(severities[warning]),
            uri,
            warning,
            ', '.join(get_severity_items_aggregated(severities[warning])),
            ))
    else:
        # FIXME display number of lower severity issues? To show that things did run.
        ok_msg.append("No issues found with severity {0} or higher".format(warning))
except Exception as e:
    nagios_exit("UNKNOWN: Unknown error: {0}.".format(e), 3)

# Exit with accumulated message(s)
if crit_msg:
    nagios_exit("CRITICAL: " + ' '.join(crit_msg), 2)
elif warn_msg:
    nagios_exit("WARNING: " + ' '.join(warn_msg), 1)
else:
    nagios_exit("OK: " + ' '.join(ok_msg), 0)