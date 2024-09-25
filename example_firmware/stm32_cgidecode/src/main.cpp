// This example program reads data from serial and parses it as json.
// Copyright (c) 2022 Robert Bosch GmbH
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// by the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include "Arduino.h"

#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif


#define FUZZ_INPUT_SIZE 2048
char buf[FUZZ_INPUT_SIZE];
size_t input_len = 0;
int led_state = 0;




#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int hex_values[256];

void init_hex_values() {
  for (int i = 0; i < sizeof(hex_values) / sizeof(int); i++) {
    hex_values[i] = -1;
  }
  hex_values['0'] = 0;
  hex_values['1'] = 1;
  hex_values['2'] = 2;
  hex_values['3'] = 3;
  hex_values['4'] = 4;
  hex_values['5'] = 5;
  hex_values['6'] = 6;
  hex_values['7'] = 7;
  hex_values['8'] = 8;
  hex_values['9'] = 9;

  hex_values['a'] = 10;
  hex_values['b'] = 11;
  hex_values['c'] = 12;
  hex_values['d'] = 13;
  hex_values['e'] = 14;
  hex_values['f'] = 15;

  hex_values['A'] = 10;
  hex_values['B'] = 11;
  hex_values['C'] = 12;
  hex_values['D'] = 13;
  hex_values['E'] = 14;
  hex_values['F'] = 15;
}

int cgi_decode(char *s, char *t) {
  while (*s != '\0') {
    if (*s == '+') {
      *t++ = ' ';
    } else if (*s == '%') {
      int digit_high = *++s;
      int digit_low = *++s;
      if (hex_values[digit_high] >= 0 && hex_values[digit_low] >= 0) {
        *t++ = hex_values[digit_high] * 16 + hex_values[digit_low];
      } else {
        return -1;
      }
    } else {
      *t++ = *s;
    }
    s++;
  }
  *t = '\0';
  return 0;
}

void strip_input(char *my_string) {
  int read = strlen(my_string);
  if (my_string[read - 1] == '\n') {
    my_string[read - 1] = '\0';
  }
}

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.begin(9600);
    init_hex_values();
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

// This example program reads data from serial and parses it as cgi encoded string.
// Copyright (c) 2023 Robert Bosch GmbH
// SPDX-License-Identifier: AGPL-3.0

#include <arduino_percent.hpp>

int parser(char *input, size_t input_size) {
  
  char result[FUZZ_INPUT_SIZE];

  //strip_input(input);
  //int ret = cgi_decode(input, result);

  percent::decode(input, result);

  int ret = 0;
  for( int i = 0; result[i] != 0; i++) {
    if (result[i] > 127) {
      ret = -1;
      break;
    }

  }

  return ret;
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
    int ret = parser(buf, (size_t)response_length);

    // Send result if parsing was successfully or not
    Serial.write((char) ret);
}
