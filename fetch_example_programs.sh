#! /bin/bash

# This script fetches example programs that cannot be distributed because of license conflicts.
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0


git clone --depth=1 https://github.com/vrthra/mimid.git mimid_repo

cp ./mimid_repo/Cmimid/examples/mjs.h ./mimid_repo/Cmimid/examples/mjs.c ./mimid_repo/Cmimid/examples/mjs_extra.h ./example_programs/mjs/
cd ./example_programs/mjs/ && clang -g -O0 -o  mjs mjs.c && cd ../../

cp ./mimid_repo/Cmimid/examples/tiny.c ./example_programs/tinyc/
cd ./example_programs/tinyc/ && clang -g -O0 -o  tinyc tiny.c && cd ../../

cd ./example_programs/calc && wget https://raw.githubusercontent.com/fbuihuu/parser/master/rdp.c && patch rdp.c < ./calc.diff && mv rdp.c calc.c && clang -g -O0 -o calc calc.c && cd ../../