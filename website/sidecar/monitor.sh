#!/bin/bash
# to be run in faraday

hostname | grep -q faraday || {
    echo $0 is designed for faraday only
    exit 1
    }

# the default socket io url points at the right place on r2lab
CODEDIR=$(dirname $0)
[ -f $CODEDIR/monitor.py ] || CODEDIR=/root/fitsophia/website/sidecar
[ -f $CODEDIR/monitor.py ] || { echo Cannot locate monitor.py - exiting; exit 1; }

LOCAL_LOG=/var/log/monitor.log

function display() {
    echo $(date '+%m/%d %H:%M:%S') "$@"
}

function locate_pid() {
    key=$1; shift
    pids=$(pgrep -f $key)
    [ -n "$pids" ] && ps $pids | egrep -v 'PID' | awk '{print $1;}'
}

function start() {
    # nodes can be specified on the command line, defaults to all nodes

    echo Using $CODEDIR/monitor.py
    # options
    delay=3
    verbose=

    while getopts ":d:" opt; do
	case $opt in
	    d)
		delay=$OPTARG;;
	    v)
		verbose=-v ;;
	esac
    done
    shift $((OPTIND-1))

    cd $CODEDIR

    while true; do
	display probing
	./monitor.py $verbose "$@"
	# no need to push anymore
	display sleep $delay s
	sleep $delay
    done >> $LOCAL_LOG 2>&1 &
}

function stop() {
    # kill sh processes first
    killed=""
    pids=$(locate_pid monitor.sh)
    [ -n "$pids" ] && { kill $pids; killed="$killed $pids"; }
    pids=$(locate_pid monitor.py)
    [ -n "$pids" ] && { kill $pids; killed="$killed $pids"; }
    if [ -z "$killed" ]; then    
	echo nothing to stop
    else
	echo stopped
    fi
}

function status() {
    pids="$(locate_pid monitor.sh) $(locate_pid monitor.py)"
    if [ -z "$pids" ]; then
	echo not running
    else
	ps $pids
    fi
}

# One can run
# monitor.sh start -v 10 23

function main() {
    verb=$1; shift
    case $verb in
	start) start "$@" ;;
	stop) stop ;;
	status) status ;;
	restart) echo "please run $0 stop; $0 start" ;;
	*) echo No such verb $1; exit 1 ;;
    esac
}

main "$@"