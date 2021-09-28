#!/bin/sh

prep_static_files() {
	if [ ! -d "$STATIC_FILES" ]
	then
		mkdir -p "$STATIC_FILES"
	fi
	cd "$STATIC_FILES"
	if [ ! -d "./nix" ]
	then
		mkdir ./nix
	fi
	if [ ! -d "./win" ]
	then
		mkdir ./win
	fi
	cp "$BASE"/trackerv2/client/*.py ./nix
	cp "$BASE"/trackerv2/client/*.py ./win
	dos2unix ./nix/*.py
	unix2dos ./win/*.py
}

if [ "$#" -eq 0 ] # Normal execution
then
	if [ "$ROLE" = "server" ]
	then
		prep_static_files
		cd "$BASE"/trackerv2/server
		if [ "$INIT" -ne 0 ]
		then
			# Generate server and client configuration
			python server.py "$SERVER_CONFIG" -c "$CLIENT_CONFIG" -g
		else
			CONDITIONALS=""
			if [ "$AGGRESSIVE_RECOVER" -ne 0 ]
			then
				CONDITIONALS="${CONDITIONALS} --aggressive-recover"
			fi
			if [ "$TRACE_MEMORY" -ne 0 ]
			then
				CONDITIONALS="${CONDITIONALS} --trace-memory"
			fi
			if [ ! -z "$RECOVER_FROM_DUMP" ]
			then
				CONDITIONALS="${CONDITIONALS} --recover ${RECOVER_FROM_DUMP}"
			fi
			python server.py "$SERVER_CONFIG" -c "$CLIENT_CONFIG" -f "$STATIC_FILES" -p $DB_PROCESSES -a $ASYNC_DB_HELPERS_PER_PROCESS $CONDITIONALS
		fi
	elif [ "$ROLE" = "client" ]
	then
		cd "$BASE"/trackerv2/client
		python update.py "$CONFIG"; python client.py "$CONFIG"
	else
		exit 3
	fi
else
	exit 4
fi
