#!/usr/bin/env python
#
#
#    NEPI, a framework to manage network experiments
#    Copyright (C) 2015 INRIA
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 2 as
#    published by the Free Software Foundation;
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Alina Quereilhac <alina.quereilhac@inria.fr>
#         Maksym Gabielkov <maksym.gabielkovc@inria.fr>
#
# Author file: Mario Zancanaro <mario.zancanaro@inria.fr>
#
# This is a maintenance functions used to make group operations at the nodes from
# INRIA testbed (R2Lab) before running a OMF experiment using Nitos nodes.
#

from nepi.execution.ec import ExperimentController
from nepi.execution.resource import ResourceAction, ResourceState
import os
from nepi.util.sshfuncs import logger
import time
import sys
import re

err_messages = ['error', 'err', 'unreachable', 'errors']

def load(nodes, connection_information):
    """ Load a new image to the nodes from the list """
    ec    = ExperimentController(exp_id="load")
    nodes = check_node_name(nodes)

    gw_node = ec.register_resource("linux::Node")
    ec.set(gw_node, "hostname", connection_information[2])
    ec.set(gw_node, "username", connection_information[3])
    ec.set(gw_node, "identity", connection_information[4])
    ec.set(gw_node, "cleanExperiment", True)
    ec.set(gw_node, "cleanProcesses", False)
    ec.set(gw_node, "cleanProcessesAfter", False)

    node_appname = {}
    node_appid   = {}
    apps         = []

    for node in nodes:
        on_cmd_a = "nodes {}; load-u1410".format(node) 
        node_appname.update({node : 'app_{}'.format(node)}) 
        node_appname[node] = ec.register_resource("linux::Application")
        ec.set(node_appname[node], "command", on_cmd_a)
        ec.register_connection(node_appname[node], gw_node)
        # contains the app id given when register the app by EC
        node_appid.update({node_appname[node] : node})
        apps.append(node_appname[node])

    ec.deploy(gw_node)

    results = {}
    for app in apps:
        ec.deploy(app)
        #ec.wait_finished(app)
    
        print "loading image at node {}".format(node_appid[app])
        time.sleep(10)
        
    results = {}
    for app in apps:
        the_trace = ec.trace(app, "stdout")
        results.update({node_appid[app] : remove_special(the_trace)})
    
    ec.shutdown()
    
    print "+ + + + + + + + + "
    for key in sorted(results):
        if set(err_messages).intersection(results[key].split()) or not results[key]:
            new_result = 'fail'
        else:
            new_result = 'loaded'

        print "node {:02}: {}".format(key, new_result)
    print "+ + + + + + + + +"

    return results


def reset(nodes, connection_information):
    """ Reset all nodes from the list """
    ec    = ExperimentController(exp_id="reset")
    nodes = check_node_name(nodes)
    
    gw_node = ec.register_resource("linux::Node")
    ec.set(gw_node, "hostname", connection_information[2])
    ec.set(gw_node, "username", connection_information[3])
    ec.set(gw_node, "identity", connection_information[4])
    ec.set(gw_node, "cleanExperiment", True)
    ec.set(gw_node, "cleanProcesses", False)
    ec.set(gw_node, "cleanProcessesAfter", False)

    node_appname = {}
    node_appid   = {}
    apps         = []

    for node in nodes:
        on_cmd_a = "curl 192.168.1.{}/reset".format(node) 
        node_appname.update({node : 'app_{}'.format(node)}) 
        node_appname[node] = ec.register_resource("linux::Application")
        ec.set(node_appname[node], "command", on_cmd_a)
        ec.register_connection(node_appname[node], gw_node)
        # contains the app id given when register the app by EC
        node_appid.update({node_appname[node] : node})
        apps.append(node_appname[node])

    ec.deploy(gw_node)

    results = {}
    for app in apps:
        ec.deploy(app)
        #ec.wait_finished(app)

        print "restarting node {}".format(node_appid[app])
        time.sleep(10)
        the_trace = ec.trace(app, "stdout")
        results.update({node_appid[app] : remove_special(the_trace)})

    ec.shutdown()
    
    print "+ + + + + + + + + "
    for key in sorted(results):
        if set(err_messages).intersection(results[key].split()) or not results[key]:
            new_result = 'fail'
        else:
            new_result = 'restarted'

        print "node {:02}: {}".format(key, new_result)
    print "+ + + + + + + + +"

    return results


