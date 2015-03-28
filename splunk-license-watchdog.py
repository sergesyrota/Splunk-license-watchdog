#!/usr/bin/env python

##################
#
# DEPENDENCIES
# 
# Python 2.6+
# Python packages: sys, getopt, requests, time
# Splunk: 4.2+
#
##################
from __future__ import print_function

#
# CONFIGURATION
#

# Authentication information for your Splunk setup
_splunkUser = "user"
_splunkPass = "pass"

# host and port for Splunk server that has license pool info
_licensingServer = "https://splunk.example.com:8089"

# List of inputs that can be disabled or enabled
# You can get a list by a helpful --discover-inputs=<host> flag
# Update inputList by creating a list with all inputs that should be toggled
# Note that you can include multiple hosts, if youhave multiple indexing heads in the same cluster
# Example: inputList = ['https://example.com:8089/servicesNS/nobody/launcher/data/inputs/tcp/cooked/9997', 
#                       'https://node2.example.com:8089/servicesNS/nobody/system/data/inputs/monitor/%24SPLUNK_HOME%252Fetc%252Fsplunk.version']
_inputList = []

# Action threshold. When current usage crosses _disableThreshold, listed inputs will be disabled.
# When today's usage will be under _enableThreshold - we're assuming new day has started, and inputs will be enabled
# Consider that 1% is ~15 minutes. Set threshold and schedules accordingly.
# Also make sure that script runs before the time you might run out of quota
_disableThreshold = 90
_enableThreshold = 30

#
# END CONFIGURATION
#
# If you change anything below, make sure you know what you're doing :)
#

# Default debug level
# 0 = Fatal errors (stderr) and action information (-q)
# 1 = Informational messages on steps and statuses
# 2 = Verbose output, with splunk responses (-v)
_debugLevel = 1

licensePoolQuery = '| rest /services/licenser/pools | rename title AS Pool | search [rest /services/licenser/groups | search is_active=1 | eval stack_id=stack_ids | fields stack_id] | eval quota=if(isnull(effective_quota),quota,effective_quota) | eval "Used"=round(used_bytes/1024/1024/1024, 3) | eval "Quota"=round(quota/1024/1024/1024, 3) | fields Pool "Used" "Quota"'

import sys
import getopt
import time
import requests
# Suppressing "InsecureRequestWarning" due to self-signed certificate on Splunk servers
requests.packages.urllib3.disable_warnings()

def main(argv):
    # at a minimum, auth token should be set, so let's check it right away
    if _splunkUser == "user" and _splunkPass == "pass":
        debugPrint("Please update user and password to access your Splunk instance and run this script", 0)
        showHelp()
        sys.exit(1)

    try:
        opts, args = getopt.getopt(argv, "hc:d:vqED", ["help", "check-license=", "discover-inputs=", "enable-all", "disable-all"])
    except getopt.GetoptError:
        showHelp()
        sys.exit(2)
    # First go through non-action arguments and adjust environment variables, before performing actions that will lead to exit.
    global _debugLevel
    for opt, arg in opts:
        if opt in ('-v'):
            _debugLevel = 2
        if opt in ('-q'):
            _debugLevel = 0

    # Separate loop for actions that result in exit
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            showHelp()
            sys.exit(0)
        if opt in ("-c", "--check-license"):
            checkLicense(arg)
            sys.exit(0)
        if opt in ("-d", "--discover-inputs"):
            discoverInputs(arg)
            sys.exit(0)
        if opt in ("-E", "--enable-all"):
            enableInputs()
            sys.exit(0)
        if opt in ("-D", "--disable-all"):
            disableInputs()
            sys.exit(0)

    # Validate that we have needed configuration
    if len(_inputList) == 0:
        exit("Please adjust the script with your configuration first. Input list is missing.")
    # High level sequence:
    # Get license details
    # If we're over our license quota - enable all inputs. Might as well catch up today, since we'll have a warning anyways.
    # If usage is under "enable" threshold: enable all disabled inputs
    # If usage is over "disable" threshold: disable all enabled inputs
    usage = getLicenseData(_licensingServer)
    debugPrint("Quota: %0.3f; Used: %0.3f (%0.1f%%)" % (usage['Quota'], usage['Used'], usage['PercentUsed']), 1)
    if usage['PercentUsed'] > 100:
        debugPrint("We're over the quota for today! Enabling all disabled inputs to catch up as much as we can:", 1)
        enableInputs()
    elif usage['PercentUsed'] < _enableThreshold:
        debugPrint("Usage is under threshold; Enabling all disabled inputs:", 1)
        enableInputs()
    elif usage['PercentUsed'] > _disableThreshold:
        debugPrint("Usage is over threshold; Disabling all enabled inputs:", 1)
        disableInputs()
    sys.exit(0)

def disableInputs():
    toggleInputs(False)

def enableInputs():
    toggleInputs(True)

