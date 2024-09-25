#!/usr/bin/env python

# This code contains the main logic for the grammar mining step
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import argparse
from os import path
import logging
import pathlib
import sys
import time
sys.setrecursionlimit(99000)

from typing import List, Tuple
import json

from configparser import ConfigParser
from miner.tree_builder import TreeBuilder
from miner.method_generalizer import MethodGeneralizer
from miner.loop_generalizer import LoopGeneralizer
from miner.token_generalizer import TokenGeneralizer
from cmimid.treeminer import miner
import cmimid.pta as pta
import cmimid.grammartools as G
import cmimid.util
import cmimid.parsinggrammar as parsinggrammar

# If we stick to original mimid structure
from miner.tree_builder import ORIGINAL_MIMID as ORIGINAL_MIMID

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


def find_output_directory(output_directory_base: pathlib.Path):
    # Find last 'trial-*' folder
    return next(reversed(sorted(output_directory_base.glob("trial-*"),
                                key = lambda x: int(x.name.split("-")[1]))))

def squash_consecutive_conditions(tree: Tuple[str, List, int, int]) -> Tuple[str, List, int, int]:


    name, childs, id1, id2 = tree
    #Dict[str, Tuple[int, str, List[int]]]
    
    if name and ':if_' in name and len(childs) == 1 and\
        ':if_' in childs[0][0]:
            
            child_name, child_childs, child_id1, child_id2 = childs[0] 
            method, ctrl, cid, altid, can_empty, method_stack = cmimid.util.decode_name(name[1:-1])
            method_c, ctrl_c, cid_c, altid_c, can_empty_c, method_stack_c = cmimid.util.decode_name(child_name[1:-1])   
            #TODO maybe just use cid_c ?
            new_name = cmimid.util.unparse_pseudo_name(method_c, ctrl_c, cid_c, altid + altid_c, can_empty_c, method_stack)
            return squash_consecutive_conditions((new_name, child_childs , id1, id2))
            #child_child_tree = [squash_consecutive_conditions(child_child) for child_child in child_childs]
            #return (new_name, child_child_tree , id1, id2) 
            
    else:
        child_tree = [squash_consecutive_conditions(child) for child in childs]
        return (name, child_tree , id1, id2)
        

def move_subtree_to_single_function_call(tree: Tuple[str, List, int, int]) -> Tuple[str, List, int, int]:


    name, childs, id1, id2 = tree

    if len(childs) >= 2 and \
        cmimid.util.is_node_method(childs[0]) and \
        cmimid.util.is_node_method(childs[1]):

            childs[1][1].insert(0, childs.pop(0))

            
    child_tree = [move_subtree_to_single_function_call(child) for child in childs]
    return (name, child_tree , id1, id2)
        

def to_grammar(tree, grammar):
    node, children, *rest = tree 
    if not children: return grammar
    tokens = []
    if node not in grammar:
        grammar[node] = list()
    for c in children:
        tokens.append(c[0])
        to_grammar(c, grammar)
    grammar[node].append(tokens)
    return grammar

def merge_grammar(g1, g2):
    all_keys = set(list(g1.keys()) + list(g2.keys()))
    merged = {}
    for k in all_keys:
        alts = list(g1.get(k, []))
        alts.extend(x for x in g2.get(k, []) if x not in alts)
        merged[k] = alts
    return {k:[l for l in merged[k]] for k in merged}

def convert_to_grammar(my_trees):
    grammar = {}
    ret = []
    for my_tree in my_trees:
        tree = my_tree['tree']
        start = tree[0]
        src_file = my_tree['original']
        arg_file = my_tree['arg']
        ret.append((start, src_file, arg_file))
        g = to_grammar(tree, grammar)
        grammar = merge_grammar(grammar, g)
    return ret, grammar


def eliminate_non_terminating_vars(grammar):
    
    new_grammar = {}
    
    #First find add all productions exclusively going on terminals
    for k in grammar:
        for rule in grammar[k]:
            is_all_terminal=True
            for p in rule:
                if G.is_nt(p):
                    is_all_terminal=False
                    break
            if is_all_terminal:
                if not k in new_grammar:
                    new_grammar[k] = []
                new_grammar[k].append(rule)
    
    
    changed = True
    while changed: # Until nothing changes anymore
        changed = False
        
        for k in grammar:
            for rule in grammar[k]:
                if k in new_grammar and rule in new_grammar[k]:
                    continue
                include = True
                for p in rule:
                    if G.is_nt(p): #Add rule if all variables are already in grammar
                        if p not in new_grammar:
                            include = False
                            break
                if include:
                    changed = True
                    if not k in new_grammar:
                        new_grammar[k] = []
                    new_grammar[k].append(rule)
                    
    return new_grammar
    