def alive(nodes, connection_information):
    """ Check if a node answer a ping command """
    ec    = ExperimentController(exp_id="alive")
    nodes = check_node_name(nodes)

    gw_node = ec.register_resource("linux::Node")
    ec.set(gw_node, "hostname", connection_information[2])
    ec.set(gw_node, "username", connection_information[3])
    ec.set(gw_node, "identity", connection_information[4])
    ec.set(gw_node, "cleanExperiment", True)
    ec.set(gw_node, "cleanProcesses", False)
    ec.set(gw_node, "cleanProcessesAfter", False)

    node_appname = {}
    node_appid   = {}
    apps         = []

    for node in nodes:
        on_cmd_a = "ping -c1 192.168.1.{}".format(node) 
        node_appname.update({node : 'app_{}'.format(node)}) 
        node_appname[node] = ec.register_resource("linux::Application")
        ec.set(node_appname[node], "command", on_cmd_a)
        ec.register_connection(node_appname[node], gw_node)
        # contains the app id given when register the app by EC
        node_appid.update({node_appname[node] : node})
        apps.append(node_appname[node])

    ec.deploy(gw_node)

    ec.deploy(apps)
    ec.wait_finished(apps) 

    #ec.register_condition(sender_app, ResourceAction.START, receiver_app, ResourceState.STARTED) 

    results = {}
    for app in apps:
        the_trace = ec.trace(app, "stdout")
        results.update({node_appid[app] : remove_special(the_trace)})

    ec.shutdown()
    
    print "+ + + + + + + + + "
    for key in sorted(results):
        if set(err_messages).intersection(results[key].split()) or not results[key]:
            new_result = 'fail'
        else:
            new_result = 'alive'

        print "node {:02}: {}".format(key, new_result)
    print "+ + + + + + + + +"

    return results


def status(nodes, connection_information):
    """ Check the status of all nodes from the list """
    return multiple_action(nodes, connection_information, 'status')


def on(nodes, connection_information):
    """ Turn on all nodes from the list """
    return multiple_action(nodes, connection_information, 'on')


def off(nodes, connection_information):
    """ Turn off all nodes from the list """
    return multiple_action(nodes, connection_information, 'off')


def multiple_action(nodes, connection_information, action):
    """ Execute the command in all nodes from the list """
    ec    = ExperimentController(exp_id=action)
    nodes = check_node_name(nodes)

    gw_node = ec.register_resource("linux::Node")
    ec.set(gw_node, "hostname", connection_information[2])
    ec.set(gw_node, "username", connection_information[3])
    ec.set(gw_node, "identity", connection_information[4])
    ec.set(gw_node, "cleanExperiment", True)
    ec.set(gw_node, "cleanProcesses", False)
    ec.set(gw_node, "cleanProcessesAfter", False)

    node_appname = {}
    node_appid   = {}
    apps         = []

    for node in nodes:
        on_cmd_a = "curl 192.168.1.{}/{}".format(node, action) 
        node_appname.update({node : 'app_{}'.format(node)}) 
        node_appname[node] = ec.register_resource("linux::Application")
        ec.set(node_appname[node], "command", on_cmd_a)
        ec.register_connection(node_appname[node], gw_node)
        # contains the app id given when register the app by EC
        node_appid.update({node_appname[node] : node})
        apps.append(node_appname[node])

    ec.deploy(gw_node)

    ec.deploy(apps)
    ec.wait_finished(apps) 

    #ec.register_condition(sender_app, ResourceAction.START, receiver_app, ResourceState.STARTED) 

    results = {}
    for app in apps:
        the_trace = ec.trace(app, "stdout")
        results.update({node_appid[app] : remove_special(the_trace)})

    ec.shutdown()
    
    print "+ + + + + + + + + "
    for key in sorted(results):
        if set(err_messages).intersection(results[key].split()) or not results[key]:
            new_result = 'fail'
        else:
            new_result = results[key]

        print "node {:02}: {}".format(key, new_result)
    print "+ + + + + + + + +"

    return results

def remove_special(str):
    """ Remove special caracters from a string """
    new_str = str.replace('\n', '').replace('\r', '').lower()
    new_str = re.sub('[^A-Za-z0-9]+', ' ', str)
    
    return new_str


def ip_node(alias):
    """ Returns the ip from the node alias [fitXX] """
    prefix = '192.168.1.xx'
    alias = alias.lower().replace('fit', '')

    try:
        int(alias)
    except Exception, e:
        raise Exception("error in ip convertion")
    
    ip = prefix.replace('xx', alias)
    return ip


def check_node_name(nodes):
    new_nodes = []

    for node in nodes:
        if "fit" in node:
            new_nodes.append(number_node(node))
        else:
            new_nodes.append(node)

    return new_nodes


def number_node(alias):
    """ Returns the number from the node alias [fitXX] """
    node = alias.lower().replace('fit', '')
    
    return int(node)
