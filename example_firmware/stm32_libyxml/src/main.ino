// This example program reads data from serial and parses it as xml.
// Copyright (c) 2023 Robert Bosch GmbH
// SPDX-License-Identifier: AGPL-3.0

#include "Arduino.h"

#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif

#define FUZZ_INPUT_SIZE 2048
char buf[FUZZ_INPUT_SIZE];
size_t input_len = 0;
int led_state = 0;


void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.begin(9600); 
}

void serial_read_bytes(uint8_t *buf, size_t length) {
    size_t bytes_read = 0;

    while (bytes_read < length) {
        if (!Serial.available()) continue;
        char byte = Serial.read();
        buf[bytes_read] = byte;
        bytes_read += 1;
    }
}



#include <yxml.h>

uint8_t xmlbuf[4096];

int parser(uint8_t *input, size_t input_size)
{
    yxml_t x;
    int ret_val = 0;
    yxml_init(&x, xmlbuf, 4096);
    for (int i = 0; i < input_size; i++) {
        yxml_ret_t ret = yxml_parse(&x, input[i]);
        if (ret < 0) {
            ret_val = -1;
            break;
        }
    }
    return ret_val;
}

void loop() {
    if (led_state == 0) {
        digitalWrite(LED_BUILTIN, HIGH);
        led_state = 1;
    } else {
        digitalWrite(LED_BUILTIN, LOW);
        led_state = 0;
    }

    // Notify that we request a new input
    Serial.write('A');

    uint32_t response_length = 0;
    serial_read_bytes((uint8_t*)&response_length, 4);

    if (response_length > FUZZ_INPUT_SIZE)
    {
        //Serial.println("ERROR: Received input with length > 1048");
        while(1){ delay(100); }
    }
    //socket_read_bytes(connection_fd, (void *)buf, response_length);
    serial_read_bytes((uint8_t*)buf, (size_t)response_length);
    buf[response_length] = 0; //nullify string
    int ret = parser((uint8_t*) buf, (size_t)response_length);
    // Send result if parsing was successfully or not
    Serial.write(ret);
}



