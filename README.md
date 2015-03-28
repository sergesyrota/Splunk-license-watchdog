# Splunk License Watchdog

Monitors your Splunk license usage, and delays indexing to the next day by disabling inputs to avoid license warning. Kind of license usage smoothing. Works well if you have unexpected spikes here and there, but your average usage is below the quota. Also assumes that you can afford a period of stale data in Splunk when approaching end of day.

# Configuration

This is a one-file script written in Python, so all configuration is encapsulated at the top of the file as standard Python variables. You'll need to adjust the values to fit your environment accordingly.

#### _splunkUser, _splunkPass

User name and password for your Splunk cluster that would be able to view licensing info, view inputs, and disable/enable them. This needs to be configured before any helper functions can be used with this script.

#### _licenseServer

Protocol, hostname, and port of your licensing server for REST API access where usage details can be retrieved. To test and make sure you're providing the right host, you can use `-c` or `--check-license` argument, and supply your host. If quota and today's usage matches your Splunk license monitor, then you got it.

#### _inputList

List of full input URLs that should be disabled by this script when we're approaching license quota threshold, and enabled the next day. This can have as many inputs as you need, and you're not limited to one server. As long as user name and password works, you can supply inputs on multiple nodes in your cluster.

After configuring user and password, you can use `-d` or `--discover-inputs` command to see all available inputs on the server. When you decide to add one to the list - just copy full URL as you see in the discover output and paste it as another element in the list. Consider your highest volume sources first, and then go down from there. I wouldn't recommend disabling any internal indexers and things that are absolutely critical to have real time even when you're approaching license limit. You also need to consider possible data loss (desired or not). If you disable file input, and this file gets rotated before you enable input again, all events after cut-off will be lost. If you re-enable before file is rotated - Splunk will catch up. If you're disabling UDP inputs - all data will be lost while it is disabled. If you're using Splunk forwarders on TCP input - they have their own cache, so once you enable your input port, Splunk will catch up.

#### _disableThreshold, _enableThreshold

Action threshold. When current usage crosses `_disableThreshold`, listed inputs will be disabled. When today's usage will be under `_enableThreshold` - we're assuming new day has started, and inputs will be enabled. If 100% has been crossed, all inputs will be enabled to catch up ASAP, as you're already getting a license warning.

When setting thresholds, you need to consider a few things. 

###### Frequency of checks

1% of the day is ~15 minutes, if your input volume is on pace to hit exactly 100% by the end of the day. If, on the other hand, you're on pace to get 125% of the indexing volume, your 1% is now ~12 minutes (as suddenly you have 125% in the day, not 100%). Your check interval should be shorter than the amount of quota you can consume in between checks pushing you over the allocation (including spikes). E.g. if you set threshold to 99%, you have 1% of margin. If you suspect you will not go over more than a few percent over your quota, then 15 minute interval is the longest possible. But it's best to give you additional margin of error.

###### Schedule

If you're not enabling checks 24x7 (although load on Splunk is extremely minimal, so you might as well), you need to follow 2 things: start checking before there is a possibility to go over your quota; do at least one check immediately after new day starts (better 2, just in case) to re-enable any inputs that have been disabled.

###### Inputs that have not been disabled

When making assumptions and setting schedules, consider inputs that you will not have disabled. If there are critical pieces that will continue indexing after you disable part of the inputs, you need to have enough quota left to run them until the end of the day. I do not disable any internal inputs, but just disable one or two of the biggest sources of data, and continue with everything else. Give yourself extra margin of error, if you're not sure how exactly it'll play out, and adjust as necessary.

###### Rollover from previous date

If you're approaching quota, and disable inputs, the volume of data will be added to the next day (unless it's UDP input, or rotating file, in which case it'll just be discarded). This needs to be taken into account when you're determining schedule and frequency of checks. One safeguard that is built in, it will keep inputs enabled if schedule was not set up to catch this in time, and you go over the limit. This would lead to catching up on everything, and hopefully having only one warning.

# Installation

Here's what you need to do to set it up:

* Download latest version: `wget https://raw.githubusercontent.com/sergesyrota/Splunk-license-watchdog/master/splunk-license-watchdog.py`
* Update top of the file with proper configuration (see configuration section, and command line arguments for help with that: `./splunk-license-watchdog.py --help`)
* Update permission to execute it: `chmod +x ./splunk-license-watchdog.py`
* Add it to cron on a desired schedule (e.g. `*/10 * * * * /path/to/splunk-license-watchdog.py`)
