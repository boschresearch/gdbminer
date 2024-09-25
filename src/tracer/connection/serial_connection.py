# This code enables serial connections to a target
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


import struct
import serial
import logging as log
from tracer.connection.connection_base_class import ConnectionBaseClass
import time

class SerialConnection(ConnectionBaseClass):
    def connect(self, config):
        port = config['Connection']['port']
        baud_rate = config['Connection'].getint('baud_rate')
        self.serial = serial.Serial(port, baud_rate)
        time.sleep(1) # Give a bit time to open connection
        self.serial.reset_input_buffer()
        # Do a reset, so that the SUT requests an input now
        self.reset_sut()
        log.info(f'Established connection with SUT via Serial at port {self.serial.name}')


    def wait_for_input_request(self):
        # SUT sends 'A' whenever it requests and input
        read = ''
        while not read or read[-1] != 65:
            read = self.serial.read(1)
        log.debug(f'READ: {read}')

    def send_input(self, input: bytes) -> bool:
        # First send length
        log.debug(f'Sending input: {input}')
        input_len = struct.pack("I", len(input))
        self.serial.write(input_len)

        # After that input
        self.serial.write(input)

        self.serial.flush()
        
        ret = self.serial.read(1)
        log.debug(f'Received: {ret}')
        if ret[0] == 0:
            return True
        elif ret[0] == 0xFF:
            return False
        else:
            log.error(f"Unexpected return value {ret[0]}")
            return True #Let's consider it accepted

    def disconnect(self):
        self.serial.close()
