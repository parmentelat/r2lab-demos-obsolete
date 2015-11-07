#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
given a set of nodes on the command line - either numbers or complete hostnames
we compute a news feed for sidecar

this is as optimized as we can think about it
* first step on CMC status - all nodes reported as off will
  * get {'cmc_on_off' : 'off'}
  * be ignored in further steps
* second step is on attempting an ssh connection to retrieve OS release
  the ones that succeed with ubuntu/fedora 
  * get { 'cmc_on_off' : 'on', 'os_release' : <>}
  * be ignored in further steps
* remaining nodes where an ssh connection can be achieved to run 'hostname' will
  * get { 'cmc_on_off' : 'on', 'os_release' : 'other' }
  * be ignored in further steps
* others will have a ping attempted on control, they get either
  * get { 'cmc_on_off' : 'on', 'control_ping' : 'on' or 'off'}
"""

default_runs = 0                # run forever
default_cycle = 3.              # wait for 3s between runs
default_nodes = range(1, 38)    # focus on nodes 1-37
default_socket_io_url = "ws://r2lab.inria.fr:443/"

from datetime import datetime
import sys
import os
import re
import json
import signal
import time
import socket

from urllib.parse import urlparse
from argparse import ArgumentParser

import subprocess
import paramiko

from socketIO_client import SocketIO, LoggingNamespace

# our local patch for paramiko & no authentication
from sshclient_noauth import SSHClient_noauth

# the channel to use when talking to the sidecar server
channel_news = 'r2lab-news'
# this one is not used here but 
channel_signalling = 'r2lab-signalling'

def hostname(node_id, prefix="fit"):
    return "{prefix}{node_id:02d}".format(**locals())

verbose = None

########## timeouts (floats are probably OK but I have not tried)
# this should amply enough
timeout_curl = 1
# cool thing with paramiko is the ability to give 2 separate timeouts
timeout_ssh_tcp    = 0.8
timeout_ssh_banner = 0.7
# here again should be amply enough
timeout_ping = 1

# global
output_file = sys.stdout

########## helper
def display(*args, **keywords):
    timestamp = time.strftime("%m/%d %H:%M:%S", time.localtime())
    keywords['file'] = output_file
    print("{} monitor".format(timestamp), *args, **keywords)
    output_file.flush()

def vdisplay(*args, **keywords):
    if verbose:
        display(*args, **keywords)

##########
# a convenience function that adds a timeout to subprocess.check_output
# stolen in http://stackoverflow.com/questions/1191374/subprocess-with-timeout
class Alarm(Exception): pass

def alarm_handler(signum, frame):
    raise Alarm

def check_output_timeout(command, timeout, **keywords):
    original = signal.getsignal(signal.SIGALRM)
    beg = time.time()
#    vdisplay("check_output_timeout : arming {}".format(timeout))
    signal.setitimer(signal.ITIMER_REAL, timeout)
    signal.signal(signal.SIGALRM, alarm_handler)
    try:
        return subprocess.check_output(command, **keywords)
    finally:
#        vdisplay("check_output disarming after {} s".format(time.time()-beg))
        signal.setitimer(signal.ITIMER_REAL, 0.)
        signal.signal(signal.SIGALRM, original)
        
def check_call_timeout(command, timeout, **keywords):
    original = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(timeout)
    try:
        return subprocess.check_call(command, **keywords)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.)
        signal.signal(signal.SIGALRM, original)

##########
# we try to keep global 'infos' ready to be emitted
# so, no dict..
def locate_id(id, infos):
    node_info = None
    for scan in infos:
        if scan['id'] == id:
            node_info = scan
            break
    return node_info

def insert_or_refine(id, infos, *overrides):
    """
    locate an info in infos with that id (or create one)
    then update it with any override(s) if provided
    returns infos
    """
    node_info = locate_id(id, infos)
    if not node_info:
        node_info = {'id' : id}
        infos.append(node_info)
    for override in overrides:
        node_info.update(override)
    return infos

# reset to 0. instead of removing
def cleanup_wlan_infos(id, infos):
    node_info = locate_id(id, infos)
    if not node_info:
        return
    for k in node_info:
        if k.startswith('wlan'):
            node_info[k] = 0.
        
##########
def pass1_on_off(node_ids, infos, history):
    """
    check for CMC status
    the ones that are OFF - or where http://<cmc>/status fails 
    are kept out of the next pass
    
    performs insertions/updates in infos 
    returns the list of nodes that still need to be probed
    """

    # the nodes that fail here will be emitted right away
    # so we need to have the following fields reset in this case
    # general pattern here is to pad infos that are not in remaining_ids
    padding_dict = {
        'control_ping' : 'off',
        'control_ssh' : 'off',
        # don't overwrite os_release though
    }
    
    # the set of nodes for which the whole process ends here
    # we use this logic instead of maintaining remaining_ids
    # because using padding_dict and marking nodes as done 
    # go together and makes code more consistent
    over_with_ids = set()
    for id in node_ids:
#        vdisplay("pass1 : {id} (CMC status via curl)".format(**locals()))
        reboot = hostname(id, "reboot")
        command = [ "curl", "--silent", "http://{reboot}/status".format(**locals()) ]
        try:
            result = check_output_timeout(command, timeout_curl, universal_newlines=True).strip()
            if result == 'off':
                # fill in all fields so we can emit these
                insert_or_refine(id, infos, {'cmc_on_off' : 'off'}, padding_dict)
                over_with_ids.add(id)
            elif result == 'on':
                insert_or_refine(id, infos, {'cmc_on_off' : 'on'})
            else:
                raise Exception("unexpected result on CMC status request " + result)
        except Exception as e:
            vdisplay('node={id}'.format(id=id), e)
            insert_or_refine(id, infos, {'cmc_on_off' : 'fail'}, padding_dict)
            over_with_ids.add(id)
    return node_ids - over_with_ids


##########
ubuntu_matcher = re.compile("DISTRIB_RELEASE=(?P<ubuntu_version>[0-9.]+)")
fedora_matcher = re.compile("Fedora release (?P<fedora_version>\d+)")
gnuradio_matcher = re.compile("\AGNURADIO:(?P<gnuradio_version>[0-9\.]+)\Z")
rxtx_matcher = re.compile("==> /sys/class/net/(?P<device>wlan[0-9])/statistics/(?P<rxtx>[rt]x)_bytes <==")
number_matcher = re.compile("\A[0-9]+\Z")

def pass2_os_release(node_ids, infos, history, report_wlan):
    """
    check for an os_release 
    the ones that do answer are kept out of the next passes

    same mechanism as pass1 in terms of side-effects and return value
    """
    padding_dict = {
        'control_ping' : 'on',
        'control_ssh' : 'on',
    }

    over_with_ids = set()
    for id in node_ids:
#        vdisplay("pass2 : {id} (os_release via ssh)".format(**locals()))
        control = hostname(id)
        remote_commands = [
            "cat /etc/lsb-release /etc/fedora-release /etc/gnuradio-release 2> /dev/null | grep -i release",
            "echo -n GNURADIO: ; gnuradio-config-info --version 2> /dev/null || echo none",
            ]
        if report_wlan:
            remote_commands.append(
                "head /sys/class/net/wlan?/statistics/[rt]x_bytes"                
            )
        remote_command = ";".join(remote_commands)
        vdisplay('node={id}'.format(id=id), remote_command)

        try:
            ssh = SSHClient_noauth()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(control, username='root',
                        timeout=timeout_ssh_tcp, banner_timeout=timeout_ssh_banner)
            stdin, stdout, stderr = ssh.exec_command(remote_command)
            cleanup_wlan_infos(id, infos)
            try:
                flavour = "other"
                extension = ""
                rxtx_dict = {}
                rxtx_key = None
                for line in stdout:
                    line = line.strip("\n")
                    match = ubuntu_matcher.match(line)
                    if match:
                        version = match.group('ubuntu_version')
                        flavour = "ubuntu-{version}".format(**locals())
                        continue
                    match = fedora_matcher.match(line)
                    if match:
                        version = match.group('fedora_version')
                        flavour = "fedora-{version}".format(**locals())
                        continue
                    match = gnuradio_matcher.match(line)
                    if match:
                        version = match.group('gnuradio_version')
                        extension += "-gnuradio-{version}".format(**locals())
                        continue
                    match = rxtx_matcher.match(line)
                    if match:
                        # use a tuple as the hash
                        rxtx_key = (match.group('device'), match.group('rxtx'))
                        continue
                    match = number_matcher.match(line)
                    if match and rxtx_key:
                        rxtx_dict[rxtx_key] = int(line)
                        continue
                    rxtx_key = None
                    
                os_release = flavour + extension
                # now that we have the counters we need to translate this into rate
                # for that purpose we use local clock; small imprecision should not impact overall result
                now = time.time()
                wlan_info_dict = {}
                for rxtx_key, bytes in rxtx_dict.items():
                    device, rxtx = rxtx_key
#                    vdisplay("node={id} collected {bytes} for device {device} in {rxtx}".format(**locals()))
                    # do we have something on this measurement ?
                    if rxtx_key in history:
                        previous_bytes, previous_time = history[rxtx_key]
                        info_key = "{device}_{rxtx}_rate".format(**locals())
                        new_rate = 8.*(bytes - previous_bytes) / (now - previous_time)
                        wlan_info_dict[info_key] = new_rate
                        vdisplay("node={} computed {} bps for key {} "
                                 "- bytes = {}, pr = {}, now = {}, pr = {}"
                                 .format(id, new_rate, info_key,
                                         bytes, previous_bytes, now, previous_time));
                    # store this measurement for next run
                    history[rxtx_key] = (bytes, now)
                # xxx would make sense to clean up history for measurements that
                # we were not able to collect at this cycle
                insert_or_refine(id, infos, {'os_release' : os_release}, padding_dict, wlan_info_dict)
                over_with_ids.add(id)
            except Exception as e:
#                import traceback
#                traceback.print_exc()
                insert_or_refine(id, infos, {'os_release' : 'other'}, padding_dict)
                over_with_ids.add(id)
        except socket.timeout:
            display("node={id} - ssh timed out".format(id=id))
            insert_or_refine(id, infos, {'control_ssh' : 'off'})
        except ConnectionRefusedError as e:
            display("node={id} - connection refused".format(id=id))
            insert_or_refine(id, infos, {'control_ssh' : 'off'})
        except Exception as e:
            import traceback
            traceback.print_exc()
            # don't overwrite os_release
            insert_or_refine(id, infos, {'control_ssh' : 'off'})
    return node_ids - over_with_ids

def pass3_control_ping(node_ids, infos, history):
    """
    check for control_ping 
    the ones that do answer are kept out of the next passes (should be empty)

    same mechanism as pass1 in terms of side-effects and return value
    """
    # nothing to pad here, it's the last attribute
    over_with_ids = set()
    for id in node_ids:
#        vdisplay("pass3 : {id} (control_ping via ping)".format(**locals()))
        # -c 1 : one packet -- -t 1 : wait for 1 second max
        control = hostname(id)
        command = [ "ping", "-c", "1", "-t", "1", control ]
        try:
            with open('/dev/null', 'w') as null:
                check_call_timeout(command, timeout_ping, stdout=null, stderr=null)
            insert_or_refine(id, infos, {'control_ping' : 'on'})
            over_with_ids.add(id)
        except Exception as e:
            vdisplay('node={id}'.format(id=id), e)
            over_with_ids.add(id)
            insert_or_refine(id, infos, {'control_ping' : 'off'})
    return node_ids - over_with_ids
                    

##########
def io_callback(*args, **kwds):
    display('on socketIO response', *args, **kwds)

def one_loop(all_ids, socketio, infos, history, report_wlan, max_index):
    start = datetime.now()
    ### init    

    focus_ids = all_ids
    remaining_ids = pass1_on_off(focus_ids, infos, history)
    pass1_ids = focus_ids - remaining_ids
    infos1 = [ info for info in infos if info['id'] in pass1_ids ]
    if infos1:
        socketio.emit(channel_news, json.dumps(infos1), io_callback)
    vdisplay("pass1 done, emitted (or not) ", infos1)
    assert(len(infos1) == len(pass1_ids))

    focus_ids = remaining_ids
    remaining_ids = pass2_os_release(focus_ids, infos, history, report_wlan)
    pass2_ids = focus_ids - remaining_ids
    infos2 = [ info for info in infos if info['id'] in pass2_ids ]
    if infos2:
        socketio.emit(channel_news, json.dumps(infos2), io_callback)
    vdisplay("pass2 done, emitted (or not) ", infos2)
    assert(len(infos2) == len(pass2_ids))

    focus_ids = remaining_ids
    remaining_ids = pass3_control_ping(focus_ids, infos, history)
    pass3_ids = focus_ids - remaining_ids
    infos3 = [ info for info in infos if info['id'] in pass3_ids ]
    if infos3:
        socketio.emit(channel_news, json.dumps(infos3), io_callback)
    vdisplay("pass3 done, emitted (or not) ", infos3)
    assert(len(infos3) == len(pass3_ids))

    # should not happen
    if remaining_ids:
        display("OOPS - unexpected remaining nodes = ", remaining_ids)
    
    # print one-line status
    def one_char_summary(info):
        if 'cmc_on_off' in info and info['cmc_on_off'] != 'on':
            return '.'
        elif 'control_ping' in info and info['control_ping'] != 'on':
            return 'o'
        elif 'control_ssh' in info and info['control_ssh'] != 'on':
            return '0'
        elif 'os_release' in info and 'fedora' in info['os_release']:
            return 'F'
        elif 'os_release' in info and 'ubuntu' in info['os_release']:
            return 'U'
        else:
            return '^'

    if not max_index:
        mask = [one_char_summary(info) for info in infos]
    else:
        # if we have e.g. max_index=37, then we want to show the focus nodes
        # in context, i.e. show 37 chars
        mask = [ '_' for i in range(max_index) ]
        for info in infos:
            mask[info['id']-1] = one_char_summary(info)
    one_liner = "".join(mask)
    summary = "{} + {} + {} = {}".format(
        len(infos1), len(infos2), len(infos3),
        len(infos1) + len(infos2) + len(infos3))
    duration = datetime.now() - start
    display("{} - {} - {} s {} ms".format(
        one_liner, summary,
        duration.seconds, int(duration.microseconds/1000)))
    print("first id=", infos[0]['id'])

##########
arg_matcher = re.compile('[^0-9]*(?P<id>\d+)')
def normalize(cli_arg):
    if isinstance(cli_arg, int):
        id = cli_arg
    else:
        match = arg_matcher.match(cli_arg)
        if match:
            id = match.group('id')
        else:
            display("discarded malformed argument {cli_arg}".format(**locals()))
            return None
    return int(id)

def mainloop(nodes, socketio, args):
    cycle = args.cycle
    runs = args.runs
    display("entering mainloop")
    ### elaborate global focus
    all_ids = { normalize(x) for x in nodes }
    all_ids = frozenset([ x for x in all_ids if x ])

    # create a single global list of results that we keep
    # between runs 
    infos = []
    # this is about keeping of what happened in the past so e can
    # compute stuff like rates based on successive measurements
    # of bytes
    history = {}
    counter = 0
    while True:
        one_loop(all_ids, socketio, infos, history, args.report_wlan, args.max_index)
        counter += 1
        if runs and counter >= runs:
            display("bailing out after {} runs".format(runs))
            break
        time.sleep(cycle)

##########
def init_signals ():
    def handler (signum, frame):
        display("Received signal {} - exiting".format(signum))
        if output_file != sys.stdout:
            output_file.close()
        os._exit(1)
    signal.signal(signal.SIGHUP, handler)
    signal.signal(signal.SIGQUIT, handler)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

def main():
    parser = ArgumentParser()
    parser.add_argument("-v", "--verbose", action='store_true', default=False)
    parser.add_argument("-c", "--cycle", action='store', default=default_cycle,
                        type=float,
                        help="Set delay in seconds to be waited between 2 runs - default = {}".
                        format(default_cycle))
    parser.add_argument('-r', '--runs', dest='runs', default=default_runs,
                        type=int,
                        help="How many runs (default={}; 0 means forever)".format(default_runs))
    parser.add_argument("-s", "--socket-io-url", action='store', default=default_socket_io_url,
                        help="""url of sidecar server for notifying results 
