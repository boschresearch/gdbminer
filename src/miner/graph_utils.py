# This code contains helper functions for working with graphs
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0



from typing import Set, Dict, List, Tuple, TypeVar
import networkx as nx


# Generics in Python -> Yeah :)
T = TypeVar("T")

def build_control_flow_graphs_from_traces(traces: List[List[Dict]] ) -> Tuple[nx.DiGraph, Dict[str, str], Dict[str, Set[str]]]:
    """
    Build control flow graphs for each traced function, as well as dictionaries
    for function_names to function entries 
    and function entry points to all instructions of the function

    Returns:
        nx.DiGraph: _description_
    """
    # Create an edge tuple list from trace
    start_node = '0'
    edge_trace : List[Tuple[str]] = []
    function_entries: Dict[str, str] = {} # from entry address to fname
    function_scopes: Dict[str, Set[str]] = {}
    function_stack: List[str] = []
        
    for trace in traces:
        previous_node = start_node
        initial_stack_len = len(trace[0]["stack"])
        prev_stack_len = initial_stack_len - 1

        for trace_entry in trace:
            
            addr = trace_entry["address"]
            fname = trace_entry["function_name"]
            stack_len = len(trace_entry["stack"])
            
            # Stay within entry function
            if stack_len < initial_stack_len:
               break
            
            #Add fallthrough edge
            if stack_len > prev_stack_len:
                edge_trace.append((previous_node, trace_entry["stack"][0]))
                function_stack.append(addr)
                if addr not in function_entries:
                    function_entries[addr] = fname
                    function_scopes[addr] = set()

                
            #Add edge is the stack did not decrease (return instructions)
            elif stack_len == prev_stack_len:
                edge_trace.append((previous_node, addr))
                
            else:
                while stack_len < prev_stack_len:
                    function_stack.pop()
                    prev_stack_len -=1
                
            function_scopes[function_stack[-1]].add(addr)
            
            previous_node = addr
            prev_stack_len = stack_len
            
            
    return nx.DiGraph(edge_trace), function_entries, function_scopes


def pre_dominator_graph(G: nx.DiGraph, entry_point: T) -> nx.DiGraph:
    return  nx.DiGraph(nx.immediate_dominators(G, entry_point).items()).reverse(copy=False)

def post_dominator_graph(G: nx.DiGraph, exit_point):
    return  pre_dominator_graph(G.reverse(), exit_point)

# Def. Back Edge: An edge n → d where d dom n
def all_back_edges(G : nx.DiGraph, start_node: T) -> Set[Tuple[T]] :
    back_edges:  Set[Tuple[T]] = set()
    
    # First get pre dominator tree
    dom_tree = pre_dominator_graph(G, start_node)
    
    for (src, dst) in G.edges():
        if src in dom_tree and dst in dom_tree and\
            nx.has_path(dom_tree, dst, src):
            
            back_edges.add((src, dst))
    return back_edges
        
# The natural loop of a back edge a->b is {b} plus the set of nodes
# that can reach a without going through b.
# Two natural loops are either disjoint, identical, or nested
def natural_loop(G: nx.DiGraph, back_edge: Tuple[T]) -> Set[T]:
    src, dst = back_edge
    nodes_in_loop = set([src, dst])
    
    # Single instruction loop
    if src == dst:
        return nodes_in_loop
    
    H = G.copy()
    H.remove_node(dst) # Remove dst from the graph
    # All nodes that can reach src are in the loop
    nodes_in_loop.update(nx.ancestors(H, src))

    
    return nodes_in_loop
    
# Map from entry of loop to a set of all containing loops    
def all_natural_loops(G: nx.DiGraph, start_node: T) -> Dict[T, List[Set[T]]]:
    
    loops : Dict[T, List[Set[T]]] = {}
    back_edges = all_back_edges(G, start_node)

    for back_edge in back_edges:
        loop = natural_loop(G, back_edge)
        if back_edge[1] in loops:
            loops[back_edge[1]].append(loop)
        else:
            loops[back_edge[1]] = [loop]
    return loops



def if_else_scope(G: nx.DiGraph, entry_point: T, conditional_node: T) -> Set[T]:
    """ Returns a set of all nodes that are within the if/else scope

    Args:
        G : The graph
        node : A node in the graph

    Returns:
        The set of dominated nodes
    """
    
    # First get pre dominator tree
    dom_tree = pre_dominator_graph(G, entry_point)


    nodes = set()
    for desc in G.successors(conditional_node):
        nodes.add(desc)
        if desc in dom_tree:
            nodes.update(nx.descendants(dom_tree, desc))
    return nodes