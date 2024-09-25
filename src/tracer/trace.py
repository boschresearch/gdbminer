#!/usr/bin/env python
# This code contains the main logic for tracing
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import argparse
import time
from os import path
import logging
import pathlib
import subprocess

from typing import List
import json

from configparser import ConfigParser
from tracer.gdb_tracer import GDBTracer


def uniquify(logfile_path):
    counter = 0
    while True:
        new_path = logfile_path + "-" + str(counter)
        counter += 1
        if not path.exists(new_path):
            return new_path


def create_output_directory(output_directory_base):
    output_directory = uniquify(logfile_path=output_directory_base + "/trial")
    pathlib.Path(output_directory).mkdir(parents=True, exist_ok=True)
    return output_directory


def setup_logging(output_directory, loglevel):
    logger = logging.getLogger()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s %(filename)s:%(lineno)s %(funcName)s()] %(message)s')

    file_logger = logging.FileHandler(
        path.join(output_directory, 'out.log')
    )
    file_logger.setLevel(loglevel)
    file_logger.setFormatter(formatter)
    logger.addHandler(file_logger)

    stdout_logger = logging.StreamHandler()
    stdout_logger.setLevel(loglevel)
    stdout_logger.setFormatter(formatter)
    logger.addHandler(stdout_logger)

    logging.root.setLevel(loglevel)


def generate_trace(filename, config: ConfigParser):


    gdb_tracer = GDBTracer(config)

    # Start gdb execution
    trace = gdb_tracer.trace_input(filename)
    logging.debug(trace)

    return trace


def main():
    start_time = time.time()
    # Create a parser
    parser = argparse.ArgumentParser(description='Generate traces of a program')

    # Add the arguments
    parser.add_argument(
        '--config',
        required=True,
        type=str,
        help='Path to a config file.'
    )

    # Execute the parse_args() methode
    config_file_path = parser.parse_args().config
    config_file_path = path.expanduser(config_file_path)

    if not path.isfile(config_file_path):
        raise Exception(f'Config file at {config_file_path} does not exist')

    # Start ConfigParser for further usage
    config = ConfigParser()
    config.read(config_file_path)

    # Setup logging
    output_directory = config['BASIC']['output_directory']
    output_directory = create_output_directory(output_directory_base=output_directory)
    loglevel = config['LOGS']['log_level']
    setup_logging(output_directory=output_directory, loglevel=loglevel)

    seed_directory = config['BASIC']['seed_directory']
    list_of_traces = []
    for filename in sorted(pathlib.Path(seed_directory).glob('*')):
        logging.info(f'Start generating trace for {filename}')
        trace = generate_trace(filename, config)
        list_of_traces.append(trace)
        trace_file_path = path.join(output_directory, filename.name + '.trace')
        with open(trace_file_path, 'w') as trace_file:
            json.dump(trace, trace_file, default=vars)
            
        logging.info(f'Write trace of {filename.name} to {trace_file_path}')

    #print(list_of_traces)
    logging.info(f"Tracing time: {time.time() - start_time} seconds")


if __name__ == '__main__':
    main()
