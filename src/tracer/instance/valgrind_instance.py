# This code contains code to connect to a valgrind instance
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

from configparser import ConfigParser
import logging
from os import path
import time
import subprocess
import tempfile
from tracer.instance.sut_instance import SUTInstance

class ValgrindInstance(SUTInstance):
    
    def __init__(self, config: ConfigParser, input_file: str) -> None:
        super().__init__(config)
        
        self.valgrind_commands = "valgrind --vgdb=yes --vgdb-stop-at=startup --undef-value-errors=no --leak-check=no ".split()
        self.valgrind_commands.append(self.elf_file)
        
        #TODO offer different connections
        self.valgrind_commands.append( input_file)
        
        logging.info(self.valgrind_commands)


    def __enter__(self):
        
        # Start valgrind in subprocess
        self.valgrind_process = subprocess.Popen(self.valgrind_commands)

        time.sleep(1)
        logging.info('GDB Server started')
        
        # init gdb controller
        self.init_gdb_controller()
        
        self.send_gdb_command(f'set disable-randomization on')
        self.send_gdb_command(f'set breakpoint pending on')

        gdb_server_address = f'| vgdb --pid={self.valgrind_process.pid}'
        # Connect to GDB Server
        logging.info(f'Trying to connect to GDB Server at {gdb_server_address}')
        self.send_gdb_command(f'-target-select extended-remote {gdb_server_address}')
        
        self.wait_for_any_stop_message()


        logging.info(f'Connected to GDB Server at {gdb_server_address}')
        
        return self
    
    def input_accepted(self, input: bytes) -> bool:
        
        self.number_of_tested_inputs += 1
        # We do not need to fire a valgrind session for checking
        # the returncode. Just execute the binary directly
        with tempfile.NamedTemporaryFile(mode="wb") as f:
            f.write(input)
            f.flush()
            #f.close()
            binary = self.config['BASIC']['binary_file']
            timeout = self.config['GDB'].getfloat('timeout')
            
            try:
                subprocess.check_call([binary, f.name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
                accepted = True
            except subprocess.CalledProcessError as e:
                accepted = False
            except subprocess.TimeoutExpired as e:
                logging.warn(f"Timeout for input <{input}> ")
                accepted = True #Debatable, whether that is accepted or rejected
            logging.debug(f"Test {input} : {accepted=}")
        return accepted
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        
        super().__exit__(exc_tb, exc_val, exc_tb)
        # Exit gdb server
        self.valgrind_process.terminate()
        try:
            self.valgrind_process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.valgrind_process.kill()
            self.valgrind_process.communicate()
        logging.info('GDB Server terminated')