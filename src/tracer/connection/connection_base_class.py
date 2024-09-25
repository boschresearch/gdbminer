# This code is an abstract class for modeling connections
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import logging as log
from abc import abstractmethod
from configparser import ConfigParser
import multiprocessing as mp

class ConnectionBaseClass(mp.Process):
        def __init__(self, config: ConfigParser, inputs: mp.Queue, response: mp.Queue, sut_reset_method):
            super().__init__()
            self.inputs = inputs
            self.response = response
            self.sut_reset_method = sut_reset_method
            self.config = config
            self.running = True

        def start(self):
            try:
                self.connect(self.config)
            except Exception as e:
                log.warning(e)

            super().start()


        def connect(self, config: ConfigParser):
            ...

        def run(self):
            while self.running:
                self.wait_for_input_request()
                fuzz_input = self.inputs.get(block=True)
                self.response.put(self.send_input(fuzz_input))

        def reset_sut(self):
            self.sut_reset_method()

        def connect_async(self):
            ...

        @abstractmethod
        def send_input(self, input: bytes) -> bool:
            """Sends 'input' to SUT
            
                Returns True if input was accepted
            """
            ...

        @abstractmethod
        def wait_for_input_request(self):
            """Blocks until SUT can receive input"""
            ...

        def disconnect(self):
            """[Optional], free connection resources
            Example: Close TCP socket.
            """
            ...
            
        def terminate(self):
            self.running = False
            self.disconnect()
            super().terminate()

