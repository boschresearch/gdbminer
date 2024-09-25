# This code contains helper functions for the active learning step
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


# This source code is derived from Mimid
#   https://github.com/vrthra/mimid/
# Copyright (c) 2018-2020 Saarland University, CISPA, authors, and contributors
# This source code is licensed under The Fuzzing Book License found in the
# 3rd-party-licenses.txt file in the root directory of this source tree.

from tracer.instance.sut_instance import SUTInstance
import cmimid.util as util
import copy
from typing import Dict, List, Tuple
import logging
from miner.tree_builder import ORIGINAL_MIMID
#Tree = Tuple[]
#Node = Tuple[str, ]

CACHE : Dict[str, bool] = {}

def is_compatible(instance: SUTInstance, a, b) -> bool:
    t1 = is_a_replaceable_with_b(instance, a, b)
    if not t1: return False
    t2 = is_a_replaceable_with_b(instance, b, a)
    return t2

def is_a_replaceable_with_b(instance: SUTInstance, a, b) -> bool:
    n1, f1, t1 = a
    n2, f2, t2 = b
    if util.tree_to_str(n1) == util.tree_to_str(n2): return True
    
    copy_a = copy.deepcopy(a)
    copy_b = copy.deepcopy(b)
    updated_tree = util.replace_nodes(copy_a, copy_b)
    updated_string = util.tree_to_str(updated_tree)
    
    if updated_string in CACHE:
        logging.debug(f"Found string in cache: {updated_string}")
        return CACHE[updated_string]
    else:
        accepted = instance.input_accepted(updated_string.encode("utf-8"))
        CACHE[updated_string] = accepted
        return accepted

def register_node(node, tree, input_file, node_register: Dict[str, List[Tuple]]):
    node_name = node[0]
    if node_name not in node_register: 
        node_register[node_name] = []
    new_elt = (node, tree, input_file,
            {'inputstr': util.tree_to_str(tree), 'node':node, 'tree':tree})
    node_register[node_name].append(new_elt)
    return new_elt

def get_compatibility_pattern(node, sampled_nodes: List[Tuple], instance: SUTInstance):
    """ Checks if the given node can be interchanged with the given list of nodes
        and returns the results as a bit pattern e.g. 10011.

    Args:
        node : The node 
        sampled_nodes : The list of nodes to check compatibility
        instance : A instance to test inputs on

    Returns:
       The compatibility bit pattern
    """
    node0, tree0, inputfile0, _info = node
    results = []
    a0 = node0, inputfile0, tree0
    for snode in sampled_nodes:
        nodeX, treeX, inputfileX, _info = snode
        aX = nodeX, inputfileX, treeX
        result = is_compatible(instance, a0, aX)
        results.append(result)
    return ''.join(['1' if i else '0' for i in results])


def identify_compatibility_patterns(node_name: str, node_register: Dict[str, List[Tuple]], instance: SUTInstance):
    nodes_with_same_name = node_register[node_name]
    sampled_nodes = util.sample(nodes_with_same_name, util.MAX_PROC_SAMPLES)
    logging.info(f"Sample {len(sampled_nodes)} from {len(nodes_with_same_name)} nodes for pattern recognition")

    node_patterns = {}
    count = 0
    # Build a NxN bit matrix representing compatible (interchangeable) nodes
    for i, node in enumerate(nodes_with_same_name):
        pattern = get_compatibility_pattern(node, sampled_nodes, instance)
        #if "1" not in pattern and not ORIGINAL_MIMID:
            # Full incompatible node resulting from sampling -> Make it unique
        #    logging.info(f"Full incompatible node {node_name} ({i})")
        #    pattern = str(i)
        if pattern not in node_patterns:
            node_patterns[pattern] = count
            count += 1
        _nodeX, _treeX, _inputfileX, infoX = node
        infoX['pattern'] = node_patterns[pattern]
    return node_patterns
