#!/usr/bin/env python
# This code can generate random inputs from context-free grammars
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

import argparse
from os import path
import pathlib
import cmimid.fuzz as F
from fuzzingbook.GrammarCoverageFuzzer import GrammarCoverageFuzzer
from tracer.gdb_tracer import GDBTracer
import json
from fuzzingbook.GrammarMiner import readable
from fuzzingbook.Grammars import START_SYMBOL, Grammar, extend_grammar, def_used_nonterminals, unreachable_nonterminals
from configparser import ConfigParser

PRECISION_SIZE=1000

def trim_grammar(grammar: Grammar, start_symbol=START_SYMBOL) -> Grammar:
    """Create a copy of `grammar` where all unused and unreachable nonterminals are removed."""
    new_grammar = extend_grammar(grammar)
    defined_nonterminals, used_nonterminals = \
        def_used_nonterminals(grammar, start_symbol)
    if defined_nonterminals is None or used_nonterminals is None:
        return new_grammar

    unused = defined_nonterminals - used_nonterminals
    unreachable = unreachable_nonterminals(grammar, start_symbol)
    for nonterminal in unused | unreachable:
        del new_grammar[nonterminal]

    return new_grammar

def find_output_directory(output_directory_base: pathlib.Path):
    # Find last 'trial-*' folder
    return next(reversed(sorted(output_directory_base.glob("trial-*"),
                                key = lambda x: int(x.name.split("-")[1]))))


                                
def main():
    # Create a parser
    parser = argparse.ArgumentParser(description='Generates inputs from grammar')

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
        'out',
        type=str,
        help='Path to output folder.'
    )
    
    parser.add_argument(
        'count',
        type=int,
        help='Number of files to generate.'
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
    
    output_directory = pathlib.Path(args.out)

 
    if args.grammar:
        grammar_file = args.grammar
    else:
        grammar_file = output_directory / "parsing_g.json"
        
    with open(grammar_file) as f:
        mined = json.load(f)
    grammar = mined['[grammar]']
    start = mined['[start]']
    #fuzzer = F.LimitFuzzer(grammar)
    grammar = trim_grammar(readable(grammar), start_symbol=start)
    fuzzer = GrammarCoverageFuzzer(grammar, start_symbol=start)
    
    seen = set()
    i = 0
    
    with GDBTracer.open_sut_instance(config) as instance:
        instance.continue_execution()

        while i < args.count:
        
            
            input = fuzzer.fuzz()
            if not input.strip(): continue
            if input in seen: continue
            seen.add(input)
            accepted = instance.input_accepted(input.encode("utf-8"))
            if accepted:
                i += 1
                with open(output_directory / f"input.{i}", "w") as out_file:
                    out_file.write(input)
            
                

if __name__ == '__main__':
    main()
