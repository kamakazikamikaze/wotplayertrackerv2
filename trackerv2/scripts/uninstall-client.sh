#!/bin/bash

if [ "$EUID" -ne 0 ]
	then echo "Please run with 'sudo'"
	exit
fi

## Global variables
username=wotnode

if [[ $(uname -s) = "Darwin"* ]]; then
	## Variables
	username=_$username
	group=$username
	homedir=/Users/$username
	cronfile=/Library/LaunchDaemons/com.wot.tracker.plist

	## Remove user
	dscl . -delete /Users/$username
	dscl . -delete /Groups/$group

	## Remove cron job
	launchctl unload $cronfile

	## Remove firewall exception
	# We'll leave this for the user to clean up. Sorry guys and gals!

else
	## Variables
	homedir=$(grep $username /etc/passwd | cut -d: -f6)
	cronfile=/etc/cron.d/wottracker

	## Remove user
	userdel $username

	## Remove firewall exception
	# We'll leave this for the user to clean up. Sorry guys and gals!
fi

## Remove home directory, python, files
rm -rf $homedir

## Remove cron job
rm -f $cronfile