def toggleInputs(enable):
    # Set variables so that we can use unified piece of code to toggle inputs
    if enable:
        commandSuffix = '/enable'
        messageText = 'enabled'
        disabledFlag = False
    else:
        commandSuffix = '/disable'
        messageText = 'disabled'
        disabledFlag = True
    # Take care of all inputs, and make sure they are not in desired state before requesting a change (and also checking that inputs actually exist)
    try:
        for inputUrl in _inputList:
            inputData = splunkRestRequest(inputUrl + '?output_mode=json')
            if inputData['entry'][0]['content']['disabled'] == disabledFlag:
                debugPrint("Already %s: %s" % (messageText, inputUrl), 2)
            else:
                # Changing status requires POST
                r = splunkRestRequest(inputUrl + commandSuffix, {'output_mode': 'json'})
                # Messages = possible problems. Need to verify
                for message in r['messages']:
                    if message['type'] == 'ERROR':
                        exit("Error toggling input state: " + message['text'])
                # Verify that status is correct now:
                if r['entry'][0]['content']['disabled'] != disabledFlag:
                    exit("Error toggling input: %s; Request OK, but input not %s." % (inputUrl, messageText))
                debugPrint("%s: %s" % (messageText, inputUrl), 1)
    except IndexError as e:
        exit("ERROR wotking with Splunk input toggles; unexpected data: %s" % str(e))
    except KeyError as e:
        exit("ERROR wotking with Splunk input toggles; unexpected data; key %s does not exist " % str(e))

# Helper function to use during setup. Just displays aggregated license quota and today's usage
def checkLicense(host):
    debugPrint("Checking license info on " + host, 0)
    data = getLicenseData(host)
    debugPrint("Licensing quota: %0.3f GiB" % data['Quota'], 0)
    debugPrint("Used today: %0.3f GiB (%0.1f%%)" % (data['Used'], data['PercentUsed']), 0)

# Helper function to use during setup. Just shows all inputs found on Splunk host (indexing head)
def discoverInputs(host):
    debugPrint("Discovering inputs at " + host, 0)
    data = splunkRestRequest(host + '/servicesNS/' + _splunkUser + '/launcher/data/inputs/all?output_mode=json')
    for entry in data['entry']:
        # entry will have links. We're interested in seeing ones we can disable and enable, so those are the links we're checking to validate (and skipping the rest)
        # then grab entry link itself from "alternate" (so that we can add /disable or /enable later)
        if 'enable' in entry['links'] or 'disable' in entry['links']:
            status = "Unknown: "
            if entry['content']['disabled']:
                status = "Disabled: "
            else:
                status = "Enabled: "
            debugPrint(status + host + entry['links']['alternate'], 0)
    debugPrint("""
Review links above. Identify which ones you want to disable when you are approaching 
license limit, then update top of the file by copying them in there.

Generally, you don't want to disable any internal indexing. You also need to consider if 
data loss is what you can tollerate or want to achieve (e.g. disabling file input past its 
rotation schedule will lead to loss of data between disabling and enabling). If you're 
using Splunk forwarders, though, they have their own cache, so disabling tcp input they 
pipe to should be safe.""", 0)

# Runs Splunk query to get license pool information, and aggregate results, presenting only usage/quota information
def getLicenseData(host):
    data = splunkQuery(host, licensePoolQuery)
    try:
        used = float(data['result']['Used'])
        quota = float(data['result']['Quota'])
        if used < 0 or quota <= 0:
            exit("Error getting license data. Invalid response received: %s" % data)
        return {'Quota': quota, 'Used': used, 'PercentUsed': 100*used/quota}
    except KeyError:
        exit("Error getting license data. Invalid response received: %s" % data)

# Generic function to run splunk query on a given node, and parse our JSON response
def splunkQuery(host, query):
    debugPrint("Running Splunk query: '%s' on host '%s'" % (query, host), 2)
    payload = {'search': query, 'output_mode': 'json', 'exec_mode': 'oneshot'}
    return splunkRestRequest(host + '/servicesNS/' + _splunkUser + '/search/search/jobs/export/', payload)

# Data format is always expected to be JSON, so need to make sure it's either in URL explicitly, or in post data when this function is used
def splunkRestRequest(url, postData=None):
    try:
        # No post means we're making a GET request
        if postData is None:
            r = requests.get(url, auth=(_splunkUser, _splunkPass), verify=False)
            debugPrint(r.text, 2)
            return r.json()
        else:
            r = requests.post(url, postData, auth=(_splunkUser, _splunkPass), verify=False)
            debugPrint(r.text, 2)
            return r.json()
    except requests.exceptions.RequestException as e:
        exit("ERROR communicating with Splunk server (%s): %s", (url, str(e)))

def showHelp():
    print("""
USAGE: splunk-license-monitor.py [options...]
Running without arguments would execute logic. Helper commands can help with config, but require
authentication variables to be set in the file.

  -c/--check-license <url> Attempts to retrieve license information from provided
                    Splunk node (Requires auth info) protocol://host:port resuired, e.g.:
                    https://your.server.com:8089
  -d/--discover-inputs <url> Discovers all inputs and current states
                    from provided Splunk node (requires auth parameters to be configured)
                    protocol://host:port resuired, e.g.:
                    https://your.server.com:8089
  -D/--disable-all     Disable all inputs that have been configured
  -E/--enable-all      Enable all inputs that have been configured
  -h/--help         This help text
  -q                Quiet mode (errors only)
  -v                Verbose output (including Splunk queries
""")

def debugPrint(message, level):
    if _debugLevel >= level:
        print("%s - %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))

def exit(message, retval=1):
    print(message, file=sys.stderr)
    sys.exit(retval)

main(sys.argv[1:])
