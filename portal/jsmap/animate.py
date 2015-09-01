#!/usr/bin/env python

import random
import json
import time

from argparse import ArgumentParser

#
status_filename = 'r2lab-status.json'

# in s
default_cycle = 0.5
default_runs = 0

node_ids = range(1, 38)
max_nodes = 3
busy_values = [ 'yes', 'no' ]
status_values = [ 'on', 'off' ]

def random_ids():
    how_many = random.randint(1, max_nodes)
    return [ random.choice(node_ids) for i in range(how_many)]

def random_status(id):
    return {
        'id' : id,
        'busy' : random.choice(busy_values),
        'status' : random.choice(status_values)
        }
    
def main():
    parser = ArgumentParser()
    parser.add_argument('-c', '--cycle', dest='cycle', default=default_cycle,
                        type=float,
                        help="Cycle duration in seconds (default={})".format(default_cycle))
    parser.add_argument('-r', '--runs', dest='runs', default=default_runs,
                        type=int,
                        help="How many runs (default={}; 0 means forever)".format(default_cycle))
    parser.add_argument('-v', '--verbose', action='store_true', default=False)
    args = parser.parse_args()

    cycle = args.cycle
    
    if args.verbose:
        print "Using cycle {}s".format(cycle)
    counter = 0
    while True:
        output = [ random_status(id) for id in random_ids()]
        with open(status_filename, 'w') as f:
            if args.verbose:
                print output
            f.write(json.dumps(output))
        counter += 1
        if args.runs and counter >= args.runs:
            break
        time.sleep(cycle)

if __name__ == '__main__':
    main()
            
            