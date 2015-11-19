#!/usr/bin/env python3

import asyncio

from argparse import ArgumentParser
import logging

from cmc import CMC
from selector import add_selector_arguments, selected_selector
from imageloader import ImageLoader
from imagerepo import ImageRepo

# for each of these there should be a symlink to imaging-main.py
# like imaging-load -> imaging-main.py
# and a function in this module with no arg
supported_commands = [ 'load', 'save', 'list', 'status', 'inventory' ]

####################
def load():
    image_repo = ImageRepo()
    default_image = image_repo.default()

    parser = ArgumentParser()
    parser.add_argument("-v", "--verbose", action='store_true', default=False)
    parser.add_argument("-i", "--image", action='store', default=default_image,
                        help="Specify image to load (default is {})".format(default_image))
    add_selector_arguments(parser)
    args = parser.parse_args()

    message_bus = asyncio.Queue()

    selector = selected_selector(args)
    cmcs = [ CMC(cmc_name, message_bus) for cmc_name in selector.cmc_names() ]
    print(selector)

    for cmc in cmcs:
        print("cmc: {} -> mac: {}".format(cmc, cmc.control_mac_address()))
        if not cmc.is_known():
            print("WARNING : cmc is not known to the inventory".format(cmc.hostname))

    actual_image = image_repo.locate(args.image)
    if not actual_image:
        print("Image file {} not found - emergency exit".format(args.image))
        exit(1)

    ImageLoader(cmcs, message_bus, actual_image).main()
 
####################
def list():
    ImageRepo().display()

####################
def status():
    
    parser = ArgumentParser()
    parser.add_argument("-v", "--verbose", action='store_true', default=False)
    add_selector_arguments(parser)
    args = parser.parse_args()

    selector = selected_selector(args)
    message_bus = asyncio.Queue()
    
    cmcs = [ CMC(cmc_name, message_bus) for cmc_name in selector.cmc_names() ]

    for cmc in cmcs:
        asyncio.Task(cmc.get_status_verbose())
    asyncio.get_event_loop().run_forever()
    asyncio.get_event_loop().close()

####################
def inventory():
    from inventory import the_inventory
    the_inventory.display(verbose=True)

####################
####################
####################
import sys

def main():
#    logging.basicConfig(level=logging.DEBUG)
    command=sys.argv[0]
    for supported in supported_commands:
        if supported in command:
            main_function = globals()[supported]
            return main_function()
    print("Unknown command {}", command)

if __name__ == '__main__':
    main()
