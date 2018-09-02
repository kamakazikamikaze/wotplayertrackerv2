#!/bin/bash

if [ "$EUID" -ne 0 ]
	then echo "Please run with 'sudo'"
	exit
fi

## Global variables
pyversion=3.7.0
username=wotnode
pyurl=https://www.python.org/ftp/python/$pyversion/Python-$pyversion.tgz
pysha=ef7462723026534d2eb1b44db7a3782276b3007d
shacmd=sha1sum
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
	download=wget

	## Create user
	useradd -m -r $username
	homedir=$(grep $username /etc/passwd | cut -d: -f6)
	gid=$(grep $username /etc/passwd | cut -d: -f4)
	group=$(grep :$gid: /etc/group | cut -d: -f1)
fi

## Python setup
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

## Pip setup
# pip3 included with Python 3.6.5 source tarball
#wget --no-check-certificate https://bootstrap.pypa.io/get-pip.py -O - | sudo -u $username bin/python - --user

## Virtualenv setup
sudo -u $username bash -c "$homedir/python/bin/pyvenv $homedir/wottracker"

## Install modules
cd ..
wget https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/client-requirements.txt
chown $username:$group client-requirements.txt
sudo -u $username bash -c "$homedir/wottracker/bin/pip3 install -r client-requirements.txt"

## Return to working directory
popd	

touch $cronfile
if [[ $kernel = "Darwin"* ]]
then
	hour=$(( (( $(date +%:z | cut -d: -f1) + 24 )) % 24 ))
	minute=$(( (( $(date +%:z | cut -d: -f2) + 60 )) % 60 ))
	echo 'MAILTO=""' > $cronfile
	echo "$minute $hour * * * bash -c 'cd $homedir && source wottracker/bin/activate && python update.py client.json; python client.py client.json'" >> $cronfile
	echo "0 2 * * * bash -c 'cd $homedir && ./adjustcron.sh'" >> $cronfile

	# macOS doesn't have an updated cron binary to use the CRON_TZ flag. We'll have to run a script to adjust for daylight savings manually
	touch $homedir/adjustcron.sh
	chmod 755 $homedir/adjustcron.sh
	chown $username $homedir/adjustcron.sh
	echo '#!/bin/bash' > $homedir/adjustcron.sh
	echo "cronfile=$cronfile" >> $homedir/adjustcron.sh
	echo "homedir=$homedir" >> $homedir/adjustcron.sh
	echo 'hour=$(( (( $(date +%:z | cut -d: -f1) + 24 )) % 24 ))' >> $homedir/adjustcron.sh
	echo 'minute=$(( (( $(date +%:z | cut -d: -f1) + 60 )) % 60 ))' >> $homedir/adjustcron.sh
	echo 'echo '"'"'MAILTO="" >> $cronfile' >> $homedir/adjustcron.sh
	echo 'echo "$minute $hour * * * bash -c '"'"'cd $homedir && source wottracker/bin/activate && python update.py client.json; python client.py client.json'"'"' >> $cronfile"' >> $homedir/adjustcron.sh
	echo 'echo "0 2 * * * bash -c '"'"'cd $homedir && ./adjustcron.sh'"'"'" >> $cronfile' >> $homedir/adjustcron.sh
	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement.
else
	## Add scheduler task for running node
	echo "CRON_TZ=UTC" > $cronfile
	echo "1 0 * * *  $username  bash -c 'cd $homedir && source wottracker/bin/activate && python update.py client.json; python client.py client.json'" >> $cronfile

	## Add Firewall exception
	# I think we'll leave firewall exceptions to the user to implement. SuSE, Redhat, Ubuntu all have different programs
fi

wget https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/trackerv2/client/update.py -O $homedir/update.py

cat <<EOF >> $homedir/client.json
{
	"server": "http://changeme/",
	"application_id": "demo",
	"throttle": 10,
	"debug": false
}
EOF
