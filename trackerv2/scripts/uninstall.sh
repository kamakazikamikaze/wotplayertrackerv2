#!/bin/bash

if [ "$EUID" -ne 0 ]
	then echo "Please run with 'sudo'"
	exit
fi

if [ $# -ne 1 ]
then
	echo "Usage: $0 {server|client}"
	exit 1
fi

## Exit on errors
set -e

## Global variables
uninstalling=$(echo $1 | tr '[:upper:]' '[:lower:]')

if [ $installing != "server" ] && [ $installing != "client" ]
then
	echo "Usage: $0 {server|client}"
	exit 1
fi

username=wot$uninstalling

if [[ $(uname -s) = "Darwin"* ]]; then
	## Variables
	username=_$username
	group=$username
	homedir=/Users/$username
	# cronfile=/Library/LaunchDaemons/com.wot.tracker.plist
	cronfile=/usr/lib/cron/tabs/$username

	## Remove user
	dscl . -delete /Users/$username
	dscl . -delete /Groups/$group

	## Remove home directory, python, files
	rm -rf $homedir

	## Remove cron job
	# launchctl unload $cronfile
	rm -f $cronfile

	## Remove firewall exception
	# We'll leave this for the user to clean up. Sorry guys and gals!

else
	## Variables
	homedir=$(grep $username /etc/passwd | cut -d: -f6)
	cronfile=/etc/cron.d/$username

	## Remove user
	userdel $username

	## Remove home directory, python, files
	rm -rf $homedir

	## Remove cron job
	rm $cronfile

	## Remove firewall exception
	# We'll leave this for the user to clean up. Sorry guys and gals!
fi