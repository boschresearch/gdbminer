
# This code contains the main logic for connecting to a target device
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


from configparser import ConfigParser
import multiprocessing as mp
from tracer.connection.connection_base_class import ConnectionBaseClass
from tracer.connection.serial_connection import SerialConnection
import logging

class SUTConnection:
    """
    Create Process for a Connection component, and this instance forwards
    generated inputs to this Connection component.
    """

    def __init__(self, config: ConfigParser, sut_reset_method):
        self.config = config
        self.sut_reset_method = sut_reset_method
        self.timeout = config.getint("GDB", "timeout")
        self.inputs = mp.Queue()
        self.responses = mp.Queue()
        self.connection = self.init_connection(config, sut_reset_method)
        

    def init_connection(self, config: ConfigParser, sut_reset_method) -> ConnectionBaseClass:
        sut_connection_type = config['Connection']['input_channel']
        if sut_connection_type == 'serial':
            connection =  SerialConnection(config, self.inputs, self.responses, sut_reset_method)
        else:
            # Here we can add other connection types
            pass
    
        connection.daemon = True
        connection.start()
        return connection

    def send_input(self, fuzz_input: bytes):
        self.inputs.put(fuzz_input)
        
    def input_accepted(self, fuzz_input: bytes) -> bool:
        while True:
            self.inputs.put(fuzz_input)
            try:
                return self.responses.get(block=True, timeout=self.timeout)
            except Exception:
                logging.warn(f"Connection timeout!")
                #return False
                self.disconnect()
                self.connection = self.init_connection(self.config, self.sut_reset_method)
        

    def disconnect(self):
        assert self.connection.pid is not None
        self.connection.terminate()
        self.connection.join(timeout=60)
        self.connection.close()