- default={}""".format(default_socket_io_url))
    parser.add_argument("-o", "--output", action='store', default=None,
                        help="Specify filename for logs (will be opened in append mode)")
    parser.add_argument("-w", "--no-wlan", dest='report_wlan', action='store_false', default=True,
                        help="Disable generation of wlan?_[rt]x_rate - unit here is bits/s")
    parser.add_argument("-m", "--max-index", dest='max_index', action='store', default=None,
                        type=int,
                        help="When set, one-liner shows subject nodes in context; e.g. -m 37")
    parser.add_argument("nodes", nargs='*')
    args = parser.parse_args()

    # deal with options and args
    global verbose
    verbose = args.verbose
    if args.output:
        global output_file
        vdisplay("Opening {} in append mode".format(args.output))
        output_file = open(args.output, "a")
        sys.stdout = output_file
        sys.stderr = output_file
    if not args.nodes:
        args.nodes = default_nodes

    try:
        hostname, port = urlparse(args.socket_io_url).netloc.split(':')
        port = int(port)
    except:
        print("Could not parse websocket URL {}".format(args.socket_io_url))
        exit(1)

    # connect socketio
    socketio = SocketIO(hostname, 443, LoggingNamespace)

    mainloop(args.nodes, socketio, args)
        
if __name__ == '__main__':
    init_signals()
    main()
    sys.exit(0)
