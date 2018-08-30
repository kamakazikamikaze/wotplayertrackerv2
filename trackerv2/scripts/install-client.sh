#!/bin/bash

if [ "$EUID" -ne 0 ]
	then echo "Please run with 'sudo'"
	exit
fi

## Global variables
pyversion=3.7.0
username=wotnode
pyurl=https://www.python.org/ftp/python/$pyversion/Python-$pyversion.tgz
kernel=$(uname -s)

if [[ $kernel = "Darwin"* ]]
then
	## Variables
	username=_$username
	group=$username
	homedir=/Users/$username
	cronfile=/usr/lib/cron/tabs/$username
	download=curl
	umaxid=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -ug | tail -1)
	uid=$((umaxid+1))
	gmaxid=$(dscl . -list /Groups PrimaryGroupID | awk '{print $2}' | sort -ug | tail -1)
	gid=$((gmaxid+1))

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
	createhomedir -u $username > /dev/null
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
mkdir $homedir/python
pushd $homedir/python
wget $pyurl
tar xzf Python-$pyversion.tgz
find $homedir/python -type d | xargs chmod 0755
pushd Python-$pyversion
./configure --prefix=$homedir/python
make && make install
rm $homedir/python/Python-$pyversion.tgz
popd # $homedir/python
rm -rf Python-$pyversion
chown -R $username:$group $homedir/python

## Pip setup
# pip3 included with Python 3.6.5 source tarball
#wget --no-check-certificate https://bootstrap.pypa.io/get-pip.py -O - | sudo -u $username bin/python - --user

## Virtualenv setup
sudo -u $username $homedir/python/bin/pyvenv $homedir/wottracker

## Install modules
cd ..
wget --no-check-certificate https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/requirements.txt -O
chown $username:$group requirements.txt
sudo -u $username $homedir/python/bin/pip3 install -r requirements.txt

## Return to working directory
popd	

touch $cronfile
if [[ $kernel = "Darwin"* ]]
then
	hour=$(( (( $(date +%:z | cut -d: -f1) + 24)) % 24 ))
	minute=$(( (( $(date +%:z | cut -d: -f2) + 60)) % 60))
	echo 'MAILTO=""' >> $cronfile
	echo "$minute $hour * * *  cd $homedir && source wottracker/bin/activate && python update.py client.json; python client.py client.json" >> $cronfile
	echo "0 0 * * * cd $homedir && ./adjustcron.sh" >> $cronfile

	# macOS doesn't have an updated cron binary to use the CRON_TZ flag. We'll have to run a script to adjust for daylight savings manually
	touch $homedir/adjustcron.sh
	chmod 755 $homedir/adjustcron.sh
	chown $username $homedir/adjustcron.sh
	echo '#!/bin/bash' >> $homedir/adjustcron.sh
	echo "cronfile=$cronfile" >> $homedir/adjustcron.sh
	echo "homedir=$homedir" >> $homedir/adjustcron.sh
	echo 'hour=$(( (( $(date +%:z | cut -d: -f1) + 24)) % 24 ))' >> $homedir/adjustcron.sh
	echo 'minute=$(( (( $(date +%:z | cut -d: -f1) + 60)) % 60 ))' >> $homedir/adjustcron.sh
	echo 'echo '"'"'MAILTO="" >> $cronfile' >> $homedir/adjustcron.sh
	echo 'echo "$minute $hour * * *  cd $homedir && source wottracker/bin/activate && python update.py client.json; python client.py client.json" >> $cronfile' >> $homedir/adjustcron.sh
	echo 'echo "0 0 * * * cd $homedir && ./adjustcron.sh" >> $cronfile' >> $homedir/adjustcron.sh
	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement.
else
	## Add scheduler task for running node
	echo "CRON_TZ=UTC" >> $cronfile
	echo "00 0 * * *  $username  cd $homedir && source wottracker/bin/activate && python update.py client.json; python client.py client.json" >> $cronfile

	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement. SuSE, Redhat, Ubuntu all have different programs
fi

cat <<EOF >> $homedir/client.json
{
	"server": "http://changeme/",
	"application_id": "demo",
	"throttle": 10,
	"debug": false
}
EOF
