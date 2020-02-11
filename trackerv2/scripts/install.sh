#!/bin/bash

if [ "$EUID" -ne 0 ]
then 
	echo "Please run with 'sudo'"
	exit 1
fi

if [ $# -ne 1 ]
then
	echo "Usage: $0 {server|client}"
	exit 1
fi

## Exit on errors
set -e

## Global variables
pyversion=3.7.0
pyurl=https://www.python.org/ftp/python/$pyversion/Python-$pyversion.tgz
pysha=ef7462723026534d2eb1b44db7a3782276b3007d
shacmd=sha1sum
kernel=$(uname -s)
installing=$(echo $1 | tr '[:upper:]' '[:lower:]')

if [ $installing != "server" ] && [ $installing != "client" ]
then
	echo "Usage: $0 {server|client}"
	exit 1
fi

username=wot$installing

if [[ $kernel = "Darwin"* ]]
then
	## Variables
	username=_$username
	group=$username
	homedir=/Users/$username
	cronfile=/usr/lib/cron/tabs/$username
	#download=curl
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
	cronfile=/etc/cron.d/$username
	#download=wget

	## Create user
	useradd -m -r $username
	homedir=$(grep $username /etc/passwd | cut -d: -f6)
	gid=$(grep $username /etc/passwd | cut -d: -f4)
	group=$(grep :$gid: /etc/group | cut -d: -f1)
fi

## Python setup

# Install the build dependencies
# Git isn't needed for clients, but it won't hurt them either
if [[ $kernel = "Darwin"* ]]
then
	# TODO
	xcode-select --install
else
	# https://devguide.python.org/setup/#unix
	if [[ $(which yum 2>/dev/null) != "" ]]
	then
		yum -y install yum-utils git
		yum-builddep python3
	#
	#elif [[ $(which zypper) != "" ]]
	#then
	#elif [[ $(which zypp) != "" ]]
	#then
	elif [[ $(which dnf 2>/dev/null) != "" ]]
	then
		dnf -y install dnf-plugins-core git
		dnf builddep python3
	elif [[ $(which apt 2>/dev/null) != "" ]]
	then
		apt-get update
		apt-get -y install git
		apt-get build-dep python3.7
	else
		echo "What OS is this? Please let us know at https://github.com/kamakazikamikaze/wotplayertrackerv2/issues"
		exit 1
	fi
fi

# TODO: build python in /tmp in case the script needs to be re-run
mkdir -p $homedir/python
pushd $homedir/python
if [ ! -e /tmp/Python-$pyversion.tgz ] || [ "$($shacmd /tmp/Python-$pyversion.tgz | cut -d' ' -f1)" != "$pysha" ]
then
	wget $pyurl -O /tmp/Python-$pyversion.tgz
fi
tar xzf /tmp/Python-$pyversion.tgz
find $homedir/python -type d | xargs chmod 0755
pushd Python-$pyversion
./configure --prefix=$homedir/python
make && make install
if [ $? -ne 0 ]
then
	echo "<-- ERROR INSTALLING PYTHON. INSTALL MISSING DEPENDENCIES AND RETRY -->"
	exit 1
fi
# rm $homedir/python/Python-$pyversion.tgz
popd # $homedir/python
rm -rf Python-$pyversion
chown -R $username:$group $homedir/python

## Virtualenv setup
sudo -u $username bash -c "$homedir/python/bin/pyvenv $homedir/wottracker"

## Install modules
cd .. # $homedir

if [ $installing = "client" ]
then
	wget https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/$installing-requirements.txt
	chown $username:$group $installing-requirements.txt
	wget https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/trackerv2/client/update.py
	chown $username:$group update.py
	cat <<EOF > $homedir/client.json
	{
		"server": "http://changeme/",
		"application_id": "demo",
		"throttle": 10,
		"debug": false
	}
EOF
	chown $username:$group client.json
else
	sudo -u $username git clone https://github.com/kamakazikamikaze/wotplayertrackerv2.git
	cd wotplayertrackerv2
	mkdir config
	chown $username:$group ../../config/
fi
sudo -u $username bash -c "$homedir/wottracker/bin/pip3 install -r $installing-requirements.txt"

if [ $installing = "server" ]
then
	cd trackerv2/server
	sudo -u $username bash -c "$homedir/wottracker/bin/python server.py ../../config/server.json -c ../../config/client.json -g"
	chown $username:$group ../../config/*
fi

## Return to working directory
popd

if [ $installing = "server" ]
then
	croncmd="cd $homedir/wotplayertrackerv2/trackerv2/server/ && wottracker/bin/python server.py ../../config/server.json -c ../../config/client.json -f ../../files"
	cronminute=0
else
	cronminute=1
	croncmd="cd $homedir && wottracker/bin/python update.py client.json; wottracker/bin/python client.py client.json"
fi
	
touch $cronfile
if [[ $kernel = "Darwin"* ]]
then
	hour=$(( (( $(date +%:z | cut -d: -f1) + 24 )) % 24 ))
	minute=$(( (( $(date +%:z | cut -d: -f2) + 60 + $cronminute )) % 60 ))
	echo 'MAILTO=""' > $cronfile
	echo "$minute $hour * * * bash -c '$croncmd'" >> $cronfile
	echo "0 2 * * * bash -c 'cd $homedir && ./adjustcron.sh'" >> $cronfile

	# macOS doesn't have an updated cron binary to use the CRON_TZ flag. We'll have to run a script to adjust for daylight savings manually
	touch $homedir/adjustcron.sh
	chmod 755 $homedir/adjustcron.sh
	chown $username $homedir/adjustcron.sh
	echo '#!/bin/bash' > $homedir/adjustcron.sh
	echo "cronfile=$cronfile" >> $homedir/adjustcron.sh
	echo "homedir=$homedir" >> $homedir/adjustcron.sh
	echo "cronminute=$cronminute" >> $homedir/adjustcron.sh
	echo 'hour=$(( (( $(date +%:z | cut -d: -f1) + 24 )) % 24 ))' >> $homedir/adjustcron.sh
	echo 'minute=$(( (( $(date +%:z | cut -d: -f1) + 60 + $cronminute )) % 60 ))' >> $homedir/adjustcron.sh
	echo 'echo '"'"'MAILTO="" >> $cronfile' >> $homedir/adjustcron.sh
	echo 'echo "$minute $hour * * * bash -c '"'"$croncmd"'"' >> $cronfile"' >> $homedir/adjustcron.sh
	echo 'echo "0 2 * * * bash -c '"'"'cd $homedir && ./adjustcron.sh'"'"'" >> $cronfile' >> $homedir/adjustcron.sh

	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement.
else
	## Add scheduler task for running node
	echo "CRON_TZ=UTC" > $cronfile
	echo "$cronminute 0 * * *  $username  bash -c '$croncmd'" >> $cronfile

	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement. SuSE, Redhat, Ubuntu all have different programs
fi

