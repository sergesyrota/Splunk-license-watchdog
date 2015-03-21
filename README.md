# Splunk License Watchdog

Monitors your Splunk license usage, and delays indexing to the next day by disabling inputs to avoid license warning. Kind of license usage smoothing.

# Configuration

This is a one-file script written in Python, so all configuration is encapsulated at the top of the file as standard Python variables. You'll need to adjust the values to fit your environment accordingly.

#### _splunkUser, _splunkPass

User name and password for your Splunk cluster that would be able to view licensing info, view inputs, and disable/enable them. This needs to be configured before any helper functions can be used with this script.

#### _licenseServer

Protocol, hostname, and port of your licensing server for REST API access where usage details can be retreived. To test and make sure you're providing the right host, you can use `-c` or `--check-license` argument, and supply your host. If quota and today's usage matches your Splunk license monitor, then you got it.

#### _inputList

List of full input URLs that should be disabled by this script when we're approaching license quota threshold, and enabled the next day. This can have as many inputs as you need, and you're not limited to one server. As long as user name and password works, you can supply inputs on multiple nodes in your cluster.

After configuring user and password, you can use `-d` or `--discover-inputs` command to see all available inputs on the server. When you decide to add one to the list - just copy full URL as you see in the discover output and paste it as another element in the list. Consider your highest volume sources first, and then go down from there. I wouldn't recommend disabling any internal indexers and things that are absolutely critical to have real time even when you're approaching license limit. You also need to consider possible data loss (desired or not). If you disable file input, and this file gets rotated before you enable input again, all events after cut-off will be lost. If you re-enable before file is rotated - Splunk will catch up. If you're disabling UDP inputs - all data will be lost while it is disabled. If you're using Splunk forwarders on TCP input - they have their own cache, so once you enable your input port, Splunk will catch up.

#### _disableThreshold

#### _enableThreshold