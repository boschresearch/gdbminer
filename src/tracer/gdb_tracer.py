# This code contains the main logic for controlling GDB
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from typing import List, Dict, Set
import logging
import re
import os
from dataclasses import dataclass
from configparser import ConfigParser
from tracer.instance.sut_instance import SUTInstance
from tracer.instance.valgrind_instance import ValgrindInstance
from tracer.instance.stm32_instance import STM32Instance
from tracer.instance.msp430_instance import MSP430Instance
import time
class GDBTracer:
    
    @dataclass
    class TraceEntry:
        address: str
        function_name: str
        function_args: List[str]
        stack: List[str]
        watchpoint_hits: List[int] 
    
    
    def __init__(self, config: ConfigParser):
        
        self.entrypoint = config['GDB']['entrypoint']
        self.exitpoint = config['GDB']['exitpoint']
        self.watchpoint_type = config['GDB']['watchpoint_type']
        self.input_buffer = config['GDB']['input_buffer']
        self.ignore_functions_regex = config.get('GDB','ignore_functions_regex', fallback="")
        self.watchpoint_count = config.getint('GDB','watchpoint_count')
        self.config = config
    

    def trace_instruction(self, response: Dict, instance: SUTInstance, execution_trace: List[TraceEntry]):
        
        address = response['payload']['frame']['addr']
        func_name = response['payload']['frame']['func']
        func_args = response['payload']['frame']['args']
        
        args = []
        for arg in func_args:
            if 'name' in arg and 'value' in arg:
                arg_name = arg['name']
                arg_val = arg['value']
                if arg_name and arg_val and '0x' not in arg_val\
                    and arg_name != 'argc' and arg_name != 'argv':
                        args.append(arg_val)
                    
        # Cut args that are sometimes contained in the function name
        #if func_name and "(" in func_name:
        #    func_name = func_name.split("(")[0]
            
        # Make the function name safe for mimid
        func_name = func_name.replace('<',"_")\
            .replace('>',"_")\
            .replace(':',"_")\
            .replace(' ',"_")\
            .replace(',',"_")\
            .replace('#',"_")\
            .replace('.',"_")
                    
        # Request a stack trace from target
        # Will be added on arrival
        instance.request_stacktrace()
        entry = GDBTracer.TraceEntry(address, func_name, args, [], [])
        execution_trace.append(entry)

    
    def open_sut_instance(config: ConfigParser, input_file: str = "") -> SUTInstance:
        instance = config['GDB']['instance']
        if instance == "valgrind":
            return ValgrindInstance(config, input_file)
        elif instance == "stm32":
            return STM32Instance(config, input_file)
        elif instance == "msp430":
            return MSP430Instance(config, input_file)
        
    def merge_traces(list1 : List[TraceEntry], list2 : List[TraceEntry]) -> List[TraceEntry]:
        if len(list1) == 0:
            return list2
        elif len(list2) == 0:
            return list1
        
        result: List[GDBTracer.TraceEntry] = []
        for elem1, elem2 in zip(list1, list2):
            assert elem1.address == elem2.address
            new_entry =  GDBTracer.TraceEntry(elem1.address, elem1.function_name, elem1.function_args, elem1.stack, elem1.watchpoint_hits)
            new_entry.watchpoint_hits.extend(elem2.watchpoint_hits)
            result.append(new_entry)
        return result
    
    def trace_input(self, filename) -> List[TraceEntry]:
        

        input_len = os.path.getsize(filename)
        
        logging.info(f"Seed length: {input_len}")

        watchpoint_window_offset = 0
        
        merged_trace : List[GDBTracer.TraceEntry] = []
        
        # Sliding window according to watchpoint count
        while watchpoint_window_offset < input_len:
            
            with GDBTracer.open_sut_instance(self.config, filename) as instance:

                trace = self.trace_input_slice(instance, input_len, watchpoint_window_offset)
            
            merged_trace = GDBTracer.merge_traces(merged_trace, trace)
            watchpoint_window_offset += self.watchpoint_count
        
        return merged_trace

    def trace_input_slice(self, instance: SUTInstance, input_len: int, watchpoint_window_offset: int = 0) -> List[TraceEntry]:

        instruction_trace_list: List[GDBTracer.TraceEntry] = []
        watchpoint_offset = {}

        
        # Set the first breakpoint at entrypoint address
        instance.set_temporary_breakpoint(self.entrypoint)
        instance.wait_for_any_gdb_response()
        instance.continue_execution()
        time.sleep(1) # Give GDB some time to continue the execution
        instance.send_input()

        response = instance.wait_for_any_stop_message()

        self.trace_instruction(response, instance, instruction_trace_list)


        string_range = range(input_len)
        watchpoint_range = range(self.watchpoint_count)
        # Set watchpoints
        for i, _ in zip(string_range[watchpoint_window_offset:], watchpoint_range):
            if self.input_buffer.startswith('0x'):
                watchpoint_address = hex(int(self.input_buffer, 16) + i)
            else:
                watchpoint_address = "&" + self.input_buffer + f"[{i}]"
            # Set watchpoint
            watchpoint_id = instance.set_watchpoint_and_get_id(watchpoint_address, self.watchpoint_type)
            watchpoint_offset[watchpoint_id] = i
            

        # Set breakpoint to exit address
        # TODO make this dependent on initial stack 
        if self.exitpoint:
            instance.set_temporary_breakpoint(self.exitpoint)

        # Request stacktrace for first trace entry
        instance.request_stacktrace()
        
        # Do one step
        instance.step_instruction()

        # To keep track of ignored functions and subroutines
        ignore_till_stack_len = -1
        
        #To remember at which stack level we start tracing
        
        entry_stack_len = -1
        
        run = True
        while run:
            responses = instance.get_gdb_responses()
            while responses:
                response = responses.pop(0)
                
                if instance.is_stack_message(response):
                    # Stacktrace incoming
                    logging.debug(f"Stacktrace {response['payload']}")
                    
                    stacktrace = self.parse_stacktrace(response)
                    
                    if entry_stack_len == -1: #Init entry stack len
                        entry_stack_len = len(stacktrace)
                    elif not self.exitpoint and entry_stack_len > len(stacktrace):
                        # We ran beyond the entry function
                        
                        # Remove last trace element
                        instruction_trace_list.pop()
                        
                        # Delete watchpoints and stop tracing
                        run = False
                        for wp_id in watchpoint_offset.keys():
                            instance.delete_breakpoint(wp_id)
                        instance.continue_execution()
                        
                        # Skip rest of loop
                        break

                        
                    if ignore_till_stack_len < 0:
                        # Just add stacktrace to latest trace entry
                        assert not instruction_trace_list[-1].stack
                        #    logging.warning(f"Overwrite stacktrace for instruction {instruction_trace_list[-1]} with {stacktrace}")
                        instruction_trace_list[-1].stack = stacktrace
                        
                    elif len(stacktrace) > ignore_till_stack_len:
                        # We currently ignore messages
                        # Best we can do is to step out of func and check again
                        instance.step_out_of_function()
                    else:
                        # We reached the desired stack len,
                        # so go back to track every instruction
                        ignore_till_stack_len = -1
                        #instruction_trace_list[-1].stack = stacktrace
                        instance.step_instruction()
                            
                # Check if execution is interrupted
                elif instance.is_stop_message(response):
                        
                    logging.debug(f"Execution stopped {response['payload']}")
                    
                    # Here we hit a breakpoint, which should only be on the exit point
                    if 'reason' in response['payload'] and \
                        response['payload']['reason'] == 'breakpoint-hit':

                        # Delete watchpoints and stop tracing
                        run = False
                        for wp_id in watchpoint_offset.keys():
                            instance.delete_breakpoint(wp_id)
                        instance.continue_execution()


                    # In this case we got a memory response and need to evaluate it
                    elif 'reason' in response['payload'] and \
                        'read-watchpoint-trigger' in response['payload']['reason']:
                        if 'hw-rwpt' in response['payload']:
                            # Sometimes 'hw-rwpt' comes as list and sometimes as single object. We take the first one, as they seems to be duplicates mostly
                            wp = response['payload']['hw-rwpt'][0] if isinstance(response['payload']['hw-rwpt'], list) and len(response['payload']['hw-rwpt']) > 0 else response['payload']['hw-rwpt']
                            watchpoint_id = wp['number']
                            logging.info(f'Watchpoint triggered: {watchpoint_id}')
                            instruction_trace_list[-1].watchpoint_hits.append(watchpoint_offset[watchpoint_id])
                            instance.step_instruction()
                            
                        elif 'offset' in response['payload']:
                            offset = watchpoint_window_offset + response['payload']['offset'] 
                            logging.info(f'Watchpoint triggered: {offset} ')
                            instruction_trace_list[-1].watchpoint_hits.append(offset)
                            
                        
                    # This case will be executed after a step instruction.
                    # We need to check, if we need to do again a step instruction
                    # or a simple continue
                    # 'reason' in response['payload'] and \
                    #     (response['payload']['reason'] == 'end-stepping-range' or \
                    #     response['payload']['reason'] == 'function-finished'):
                    else:
                        
                        func_name = response['payload']['frame']['func']
                        
                        #Check if we currently ignore interruptions
                        if  ignore_till_stack_len > 0:
                        
                            #Request stack trace to check if we reached our desired stack len
                            instance.request_stacktrace()

                        elif self.ignore_functions_regex and re.search(self.ignore_functions_regex, func_name):
          
                            #Ignore all interruption until stack is back to previous function
                            ignore_till_stack_len = len(instruction_trace_list[-1].stack)
                            instance.step_out_of_function()
                        else:                        
                            assert instruction_trace_list[-1].stack
                            #    logging.warning(f"No stack trace for instruction {instruction_trace_list[-1]} received")
                            self.trace_instruction( response, instance, instruction_trace_list)
                            instance.step_instruction()
                else:
                    logging.debug(f"Unprocessed GDB message {response}")


        return instruction_trace_list

    def parse_stacktrace(self, response) -> List[str]:
        stacktrace = [] 
        # Skip first address on stack trace, because it can be unreliable
        if len(response['payload']['stack']) > 0:
            for frame in response['payload']['stack'][1:]:
                stacktrace.append(frame['addr'])
        stacktrace.append("0x0") #Put a dummy element on stack
        return stacktrace

