# This code contains the main logic for recovering derivation trees from traces
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


from dataclasses import dataclass
import json
import urllib.parse
import cmimid.util
from typing import Set, Dict, List, Tuple
import pathlib
from miner.graph_utils import build_control_flow_graphs_from_traces, all_natural_loops, if_else_scope, T
import logging
import os
import networkx as nx

# If we stick to original mimid structure
ORIGINAL_MIMID = os.getenv('ORIGINAL_MIMID', '0') == '1'

# If we delay watchpoints until the next one is hit
DELAY_WP = os.getenv('DELAY_WP', '0') == '1'

@dataclass
class PseudoMethodScope:
    addr: T #The address where the scope starts
    scope_addresses: Set[T] #Addresses belonging to the scope
    method_stack_len: int # The length of the method stack
    name:str
    id:str # A unique id

class TreeBuilder:
    
    def __init__(self, trace_files: List[pathlib.Path], seeds: List[pathlib.Path], program_path: str) -> None:
        
        #Read trace files
        self.traces: List[List[Dict]] = []
        for f_name in trace_files:
            with open(f_name, "r")as f:
                self.traces.append(json.load(f))
                
        #Read seeds
        self.seeds = seeds
        self.seed_contents: List[bytes] = []
        for f_name in seeds:
            with open(f_name, "rb")as f:
                self.seed_contents.append(f.read())

        
        # Derive cfg and function dicts from traces
        self.cfg, self.function_entries, self.function_scopes = build_control_flow_graphs_from_traces(self.traces)

        logging.info(f"Functions: {' '.join(self.function_entries.values())}")
        logging.info(f"Using original Mimid algo: {ORIGINAL_MIMID}")
        # Find loops in all functions
        self.loop_scopes: Dict[T, List[Set[T]]] = {}
        for entry_addr, fname in self.function_entries.items():
            try:
                self.loop_scopes.update(all_natural_loops(self.cfg, entry_addr))
            except nx.NetworkXError as e:
                logging.warning(f"Error with function {fname} and entrypoint {entry_addr}")
                raise e


        self.pseudo_method_names: Dict[str, str] = {}
        
        self.tree_list: List[Dict] = []
        
        #Translate all traces into the Mimid tree list
        for trace , seed_content, seed_file in zip(self.traces, self.seed_contents, self.seeds):
            self.add_trace_to_tree_list(trace, seed_content, seed_file, program_path)
    
    
    def add_to_scope_stack(self, scope_stack: List[PseudoMethodScope], method_map: Dict[str, Tuple[int, str, List[int]]], addr: T, scope_addresses: Set[T], method_stack_len: int, name: str):
        
        # Assert not empty 
        assert scope_stack
        
        stack_entry = PseudoMethodScope(addr, scope_addresses, method_stack_len, name, self.scope_count)
        method_map[str(stack_entry.id)] = (stack_entry.id, name, [])
        method_map[str(scope_stack[-1].id)][2].append(stack_entry.id)

        scope_stack.append(stack_entry)
        self.scope_count += 1
        
    def is_conditional_scope(scope_name:str) -> bool :
        return ':if_' in scope_name or \
            ':while_' in scope_name

        
    def encode_current_scope_conditions(self, scope_stack: List[PseudoMethodScope]) -> List[str]:
        
        assert scope_stack
        scope = scope_stack[-1]
        
        scope_name = scope.name
        
        if TreeBuilder.is_conditional_scope(scope_name):
            method, ctrl, cid, altid, can_empty, conditional_stack = cmimid.util.decode_name(scope_name)
            return conditional_stack
        else:
            return []
                
    def get_curent_function_scope(self, scope_stack: List[PseudoMethodScope]) -> PseudoMethodScope:
        
        for scope in reversed(scope_stack):
            if not TreeBuilder.is_conditional_scope(scope.name):
                return scope
    def get_curent_function_name(self, scope_stack: List[PseudoMethodScope]) -> str:
        

        return self.get_curent_function_scope(scope_stack).name

    
    def function_args_lookahead(self, trace: List[str], current_trace_index: int, current_method_scope: List[T]) -> str:
        
        # Function arguments can not be retrieved on the entry of a function,
        # but only after the preamble (stack setup, register saving) is finished.
        # Therefore we lookahead for some instructions.
        # TODO maybe limit to 10 instructions, or so? 
        args = trace[current_trace_index]["function_args"]
        for elem in trace[current_trace_index + 1:]:
            if elem["address"] not in current_method_scope:
                break
            
            args = elem["function_args"]
            
        #TODO make more generic 
        return urllib.parse.quote('_'.join([str(i).encode('unicode_escape').decode('utf-8') for i in args]))


    # Check in which loop we are by looking 
    def loop_lookahead(self, trace: List[str], current_trace_index: int, loop_scopes: List[List[T]]) -> int:
        
        # Add all loops as candidates
        loop_candidates: Set[int] = set(range(len(loop_scopes)))
        
        all_nodes = set()
        for loop in loop_scopes:
            all_nodes.update(loop)
        
        for elem in trace[current_trace_index:]:
            
            addr = elem["address"]
            
            if addr not in all_nodes: #Skip traces outside of the method scope
                continue
            for candidate_index in loop_candidates.copy():
                if addr not in loop_scopes[candidate_index]:
                    loop_candidates.remove(candidate_index)
                    
            # We found our candidate :=)
            if len(loop_candidates) == 1:
                return next(iter(loop_candidates))
            #elif len(loop_candidates) == 0: 
            
        return None # Could happen
        

        
    def add_trace_to_tree_list(self, trace: List[dict], input:bytes, input_file_name: str, program_file_name: str ) :
        
        assert len(trace) > 0
        
        #Map with  m_id, m_name, m_children 
        method_map: Dict[str, Tuple[int, str, List[int]]] = {"0": (0, None, [])}
        
        #List with idx, char, mid 
        comparisons: List[Tuple[int, str, int]] = []

        # Add root node with all addresses of the parsing methods as scope #set().union(*self.function_scopes.values())
        scope_stack: List[PseudoMethodScope] = [PseudoMethodScope( "0",  set([]), 0, "0", 0)]
        
        self.scope_count = 1
        
        pending_watchpoint = -1
        
        #Get Stack len of first trace element
        initial_stack_len = len(trace[0]["stack"])
        

        # Iterate through the trace
        for idx, elem in enumerate(trace):
            
            addr = elem["address"]
            method_stack_len = len(elem["stack"])
            
            # Step within scope of entry function
            if method_stack_len < initial_stack_len:
                break
            

            # First we check if the node opens a new 'method' scope.
            if addr in self.function_scopes.keys() and \
                method_stack_len > scope_stack[-1].method_stack_len:
                func_args = self.function_args_lookahead(trace, idx, self.function_scopes[addr])
                function_name = f'{elem["function_name"]}' #({func_args})'
                # Add the node to the scope_stack #TODO add function args
                self.add_to_scope_stack(scope_stack, method_map, addr, self.function_scopes[addr], method_stack_len, function_name )
                
                
            # Next we check if the current element ends the current scope
            while addr not in scope_stack[-1].scope_addresses \
                or method_stack_len < scope_stack[-1].method_stack_len:
                
                logging.debug(f"Leave scope: {scope_stack[-1].name}")
                scope_stack.pop()


            # Check if node opens a new 'loop' scope
            # That is the case, if we are at the beginning of a 'natural loop',
            # and the loop is not already the current scope
            if addr in self.loop_scopes.keys():
                loop_index = self.loop_lookahead(trace, idx, self.loop_scopes[addr])
                # Add the node to the scope_stack
                if loop_index is not None:
                    conditional_stack = self.encode_current_scope_conditions(scope_stack)
                    loop_id = f'{addr}_{loop_index}'
                    if loop_id not in self.pseudo_method_names:
                        self.pseudo_method_names[loop_id] = len(self.pseudo_method_names)
 
                    if ORIGINAL_MIMID:
                        if scope_stack[-1].scope_addresses == self.loop_scopes[addr][loop_index]:
                            #We are in another loop iteration
                            conditional_stack[-1] = str(int(conditional_stack[-1])+1)
                            scope_stack.pop()
                        else:          
                           conditional_stack.append("1")
                        can_empty = '?'
                    else:
                        #Alternatively append the loop under previous loop iteration
                        can_empty = '?'
                        #conditional_stack = []
                    
                        
                    scope_name = cmimid.util.encode_name(self.get_curent_function_name(scope_stack), "while", self.pseudo_method_names[loop_id], 0, can_empty, conditional_stack)
                    self.add_to_scope_stack(scope_stack, method_map, addr, self.loop_scopes[addr][loop_index], method_stack_len, scope_name)
                else:
                    logging.warn(f"No suitable loop for addr {addr}")
                    
            
            # Check if node opens a new 'if' scope
            # Thats the case, when node has multiple successors,
            # and all successors stay within the current scope.
            node_successors = set(self.cfg.successors(addr)) if addr in self.cfg  else []
            if len(node_successors) > 1 :
                if node_successors.issubset(scope_stack[-1].scope_addresses): # Probably an if else construct
                    # We sort the list of successors for identifying 'if' and 'else' branches
                    sorted_successors = sorted(node_successors)
                    next_addr = trace[idx + 1]["address"]
                    
                    if next_addr in sorted_successors: # Seen that in conditional returns or maybe exception handling?
                        entry = self.get_curent_function_scope(scope_stack).addr
                        #self.function_entries[self.get_curent_function_name(scope_stack)]
                        nodes_in_scope = if_else_scope(self.cfg, entry, addr)
                        
                        # Add the node to the scope_stack
                        conditional_stack = self.encode_current_scope_conditions(scope_stack)
                        conditional_stack.append("-1")
                        if addr not in self.pseudo_method_names:
                            self.pseudo_method_names[addr] = len(self.pseudo_method_names)
                            
                        scope_name = cmimid.util.encode_name(self.get_curent_function_name(scope_stack), "if", self.pseudo_method_names[addr], f'{sorted_successors.index(next_addr)}', '?', conditional_stack)
                        self.add_to_scope_stack(scope_stack, method_map, addr,  nodes_in_scope, method_stack_len, scope_name)

                else: # Probably an exit of a loop
                    pass

            for offset in elem["watchpoint_hits"]:
                if DELAY_WP:
                    if pending_watchpoint >= 0:
                        char = chr(input[pending_watchpoint]).encode('unicode_escape').decode('utf-8')
                        comparisons.append((pending_watchpoint, char, scope_stack[-1].id))
                    
                    pending_watchpoint = offset
                else:
                    char = chr(input[offset]).encode('unicode_escape').decode('utf-8')
                    comparisons.append((offset, char, scope_stack[-1].id))
                
        if DELAY_WP and pending_watchpoint >= 0:
            char = chr(input[pending_watchpoint]).encode('unicode_escape').decode('utf-8')
            comparisons.append((pending_watchpoint, char, scope_stack[-1].id))
                    
                
        # Put everything into Mimid format
        self.tree_list.append({"comparisons_fmt": "idx, char, method_call_id", 
                               "comparisons": comparisons,
                               "method_map_fmt": "method_call_id, method_name, children", 
                               "method_map": method_map,
                               "inputstr": input.decode("utf-8"), 
                               #TODO
                               "original": str(program_file_name),
                               "arg": str(input_file_name),
                               })
   
        
    def get_tree_list(self) -> List[Dict]:
        return self.tree_list
    def dump_to_file(self, filename: pathlib.Path):
    
        with open(filename, 'w') as f: 
            json.dump(self.tree_list, f)
            