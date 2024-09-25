# This code contains code to connect to MSP430 controllers
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


from configparser import ConfigParser
import logging
import time
import subprocess
from typing import List, Dict
from tracer.connection.sut_connection import SUTConnection
from tracer.instance.sut_instance import SUTInstance

class MSP430Instance(SUTInstance):
    
    def __init__(self, config: ConfigParser, input_file: str) -> None:
        super().__init__(config)
        
        self.gdb_server_path_with_args = config['GDB']['gdb_server_path'].split(' ')
        self.gdb_server_address = config['GDB']['gdb_server_address']
        self.watchpoint_count = config.getint('GDB', 'watchpoint_count')
        self.input_file = input_file


    def __enter__(self):
        
        # Start gdb server in subprocess
        self.gdb_server = subprocess.Popen(self.gdb_server_path_with_args)

        time.sleep(3)
        logging.info('GDB Server started')
        
        # init gdb controller
        self.init_gdb_controller()
        
        
        # Connect to GDB Server
        logging.info(f'Trying to connect to GDB Server at {self.gdb_server_address}')
        self.gdb_controller.write(f'-target-select extended-remote {self.gdb_server_address}', read_response=False, timeout_sec=0,
                            raise_error_on_timeout=False)
        logging.info(f'Connected to GDB Server at {self.gdb_server_address}')
        
        self.wait_for_any_stop_message()

        self.connection = self.init_sut_connection()

        return self
    
    # Subclasses may override init_SUT_connection
    def init_sut_connection(self):
        return SUTConnection(self.config, self.reset)
        

                
    def reset(self):
        # Reset target
        self.interrupt()
        self.wait_for_any_gdb_response()
        self.send_gdb_command('monitor reset halt')
        self.wait_for_any_gdb_response()
        self.send_gdb_command('flushregs')

        #wait till something happened
        self.wait_for_any_gdb_response()
        
    def send_input(self):
        with open(self.input_file, 'rb') as f:
            input = f.read()
        self.connection.send_input(input)
        
    def input_accepted(self, input: bytes) -> bool:
        self.number_of_tested_inputs += 1
        accepted = self.connection.input_accepted(input)
        logging.debug(f"Test {input} : {accepted=}")
        return accepted
        
    def __exit__(self, exc_type, exc_val, exc_tb):
                
        self.connection.disconnect()
        
        super().__exit__(exc_tb, exc_val, exc_tb)
        
        # Need a short time to wait between GDB and GDB Server shutdown, else we get errors like the following:
        # [!] send_recv send request failed: LIBUSB_ERROR_BUSY
        # [!] send_recv STLINK_DEBUG_RUNCORE
        # [!] send_recv send request failed: LIBUSB_ERROR_BUSY
        # [!] send_recv STLINK_JTAG_WRITEDEBUG_32BIT
        
        time.sleep(1)
        # Exit gdb server
        self.gdb_server.terminate()
        try:
            self.gdb_server.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.gdb_server.kill()
            self.gdb_server.communicate()
        logging.info('GDB Server terminated')