def check_empty_rules(grammar):
    new_grammar = {}
    for k in grammar:
        new_grammar[k] = grammar[k]
        if cmimid.util.is_node_method([k]):
            if cmimid.util.parse_method_name(k)[0].endswith(cmimid.util.Epsilon):
                new_grammar[k].append([]) #empty rule
        elif ':if_' in k or \
            ':while_' in k :
            name, _ = k.split('#')
            if name.endswith(cmimid.util.Epsilon):
                new_grammar[k].append([]) #empty rule
                
    while True:      # Remove epsilon productions
        # Find epsilon production rules
        epsilon_variables = set()
        for k in new_grammar:
            keep_rules = []
            for rule in new_grammar[k]:
                if len(rule) == 0:
                    epsilon_variables.add(k)
                else:
                    keep_rules.append(rule)
            new_grammar[k].clear()
            new_grammar[k].extend(keep_rules)     
            
        if not epsilon_variables:
            break       
        
        #Add rules without epsilon variables
        for k in new_grammar:
            for rule in new_grammar[k]:
                new_rule = [p for p in rule if p not in epsilon_variables]
                if len(new_rule)< len(rule) and len(new_rule) > 0:                        
                    new_grammar[k].append(new_rule)
                    
        
  
    return new_grammar


def collapse_alts(rules, k):
    ss = [[str(r) for r in rule] for rule in rules]
    x = pta.generate_grammar(ss, k[1:-1])
    return x

def collapse_rules(grammar):
    r_grammar = {}
    for k in grammar:
        new_grammar = collapse_alts(grammar[k], k)
        # merge the new_grammar with r_grammar
        # we know none of the keys exist in r_grammar because
        # new keys are k prefixed.
        for k_ in new_grammar:
            r_grammar[k_] = new_grammar[k_]
    return r_grammar

def convert_spaces_in_keys(grammar):
    keys = {key: key.replace(' ', '_') for key in grammar}
    new_grammar = {}
    for key in grammar:
        new_alt = []
        for rule in grammar[key]:
            new_rule = []
            for t in rule:
                for k in keys:
                    t = t.replace(k, keys[k])
                new_rule.append(t)
            new_alt.append(new_rule)
        new_grammar[keys[key]] = new_alt
    return new_grammar

def main():
    
    start_time = time.time()
    # Create a parser
    parser = argparse.ArgumentParser(description='Generate a context free grammar')

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

    output_directory = find_output_directory(pathlib.Path(config['BASIC']['output_directory']))
    seed_directory = config['BASIC']['seed_directory']
    
    loglevel = config['LOGS']['log_level']
    setup_logging(output_directory=output_directory, loglevel=loglevel)
    
    trace_files = list(sorted(pathlib.Path(output_directory).glob('*.trace')))
    seed_files = list(sorted(pathlib.Path(seed_directory).glob('*')))
    

    builder = TreeBuilder(trace_files, seed_files, config['BASIC']['binary_file'])

    builder.dump_to_file(output_directory / "trace.json")
    
    mined_trees = miner(builder.get_tree_list())
    

    with open (output_directory / "trees.json", "w") as f:
        json.dump(mined_trees, f)
        
    # Squashing consecutive if conditions
    # for entry in mined_trees:      
    #     entry['tree'] = squash_consecutive_conditions(entry['tree'])

    # with open(output_directory / "squash_trees.json", 'w') as f: 
    #     json.dump(mined_trees, f)
    
    method_generalizer = MethodGeneralizer(config)
    trees = method_generalizer.generalize_method_trees(mined_trees)
    
    with open(output_directory / "method_trees.json", 'w') as f: 
         json.dump(trees, f)
         
    loop_generalizer = LoopGeneralizer(config)
    trees = loop_generalizer.generalize_loop_trees(trees)

    with open(output_directory / "loop_trees.json", 'w') as f: 
            json.dump(trees, f)
    
    
    
    with open(output_directory / "loop_trees.json", 'r') as f: 
        trees = json.load(f)
        
    #for entry in trees:      
    #    entry['tree'] = move_subtree_to_single_function_call(entry['tree'])


    ret, g = convert_to_grammar(trees)
    cmds = {src for starts,src,arg in ret}
    starts = {starts for starts,src,arg in ret}
    assert len(cmds) == 1
    cmd = list(cmds)[0]
    starts = {starts for starts,src,arg in ret}
    assert len(starts) == 1
    start_symbol = list(starts)[0]
    g = G.grammar_gc(g, start_symbol) # garbage collect

    g = check_empty_rules(g) # add optional rules
    g = eliminate_non_terminating_vars(g)
    g = G.grammar_gc(g, start_symbol) # garbage collect

    g = collapse_rules(g) # learn regex
    g = G.grammar_gc(g, start_symbol) # garbage collect


    g = convert_spaces_in_keys(g) # fuzzable grammar
    g = G.grammar_gc(g, start_symbol) # garbage collect
    
    grammar_map = {'[start]': start_symbol, '[grammar]':g, '[command]':cmd}
    with open(output_directory / "mined_g.json", 'w') as f: 
        json.dump(grammar_map, f, indent=4)
        
    token_generalizer = TokenGeneralizer(config)
    g = token_generalizer.generalize_tokens_in_grammar(g, start_symbol)
    
    compact_g = G.compact_grammar(g, start_symbol)

    final_grammar = parsinggrammar.enhance_grammar(compact_g)
    
    number_of_tested_inputs = method_generalizer.number_of_tested_inputs + loop_generalizer.number_of_tested_inputs + token_generalizer.number_of_tested_inputs
    
    with open(output_directory / "parsing_g.json", 'w') as f: 
         json.dump({'[start]': start_symbol, '[grammar]':final_grammar, '[command]':cmd, '[no_tested_inputs]': number_of_tested_inputs}, f)
         
         
    logging.info(f"Mining time: {time.time() - start_time} seconds")
         
if __name__ == '__main__':
    main()
