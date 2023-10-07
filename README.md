# Remote Host Uptime Tool

Tool to check if hosts on Linode and DreamHost are currently up and accessible and if docker containers running on those hosts are accessible

# Usage

This tool can be run from the command line or used in a script. Option 2 should be run first (and perhaps on occasion to update hosts) to generate a list of hosts from Linode and then options 1, 3, or 13 can be run at user discretion. A Bearer token for the Linode API is required and an API key is required for DreamHost.