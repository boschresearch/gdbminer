# This code contains helper functions for generalizing methods
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


# This source code is derived from Mimid
#   https://github.com/vrthra/mimid/
# Copyright (c) 2018-2020 Saarland University, CISPA, authors, and contributors
# This source code is licensed under The Fuzzing Book License found in the
# 3rd-party-licenses.txt file in the root directory of this source tree.

from configparser import ConfigParser
import cmimid.util as util
import logging
import copy
from typing import List, Dict, Tuple
from tracer.gdb_tracer import GDBTracer
from tracer.instance.sut_instance import SUTInstance
from miner.active_learning_utils import identify_compatibility_patterns, register_node, is_a_replaceable_with_b
class MethodGeneralizer:
    
    def __init__(self, config:ConfigParser) -> None:
        self.config = config
        self.NODE_REGISTER: Dict[str, List[Tuple]] = {}
        
    def can_method_be_deleted(self, pattern, k, instance: SUTInstance):
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
            if can_be_deleted:
                new_name = '<%s>' % (node0[0][1:-1] + util.Epsilon)
                info['node'][0] = new_name


    def update_method_stack(self, node, old_name, new_name):
        nname, children, *rest = node
        if not (':if_' in nname or ':while_' in nname):
            return
        method, ctrl, cname, num, can_empty, cstack = util.parse_pseudo_name(nname)
        assert old_name.startswith(method)
        name = util.unparse_pseudo_name(new_name, ctrl, cname, num, can_empty, cstack)
        node[0] = name
        for c in node[1]:
            self.update_method_stack(c, old_name, new_name)

    def update_method_name(self, node, my_id):
        # fixup k_m with what is in my_id
        original = node[0]
        method, old_id = util.parse_method_name(original)
        name = util.unparse_method_name(method, my_id)
        node[0] = name

        for c in node[1]:
            self.update_method_stack(c, original[1:-1], name[1:-1])

        return name, node


    def collect_method_nodes(self, node, tree, inputfile):
        node_name, children, si, ei = node

        if util.is_node_method(node):
            register_node(node, tree, inputfile, self.NODE_REGISTER)
        for child in children:
            self.collect_method_nodes(child, tree, inputfile)
            

        
    def update_original_method_names(self, node_name):
        registered_xnodes = self.NODE_REGISTER[node_name]
        for xnode in registered_xnodes:
            # name it according to its pattern
            nodeX, treeX, inputfileX, infoX = xnode
            pattern = infoX['pattern']
            self.update_method_name(infoX['node'], pattern)

    # The idea is to first collect and register all nodes by their names.
    # Next, we sample N of these, and use the pattern of matches
    # (Todo: Do we simply use the pattern of compatibility or the pattern
    # of left to right replaceability -- that is, a is replaceable with b
    # but b is not replaceable with a is 10 while full compatibility would
    # be 11 -> 1)
    def generalize_method_trees(self, tree_list: List[Dict]):
        
        my_trees: List[Dict] = []
        
        for i,t in enumerate(tree_list):
            tree = util.to_modifiable(t['tree']) # The tree ds.
            executable = t['original']
            inputfile = t['arg']
            logging.info("progress: %s %d/%d" % (inputfile, i, len(tree_list)))
            # we skip START
            node_name, children, *rest = tree
            assert node_name == '<START>'
            for child in children:
                self.collect_method_nodes(child, tree, inputfile)
            my_trees.append({'tree':tree, 'original': executable, 'arg': inputfile})

        with GDBTracer.open_sut_instance(self.config) as instance:
            instance.continue_execution()
            for i,k in enumerate(self.NODE_REGISTER):
                logging.info("compat: %s %d/%d" % (k, i, len(self.NODE_REGISTER)))
                patterns = identify_compatibility_patterns(k, self.NODE_REGISTER, instance) # XTODO: switch to identify_buckets
                for p in patterns:
                    self.can_method_be_deleted(patterns[p], k, instance)

            self.number_of_tested_inputs = instance.number_of_tested_inputs
        logging.info(f"Used {self.number_of_tested_inputs} requests to generalize methods")
        # finally, update the original names.
        for i,k in enumerate(self.NODE_REGISTER):
            logging.info("update: %s %d/%d" % (k, i, len(self.NODE_REGISTER)))
            if k == '<START>': continue
            self.update_original_method_names(k)
        return my_trees
