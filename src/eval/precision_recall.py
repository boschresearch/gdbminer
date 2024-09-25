#!/usr/bin/env python
# This code can generate calculate precision and recall values from a grammar
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import argparse
from os import path
import logging
import pathlib
import cmimid.fuzz as F
import cmimid.util as util
from tracer.gdb_tracer import GDBTracer
from typing import List
import json
import fuzzingbook.Parser as P
import signal
from fuzzingbook.GrammarMiner import readable
from fuzzingbook.GrammarCoverageFuzzer import GrammarCoverageFuzzer

from configparser import ConfigParser

PRECISION_SIZE=1000

def find_output_directory(output_directory_base: pathlib.Path):
    # Find last 'trial-*' folder
    return next(reversed(sorted(output_directory_base.glob("trial-*"),
                                key = lambda x: int(x.name.split("-")[1]))))


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

                                
def main():
    # Create a parser
    parser = argparse.ArgumentParser(description='Calculates the precision of a mined grammar')

    # Add the arguments
    parser.add_argument(
        '--config',
        required=True,
        type=str,
        help='Path to a config file.'
    )
    
    parser.add_argument(
        '--grammar',
        required=False,
        type=str,
        help='Path to a grammar file.'
    )
    
    parser.add_argument(
        '--out',
        required=False,
        type=str,
        help='Path to an output file.'
    )

    # Execute the parse_args() methode
    args = parser.parse_args()
    config_file_path = args.config
    config_file_path = path.expanduser(config_file_path)

    if not path.isfile(config_file_path):
        raise Exception(f'Config file at {config_file_path} does not exist')

    # Start ConfigParser for further usage
    config = ConfigParser()
    config.read(config_file_path)

    
    output_directory = find_output_directory(pathlib.Path(config['BASIC']['output_directory']))

    loglevel = config['LOGS']['log_level']
    setup_logging(output_directory=output_directory, loglevel=loglevel)

    eval_directory = pathlib.Path(config['BASIC']['eval_directory'])
    
        
    if args.grammar:
        grammar_file = args.grammar
    else:
        grammar_file = output_directory / "parsing_g.json"
        
    with open(grammar_file) as f:
        mined = json.load(f)
    grammar = mined['[grammar]']
    start = mined['[start]']
    
    #fuzzer = GrammarCoverageFuzzer(readable(grammar), start_symbol=start)
    fuzzer = F.LimitFuzzer(grammar)
    accepted_count = 0
    
    with GDBTracer.open_sut_instance(config) as instance:
        instance.continue_execution()
        for i in range(PRECISION_SIZE):
            #input = fuzzer.fuzz()
            input = fuzzer.fuzz(start)
            accepted = instance.input_accepted(input.encode("utf-8"))
            if accepted:
                accepted_count += 1.0
            else:
                logging.info(f"Generated non accepting input: {repr(input)}")
                
 
    def handler(signum, frame):
        raise TimeoutError()

    # set the timeout handler
    signal.signal(signal.SIGALRM, handler) 
    
    parser = P.IterativeEarleyParser(P.non_canonical(grammar), start_symbol=start)
    parsed_count = 0
    eval_set_len = 0
    for eval_f_name in eval_directory.glob('*'):
        with open(eval_f_name) as eval_file:
            eval_string = eval_file.read()
            eval_set_len += 1
            try:
                
                signal.alarm(10)
                result = parser.parse(eval_string)
                if not any([eval_string != util.tree_to_str(tree) for tree in result]):
                    # s = util.tree_to_str(tree)
                    # if s == eval_string:
                    parsed_count += 1.0
            except (SyntaxError, TimeoutError):
                logging.warning(f'Can not parse {repr(eval_string)}' )
            finally:
                signal.alarm(0)
    prec = accepted_count/PRECISION_SIZE
    rec = parsed_count/eval_set_len
    result = {"precision"   : prec,
              "recall"      : rec}
    
    result["f1"] = 2 * (( prec*rec) /(prec + rec) )
    
    if '[no_tested_inputs]' in mined:
        result['no_tested_inputs'] = mined['[no_tested_inputs]']
        
    logging.info(result)

    
    if args.out:
        with open(args.out, "w") as f:
            json.dump(result, f)
    

if __name__ == '__main__':
    main()
