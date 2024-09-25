# This code contains helper functions for generalizing loops
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


# This source code is derived from Mimid
#   https://github.com/vrthra/mimid/
# Copyright (c) 2018-2020 Saarland University, CISPA, authors, and contributors
# This source code is licensed under The Fuzzing Book License found in the
# 3rd-party-licenses.txt file in the root directory of this source tree.

import logging
import cmimid.util as util
import copy
from configparser import ConfigParser
from typing import Dict, List, Tuple
from tracer.gdb_tracer import GDBTracer
from tracer.instance.sut_instance import SUTInstance

from miner.active_learning_utils import register_node, identify_compatibility_patterns, is_a_replaceable_with_b

class LoopGeneralizer:
    
    def __init__(self, config:ConfigParser) -> None:
        self.config = config
        self.NODE_REGISTER: Dict[str, List[Tuple]] = {}

    
    def can_the_loop_be_deleted(self, pattern, k, instance: SUTInstance):
        xnodes = [xnode for xnode in self.NODE_REGISTER[k] if xnode[-1]['pattern'] == pattern]
        can_be_deleted = True
        for xnode in xnodes:
            node0, tree0, inputfile0, _info = xnode
            
            a = is_a_replaceable_with_b(instance, (node0, '', tree0), (['', [], 0, 0], '', tree0))
            if not a:
                can_be_deleted = False
                break
        for xnode in xnodes:
            node0, tree0, inputfile0, info = xnode
            method1, ctrl1, cname1, num1, can_empty, cstack1 = util.parse_pseudo_name(node0[0])
            name = util.unparse_pseudo_name(method1, ctrl1, cname1, num1, util.Epsilon if can_be_deleted else util.NoEpsilon, cstack1)
            info['node'][0] = name

    def update_pseudo_name(self, k_m, my_id):
        # fixup k_m with what is in my_id
        original = k_m[0]
        method, ctrl, cid, altid, can_empty, method_stack = util.parse_pseudo_name(original)
        if ctrl == 'if':
            name = util.unparse_pseudo_name(method, ctrl, cid, "%s.%d" % (altid, my_id), can_empty, method_stack)
        elif ctrl == 'while':
            assert altid == '0'
            name = util.unparse_pseudo_name(method, ctrl, cid, my_id, can_empty, method_stack)
        else:
            assert False
        k_m[0] = name
        return name, k_m

    def collect_pseudo_nodes(self, node, tree, inputfile):
        if util.is_node_pseudo(node):
            register_node(node, tree, inputfile, self.NODE_REGISTER)

        node_name, children, *rest = node
        for child in children:
            self.collect_pseudo_nodes(child, tree, inputfile)

    def update_original_pseudo_names(self, node_name):
        registered_xnodes = self.NODE_REGISTER[node_name]
        for xnode in registered_xnodes:
            # name it according to its pattern
            nodeX, treeX, inputfileX, infoX = xnode
            pattern = infoX['pattern']
            self.update_pseudo_name(infoX['node'], pattern)

    def generalize_loop_trees(self, jtrees):
        my_trees = []
        for t in jtrees:
            tree = util.to_modifiable(t['tree']) # The tree ds.
            executable = t['original']
            inputfile = t['arg']
            # we skip START
            node_name, children, *rest = tree
            assert node_name == '<START>'
            for child in children:
                self.collect_pseudo_nodes(child, tree, inputfile)
            my_trees.append({'tree':tree, 'original': executable, 'arg': inputfile})

        with GDBTracer.open_sut_instance(self.config) as instance:
            instance.continue_execution()
            for i,k in enumerate(self.NODE_REGISTER):
                logging.info("compat: %s %d/%d" % (k, i, len(self.NODE_REGISTER)))
                patterns = identify_compatibility_patterns(k, self.NODE_REGISTER, instance)
                for p in patterns:
                    self.can_the_loop_be_deleted(patterns[p], k, instance)                 
   
            self.number_of_tested_inputs = instance.number_of_tested_inputs
        logging.info(f"Used {self.number_of_tested_inputs} requests to generalize loops")
        # finally, update the original names.
        for i,k in enumerate(self.NODE_REGISTER):
            if k == '<START>': continue
            logging.info("update: %s %d/%d" % (k, i, len(self.NODE_REGISTER)))
            self.update_original_pseudo_names(k)
        return my_trees