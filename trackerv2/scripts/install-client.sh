#!/bin/bash

if [ "$EUID" -ne 0 ]
	then echo "Please run with 'sudo'"
	exit
fi

## Global variables
pyversion=3.6.5
username=wotnode
pyurl=https://www.python.org/ftp/python/$pyversion/Python-$pyversion.tgz
pysha=12046118d20f9d2007dcc515b15adb4d28a0f7f7
shacmd=sha1sum
kernel=$(uname -s)

if [[ $kernel = "Darwin"* ]]
then
	## Variables
	username=_$username
	group=$username
	homedir=/Users/$username
	cronfile=/Library/LaunchDaemons/com.wot.tracker.plist
	download=curl
	umaxid=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -ug | tail -1)
	uid=$((umaxid+1))
	gmaxid=$(dscl . -list /Groups PrimaryGroupID | awk '{print $2}' | sort -ug | tail -1)
	gid=$((gmaxid+1))
	shacmd=shasum

	## Create user
	# Group
	dscl . -create /Groups/$group
	dscl . -create /Groups/$group PrimaryGroupID $gid
	# User
	dscl . -create /Users/$username UniqueID $uid
	dscl . -create /Users/$username PrimaryGroupID $gid
	dscl . -create /Users/$username UserShell /usr/bin/false
	# Home
	dscl . -create /Users/$username NFSHomeDirectory $homedir
	#createhomedir -c > /dev/null
	createhomedir -l -u $username > /dev/null
else
	## Variables
	cronfile=/etc/cron.d/wottracker
	download=wget

	## Create user
	useradd -m -r $username
	homedir=$(grep $username /etc/passwd | cut -d: -f6)
	gid=$(grep $username /etc/passwd | cut -d: -f4)
	group=$(grep :$gid: /etc/group | cut -d: -f1)
fi

## Python setup
mkdir -p $homedir/python
if [ ! -e /tmp/Python-$pyversion.tgz ] || [ "$($shacmd /tmp/Python-$pyversion.tgz)" != "$pysha" ]
then
	wget $pyurl -O /tmp/Python-$pyversion.tgz
fi
pushd $homedir/python # 1
tar xzf /tmp/Python-$pyversion.tgz
find $homedir/python -type d | xargs chmod 0755
pushd Python-$pyversion # 2
./configure --prefix=$homedir/python
make && make install
#rm $homedir/python/Python-$pyversion.tgz
popd # $homedir/python, 2
rm -rf Python-$pyversion
chown -R $username:$group $homedir/python

## Pip setup
# pip3 included with Python 3.6.5 source tarball
#wget --no-check-certificate https://bootstrap.pypa.io/get-pip.py -O - | sudo -u $username bin/python - --user

## Virtualenv setup
sudo -u $username $homedir/python/bin/pyvenv $homedir/wottracker

## Install modules
cd ..
wget https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/requirements.txt
chown $username:$group requirements.txt
sudo -u $username $homedir/python/bin/pip3 install -r requirements.txt

## Return to working directory
popd # 1

if [[ $kernel = "Darwin"* ]]
then
	## Add scheduler task for running node
	# UTC calculation: https://stackoverflow.com/a/30371208/1993468
	offset=$(date +%z) # get TZ offset as [+-]<HH><MM> - for *now*
	sign=${offset:0:1} # get sign
	hours=${offset:1:2} # get hours
	mins=${offset:3:2} # get minutes
	# Want to start at least 15 minutes early. Hopefully this calculates right
	hourstart=$((24 $sign $hours - 1 % 24))
	minstart=$((60 $sign $mins - 15 % 60))
	cat <<EOF >> $cronfile
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$(echo $cronfile | cut -d/ -f3)</string>

  <key>ProgramArguments</key>
  <array>
    <string>source wottracker/bin/activate && python node.py</string>
  </array>

  <key>Nice</key>
  <integer>1</integer>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$hourstart</integer>
    <key>Minute</key>
    <integer>$minstart</integer>
  </dict>

  <key>UserName</key>
  <string>$username</string>

  <key>RootDirectory</key>
  <string>$homedir</string>

  <key>RunAtLoad</key>
  <false/>

</dict>
</plist>
EOF
	launchctl load $cronfile

	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement.
else
	## Add scheduler task for running node
	touch $cronfile
	echo "CRON_TZ=UTC" >> $cronfile
	echo "45 23 * * *  $username  cd $homedir && source wottracker/bin/activate && python node.py" >> $cronfile

	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement. SuSE, Redhat, Ubuntu all have different programs
fi