# This is an abstract class enabling different debug targets
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from configparser import ConfigParser
import logging
from typing import List, Dict
from pygdbmi import gdbcontroller

class SUTInstance:
    def __init__(self, config: ConfigParser) -> None:
        self.timeout = config['GDB'].getint('timeout')
        self.elf_file = config['BASIC']['binary_file']
        self.gdb_with_args = config['GDB']['gdb_path'].split(' ')
        self.config = config
        self.number_of_tested_inputs: int = 0


    def init_gdb_controller(self):
        
        self.gdb_controller = gdbcontroller.GdbController([*self.gdb_with_args, "--nx", "--quiet", "--interpreter=mi3"])
        logging.info(f'GDB started')

        self.send_gdb_command(f'-file-exec-and-symbols {self.elf_file}')
        logging.info(f'GDB loaded symbols from {self.elf_file=} successfully')
        

    def set_temporary_breakpoint(self, breakpoint_address):
        # -t for a temporary breakpoint.
        # -h for a hardware breakpoint
        if breakpoint_address.startswith('0x'):
            logging.info(f'Set breakpoint at address {breakpoint_address}')
            self.send_gdb_command(f"-break-insert -t *{breakpoint_address}")
        else:
            logging.info(f'Set breakpoint at symbol {breakpoint_address}')
            self.send_gdb_command(f"-break-insert -t {breakpoint_address}")


    def enable_breakpoints(self, breakpoint_ids):
        ids = " ".join(breakpoint_ids)
        logging.info(f'Enable breakpoints {ids=}')
        self.send_gdb_command(f'-break-enable {ids}')
        
    def disable_breakpoints(self, breakpoint_ids):
        ids = " ".join(breakpoint_ids)
        logging.info(f'Disable breakpoints {ids=}')
        self.send_gdb_command(f'-break-disable {ids}')
        
    def continue_execution(self):
        logging.info(f'Continue program execution')
        self.send_gdb_command('-exec-continue')


    def step_instruction(self):
        logging.debug(f'Step instruction')
        self.send_gdb_command('-exec-step-instruction')

    def step_out_of_function(self):
        logging.debug(f'Finish function instruction')
        self.send_gdb_command('-exec-finish')


    def delete_breakpoint(self, breakpoint_id):
        logging.info(f'Remove Breakpoint #{breakpoint_id}')
        self.send_gdb_command(f'-break-delete {breakpoint_id}')
        

    def execute_find(self, ram_begin_address, ram_end_address, find_string):
        self.send_gdb_command(f'find {ram_begin_address}, {ram_end_address}, "{find_string}"')


    def read_memory_bytes(self, address, size):
        self.send_gdb_command(f'-data-read-memory-bytes {address} {size}')
        
    def request_stacktrace(self):
        self.send_gdb_command('-stack-list-frames')

    
    def interrupt(self):
        self.send_gdb_command("-exec-interrupt")
    
    def send_gdb_command(self, command: str) :
        self.gdb_controller.write(command, read_response=False, timeout_sec=0,
                            raise_error_on_timeout=False)

    def set_watchpoint_and_get_id(self, address, watchpoint_type) -> str:
        """
        Set a watchpoint on the given address and fetch the assigned id.

        Args:
            address : The address to set set the watchpoint on
            watchpoint_type : The type of the watchpoint, e.g. (char*)

        Returns:
            id: The watchpoint id assigned by GDB
        """
        # -r for a read watchpoint
        logging.info(f'Set {address=}')
        self.send_gdb_command(f'rwatch *{watchpoint_type}{address}')

        while True:
            responses = self.gdb_controller.get_gdb_response(self.timeout)
            for response in responses:
                if response['message'] == 'breakpoint-created':
                    return response['payload']['bkpt']['number']
                
    def wait_for_any_stop_message(self):

        while True:
            for response in self.wait_for_any_gdb_response():
                if self.is_stop_message(response):
                    return response

    def wait_for_any_gdb_response(self):
        responses = []
        # Do active waiting, as everything else is painfully slow
        while not responses:
            responses = self.get_gdb_responses()
            
        return responses
            
    def get_gdb_responses(self) -> List[Dict]:
        return self.gdb_controller.get_gdb_response(timeout_sec=0, raise_error_on_timeout=False)
    
    def send_input(self):
        pass
        
    def input_accepted(self, input: bytes) -> bool:
        ...
    def __exit__(self, exc_type, exc_val, exc_tb):
                
        self.gdb_controller.exit()


    def is_stop_message(self, response) -> bool:
        return response['type'] == 'notify' and \
                    response['message'] == 'stopped' \
                    and 'payload' in response

    def is_stack_message(self, response) -> bool:
        return 'message' in response and response['message'] == 'done' and \
            'payload' in response and response['payload'] and 'stack' in response['payload']
    