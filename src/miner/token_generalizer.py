# This code contains helper functions for generalizing tokens
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


# This source code is derived from Mimid
#   https://github.com/vrthra/mimid/
# Copyright (c) 2018-2020 Saarland University, CISPA, authors, and contributors
# This source code is licensed under The Fuzzing Book License found in the
# 3rd-party-licenses.txt file in the root directory of this source tree.

from configparser import ConfigParser
import cmimid.util as util
import random
import string
import copy
import logging
from typing import List, Dict, Tuple
from tracer.gdb_tracer import GDBTracer
from tracer.instance.sut_instance import SUTInstance
from miner.active_learning_utils import is_a_replaceable_with_b
import cmimid.grammartools as grammartools
import cmimid.fuzz as F
from cmimid.fuzz import ASCII_MAP, CHARACTER_PARENT_MAP

class TokenGeneralizer:
    
        
    GK = '<__GENERALIZE__>'
    MAX_CHECKS = 100
        
    def __init__(self, config:ConfigParser) -> None:
        self.config = config
        
        
    def is_nt(token):
        return token.startswith('<') and token.endswith('>')

    def generalize_tokens(grammar):
        g_ = {}
        for k in grammar:
            new_rules = []
            for rule in grammar[k]:
                new_rule = []
                for token in rule:
                    if not TokenGeneralizer.is_nt(token):
                        new_rule.extend(list(token))
                    else:
                        new_rule.append(token)
                new_rules.append(new_rule)
            g_[k]  = new_rules
        return g_

    def get_list_of_single_chars(grammar) -> List[Tuple[str, int, int, str]]:
        lst = []
        for p,key in enumerate(grammar):
            for rule_index,rule in enumerate(grammar[key]):
                for token_index,token in enumerate(rule):
                    if TokenGeneralizer.is_nt(token): continue
                    if len(token) == 1:
                        lst.append((key, rule_index, token_index, token))
        return lst

    def remove_recursion(d):
        new_d = {}
        for k in d:
            new_rs = []
            for t in d[k]:
                if t != k:
                    new_rs.append(t)
            new_d[k] = new_rs
        return new_d

    def fill_tree(tree, parent, gk):
        filled_tree = []
        to_fill = [(tree, filled_tree)]
        while to_fill:
            (node, filled_node), *to_fill = to_fill
            name, children = node
            if name == gk:
                new_node = [name, [[parent, []]]]
                filled_node.extend(new_node)
                my_node = filled_node
                # return my_node
            elif not children:
                if name in ASCII_MAP:
                    new_node = [random.choice(ASCII_MAP[name]), []]
                    filled_node.extend(new_node)
                    # return (random.choice(ASCII_MAP[name]), [])
                else:
                    new_node = [name, []]
                    filled_node.extend(new_node)
                    # return (name, [])
            else:
                # update the new nodes
                child_nodes = [[] for c in children]
                new_node = [name, child_nodes]
                filled_node.extend(new_node)
                to_fill = [(c, child_nodes[i]) for i,c in enumerate(children)] + to_fill
        return my_node, filled_tree


    def replaceable_with_kind(stree, orig, parent, gk, instance: SUTInstance):
        my_node, tree0 = TokenGeneralizer.fill_tree(stree, parent, gk)
        #print(json.dumps(tree0, indent=4), file=sys.stderr)
        sval = util.tree_to_str(tree0)
        assert my_node is not None
        a1 = my_node, '', tree0
        if parent == orig:
            aX = ((gk, [[orig, []]]), '', tree0)
            val = is_a_replaceable_with_b(instance, a1, aX)
            if val:
                return True
            else:
                return False
        else:
            for pval in ASCII_MAP[parent]:
                aX = ((gk, [[pval, []]]), '', tree0)
                val = is_a_replaceable_with_b(instance, a1, aX)
                if val:
                    continue
                else:
                    return False
            return True


    def find_max_generalized(tree, kind, gk, instance: SUTInstance):
        if kind not in CHARACTER_PARENT_MAP: return kind
        parent = CHARACTER_PARENT_MAP[kind]
        if TokenGeneralizer.replaceable_with_kind(tree, kind, parent, gk, instance):
            return TokenGeneralizer.find_max_generalized(tree, parent, gk, instance)
        else:
            return kind

    def do_n(tree, kind, gk, n):
        ret = []
        for i in range(n):
            pval = random.choice(ASCII_MAP[kind])
            ret.append([pval, []])
        return (gk, ret)

    def find_max_widened(tree, kind, gk, instance: SUTInstance):
        my_node, tree0 = TokenGeneralizer.fill_tree(tree, kind, gk)
        sval = util.tree_to_str(tree0)
        assert my_node is not None
        a1 = my_node, '', tree0

        # this is a single character. Now, try 2, 4 etc.
        pvals = TokenGeneralizer.do_n(tree, kind, gk, 2)
        aX = (pvals, '', tree0)
        val = is_a_replaceable_with_b(instance, a1, aX)
        if not val: return kind
        pvals = TokenGeneralizer.do_n(tree, kind, gk, 4)
        aX = (pvals, '', tree0)
        val = is_a_replaceable_with_b(instance, a1, aX)
        if not val: return kind
        logging.info(f"Found widened {kind}")
        return kind + '+'

    def generalize_single_token(grammar, start, key, rule_index, token_index, instance: SUTInstance, blacklist):
        # first we replace the token with a temporary key
        gk = TokenGeneralizer.GK
        # was there a previous widened char? and if ther wase,
        # do we belong to it?
        char = grammar[key][rule_index][token_index]
        if token_index > 0 and grammar[key][rule_index][token_index-1][-1] == '+':
            # remove the +
            last_char = grammar[key][rule_index][token_index-1][0:-1]
            if last_char in ASCII_MAP and char in ASCII_MAP[last_char]:
                #we are part of the last.
                grammar[key][rule_index][token_index] = last_char + '+'
                return grammar

        g_ = copy.deepcopy(grammar)
        g_[key][rule_index][token_index] = gk
        g_[gk] = [[char]]
        #reachable_keys = grammartools.reachable_dict(g_)
        # now, we need a path to reach this.
        fg = grammartools.get_focused_grammar(g_, gk)
        fuzzer = F.LimitFuzzer(fg)
        #skel_tree = find_path_key(g_, start, gk, reachable_keys, fuzzer)
        tree = None
        check = 0
        while tree is None:
            #tree = flush_tree(skel_tree, fuzzer, gk, char)
            #tree = fuzzer.gen_key(grammartools.focused_key(start), depth=0, max_depth=1)
            tree = fuzzer.iter_gen_key(grammartools.focused_key(start), max_depth=1)
            
            val = instance.input_accepted(util.tree_to_str(tree).encode("utf-8"))
            check += 1
            if not val:
                tree = None
            if check > TokenGeneralizer.MAX_CHECKS:
                logging.info("Exhausted limit for key:%s, rule:%d, token:%d, char:%s" % (key, rule_index, token_index, char))
                blacklist.append((key, rule_index, token_index, char))
                #raise "Exhausted limit for key:%s, rule:%d, token:%d, char:%s" % (k, q, r, char)
                return None
            # now we need to make sure that this works.

        gen_token = TokenGeneralizer.find_max_generalized(tree, char, gk, instance)
        if gen_token != char:
            # try widening
            gen_token = TokenGeneralizer.find_max_widened(tree, gen_token, gk, instance)
        del g_[gk]
        g_[key][rule_index][token_index] = gen_token
        # preserve the order
        #grammar[key][rule_index][token_index] = gen_token
        return gen_token

    def remove_duplicate_repetitions(g):
        new_g = {}
        for k in g:
            new_rules = []
            for rule in g[k]:
                #srule = ''.join(rule)
                new_rule = []
                last = -1
                for i,t in enumerate(rule):
                    if last >= 0 and len(t) > 0 and t[-1] == '+' and t == rule[last]:
                        continue
                    else:
                        last = i
                    new_rule.append(t)
                #snrule = ''.join(new_rule)
                #if srule != snrule:
                #    print("change:",file=sys.stderr)
                #    print("  ", srule, file=sys.stderr)
                #    print("  ", snrule, file=sys.stderr)
                new_rules.append(new_rule)
            new_g[k] = new_rules
        return new_g

    def generalize_tokens_in_grammar(self, grammar, start) -> Dict:
        

        # now, what we want to do is first regularize the grammar by splitting each
        # multi-character tokens into single characters.
        generalized_grammar = TokenGeneralizer.generalize_tokens(grammar)

        # next, we want to get the list of all such instances

        list_of_things_to_generalize = TokenGeneralizer.get_list_of_single_chars(generalized_grammar)
        logging.info(f"Generalize {len(list_of_things_to_generalize)} tokens")

        list_of_generalizations = []
        # next, we want to generalize each in turn
        # finally, we want to generalize the length.
        #reachable_keys = reachable_dict(grammar)
        with GDBTracer.open_sut_instance(self.config) as instance:
            instance.continue_execution()
            g_ = generalized_grammar
            blacklist = []
            for key, rule_index, token_index, token in list_of_things_to_generalize:
                assert g_[key][rule_index][token_index] == token
                bl = []
                new_token = TokenGeneralizer.generalize_single_token(g_, start, key, rule_index, token_index, instance, bl)
                if bl:
                    logging.info(f"Blacklisted: {bl}")
                    blacklist.extend(bl)
                if new_token:
                    list_of_generalizations.append((key, rule_index, token_index, new_token))
                    
                    
            self.number_of_tested_inputs = instance.number_of_tested_inputs
        logging.info(f"Used {self.number_of_tested_inputs} requests to generalize tokens")
        
        for (key, rule_index, token_index, new_token) in list_of_generalizations:
            g_[key][rule_index][token_index] = new_token
        g = TokenGeneralizer.remove_duplicate_repetitions(g_)
        g = grammartools.remove_duplicate_rules_in_a_key(g)

        # finally, we want to generalize the length.
        #g = generalize_size(g_)
        return g

